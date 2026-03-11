"""구독 결제 & 구독 상태 관리 쿼리."""

import logging
from datetime import datetime, timedelta, timezone
from database.connection import get_db

logger = logging.getLogger(__name__)


# ─── 결제 대기 ────────────────────────────────────

async def create_pending_payment(
    user_id: int, tier: str, amount_raw: int, amount_usd: float,
    token: str, expires_at: datetime,
) -> int:
    """결제 대기 레코드 생성. 반환: payment_id."""
    pool = await get_db()
    row = await pool.fetchrow(
        """INSERT INTO subscription_payments
           (user_id, tier, amount_raw, amount_usd, token, expires_at)
           VALUES ($1, $2, $3, $4, $5, $6)
           RETURNING id""",
        user_id, tier, amount_raw, amount_usd, token, expires_at,
    )
    return row["id"]


async def get_user_pending(user_id: int) -> dict | None:
    """유저의 활성 pending 결제 조회."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT * FROM subscription_payments
           WHERE user_id = $1 AND status = 'pending' AND expires_at > NOW()
           ORDER BY created_at DESC LIMIT 1""",
        user_id,
    )
    return dict(row) if row else None


async def get_pending_by_amount(amount_raw: int, token: str) -> dict | None:
    """금액+토큰으로 pending 결제 매칭 (가장 오래된 것 우선)."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT * FROM subscription_payments
           WHERE amount_raw = $1 AND token = $2
             AND status = 'pending' AND expires_at > NOW()
           ORDER BY created_at ASC LIMIT 1""",
        amount_raw, token,
    )
    return dict(row) if row else None


async def get_all_pending_by_token(token: str) -> list[dict]:
    """해당 토큰의 모든 활성 pending 결제 목록."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT * FROM subscription_payments
           WHERE token = $1 AND status = 'pending' AND expires_at > NOW()
           ORDER BY created_at ASC""",
        token,
    )
    return [dict(r) for r in rows]


async def confirm_payment(payment_id: int, tx_hash: str, from_address: str) -> None:
    """결제 확인 (pending → confirmed)."""
    pool = await get_db()
    await pool.execute(
        """UPDATE subscription_payments
           SET status = 'confirmed', tx_hash = $2, from_address = $3,
               confirmed_at = NOW()
           WHERE id = $1 AND status = 'pending'""",
        payment_id, tx_hash, from_address,
    )


async def expire_stale_payments() -> int:
    """30분 초과 pending 결제 만료. 반환: 만료 건수."""
    pool = await get_db()
    result = await pool.execute(
        """UPDATE subscription_payments
           SET status = 'expired'
           WHERE status = 'pending' AND expires_at <= NOW()"""
    )
    count = int(result.split()[-1]) if result else 0
    if count:
        logger.info(f"Expired {count} stale subscription payments")
    return count


async def is_amount_taken(amount_raw: int, token: str) -> bool:
    """해당 금액+토큰 조합이 이미 pending에 존재하는지."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT 1 FROM subscription_payments
           WHERE amount_raw = $1 AND token = $2
             AND status = 'pending' AND expires_at > NOW()""",
        amount_raw, token,
    )
    return row is not None


async def cancel_payment(payment_id: int, user_id: int) -> bool:
    """유저가 직접 취소. 반환: 성공 여부."""
    pool = await get_db()
    result = await pool.execute(
        """UPDATE subscription_payments SET status = 'expired'
           WHERE id = $1 AND user_id = $2 AND status = 'pending'""",
        payment_id, user_id,
    )
    return "UPDATE 1" in result


# ─── 구독 상태 ────────────────────────────────────

async def create_subscription(
    user_id: int, tier: str, expires_at: datetime, payment_id: int,
) -> int:
    """구독 생성. 반환: subscription_id."""
    pool = await get_db()
    # 기존 같은 티어 구독 비활성화
    await pool.execute(
        """UPDATE subscriptions SET is_active = 0
           WHERE user_id = $1 AND is_active = 1""",
        user_id,
    )
    row = await pool.fetchrow(
        """INSERT INTO subscriptions (user_id, tier, expires_at, payment_id)
           VALUES ($1, $2, $3, $4)
           RETURNING id""",
        user_id, tier, expires_at, payment_id,
    )
    return row["id"]


async def get_active_subscription(user_id: int) -> dict | None:
    """유저의 활성 구독 조회."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT * FROM subscriptions
           WHERE user_id = $1 AND is_active = 1 AND expires_at > NOW()
           ORDER BY expires_at DESC LIMIT 1""",
        user_id,
    )
    return dict(row) if row else None


async def get_all_active_subscriptions() -> list[dict]:
    """모든 활성 구독 조회 (일일 혜택 지급용)."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT * FROM subscriptions
           WHERE is_active = 1 AND expires_at > NOW()"""
    )
    return [dict(r) for r in rows]


async def deactivate_expired() -> list[int]:
    """만료된 구독 비활성화. 반환: 만료된 유저 ID 목록."""
    pool = await get_db()
    rows = await pool.fetch(
        """UPDATE subscriptions SET is_active = 0
           WHERE is_active = 1 AND expires_at <= NOW()
           RETURNING user_id"""
    )
    return [r["user_id"] for r in rows]


async def get_expiring_soon(days: int = 3) -> list[dict]:
    """N일 이내 만료 예정 구독 조회."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT s.*, u.display_name
           FROM subscriptions s
           JOIN users u ON u.user_id = s.user_id
           WHERE s.is_active = 1
             AND s.expires_at > NOW()
             AND s.expires_at <= NOW() + $1 * INTERVAL '1 day'""",
        days,
    )
    return [dict(r) for r in rows]


# ─── 블록 추적 ────────────────────────────────────

async def get_last_processed_block() -> int | None:
    """마지막 처리 블록 번호 조회."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT value FROM bot_settings WHERE key = 'last_sub_block'"
    )
    return int(row["value"]) if row else None


async def set_last_processed_block(block_number: int) -> None:
    """마지막 처리 블록 번호 저장."""
    pool = await get_db()
    await pool.execute(
        """INSERT INTO bot_settings (key, value)
           VALUES ('last_sub_block', $1)
           ON CONFLICT (key) DO UPDATE SET value = $1""",
        str(block_number),
    )
