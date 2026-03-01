"""DM handlers for trading: 교환, 수락, 거절."""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from database import queries
from services.trade_service import create_trade_offer, accept_trade
from utils.parse import parse_args

logger = logging.getLogger(__name__)


async def trade_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '교환 @상대 [내포켓몬이름]' command."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or "트레이너",
        update.effective_user.username,
    )

    args = parse_args(update.message.text or "")
    if len(args) < 2:
        await update.message.reply_text(
            "사용법: 교환 @상대닉네임 [포켓몬이름]\n"
            "예: 교환 @철수 피카츄"
        )
        return

    target_mention = args[0]
    pokemon_name = " ".join(args[1:])

    if target_mention.startswith("@"):
        target_username = target_mention[1:]
    else:
        target_username = target_mention

    from database.connection import get_db
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT user_id FROM users WHERE username = $1",
        target_username,
    )

    if not row:
        await update.message.reply_text(
            f"@{target_username} 트레이너를 찾을 수 없습니다.\n"
            "상대방이 봇에 /start 를 해야 합니다."
        )
        return

    to_user_id = row["user_id"]

    if to_user_id == user_id:
        await update.message.reply_text("자기 자신과는 교환할 수 없습니다!")
        return

    success, message, trade_id = await create_trade_offer(
        user_id, to_user_id, pokemon_name
    )
    await update.message.reply_text(message)

    if success and trade_id:
        try:
            sender = await queries.get_user(user_id)
            sender_name = sender["display_name"] if sender else "트레이너"
            pokemon = await queries.find_user_pokemon_by_name(user_id, pokemon_name)
            pokemon_display = f"{pokemon['emoji']} {pokemon['name_ko']}" if pokemon else pokemon_name

            await context.bot.send_message(
                chat_id=to_user_id,
                text=(
                    f"📨 교환 요청이 도착했습니다!\n\n"
                    f"보낸 사람: {sender_name}\n"
                    f"제안 포켓몬: {pokemon_display}\n\n"
                    f"수락 {trade_id} — 교환 수락\n"
                    f"거절 {trade_id} — 교환 거절"
                ),
            )
        except Exception as e:
            logger.warning(f"Could not DM trade notification to {to_user_id}: {e}")


async def accept_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '수락 [교환번호]' command."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or "트레이너",
        update.effective_user.username,
    )

    args = parse_args(update.message.text or "")

    if not args or not args[0].isdigit():
        pending = await queries.get_pending_trades_for_user(user_id)
        if not pending:
            await update.message.reply_text("대기 중인 교환 요청이 없습니다.")
            return

        lines = ["📨 대기 중인 교환 요청:\n"]
        for t in pending:
            lines.append(
                f"#{t['id']} — {t['from_name']}의 "
                f"{t['offer_emoji']} {t['offer_name']}\n"
                f"  수락 {t['id']} 또는 거절 {t['id']}"
            )
        await update.message.reply_text("\n".join(lines))
        return

    trade_id = int(args[0])
    success, message, trade_info = await accept_trade(user_id, trade_id)
    await update.message.reply_text(message)

    if success and trade_info:
        try:
            receiver = await queries.get_user(user_id)
            receiver_name = receiver["display_name"] if receiver else "트레이너"
            await context.bot.send_message(
                chat_id=trade_info["from_user_id"],
                text=(
                    f"✅ 교환 완료!\n\n"
                    f"{receiver_name}이(가) 교환을 수락했습니다.\n"
                    f"{trade_info['offer_emoji']} {trade_info['offer_name']}이(가) "
                    f"새 트레이너에게 갔습니다."
                ),
            )
        except Exception as e:
            logger.warning(f"Could not DM trade completion to sender: {e}")


async def reject_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '거절 [교환번호]' command."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    args = parse_args(update.message.text or "")

    if not args or not args[0].isdigit():
        pending = await queries.get_pending_trades_for_user(user_id)
        if not pending:
            await update.message.reply_text("대기 중인 교환 요청이 없습니다.")
            return

        lines = ["📨 대기 중인 교환 요청:\n"]
        for t in pending:
            lines.append(
                f"#{t['id']} — {t['from_name']}의 "
                f"{t['offer_emoji']} {t['offer_name']}\n"
                f"  수락 {t['id']} 또는 거절 {t['id']}"
            )
        await update.message.reply_text("\n".join(lines))
        return

    trade_id = int(args[0])

    trade = await queries.get_trade(trade_id)
    if not trade or trade["to_user_id"] != user_id:
        await update.message.reply_text("해당 교환 요청을 찾을 수 없습니다.")
        return

    if trade["status"] != "pending":
        await update.message.reply_text("이미 처리된 교환입니다.")
        return

    await queries.update_trade_status(trade_id, "rejected")

    await update.message.reply_text(
        f"❌ 교환을 거절했습니다.\n"
        f"({trade['offer_emoji']} {trade['offer_name']})"
    )

    try:
        receiver = await queries.get_user(user_id)
        receiver_name = receiver["display_name"] if receiver else "트레이너"
        await context.bot.send_message(
            chat_id=trade["from_user_id"],
            text=(
                f"❌ 교환 거절\n\n"
                f"{receiver_name}이(가) 교환을 거절했습니다.\n"
                f"{trade['offer_emoji']} {trade['offer_name']}이(가) 돌아왔습니다."
            ),
        )
    except Exception as e:
        logger.warning(f"Could not DM trade rejection to sender: {e}")
