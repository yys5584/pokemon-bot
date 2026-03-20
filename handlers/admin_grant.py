"""Admin grant handlers: 마볼지급, BP지급, 구독권지급, 구독승인."""

import logging
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import ContextTypes

import config

from database import queries
from handlers.admin import is_admin
from utils.helpers import icon_emoji

logger = logging.getLogger(__name__)


async def grant_masterball_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '마볼지급 [개수]' command.
    - 그룹: 상대 메시지에 답장 + '마볼지급 [개수]'
    - DM: '마볼지급 [유저ID] [개수]'
    """
    if not update.effective_user or not update.message:
        return
    if not is_admin(update.effective_user.id):
        return

    text = (update.message.text or "").strip()
    parts = text.split()
    is_group = update.effective_chat.type in ("group", "supergroup")

    target_user_id = None
    count = 1

    if is_group:
        reply = update.message.reply_to_message
        if not reply or not reply.from_user:
            await update.message.reply_text("대상의 메시지에 답장으로 '마볼지급 [개수]' 를 입력하세요.")
            return
        target_user_id = reply.from_user.id
        if len(parts) >= 2:
            try:
                count = int(parts[1])
                if count < 1 or count > 99:
                    await update.message.reply_text("개수는 1~99 사이로 입력해주세요.")
                    return
            except ValueError:
                pass
    else:
        if len(parts) < 2:
            await update.message.reply_text(
                "사용법: 마볼지급 [유저ID] [개수]\n"
                "예: 마볼지급 123456789 1\n"
                "그룹에서는 답장으로 사용 가능"
            )
            return
        try:
            target_user_id = int(parts[1])
        except ValueError:
            await update.message.reply_text("유저 ID를 숫자로 입력해주세요.")
            return
        if len(parts) >= 3:
            try:
                count = int(parts[2])
                if count < 1 or count > 99:
                    await update.message.reply_text("개수는 1~99 사이로 입력해주세요.")
                    return
            except ValueError:
                pass

    user = await queries.get_user(target_user_id)
    if not user:
        await update.message.reply_text(f"유저를 찾을 수 없습니다. (봇 미등록)")
        return

    await queries.add_master_ball(target_user_id, count)
    new_total = await queries.get_master_balls(target_user_id)

    await update.message.reply_text(
        f"{icon_emoji('check')} 마스터볼 지급 완료!\n"
        f"대상: {user['display_name']}\n"
        f"지급: {count}개\n"
        f"현재 보유: {new_total}개",
        parse_mode="HTML",
    )

    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"🎁 마스터볼 {count}개를 지급받았습니다!\n현재 보유: {new_total}개",
        )
    except Exception:
        pass

    logger.info(f"Admin granted {count} master ball(s) to user {target_user_id}")


async def grant_bp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'BP지급 [금액]' command.
    - 그룹: 답장 + 'BP지급 [금액]'
    - DM: 'BP지급 [유저ID] [금액]'
    """
    if not update.effective_user or not update.message:
        return
    if not is_admin(update.effective_user.id):
        return

    from database import battle_queries as bq

    text = (update.message.text or "").strip()
    parts = text.split()
    is_group = update.effective_chat.type in ("group", "supergroup")

    target_user_id = None
    amount = 0

    if is_group:
        reply = update.message.reply_to_message
        if not reply or not reply.from_user:
            await update.message.reply_text("대상의 메시지에 답장으로 'BP지급 [금액]' 을 입력하세요.")
            return
        target_user_id = reply.from_user.id
        if len(parts) >= 2:
            try:
                amount = int(parts[1])
            except ValueError:
                await update.message.reply_text("금액을 숫자로 입력해주세요.")
                return
        else:
            await update.message.reply_text("사용법: BP지급 [금액]")
            return
    else:
        if len(parts) < 3:
            await update.message.reply_text(
                "사용법: BP지급 [유저ID] [금액]\n"
                "예: BP지급 123456789 500\n"
                "그룹에서는 답장으로 사용 가능"
            )
            return
        try:
            target_user_id = int(parts[1])
        except ValueError:
            await update.message.reply_text("유저 ID를 숫자로 입력해주세요.")
            return
        try:
            amount = int(parts[2])
        except ValueError:
            await update.message.reply_text("금액을 숫자로 입력해주세요.")
            return

    if amount <= 0 or amount > 99999:
        await update.message.reply_text("금액은 1~99999 사이로 입력해주세요.")
        return

    user = await queries.get_user(target_user_id)
    if not user:
        await update.message.reply_text("유저를 찾을 수 없습니다. (봇 미등록)")
        return

    await bq.add_bp(target_user_id, amount, "admin")
    new_bp = await bq.get_bp(target_user_id)

    await update.message.reply_text(
        f"{icon_emoji('check')} BP 지급 완료!\n"
        f"대상: {user['display_name']}\n"
        f"지급: {amount} BP\n"
        f"현재 보유: {new_bp} BP",
        parse_mode="HTML",
    )

    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"🎁 BP {amount}을(를) 지급받았습니다!\n현재 보유: {new_bp} BP",
        )
    except Exception:
        pass

    logger.info(f"Admin granted {amount} BP to user {target_user_id}")


