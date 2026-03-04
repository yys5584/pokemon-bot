"""DM handlers for trading: 교환, 수락, 거절."""

import logging
from telegram import Update
from telegram.ext import ContextTypes

import config
from database import queries
from services.trade_service import create_trade_offer, accept_trade
from utils.parse import parse_args
from utils.helpers import type_badge, hearts_display
from utils.battle_calc import iv_total

logger = logging.getLogger(__name__)


async def trade_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '교환 @상대 [내포켓몬이름] (#번호)' command."""
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
            "예: 교환 @철수 피카츄\n\n"
            "중복 포켓몬이 있을 경우:\n"
            "교환 @철수 피카츄 #2 (2번째 선택)"
        )
        return

    target_mention = args[0]
    # Check if last arg is #N (index selector for duplicates)
    select_index = None
    remaining_args = args[1:]
    if remaining_args and remaining_args[-1].startswith("#") and remaining_args[-1][1:].isdigit():
        select_index = int(remaining_args[-1][1:])
        remaining_args = remaining_args[:-1]

    if not remaining_args:
        await update.message.reply_text(
            "포켓몬 이름을 입력해주세요.\n"
            "예: 교환 @철수 피카츄"
        )
        return

    pokemon_name = " ".join(remaining_args)

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

    # Check for duplicate Pokemon
    all_matches = await queries.find_all_user_pokemon_by_name(user_id, pokemon_name)

    if not all_matches:
        await update.message.reply_text(f"'{pokemon_name}'을(를) 보유하고 있지 않습니다.")
        return

    instance_id = None

    if len(all_matches) > 1:
        # Multiple duplicates exist
        if select_index is None:
            # Show selection list
            lines = [f"⚠️ {pokemon_name}을(를) {len(all_matches)}마리 보유 중입니다.\n번호를 지정해주세요:\n"]
            for i, p in enumerate(all_matches, 1):
                shiny = " ✨이로치" if p.get("is_shiny") else ""
                tb = type_badge(p["pokemon_id"])
                iv_tag = ""
                if p.get("iv_hp") is not None:
                    total = iv_total(p.get("iv_hp"), p.get("iv_atk"), p.get("iv_def"),
                                     p.get("iv_spa"), p.get("iv_spdef"), p.get("iv_spd"))
                    grade, _ = config.get_iv_grade(total)
                    iv_tag = f" [{grade}]"
                hearts = hearts_display(p["friendship"], config.get_max_friendship(p))
                lines.append(f"  #{i} — {tb} {p['name_ko']}{shiny}{iv_tag}  {hearts}")
            lines.append(f"\n사용법: 교환 @{target_username} {pokemon_name} #번호")
            await update.message.reply_text("\n".join(lines), parse_mode="HTML")
            return

        if select_index < 1 or select_index > len(all_matches):
            await update.message.reply_text(
                f"잘못된 번호입니다. 1~{len(all_matches)} 사이의 번호를 입력해주세요."
            )
            return

        instance_id = all_matches[select_index - 1]["id"]
    else:
        # Single match — use it directly
        instance_id = all_matches[0]["id"]

    success, message, trade_id = await create_trade_offer(
        user_id, to_user_id, pokemon_name, instance_id=instance_id
    )
    await update.message.reply_text(message)

    if success and trade_id:
        try:
            sender = await queries.get_user(user_id)
            sender_name = sender["display_name"] if sender else "트레이너"
            selected_pokemon = None
            for p in all_matches:
                if p["id"] == instance_id:
                    selected_pokemon = p
                    break
            if selected_pokemon:
                shiny_tag = " ★이로치" if selected_pokemon.get("is_shiny") else ""
                tb = type_badge(selected_pokemon["pokemon_id"])
                pokemon_display = f"{tb} {selected_pokemon['name_ko']}{shiny_tag}"
            else:
                pokemon_display = pokemon_name

            await context.bot.send_message(
                chat_id=to_user_id,
                text=(
                    f"📨 교환 요청이 도착했습니다!\n\n"
                    f"보낸 사람: {sender_name}\n"
                    f"제안 포켓몬: {pokemon_display}\n\n"
                    f"수락 {trade_id} — 교환 수락\n"
                    f"거절 {trade_id} — 교환 거절"
                ),
                parse_mode="HTML",
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
            shiny_tag = " ★이로치" if t.get("offer_is_shiny") else ""
            tb = type_badge(t["offer_pokemon_id"]) if t.get("offer_pokemon_id") else ""
            lines.append(
                f"#{t['id']} — {t['from_name']}의 "
                f"{tb} {t['offer_name']}{shiny_tag}\n"
                f"  수락 {t['id']} 또는 거절 {t['id']}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        return

    trade_id = int(args[0])
    success, message, trade_info = await accept_trade(user_id, trade_id)
    await update.message.reply_text(message)

    if success and trade_info:
        try:
            receiver = await queries.get_user(user_id)
            receiver_name = receiver["display_name"] if receiver else "트레이너"
            tb = type_badge(trade_info["offer_pokemon_id"]) if trade_info.get("offer_pokemon_id") else ""
            await context.bot.send_message(
                chat_id=trade_info["from_user_id"],
                text=(
                    f"✅ 교환 완료!\n\n"
                    f"{receiver_name}이(가) 교환을 수락했습니다.\n"
                    f"{tb} {trade_info['offer_name']} "
                    f"새 트레이너에게 갔습니다."
                ),
                parse_mode="HTML",
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
            shiny_tag = " ★이로치" if t.get("offer_is_shiny") else ""
            tb = type_badge(t["offer_pokemon_id"]) if t.get("offer_pokemon_id") else ""
            lines.append(
                f"#{t['id']} — {t['from_name']}의 "
                f"{tb} {t['offer_name']}{shiny_tag}\n"
                f"  수락 {t['id']} 또는 거절 {t['id']}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
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

    tb = type_badge(trade["offer_pokemon_id"]) if trade.get("offer_pokemon_id") else ""
    await update.message.reply_text(
        f"❌ 교환을 거절했습니다.\n"
        f"({tb} {trade['offer_name']})",
        parse_mode="HTML",
    )

    try:
        receiver = await queries.get_user(user_id)
        receiver_name = receiver["display_name"] if receiver else "트레이너"
        await context.bot.send_message(
            chat_id=trade["from_user_id"],
            text=(
                f"❌ 교환 거절\n\n"
                f"{receiver_name}이(가) 교환을 거절했습니다.\n"
                f"{tb} {trade['offer_name']} 돌아왔습니다."
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Could not DM trade rejection to sender: {e}")
