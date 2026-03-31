"""DM 구독 핸들러: 구독/구독정보/프리미엄상점/채팅상점."""

import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from database import subscription_queries as sq
from services.subscription_service import (
    create_payment_request,
    get_user_subscription,
    has_benefit,
    get_user_tier,
)
from utils.helpers import ball_emoji, icon_emoji
from utils.i18n import t, get_user_lang

logger = logging.getLogger(__name__)

# 구독 UI 커스텀 이모지 단축
_E_CRYSTAL = icon_emoji("crystal")       # 💎
_E_PIKACHU = icon_emoji("pikachu")       # 🟢 베이직
_E_CROWN = icon_emoji("crown")           # 🟣 채널장
_E_CHECK = icon_emoji("check")           # ✅
_E_COIN = icon_emoji("coin")             # 💰
_E_BOLT = icon_emoji("bolt")             # ⚡
_E_SHOP = icon_emoji("shopping-bag")     # 🏪
_E_MASTER = ball_emoji("masterball")     # 마스터볼
_E_POKE = icon_emoji("pokecenter")       # 포케센터


# ─── 프리미엄 허브 (DM: "프리미엄") ──────────────────

async def premium_hub_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """프리미엄 허브 — 구독/프리미엄상점/가이드 세부 메뉴."""
    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    sub = await get_user_subscription(user_id)

    status_line = ""
    if sub:
        tier_name = config.SUBSCRIPTION_TIERS.get(sub["tier"], {}).get("name", sub["tier"])
        exp = sub["expires_at"].astimezone(config.KST).strftime("%Y-%m-%d")
        status_line = f"\n{_E_CHECK} 현재 구독: <b>{tier_name}</b> (~ {exp})\n"

    lines = [
        f"{_E_CRYSTAL} <b>프리미엄</b>",
        "",
    ]
    if status_line:
        lines.append(status_line)

    lines.extend([
        "아래에서 원하는 메뉴를 선택하세요.",
    ])

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💎 구독", callback_data="pmenu_subscribe"),
            InlineKeyboardButton("🏪 프리미엄상점", callback_data="pmenu_shop"),
        ],
        [
            InlineKeyboardButton("📖 가이드", callback_data="pmenu_guide"),
        ],
    ])
    if sub:
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("💎 구독정보", callback_data="pmenu_status"),
                InlineKeyboardButton("🏪 프리미엄상점", callback_data="pmenu_shop"),
            ],
            [
                InlineKeyboardButton("📖 가이드", callback_data="pmenu_guide"),
            ],
        ])

    await update.message.reply_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=keyboard,
    )


# ─── 구독 메인 (DM: "구독") ──────────────────────

async def subscription_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """구독 티어 목록 표시."""
    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)

    # 현재 구독 상태
    sub = await get_user_subscription(user_id)
    status_line = ""
    if sub:
        tier_name = config.SUBSCRIPTION_TIERS.get(sub["tier"], {}).get("name", sub["tier"])
        exp = sub["expires_at"].astimezone(config.KST).strftime("%Y-%m-%d")
        status_line = f"\n{_E_CHECK} 현재 구독: <b>{tier_name}</b> (~ {exp})\n"

    lines = [f"{_E_CRYSTAL} <b>TG포켓 구독 서비스</b>\n"]
    if status_line:
        lines.append(status_line)

    # 오픈 티어
    buttons = []
    _TIER_EMOJI = {"basic": _E_PIKACHU, "channel_owner": _E_CROWN}
    for key, tier in config.SUBSCRIPTION_TIERS.items():
        emoji = _TIER_EMOJI.get(key, _E_POKE)
        current = f" {_E_CHECK}" if sub and sub["tier"] == key else ""
        lines.append(
            f"{emoji} <b>{tier['name']}</b> — ${tier['price_usd']}/월{current}\n"
            f"  {tier['description']}\n"
        )
        label = f"{tier['name']} ${tier['price_usd']}"
        buttons.append(InlineKeyboardButton(label, callback_data=f"sub_tier_{key}"))

    # 커밍쑨
    for key, info in config.SUBSCRIPTION_COMING_SOON.items():
        lines.append(f"🔒 <b>{info['name']}</b> — Coming Soon\n  {info['description']}\n")

    keyboard = [buttons]
    if sub:
        keyboard.append([InlineKeyboardButton("구독정보", callback_data="sub_status")])

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ─── 구독 콜백 ───────────────────────────────────