async def grant_subscription_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '구독권지급 [티어] [일수]' command."""
    if not update.effective_user or not update.message:
        return
    if not is_admin(update.effective_user.id):
        return

    from database import subscription_queries as sq

    text = (update.message.text or "").strip()
    parts = text.split()
    is_group = update.effective_chat.type in ("group", "supergroup")

    target_user_id = None
    tier = "basic"
    days = 30

    _TIER_MAP = {"베이직": "basic", "basic": "basic", "채널장": "channel_owner", "channel_owner": "channel_owner"}

    if is_group:
        reply = update.message.reply_to_message
        if not reply or not reply.from_user:
            await update.message.reply_text("대상의 메시지에 답장으로 '구독권지급 [티어] [일수]' 를 입력하세요.")
            return
        target_user_id = reply.from_user.id
        if len(parts) >= 2:
            tier = _TIER_MAP.get(parts[1], parts[1])
        if len(parts) >= 3:
            try:
                days = int(parts[2])
            except ValueError:
                pass
    else:
        if len(parts) < 2:
            await update.message.reply_text(
                "사용법: 구독권지급 [유저ID] [티어] [일수]\n"
                "예: 구독권지급 123456789 채널장 30\n"
                "티어: 베이직 / 채널장\n"
                "일수 생략 시 30일"
            )
            return
        try:
            target_user_id = int(parts[1])
        except ValueError:
            await update.message.reply_text("유저 ID를 숫자로 입력해주세요.")
            return
        if len(parts) >= 3:
            tier = _TIER_MAP.get(parts[2], parts[2])
        if len(parts) >= 4:
            try:
                days = int(parts[3])
            except ValueError:
                pass

    if tier not in config.SUBSCRIPTION_TIERS:
        await update.message.reply_text(f"유효하지 않은 티어입니다. (베이직 / 채널장)")
        return

    if days < 1 or days > 365:
        await update.message.reply_text("일수는 1~365 사이로 입력해주세요.")
        return

    user = await queries.get_user(target_user_id)
    if not user:
        await update.message.reply_text("유저를 찾을 수 없습니다. (봇 미등록)")
        return

    existing = await sq.get_active_subscription(target_user_id)
    if existing and existing["tier"] == tier:
        new_expires = existing["expires_at"] + timedelta(days=days)
    else:
        new_expires = datetime.utcnow() + timedelta(days=days)

    await sq.create_subscription(target_user_id, tier, new_expires, payment_id=None)

    tier_name = config.SUBSCRIPTION_TIERS[tier]["name"]
    exp_kst = (new_expires + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M")

    await update.message.reply_text(
        f"{icon_emoji('check')} 구독권 지급 완료!\n"
        f"대상: {user['display_name']}\n"
        f"티어: {tier_name}\n"
        f"기간: {days}일\n"
        f"만료: {exp_kst} (KST)",
        parse_mode="HTML",
    )

    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"🎁 {tier_name} 구독권 {days}일이 지급되었습니다!\n만료: {exp_kst} (KST)",
        )
    except Exception:
        pass

    logger.info(f"Admin granted {tier} subscription ({days}d) to user {target_user_id}")


async def manual_subscription_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: 구독승인 {user_id} {tier} — RPC 장애 시 수동 승인."""
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    text = (update.message.text or "").strip()
    parts = text.split()
    if len(parts) < 2:
        await update.message.reply_text(
            "사용법: 구독승인 {user_id} {tier}\n"
            "tier: basic / channel_owner (기본: basic)"
        )
        return

    try:
        target_uid = int(parts[1])
    except ValueError:
        await update.message.reply_text("❌ user_id는 숫자여야 합니다.")
        return

    tier = parts[2] if len(parts) >= 3 else "basic"
    if tier not in config.SUBSCRIPTION_TIERS:
        await update.message.reply_text(f"❌ 알 수 없는 티어: {tier}\n사용 가능: {', '.join(config.SUBSCRIPTION_TIERS.keys())}")
        return

    from database import subscription_queries as sq

    tier_cfg = config.SUBSCRIPTION_TIERS[tier]
    duration = tier_cfg.get("duration_days", 30)

    existing = await sq.get_active_subscription(target_uid)
    if existing and existing["tier"] == tier:
        base_date = existing["expires_at"]
    else:
        base_date = config.get_kst_now()

    expires_at = base_date + timedelta(days=duration)

    pending = await sq.get_user_pending(target_uid)
    if pending:
        payment_id = pending["id"]
        await sq.confirm_payment(payment_id, f"manual_{int(config.get_kst_now().timestamp())}", "admin")
    else:
        payment_id = await sq.create_pending_payment(
            target_uid, tier, 0, 0.0, "MANUAL", expires_at,
        )
        await sq.confirm_payment(payment_id, f"manual_{int(config.get_kst_now().timestamp())}", "admin")

    await sq.create_subscription(target_uid, tier, expires_at, payment_id)

    tier_name = tier_cfg.get("name", tier)
    exp_kst = expires_at.astimezone(config.KST).strftime("%Y-%m-%d %H:%M")

    await update.message.reply_text(
        f"✅ 구독 수동 승인 완료!\n\n"
        f"유저: {target_uid}\n"
        f"티어: {tier_name}\n"
        f"만료: {exp_kst} (KST)"
    )

    try:
        await context.bot.send_message(
            chat_id=target_uid,
            text=(
                f"✅ <b>구독이 활성화되었습니다!</b>\n\n"
                f"💎 티어: {tier_name}\n"
                f"📅 만료: {exp_kst} (KST)\n\n"
                f"DM에서 '구독정보'로 혜택을 확인하세요!"
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass
