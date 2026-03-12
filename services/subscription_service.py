"""구독 서비스: 블록체인 모니터링 + 결제 매칭 + 혜택 체크."""

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import config
from database import subscription_queries as sq

logger = logging.getLogger(__name__)

# ERC-20 Transfer(address,address,uint256) event topic
_TRANSFER_TOPIC = None  # lazy init

_w3 = None  # AsyncWeb3 singleton


_BASE_RPC_FALLBACKS = [
    "https://base.llamarpc.com",
    "https://base-mainnet.public.blastapi.io",
    "https://1rpc.io/base",
    "https://mainnet.base.org",
]


async def _get_web3():
    """AsyncWeb3 싱글턴 (RPC fallback 지원)."""
    global _w3
    if _w3 is not None:
        # 기존 연결 확인
        try:
            await _w3.eth.block_number
            return _w3
        except Exception:
            logger.warning("Web3 connection lost, reconnecting...")
            _w3 = None

    # 설정된 RPC + fallback 목록
    rpc_list = [config.BASE_RPC_URL] + [
        url for url in _BASE_RPC_FALLBACKS if url != config.BASE_RPC_URL
    ]

    try:
        from web3 import AsyncWeb3
        from web3.providers import AsyncHTTPProvider
    except ImportError:
        logger.error("web3 패키지 미설치! pip install web3")
        return None

    for url in rpc_list:
        try:
            w3 = AsyncWeb3(AsyncHTTPProvider(url))
            await w3.eth.block_number  # 연결 테스트
            _w3 = w3
            logger.info(f"Web3 connected to {url}")
            return _w3
        except Exception as e:
            logger.warning(f"Web3 RPC failed: {url} ({e})")
            continue

    logger.error("All RPC endpoints failed!")
    return None


def _get_transfer_topic() -> str:
    """Transfer event signature hash (lazy)."""
    global _TRANSFER_TOPIC
    if _TRANSFER_TOPIC is None:
        from web3 import Web3
        _TRANSFER_TOPIC = "0x" + Web3.keccak(text="Transfer(address,address,uint256)").hex()
    return _TRANSFER_TOPIC


def _token_name(contract_addr: str) -> str | None:
    """컨트랙트 주소 → 토큰명."""
    addr = contract_addr.lower()
    if addr == config.USDC_CONTRACT.lower():
        return "USDC"
    if addr == config.USDT_CONTRACT.lower():
        return "USDT"
    return None


# ─── 금액 계산 ────────────────────────────────────

async def generate_unique_amount(tier: str, token: str) -> tuple[int, float]:
    """티어 정가 + jitter로 유저별 고유 금액 생성.

    동시 결제 시에도 금액으로 유저를 구별할 수 있도록
    $0.01~$0.49 범위의 센트를 추가. 기존 pending과 겹치지 않도록 재시도.

    Returns:
        (amount_raw, amount_usd): raw = 6 decimals int, usd = float
    """
    tier_cfg = config.SUBSCRIPTION_TIERS.get(tier)
    if not tier_cfg:
        raise ValueError(f"Unknown tier: {tier}")

    base_usd = tier_cfg["price_usd"]
    base_raw = int(base_usd * 1_000_000)

    # 기존 pending 금액 수집 (겹침 방지)
    from database import subscription_queries as sq
    pending = await sq.get_all_pending_by_token(token)
    used_amounts = {p["amount_raw"] for p in pending}

    # jitter: $0.01 ~ $0.49 (1센트 단위, 49가지)
    for _ in range(50):
        jitter_cents = random.randint(1, 49)
        amount_raw = base_raw + jitter_cents * 10_000  # 1 cent = 10,000 raw (6 decimals)
        if amount_raw not in used_amounts:
            amount_usd = amount_raw / 1_000_000
            return amount_raw, amount_usd

    # fallback: jitter 없이 정가
    return base_raw, base_usd


# ─── 결제 요청 생성 ───────────────────────────────