async def subscription_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """인라인 버튼 콜백 처리."""
    query = update.callback_query
    await query.answer()
    data = query.data

    user_id = update.effective_user.id

    # 티어 선택 → 토큰 선택
    if data.startswith("sub_tier_"):
        tier = data.replace("sub_tier_", "")
        if tier not in config.SUBSCRIPTION_TIERS:
            await query.edit_message_text("❌ 알 수 없는 티어입니다.")
            return

        tier_cfg = config.SUBSCRIPTION_TIERS[tier]
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("USDC", callback_data=f"sub_token_{tier}_USDC"),
                InlineKeyboardButton("USDT", callback_data=f"sub_token_{tier}_USDT"),
            ],
            [InlineKeyboardButton("← 뒤로", callback_data="sub_back")],
        ])
        await query.edit_message_text(
            f"{_E_COIN} <b>{tier_cfg['name']}</b> 결제\n\n"
            f"Base 체인에서 결제할 토큰을 선택하세요:",
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    # 토큰 선택 → 결제 안내
    elif data.startswith("sub_token_"):
        # sub_token_{tier}_{TOKEN} — tier에 _가 포함될 수 있으므로 마지막 _로 분리
        rest = data.replace("sub_token_", "")
        tier, token = rest.rsplit("_", 1)

        if not config.SUBSCRIPTION_WALLET:
            await query.edit_message_text("❌ 결제 지갑이 설정되지 않았습니다. 관리자에게 문의하세요.")
            return

        try:
            payment = await create_payment_request(user_id, tier, token)
        except Exception as e:
            logger.error(f"Payment request failed: {e}")
            await query.edit_message_text("❌ 결제 요청 생성에 실패했습니다. 잠시 후 다시 시도해주세요.")
            return

        exp_min = config.PAYMENT_WINDOW // 60
        wallet = payment["wallet"]
        amount = payment["amount_usd"]

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 결제 확인", callback_data=f"sub_check_{payment['payment_id']}")],
            [InlineKeyboardButton("❌ 취소", callback_data=f"sub_cancel_{payment['payment_id']}")],
        ])

        await query.edit_message_text(
            f"{_E_CRYSTAL} <b>구독 결제 안내</b>\n\n"
            f"{_E_POKE} 티어: {config.SUBSCRIPTION_TIERS[tier]['name']}\n"
            f"{_E_COIN} 금액: <b>{amount} {token}</b>\n"
            f"{_E_BOLT} 체인: Base\n"
            f"📮 주소:\n<code>{wallet}</code>\n\n"
            f"⚠️ 정확히 <b>{amount} {token}</b>을 보내주세요!\n"
            f"⏱️ {exp_min}분 이내에 전송해주세요.\n\n"
            f"<i>금액이 다르면 자동 매칭이 안 됩니다.</i>",
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    # 수동 결제 확인
    elif data.startswith("sub_check_"):
        payment_id = int(data.replace("sub_check_", ""))
        # 폴링 한번 강제 실행
        try:
            from services.subscription_service import poll_chain_transfers
            await poll_chain_transfers(context.bot)
        except Exception:
            pass

        # 구독 확인
        sub = await get_user_subscription(user_id)
        if sub:
            tier_name = config.SUBSCRIPTION_TIERS.get(sub["tier"], {}).get("name", sub["tier"])
            exp = sub["expires_at"].astimezone(config.KST).strftime("%Y-%m-%d %H:%M")
            await query.edit_message_text(
                f"{_E_CHECK} <b>구독이 활성화되었습니다!</b>\n\n"
                f"{_E_CRYSTAL} 티어: {tier_name}\n"
                f"📅 만료: {exp} (KST)\n\n"
                f"DM에서 '구독정보'로 혜택을 확인하세요!",
                parse_mode="HTML",
            )
        else:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔍 다시 확인", callback_data=f"sub_check_{payment_id}")],
                [InlineKeyboardButton("❌ 취소", callback_data=f"sub_cancel_{payment_id}")],
            ])
            await query.edit_message_text(
                "⏳ 아직 결제가 확인되지 않았습니다.\n\n"
                "전송 후 1-2분 정도 기다려주세요.\n"
                "자동으로 감지되면 DM으로 알림이 옵니다!",
                reply_markup=keyboard,
            )

    # 취소
    elif data.startswith("sub_cancel_"):
        payment_id = int(data.replace("sub_cancel_", ""))
        await sq.cancel_payment(payment_id, user_id)
        await query.edit_message_text("❌ 결제가 취소되었습니다.\n\nDM에서 '구독'으로 다시 시작할 수 있습니다.")

    # 뒤로
    elif data == "sub_back":
        # 구독 메인으로 돌아가기 (message 재생성)
        await query.delete_message()
        # 메인 화면을 다시 보여주기 위해 새 메시지 전송
        fake_update = update
        fake_update._effective_message = None  # noqa
        sub = await get_user_subscription(user_id)
        status_line = ""
        if sub:
            tier_name = config.SUBSCRIPTION_TIERS.get(sub["tier"], {}).get("name", sub["tier"])
            exp = sub["expires_at"].astimezone(config.KST).strftime("%Y-%m-%d")
            status_line = f"\n{_E_CHECK} 현재 구독: <b>{tier_name}</b> (~ {exp})\n"

        lines = [f"{_E_CRYSTAL} <b>TG포켓 구독 서비스</b>\n"]
        if status_line:
            lines.append(status_line)

        _TIER_EMOJI = {"basic": _E_PIKACHU, "channel_owner": _E_CROWN}
        buttons = []
        for key, tier in config.SUBSCRIPTION_TIERS.items():
            emoji = _TIER_EMOJI.get(key, _E_POKE)
            current = f" {_E_CHECK}" if sub and sub["tier"] == key else ""
            lines.append(
                f"{emoji} <b>{tier['name']}</b> — ${tier['price_usd']}/월{current}\n"
                f"  {tier['description']}\n"
            )
            buttons.append(InlineKeyboardButton(f"{tier['name']} ${tier['price_usd']}", callback_data=f"sub_tier_{key}"))

        for key, info in config.SUBSCRIPTION_COMING_SOON.items():
            lines.append(f"🔒 <b>{info['name']}</b> — Coming Soon\n  {info['description']}\n")

        keyboard = [buttons]
        await context.bot.send_message(
            chat_id=user_id,
            text="\n".join(lines),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    # 구독 상태
    elif data == "sub_status":
        await _show_status(query, user_id)

    # 프리미엄상점: 새로고침 (구매 후 돌아가기)
    elif data == "sub_pshop_refresh":
        await _refresh_premium_shop(query, user_id)

    # 프리미엄상점: 마스터볼 구매
    elif data == "sub_pshop_mb":
        await _handle_premium_shop_buy(query, user_id)

    # 프리미엄상점: 하이퍼볼 묶음 구매
    elif data in ("sub_pshop_hb5", "sub_pshop_hb10"):
        qty = 5 if data == "sub_pshop_hb5" else 10
        await _handle_premium_hyperball_buy(query, user_id, qty)

    # 프리미엄상점: 5연뽑기권 구매
    elif data == "sub_pshop_gacha5":
        await _handle_premium_gacha_ticket_buy(query, user_id)

    # 채팅상점: 아케이드 속도 부스트
    elif data.startswith("sub_cshop_speed_"):
        chat_id = int(data.replace("sub_cshop_speed_", ""))
        await _handle_channel_shop_speed(query, user_id, chat_id, context)

    # 채팅상점: 아케이드 시간 연장
    elif data.startswith("sub_cshop_extend_"):
        chat_id = int(data.replace("sub_cshop_extend_", ""))
        await _handle_channel_shop_extend(query, user_id, chat_id, context)


# ─── 프리미엄 허브 콜백 ──────────────────────────

_PREMIUM_GUIDE_TEXT = (
    "💎 <b>프리미엄 가이드</b>\n"
    "━━━━━━━━━━━━━━━\n\n"

    "📍 <b>베이직</b> ($3.90/월)\n"
    "━━━━━━━━━━━━━━━\n"
    "  🔴 포케볼 무제한 충전\n"
    "  🟣 매일 마스터볼 +1개\n"
    "  🔵 매일 하이퍼볼 +5개\n"
    "  ⚔️ 배틀 BP 보상 <b>1.5배</b>\n"
    "  📋 일일미션 보상 <b>1.5배</b>\n"
    "  🛒 프리미엄상점 이용 가능\n"
    "  🏕️ 캠프 거점 <b>2개</b>까지\n"
    "  🎩 '정중한' 칭호 해금\n\n"

    "📍 <b>채널장</b> ($9.90/월)\n"
    "━━━━━━━━━━━━━━━\n"
    "  ✅ 베이직 혜택 <b>전부 포함</b>\n"
    "  ⚡ 강제스폰 <b>무제한</b>\n"
    "  ✨ 이로치 강스권 매일 +2장\n"
    "  🏪 채팅상점 이용 가능\n"
    "  📈 채널 스폰률 <b>+30%</b>\n"
    "  🎮 아케이드 이용권 매일 +1장\n"
    "  📊 채널 경험치 <b>1.5배</b>\n"
    "  👑 '최고' 칭호 해금\n\n"

    "🛒 <b>프리미엄상점 (구독자 전용)</b>\n"
    "━━━━━━━━━━━━━━━\n"
    "  🟣 마스터볼 — 200→300→500 BP (일 5개)\n"
    "  🔵 하이퍼볼 x5 — 90 BP (10%↓)\n"
    "  🔵 하이퍼볼 x10 — 160 BP (20%↓)\n"
    "  🎰 5연뽑기권 — 100 BP (일 3장)\n\n"

    "🏪 <b>채팅상점 (채널장 전용)</b>\n"
    "━━━━━━━━━━━━━━━\n"
    "  채팅방에서 '채팅상점' 입력!\n"
    "  ⚡ 아케이드 속도 부스트 — 100 BP\n"
    "    → 스폰 간격 60초 → 50초 (아케이드당 1회)\n"
    "  ⏰ 아케이드 시간 연장 — 100 BP\n"
    "    → +30분 연장 (중첩 가능)\n\n"

    "💳 <b>결제 방법</b>\n"
    "━━━━━━━━━━━━━━━\n"
    "  1. 위 '구독' 버튼으로 등급 선택\n"
    "  2. 표시된 지갑에 Base 체인 USDC/USDT 전송\n"
    "  3. 30분 이내 자동 인식 → 즉시 활성화!\n"
    "  💡 갱신 시 만료일에서 +30일 추가"
)


async def premium_hub_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """프리미엄 허브 인라인 버튼 콜백."""
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data == "pmenu_subscribe":
        # 구독 화면으로 전환 — subscription_handler와 동일 로직
        await query.delete_message()
        sub = await get_user_subscription(user_id)
        status_line = ""
        if sub:
            tier_name = config.SUBSCRIPTION_TIERS.get(sub["tier"], {}).get("name", sub["tier"])
            exp = sub["expires_at"].astimezone(config.KST).strftime("%Y-%m-%d")
            status_line = f"\n{_E_CHECK} 현재 구독: <b>{tier_name}</b> (~ {exp})\n"

        lines = [f"{_E_CRYSTAL} <b>TG포켓 구독 서비스</b>\n"]
        if status_line:
            lines.append(status_line)

        _TIER_EMOJI = {"basic": _E_PIKACHU, "channel_owner": _E_CROWN}
        buttons = []
        for key, tier in config.SUBSCRIPTION_TIERS.items():
            emoji = _TIER_EMOJI.get(key, _E_POKE)
            current = f" {_E_CHECK}" if sub and sub["tier"] == key else ""
            lines.append(
                f"{emoji} <b>{tier['name']}</b> — ${tier['price_usd']}/월{current}\n"
                f"  {tier['description']}\n"
            )
            buttons.append(InlineKeyboardButton(f"{tier['name']} ${tier['price_usd']}", callback_data=f"sub_tier_{key}"))

        for key, info in config.SUBSCRIPTION_COMING_SOON.items():
            lines.append(f"🔒 <b>{info['name']}</b> — Coming Soon\n  {info['description']}\n")

        keyboard = [buttons]
        if sub:
            keyboard.append([InlineKeyboardButton("구독정보", callback_data="sub_status")])

        await context.bot.send_message(
            chat_id=user_id,
            text="\n".join(lines),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data == "pmenu_status":
        # 구독 정보 표시
        await _show_status(query, user_id)

    elif data == "pmenu_shop":
        # 프리미엄 상점으로 전환
        await query.delete_message()
        if not await has_benefit(user_id, "premium_shop"):
            await context.bot.send_message(
                chat_id=user_id,
                text="🔒 프리미엄 상점은 구독자 전용입니다.\n\nDM에서 '구독'으로 구독하세요!",
            )
            return
        await _send_premium_shop(user_id, context)

    elif data == "pmenu_guide":
        await query.edit_message_text(
            _PREMIUM_GUIDE_TEXT, parse_mode="HTML",
        )


async def _send_premium_shop(user_id: int, context):
    """프리미엄 상점 화면 전송 (콜백에서 호출 — premium_shop_handler와 동일 로직)."""
    from database import queries, battle_queries as bq

    today = config.get_kst_today()
    purchases_today = await bq.get_bp_purchases_today(user_id, "masterball_premium")
    sub = await get_user_subscription(user_id)
    max_limit = sub["benefits"].get("masterball_daily_limit", 5) if sub else 5
    remaining = max(0, max_limit - purchases_today)

    prices = list(config.BP_MASTERBALL_PRICES)
    while len(prices) < max_limit:
        prices.append(500)

    bp = await bq.get_bp(user_id)
    next_price = prices[purchases_today] if purchases_today < max_limit else None

    lines = [
        f"{_E_CRYSTAL} <b>프리미엄 상점</b>\n",
        f"{_E_MASTER} 마스터볼 ({purchases_today}/{max_limit})",
    ]

    if next_price:
        lines.append(f"   다음 가격: {next_price} BP")
        lines.append(f"   보유 BP: {bp:,}")
    else:
        lines.append("   오늘 구매 완료!")

    hb_price = config.BP_HYPER_BALL_COST
    hb5_cost = int(hb_price * 5 * 0.9)
    hb10_cost = int(hb_price * 10 * 0.8)
    hyper_balls = await queries.get_hyper_balls(user_id)

    lines.append("")
    _E_HYPER = ball_emoji("hyperball")
    lines.append(f"{_E_HYPER} 하이퍼볼 (보유: {hyper_balls}개)")
    lines.append(f"   x5 — {hb5_cost} BP <b>(10% 할인)</b>")
    lines.append(f"   x10 — {hb10_cost} BP <b>(20% 할인)</b>")

    gacha_ticket_cost = config.GACHA_MULTI_TICKET_COST
    gacha_ticket_daily = config.GACHA_MULTI_TICKET_DAILY
    gacha_ticket_bought = await bq.get_bp_purchases_today(user_id, "gacha_ticket_5")
    gacha_ticket_remaining = max(0, gacha_ticket_daily - gacha_ticket_bought)

    lines.append("")
    lines.append(f"🎰 5연뽑기권 ({gacha_ticket_bought}/{gacha_ticket_daily})")
    lines.append(f"   {gacha_ticket_cost} BP — 뽑기 5회 (BP 차감 없이!)")
    if gacha_ticket_remaining <= 0:
        lines.append("   오늘 구매 완료!")

    keyboard = []
    if remaining > 0 and next_price and bp >= next_price:
        keyboard.append([InlineKeyboardButton(
            f"마스터볼 구매 ({next_price} BP)", callback_data="sub_pshop_mb",
        )])

    hb_row = []
    if bp >= hb5_cost:
        hb_row.append(InlineKeyboardButton(f"🔵 하이퍼볼 x5 ({hb5_cost}BP)", callback_data="sub_pshop_hb5"))
    if bp >= hb10_cost:
        hb_row.append(InlineKeyboardButton(f"🔵 하이퍼볼 x10 ({hb10_cost}BP)", callback_data="sub_pshop_hb10"))
    if hb_row:
        keyboard.append(hb_row)

    if gacha_ticket_remaining > 0 and bp >= gacha_ticket_cost:
        keyboard.append([InlineKeyboardButton(
            f"🎰 5연뽑기권 ({gacha_ticket_cost} BP)", callback_data="sub_pshop_gacha5",
        )])

    await context.bot.send_message(
        chat_id=user_id,
        text="\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
    )


async def _refresh_premium_shop(query, user_id: int):
    """프리미엄 상점 새로고침 (구매 후 돌아가기 — edit_message_text 사용)."""
    from database import queries, battle_queries as bq

    purchases_today = await bq.get_bp_purchases_today(user_id, "masterball_premium")
    sub = await get_user_subscription(user_id)
    max_limit = sub["benefits"].get("masterball_daily_limit", 5) if sub else 5
    remaining = max(0, max_limit - purchases_today)

    prices = list(config.BP_MASTERBALL_PRICES)
    while len(prices) < max_limit:
        prices.append(500)

    bp = await bq.get_bp(user_id)
    next_price = prices[purchases_today] if purchases_today < max_limit else None

    lines = [
        f"{_E_CRYSTAL} <b>프리미엄 상점</b>\n",
        f"{_E_MASTER} 마스터볼 ({purchases_today}/{max_limit})",
    ]
    if next_price:
        lines.append(f"   다음 가격: {next_price} BP")
        lines.append(f"   보유 BP: {bp:,}")
    else:
        lines.append("   오늘 구매 완료!")

    hb_price = config.BP_HYPER_BALL_COST
    hb5_cost = int(hb_price * 5 * 0.9)
    hb10_cost = int(hb_price * 10 * 0.8)
    hyper_balls = await queries.get_hyper_balls(user_id)

    lines.append("")
    _E_HYPER = ball_emoji("hyperball")
    lines.append(f"{_E_HYPER} 하이퍼볼 (보유: {hyper_balls}개)")
    lines.append(f"   x5 — {hb5_cost} BP (10% 할인)")
    lines.append(f"   x10 — {hb10_cost} BP (20% 할인)")

    gacha_ticket_cost = config.GACHA_MULTI_TICKET_COST
    gacha_ticket_daily = config.GACHA_MULTI_TICKET_DAILY
    gacha_ticket_bought = await bq.get_bp_purchases_today(user_id, "gacha_ticket_5")
    gacha_ticket_remaining = max(0, gacha_ticket_daily - gacha_ticket_bought)

    lines.append("")
    lines.append(f"🎰 5연뽑기권 ({gacha_ticket_bought}/{gacha_ticket_daily})")
    lines.append(f"   {gacha_ticket_cost} BP")
    if gacha_ticket_remaining <= 0:
        lines.append("   오늘 구매 완료!")

    keyboard = []
    if remaining > 0 and next_price and bp >= next_price:
        keyboard.append([InlineKeyboardButton(
            f"마스터볼 구매 ({next_price} BP)", callback_data="sub_pshop_mb",
        )])
    hb_row = []
    if bp >= hb5_cost:
        hb_row.append(InlineKeyboardButton(f"🔵 x5 ({hb5_cost}BP)", callback_data="sub_pshop_hb5"))
    if bp >= hb10_cost:
        hb_row.append(InlineKeyboardButton(f"🔵 x10 ({hb10_cost}BP)", callback_data="sub_pshop_hb10"))
    if hb_row:
        keyboard.append(hb_row)
    if gacha_ticket_remaining > 0 and bp >= gacha_ticket_cost:
        keyboard.append([InlineKeyboardButton(
            f"🎰 5연뽑기권 ({gacha_ticket_cost} BP)", callback_data="sub_pshop_gacha5",
        )])

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
    )


# ─── 구독정보 (DM: "구독정보") ────────────────────

async def subscription_status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """현재 구독 상태 표시."""
    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    sub = await get_user_subscription(user_id)

    if not sub:
        await update.message.reply_text(
            f"{_E_CRYSTAL} {t(lang, 'subscription.not_subscribed')}",
            parse_mode="HTML",
        )
        return

    tier_cfg = config.SUBSCRIPTION_TIERS.get(sub["tier"], {})
    tier_name = tier_cfg.get("name", sub["tier"])
    exp = sub["expires_at"].astimezone(config.KST).strftime("%Y-%m-%d %H:%M")
    benefits = tier_cfg.get("benefits", {})

    benefit_lines = []
    if benefits.get("pokeball_unlimited"):
        benefit_lines.append("• 포케볼 무제한")
    if benefits.get("premium_shop"):
        limit = benefits.get("masterball_daily_limit", 3)
        benefit_lines.append(f"• 프리미엄상점 (마스터볼 {limit}개/일)")
    if benefits.get("catch_cooldown_bypass"):
        benefit_lines.append("• 연속포획 쿨다운 해제")
    if benefits.get("daily_masterball"):
        benefit_lines.append(f"• 일일 마스터볼 +{benefits['daily_masterball']}")
    if benefits.get("daily_hyperball"):
        benefit_lines.append(f"• 일일 하이퍼볼 +{benefits['daily_hyperball']}")
    if benefits.get("bp_multiplier"):
        benefit_lines.append(f"• 배틀 BP {benefits['bp_multiplier']}배")
    if benefits.get("mission_reward_multiplier"):
        benefit_lines.append(f"• 미션 보상 {benefits['mission_reward_multiplier']}배")
    if benefits.get("force_spawn_unlimited"):
        benefit_lines.append("• 강제스폰 무제한")
    if benefits.get("channel_shop"):
        benefit_lines.append("• 채팅상점 이용 가능")
    if benefits.get("channel_spawn_boost"):
        pct = int((benefits["channel_spawn_boost"] - 1) * 100)
        benefit_lines.append(f"• 채널 스폰 +{pct}%")
    if benefits.get("daily_free_arcade_pass"):
        benefit_lines.append(f"• 일일 무료 아케이드 +{benefits['daily_free_arcade_pass']}")
    if benefits.get("channel_cxp_multiplier"):
        benefit_lines.append(f"• 채널 경험치 {benefits['channel_cxp_multiplier']}배")
    if benefits.get("daily_shiny_ticket"):
        benefit_lines.append(f"• 일일 이로치 강스권 +{benefits['daily_shiny_ticket']}")
    if benefits.get("honorific"):
        benefit_lines.append("• 🎩 ???")

    text = (
        f"{_E_CRYSTAL} <b>구독 정보</b>\n\n"
        f"티어: <b>{tier_name}</b>\n"
        f"만료: {exp} (KST)\n\n"
        f"<b>혜택:</b>\n" + "\n".join(benefit_lines)
    )

    await update.message.reply_text(text, parse_mode="HTML")


async def _show_status(query, user_id: int):
    """콜백에서 호출되는 상태 표시."""
    sub = await get_user_subscription(user_id)
    if not sub:
        await query.edit_message_text(f"{_E_CRYSTAL} 현재 구독 중인 티어가 없습니다.", parse_mode="HTML")
        return

    tier_cfg = config.SUBSCRIPTION_TIERS.get(sub["tier"], {})
    tier_name = tier_cfg.get("name", sub["tier"])
    exp = sub["expires_at"].astimezone(config.KST).strftime("%Y-%m-%d %H:%M")
    await query.edit_message_text(
        f"{_E_CRYSTAL} <b>{tier_name}</b> 구독 중\n📅 만료: {exp} (KST)",
        parse_mode="HTML",
    )


# ─── 프리미엄상점 (DM: "프리미엄상점") ────────────

async def premium_shop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """프리미엄 상점 (구독자 전용 마스터볼 확장 구매)."""
    user_id = update.effective_user.id

    if not await has_benefit(user_id, "premium_shop"):
        await update.message.reply_text(
            "🔒 프리미엄 상점은 구독자 전용입니다.\n\nDM에서 '구독'으로 구독하세요!",
        )
        return

    from database import queries, battle_queries as bq

    # 오늘 마스터볼 구매 횟수
    today = config.get_kst_today()
    purchases_today = await bq.get_bp_purchases_today(user_id, "masterball_premium")
    sub = await get_user_subscription(user_id)
    max_limit = sub["benefits"].get("masterball_daily_limit", 5) if sub else 5
    remaining = max(0, max_limit - purchases_today)

    # 가격: 1번째 200, 2번째 300, 3번째 500, 4-5번째 500
    prices = list(config.BP_MASTERBALL_PRICES)  # [200, 300, 500]
    while len(prices) < max_limit:
        prices.append(500)  # 4, 5번째도 500BP

    bp = await bq.get_bp(user_id)
    next_price = prices[purchases_today] if purchases_today < max_limit else None

    lines = [
        f"{_E_CRYSTAL} <b>프리미엄 상점</b>\n",
        f"{_E_MASTER} 마스터볼 ({purchases_today}/{max_limit})",
    ]

    if next_price:
        lines.append(f"   다음 가격: {next_price} BP")
        lines.append(f"   보유 BP: {bp:,}")
    else:
        lines.append("   오늘 구매 완료!")

    # 하이퍼볼 묶음 할인
    hb_price = config.BP_HYPER_BALL_COST  # 20 BP
    hb5_cost = int(hb_price * 5 * 0.9)   # 5개 10% 할인 → 90 BP
    hb10_cost = int(hb_price * 10 * 0.8)  # 10개 20% 할인 → 160 BP
    hyper_balls = await queries.get_hyper_balls(user_id)

    lines.append("")
    _E_HYPER = ball_emoji("hyperball")
    lines.append(f"{_E_HYPER} 하이퍼볼 (보유: {hyper_balls}개)")
    lines.append(f"   x5 — {hb5_cost} BP <b>(10% 할인)</b>")
    lines.append(f"   x10 — {hb10_cost} BP <b>(20% 할인)</b>")

    # 5연뽑기권
    gacha_ticket_cost = config.GACHA_MULTI_TICKET_COST
    gacha_ticket_daily = config.GACHA_MULTI_TICKET_DAILY
    gacha_ticket_bought = await bq.get_bp_purchases_today(user_id, "gacha_ticket_5")
    gacha_ticket_remaining = max(0, gacha_ticket_daily - gacha_ticket_bought)

    lines.append("")
    lines.append(f"🎰 5연뽑기권 ({gacha_ticket_bought}/{gacha_ticket_daily})")
    lines.append(f"   {gacha_ticket_cost} BP — 뽑기 5회 (BP 차감 없이!)")
    if gacha_ticket_remaining <= 0:
        lines.append("   오늘 구매 완료!")

    keyboard = []
    if remaining > 0 and bp >= next_price:
        keyboard.append([InlineKeyboardButton(
            f"마스터볼 구매 ({next_price} BP)",
            callback_data="sub_pshop_mb",
        )])

    hb_row = []
    if bp >= hb5_cost:
        hb_row.append(InlineKeyboardButton(
            f"🔵 하이퍼볼 x5 ({hb5_cost}BP)",
            callback_data="sub_pshop_hb5",
        ))
    if bp >= hb10_cost:
        hb_row.append(InlineKeyboardButton(
            f"🔵 하이퍼볼 x10 ({hb10_cost}BP)",
            callback_data="sub_pshop_hb10",
        ))
    if hb_row:
        keyboard.append(hb_row)

    if gacha_ticket_remaining > 0 and bp >= gacha_ticket_cost:
        keyboard.append([InlineKeyboardButton(
            f"🎰 5연뽑기권 ({gacha_ticket_cost} BP)",
            callback_data="sub_pshop_gacha5",
        )])

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
    )


# ─── 채팅상점 (그룹: "채팅상점") ──────────────────

async def channel_shop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """채널장 상점 (그룹 채팅에서 사용)."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # 그룹 채팅에서만
    if update.effective_chat.type == "private":
        await update.message.reply_text("채팅상점은 그룹 채팅방에서 사용해주세요!")
        return

    if not await has_benefit(user_id, "channel_shop"):
        await update.message.reply_text(
            "🔒 채팅상점은 채널장 구독자 전용입니다.\n\nDM에서 '구독'으로 구독하세요!",
        )
        return

    from database import queries, battle_queries as bq

    bp = await bq.get_bp(user_id)

    text = (
        f"{_E_SHOP} <b>채널장 상점</b>\n\n"
        f"{_E_BOLT} <b>아케이드 속도 부스트</b> — {config.CHANNEL_SHOP_ARCADE_SPEED_COST} BP\n"
        f"   스폰 간격 {config.ARCADE_TICKET_SPAWN_INTERVAL}초 → {config.ARCADE_TICKET_SPAWN_INTERVAL - config.ARCADE_SPEED_BOOST_REDUCTION}초 (아케이드당 1회)\n\n"
        f"⏱️ <b>아케이드 시간 연장</b> — {config.CHANNEL_SHOP_ARCADE_EXTEND_COST} BP\n"
        f"   활성 아케이드 +{config.ARCADE_EXTEND_MINUTES}분 연장\n\n"
        f"{_E_COIN} 보유 BP: {bp:,}"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"속도 부스트 ({config.CHANNEL_SHOP_ARCADE_SPEED_COST} BP)",
                callback_data=f"sub_cshop_speed_{chat_id}",
            ),
            InlineKeyboardButton(
                f"시간 연장 ({config.CHANNEL_SHOP_ARCADE_EXTEND_COST} BP)",
                callback_data=f"sub_cshop_extend_{chat_id}",
            ),
        ],
    ])

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


# ─── 프리미엄상점 콜백 ────────────────────────────

async def _handle_premium_shop_buy(query, user_id: int):
    """프리미엄상점 마스터볼 구매 처리."""
    if not await has_benefit(user_id, "premium_shop"):
        await query.edit_message_text("🔒 프리미엄 상점은 구독자 전용입니다.")
        return

    from database import queries, battle_queries as bq

    today = config.get_kst_today()
    purchases_today = await bq.get_bp_purchases_today(user_id, "masterball_premium")
    sub = await get_user_subscription(user_id)
    max_limit = sub["benefits"].get("masterball_daily_limit", 5) if sub else 5

    if purchases_today >= max_limit:
        await query.edit_message_text("❌ 오늘의 마스터볼 구매 한도를 모두 사용했습니다.")
        return

    prices = list(config.BP_MASTERBALL_PRICES)
    while len(prices) < max_limit:
        prices.append(500)
    price = prices[purchases_today]

    bp = await bq.get_bp(user_id)
    if bp < price:
        await query.edit_message_text(f"❌ BP가 부족합니다. (필요: {price} / 보유: {bp:,})")
        return

    # BP 차감 + 마스터볼 지급
    await bq.add_bp(user_id, -price, "shop_masterball")
    await queries.add_master_ball(user_id, 1)
    await bq.log_bp_purchase(user_id, "masterball_premium", 1)

    new_bp = bp - price
    remaining = max_limit - purchases_today - 1

    text = (
        f"✅ 마스터볼 구매 완료!\n\n"
        f"💰 {price} BP 사용 (잔여: {new_bp:,} BP)\n"
        f"🔴 남은 구매: {remaining}/{max_limit}"
    )
    # 재구매 / 돌아가기 버튼
    kb = []
    if remaining > 0:
        next_idx = purchases_today + 1
        next_prices = list(config.BP_MASTERBALL_PRICES)
        while len(next_prices) < max_limit:
            next_prices.append(500)
        if next_idx < len(next_prices) and new_bp >= next_prices[next_idx]:
            kb.append([InlineKeyboardButton(
                f"🔴 한 개 더 ({next_prices[next_idx]} BP)", callback_data="sub_pshop_mb",
            )])
    kb.append([InlineKeyboardButton("🔙 상점으로", callback_data="sub_pshop_refresh")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def _handle_premium_hyperball_buy(query, user_id: int, qty: int):
    """프리미엄상점 하이퍼볼 묶음 구매 처리."""
    if not await has_benefit(user_id, "premium_shop"):
        await query.edit_message_text("🔒 프리미엄 상점은 구독자 전용입니다.")
        return

    from database import queries, battle_queries as bq

    hb_price = config.BP_HYPER_BALL_COST  # 20 BP
    if qty == 5:
        cost = int(hb_price * 5 * 0.9)   # 90 BP
    else:
        cost = int(hb_price * 10 * 0.8)  # 160 BP

    bp = await bq.get_bp(user_id)
    if bp < cost:
        await query.edit_message_text(f"❌ BP가 부족합니다. (필요: {cost} / 보유: {bp:,})")
        return

    # BP 차감 + 하이퍼볼 지급
    await bq.add_bp(user_id, -cost, "shop_hyperball")
    await queries.add_hyper_ball(user_id, qty)

    new_bp = bp - cost
    hyper_balls = await queries.get_hyper_balls(user_id)

    discount = "10%" if qty == 5 else "20%"
    await query.edit_message_text(
        f"✅ 하이퍼볼 x{qty} 구매 완료! ({discount} 할인)\n\n"
        f"💰 {cost} BP 사용 (잔여: {new_bp:,} BP)\n"
        f"🔵 보유 하이퍼볼: {hyper_balls}개",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 상점으로", callback_data="sub_pshop_refresh"),
        ]]),
    )


async def _handle_premium_gacha_ticket_buy(query, user_id: int):
    """프리미엄상점 5연뽑기권 구매 처리."""
    if not await has_benefit(user_id, "premium_shop"):
        await query.edit_message_text("🔒 프리미엄 상점은 구독자 전용입니다.")
        return

    from database import queries, item_queries, battle_queries as bq

    # 일일 한도 체크
    bought = await bq.get_bp_purchases_today(user_id, "gacha_ticket_5")
    if bought >= config.GACHA_MULTI_TICKET_DAILY:
        await query.edit_message_text(
            f"❌ 오늘 구매 한도({config.GACHA_MULTI_TICKET_DAILY}회)를 초과했습니다."
        )
        return

    cost = config.GACHA_MULTI_TICKET_COST
    bp = await bq.get_bp(user_id)
    if bp < cost:
        await query.edit_message_text(f"❌ BP가 부족합니다. (필요: {cost} / 보유: {bp:,})")
        return

    # BP 차감 + 아이템 지급 + 로그
    await bq.add_bp(user_id, -cost, "shop_gacha_ticket")
    await item_queries.add_user_item(user_id, "gacha_ticket_5", 1)
    await bq.log_bp_purchase(user_id, "gacha_ticket_5", 1)

    new_bp = bp - cost
    qty = await item_queries.get_user_item(user_id, "gacha_ticket_5")

    await query.edit_message_text(
        f"✅ 5연뽑기권 구매 완료!\n\n"
        f"💰 {cost} BP 사용 (잔여: {new_bp:,} BP)\n"
        f"🎰 보유 5연뽑기권: {qty}개\n\n"
        f"💡 DM에서 '아이템'을 입력해서 사용하세요!",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 상점으로", callback_data="sub_pshop_refresh"),
        ]]),
    )


# ─── 채팅상점 콜백 ─────────────────────────────────

async def _handle_channel_shop_speed(query, user_id: int, chat_id: int, context):
    """아케이드 속도 부스트 (-10초)."""
    if not await has_benefit(user_id, "channel_shop"):
        await query.edit_message_text("🔒 채팅상점은 채널장 구독자 전용입니다.")
        return

    from database import battle_queries as bq

    cost = config.CHANNEL_SHOP_ARCADE_SPEED_COST
    bp = await bq.get_bp(user_id)
    if bp < cost:
        await query.edit_message_text(f"❌ BP가 부족합니다. (필요: {cost} / 보유: {bp:,})")
        return

    # 활성 아케이드가 있는지 확인
    from services.spawn_service import get_arcade_state
    arcade = get_arcade_state(context.application, chat_id)
    if not arcade or not arcade.get("active"):
        await query.edit_message_text("❌ 이 채팅방에 활성 아케이드가 없습니다.")
        return

    # 1회만 사용 가능
    if arcade.get("speed_boosted"):
        await query.edit_message_text("❌ 이미 속도 부스트를 사용했습니다! (아케이드당 1회)")
        return

    current_interval = arcade.get("interval", config.ARCADE_SPAWN_INTERVAL)
    min_interval = 20
    if current_interval <= min_interval:
        await query.edit_message_text(f"❌ 이미 최소 간격({min_interval}초)입니다.")
        return

    # BP 차감 + 속도 부스트 적용
    await bq.add_bp(user_id, -cost, "shop_arcade_speed")
    new_interval = max(min_interval, current_interval - config.ARCADE_SPEED_BOOST_REDUCTION)

    from services.spawn_service import set_arcade_interval
    set_arcade_interval(context.application, chat_id, new_interval)

    await query.edit_message_text(
        f"{_E_BOLT} 아케이드 속도 부스트 적용!\n\n"
        f"스폰 간격: {current_interval}초 → {new_interval}초\n"
        f"{_E_COIN} {cost} BP 사용 (잔여: {bp - cost:,} BP)",
        parse_mode="HTML",
    )


async def _handle_channel_shop_extend(query, user_id: int, chat_id: int, context):
    """아케이드 시간 연장 (+30분)."""
    if not await has_benefit(user_id, "channel_shop"):
        await query.edit_message_text("🔒 채팅상점은 채널장 구독자 전용입니다.")
        return

    from database import battle_queries as bq

    cost = config.CHANNEL_SHOP_ARCADE_EXTEND_COST
    bp = await bq.get_bp(user_id)
    if bp < cost:
        await query.edit_message_text(f"❌ BP가 부족합니다. (필요: {cost} / 보유: {bp:,})")
        return

    # 활성 아케이드가 있는지 확인
    from services.spawn_service import get_arcade_state, extend_arcade_time
    arcade = get_arcade_state(context.application, chat_id)
    if not arcade or not arcade.get("active"):
        await query.edit_message_text("❌ 이 채팅방에 활성 아케이드가 없습니다.")
        return

    # BP 차감 + 시간 연장
    await bq.add_bp(user_id, -cost, "shop_arcade_extend")
    extend_minutes = config.ARCADE_EXTEND_MINUTES
    await extend_arcade_time(context.application, chat_id, extend_minutes)

    await query.edit_message_text(
        f"⏱️ 아케이드 시간 연장 완료!\n\n"
        f"+{extend_minutes}분 연장되었습니다.\n"
        f"{_E_COIN} {cost} BP 사용 (잔여: {bp - cost:,} BP)",
        parse_mode="HTML",
    )