async def create_payment_request(user_id: int, tier: str, token: str) -> dict:
    """결제 대기 생성. 반환: {payment_id, amount_usd, amount_raw, token, wallet, expires_at}."""
    # 기존 pending 취소
    existing = await sq.get_user_pending(user_id)
    if existing:
        await sq.cancel_payment(existing["id"], user_id)

    amount_raw, amount_usd = await generate_unique_amount(tier, token)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=config.PAYMENT_WINDOW)

    payment_id = await sq.create_pending_payment(
        user_id, tier, amount_raw, amount_usd, token, expires_at,
    )

    return {
        "payment_id": payment_id,
        "amount_usd": amount_usd,
        "amount_raw": amount_raw,
        "token": token,
        "wallet": config.SUBSCRIPTION_WALLET,
        "expires_at": expires_at,
        "tier": tier,
    }


# ─── 블록체인 모니터 ─────────────────────────────

async def poll_chain_transfers(bot) -> None:
    """Base 체인에서 USDC/USDT Transfer 이벤트 폴링."""
    if not config.SUBSCRIPTION_WALLET:
        return

    w3 = await _get_web3()
    if not w3:
        return

    try:
        current_block = await w3.eth.block_number
    except Exception as e:
        logger.error(f"Chain poll: block_number failed: {e}")
        return

    last_block = await sq.get_last_processed_block()
    if last_block is None:
        last_block = current_block - 50  # 첫 실행: 50블록 뒤부터

    if current_block <= last_block:
        return

    # 최대 500블록씩 처리
    from_block = last_block + 1
    to_block = min(current_block, from_block + 500)

    wallet_topic = "0x" + config.SUBSCRIPTION_WALLET.lower()[2:].zfill(64)
    transfer_topic = _get_transfer_topic()

    try:
        logs = await w3.eth.get_logs({
            "fromBlock": from_block,
            "toBlock": to_block,
            "address": [
                w3.to_checksum_address(config.USDC_CONTRACT),
                w3.to_checksum_address(config.USDT_CONTRACT),
            ],
            "topics": [transfer_topic, None, wallet_topic],
        })
    except Exception as e:
        logger.error(f"Chain poll: get_logs failed ({from_block}-{to_block}): {e}")
        return

    for log in logs:
        try:
            await _process_transfer(log, bot)
        except Exception as e:
            logger.error(f"Chain poll: process_transfer error: {e}")

    await sq.set_last_processed_block(to_block)


async def _process_transfer(log, bot) -> None:
    """단일 Transfer 이벤트 처리 — 범위 내 금액이면 자동 매칭."""
    contract_addr = log["address"]
    token = _token_name(contract_addr)
    if not token:
        return

    # Transfer event: topics[1]=from, topics[2]=to, data=amount
    from_addr = "0x" + log["topics"][1].hex()[-40:]
    amount_raw = int(log["data"].hex(), 16)
    tx_hash = "0x" + log["transactionHash"].hex()
    amount_usd = amount_raw / 1_000_000

    # pending 결제 중 금액 매칭 (±$0.005 — jitter로 유저별 고유 금액)
    TOLERANCE_RAW = 5_000  # $0.005 in 6 decimals
    pending_list = await sq.get_all_pending_by_token(token)
    matched = None
    for p in pending_list:
        if abs(p["amount_raw"] - amount_raw) <= TOLERANCE_RAW:
            matched = p
            break

    if not matched:
        logger.info(
            f"Transfer detected (no match): {amount_usd} {token} "
            f"from {from_addr[:10]}... tx={tx_hash[:20]}"
        )
        return

    # 이미 처리된 tx인지 확인 (tx_hash UNIQUE)
    try:
        await sq.confirm_payment(matched["id"], tx_hash, from_addr)
    except Exception:
        logger.warning(f"Duplicate tx or confirm error: {tx_hash}")
        return

    # 구독 활성화
    tier_cfg = config.SUBSCRIPTION_TIERS.get(matched["tier"], {})
    duration = tier_cfg.get("duration_days", 30)

    # 기존 구독이 있으면 만료일부터 연장
    existing = await sq.get_active_subscription(matched["user_id"])
    if existing and existing["tier"] == matched["tier"]:
        base_date = existing["expires_at"]
    else:
        base_date = datetime.now(timezone.utc)

    expires_at = base_date + timedelta(days=duration)
    await sq.create_subscription(
        matched["user_id"], matched["tier"], expires_at, matched["id"],
    )

    tier_name = tier_cfg.get("name", matched["tier"])
    exp_kst = expires_at.astimezone(config.KST).strftime("%Y-%m-%d %H:%M")

    logger.info(
        f"Subscription activated: user={matched['user_id']} "
        f"tier={matched['tier']} paid={amount_usd} {token} expires={expires_at}"
    )

    # 유저에게 DM 알림
    try:
        user_text = (
            f"✅ <b>구독이 활성화되었습니다!</b>\n\n"
            f"💎 티어: {tier_name}\n"
            f"📅 만료: {exp_kst} (KST)\n\n"
            f"DM에서 '구독정보'로 혜택을 확인하세요!"
        )
        await bot.send_message(
            chat_id=matched["user_id"], text=user_text, parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Subscription DM failed for {matched['user_id']}: {e}")

    # 관리자에게도 알림
    try:
        basescan_url = f"https://basescan.org/tx/{tx_hash}"
        admin_text = (
            f"💰 <b>구독 자동 승인</b>\n"
            f"👤 user: {matched['user_id']}\n"
            f"💎 tier: {tier_name}\n"
            f"💵 paid: {amount_usd} {token}\n"
            f"🔗 from: <code>{from_addr}</code>\n"
            f"📜 <a href=\"{basescan_url}\">tx: {tx_hash[:18]}...</a>"
        )
        for aid in config.ADMIN_IDS:
            await bot.send_message(
                chat_id=aid, text=admin_text,
                parse_mode="HTML", disable_web_page_preview=True,
            )
    except Exception:
        pass


# ─── 혜택 체크 ────────────────────────────────────

# 캐시: 유저별 구독 정보 (60초 TTL 대신 매번 DB 조회 — 규모 작음)
async def get_user_subscription(user_id: int) -> dict | None:
    """유저 활성 구독 + benefits dict 반환."""
    sub = await sq.get_active_subscription(user_id)
    if not sub:
        return None
    tier_cfg = config.SUBSCRIPTION_TIERS.get(sub["tier"], {})
    return {**sub, "benefits": tier_cfg.get("benefits", {})}


async def has_benefit(user_id: int, key: str) -> bool:
    """유저가 특정 혜택을 가지고 있는지."""
    sub = await get_user_subscription(user_id)
    if not sub:
        return False
    return bool(sub["benefits"].get(key))


async def get_benefit_value(user_id: int, key: str, default=None):
    """혜택 값 조회 (예: bp_multiplier → 1.5)."""
    sub = await get_user_subscription(user_id)
    if not sub:
        return default
    return sub["benefits"].get(key, default)


async def get_user_tier(user_id: int) -> str | None:
    """유저 구독 티어 반환 (없으면 None)."""
    sub = await sq.get_active_subscription(user_id)
    return sub["tier"] if sub else None


# ─── 만료 / 갱신 알림 ────────────────────────────

async def check_expiry_and_notify(bot) -> None:
    """만료 구독 비활성화 + 갱신 알림."""
    # 1. 만료 처리
    expired_users = await sq.deactivate_expired()
    for uid in expired_users:
        try:
            await bot.send_message(
                chat_id=uid,
                text="⏰ <b>구독이 만료되었습니다.</b>\n\nDM에서 '구독'으로 갱신할 수 있습니다!",
                parse_mode="HTML",
            )
        except Exception:
            pass
    if expired_users:
        logger.info(f"Deactivated {len(expired_users)} expired subscriptions")

    # 2. 갱신 알림 (3일 전)
    expiring = await sq.get_expiring_soon(config.RENEWAL_REMINDER_DAYS)
    for sub in expiring:
        try:
            exp_kst = sub["expires_at"].astimezone(config.KST).strftime("%m/%d %H:%M")
            await bot.send_message(
                chat_id=sub["user_id"],
                text=(
                    f"⚠️ 구독이 <b>{exp_kst}</b>에 만료됩니다.\n"
                    f"DM에서 '구독'으로 갱신해주세요!"
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass


# ─── 백그라운드 루프 ─────────────────────────────

async def chain_monitor_loop(bot) -> None:
    """블록체인 모니터 + pending 만료 백그라운드 루프."""
    backoff = config.CHAIN_POLL_INTERVAL
    max_backoff = 60

    while True:
        try:
            await poll_chain_transfers(bot)
            await sq.expire_stale_payments()
            backoff = config.CHAIN_POLL_INTERVAL  # 성공 시 리셋
        except Exception as e:
            logger.error(f"Chain monitor loop error: {e}")
            backoff = min(backoff * 2, max_backoff)

        await asyncio.sleep(backoff)
