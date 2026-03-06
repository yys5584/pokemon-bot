"""Group reply-based Pokemon trade handler.

Usage: Reply to someone's message with '교환 [포켓몬이름]' to offer a trade.
"""

import asyncio
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from database import queries
from database import battle_queries as bq
from services.evolution_service import try_trade_evolve
from utils.battle_calc import iv_total
from utils.helpers import update_title

logger = logging.getLogger(__name__)


def _iv_grade(total: int) -> str:
    if total >= 168:
        return "S"
    if total >= 140:
        return "A"
    if total >= 93:
        return "B"
    if total >= 47:
        return "C"
    return "D"


def _iv_tag(p: dict) -> str:
    if p.get("iv_hp") is None:
        return ""
    total = iv_total(
        p.get("iv_hp"), p.get("iv_atk"), p.get("iv_def"),
        p.get("iv_spa"), p.get("iv_spdef"), p.get("iv_spd"),
    )
    return f"[{_iv_grade(total)}]"


def _hearts(friendship: int) -> str:
    return "♥" * friendship + "○" * (5 - friendship)


async def group_trade_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '교환 [포켓몬이름]' as a reply in group chat."""
    msg = update.message
    if not msg or not update.effective_user:
        return

    # Must be a reply
    if not msg.reply_to_message or not msg.reply_to_message.from_user:
        await msg.reply_text("교환하려면 상대방의 메시지에 답장으로 사용하세요.\n예시: (답장) 교환 피카츄")
        return

    from_user = update.effective_user
    to_user = msg.reply_to_message.from_user
    chat_id = msg.chat_id

    # Can't trade with self
    if from_user.id == to_user.id:
        await msg.reply_text("자기 자신에게는 교환할 수 없습니다.")
        return

    # Can't trade with bot
    if to_user.is_bot:
        await msg.reply_text("봇에게는 교환할 수 없습니다.")
        return

    # Ensure both users are registered
    await queries.ensure_user(from_user.id, from_user.first_name or "트레이너", from_user.username)
    await queries.ensure_user(to_user.id, to_user.first_name or "트레이너", to_user.username)

    # Parse pokemon name (and optional #N)
    text = (msg.text or "").strip()
    parts = text.split()
    if len(parts) < 2:
        await msg.reply_text("사용법: 교환 [포켓몬이름]\n예시: 교환 피카츄")
        return

    pokemon_name = parts[1]
    select_idx = None

    # Check for #N selector
    if len(parts) >= 3 and parts[2].startswith("#"):
        try:
            select_idx = int(parts[2][1:])
        except ValueError:
            await msg.reply_text("잘못된 번호입니다. 예: 교환 피카츄 #2")
            return

    # Find pokemon
    all_pokemon = await queries.get_user_pokemon_list(from_user.id)
    name_lower = pokemon_name.strip().lower()
    matches = [p for p in all_pokemon if p["name_ko"].lower() == name_lower]
    if not matches:
        matches = [p for p in all_pokemon if name_lower in p["name_ko"].lower()]
    if not matches:
        await msg.reply_text(f"'{pokemon_name}'을(를) 보유하고 있지 않습니다.")
        return

    if len(matches) > 1:
        if select_idx is None:
            # Show numbered list
            lines = [f"⚠️ {pokemon_name} {len(matches)}마리 보유 중", "번호를 지정해주세요:", ""]
            for i, p in enumerate(matches, 1):
                shiny = "✨" if p.get("is_shiny") else ""
                iv = _iv_tag(p)
                lines.append(f"  #{i} {p['name_ko']}{shiny} {iv} {_hearts(p.get('friendship', 0))}")
            lines.append(f"\n예시: 교환 {pokemon_name} #1")
            await msg.reply_text("\n".join(lines))
            return
        if select_idx < 1 or select_idx > len(matches):
            await msg.reply_text(f"1~{len(matches)} 사이의 번호를 입력하세요.")
            return
        pokemon = matches[select_idx - 1]
    else:
        pokemon = matches[0]

    # Check pokemon lock
    locked, reason = await queries.is_pokemon_locked(pokemon["id"])
    if locked:
        await msg.reply_text(reason)
        return

    # Check not on battle team
    if pokemon.get("team_slot") is not None:
        await msg.reply_text("배틀 팀에 등록된 포켓몬은 교환할 수 없습니다.")
        return

    # Check & deduct BP
    cost = config.GROUP_TRADE_BP_COST
    if cost > 0:
        current_bp = await bq.get_bp(from_user.id)
        if current_bp < cost:
            await msg.reply_text(f"BP가 부족합니다! (필요: {cost:,} BP, 보유: {current_bp:,} BP)")
            return
        spent = await bq.spend_bp(from_user.id, cost)
        if not spent:
            await msg.reply_text("BP 차감에 실패했습니다.")
            return

    # Create group trade
    trade_id = await queries.create_group_trade(
        from_user_id=from_user.id,
        to_user_id=to_user.id,
        offer_instance_id=pokemon["id"],
        chat_id=chat_id,
    )

    # Build trade message
    shiny = "✨" if pokemon.get("is_shiny") else ""
    iv = _iv_tag(pokemon)
    hearts = _hearts(pokemon.get("friendship", 0))

    from_name = from_user.first_name or "트레이너"
    to_name = to_user.first_name or "트레이너"

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("수락 ✅", callback_data=f"gtrade_accept_{trade_id}"),
            InlineKeyboardButton("거절 ❌", callback_data=f"gtrade_reject_{trade_id}"),
        ]
    ])

    trade_msg = await msg.reply_text(
        f"🔄 {from_name}님이 {to_name}님에게 교환을 제안합니다!\n\n"
        f"제안: {pokemon['emoji']} {pokemon['name_ko']}{shiny} {iv} {hearts}\n"
        f"{to_name}님만 응답할 수 있습니다. (5분 내)",
        reply_markup=buttons,
        parse_mode="HTML",
    )

    # Save message_id for later editing
    await queries.update_group_trade_message_id(trade_id, trade_msg.message_id)

    # Schedule auto-expire
    context.job_queue.run_once(
        _expire_group_trade,
        when=config.GROUP_TRADE_TIMEOUT,
        data={"trade_id": trade_id, "chat_id": chat_id, "message_id": trade_msg.message_id},
        name=f"gtrade_expire_{trade_id}",
    )


async def _expire_group_trade(context: ContextTypes.DEFAULT_TYPE):
    """Auto-expire a group trade after timeout."""
    job_data = context.job.data
    trade_id = job_data["trade_id"]
    chat_id = job_data["chat_id"]
    message_id = job_data["message_id"]

    trade = await queries.get_group_trade(trade_id)
    if not trade or trade["status"] != "pending":
        return

    await queries.update_trade_status(trade_id, "cancelled")

    # Refund BP
    cost = config.GROUP_TRADE_BP_COST
    if cost > 0:
        await bq.add_bp(trade["from_user_id"], cost)

    try:
        refund_msg = f"\n💰 {cost:,} BP 환불됨" if cost > 0 else ""
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"⏰ 교환 시간 초과\n\n"
                 f"{trade['from_name']}님의 {trade['offer_emoji']} {trade['offer_name']} 교환 제안이 만료되었습니다.{refund_msg}",
        )
    except Exception:
        pass


async def group_trade_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle gtrade_accept_{trade_id} and gtrade_reject_{trade_id}."""
    query = update.callback_query
    if not query:
        return

    user_id = query.from_user.id
    data = query.data or ""

    if data.startswith("gtrade_accept_"):
        try:
            trade_id = int(data.split("_")[2])
        except (ValueError, IndexError):
            await query.answer("오류가 발생했습니다.")
            return

        trade = await queries.get_group_trade(trade_id)
        if not trade:
            await query.answer("교환 요청을 찾을 수 없습니다.")
            return

        # Only target user can accept
        if trade["to_user_id"] != user_id:
            await query.answer("본인에게 온 교환만 수락할 수 있습니다.", show_alert=True)
            return

        if trade["status"] != "pending":
            await query.answer("이미 처리된 교환입니다.")
            try:
                await query.edit_message_text("이미 처리된 교환입니다.")
            except Exception:
                pass
            return

        # Verify pokemon still exists
        offer_instance_id = trade["offer_pokemon_instance_id"]
        offer_pokemon = await queries.get_user_pokemon_by_id(offer_instance_id)
        if not offer_pokemon or offer_pokemon["user_id"] != trade["from_user_id"]:
            await queries.update_trade_status(trade_id, "cancelled")
            await query.answer("이 포켓몬은 이미 교환되었습니다.")
            try:
                await query.edit_message_text("❌ 교환 실패 — 포켓몬이 이미 다른 곳으로 갔습니다.")
            except Exception:
                pass
            return

        # Execute trade: deactivate from sender, give to receiver
        await queries.deactivate_pokemon(offer_instance_id)

        is_shiny = bool(offer_pokemon.get("is_shiny", 0))
        original_ivs = {
            "iv_hp": offer_pokemon.get("iv_hp"),
            "iv_atk": offer_pokemon.get("iv_atk"),
            "iv_def": offer_pokemon.get("iv_def"),
            "iv_spa": offer_pokemon.get("iv_spa"),
            "iv_spdef": offer_pokemon.get("iv_spdef"),
            "iv_spd": offer_pokemon.get("iv_spd"),
        }
        new_instance_id, _ivs = await queries.give_pokemon_to_user(
            user_id, trade["offer_pokemon_id"],
            is_shiny=is_shiny, ivs=original_ivs,
        )

        # Register in pokedex
        await queries.register_pokedex(user_id, trade["offer_pokemon_id"], "trade")

        # Check trade evolution
        evo_msg = await try_trade_evolve(user_id, new_instance_id, trade["offer_pokemon_id"])

        # Update trade status
        await queries.update_trade_status(trade_id, "accepted")

        # Update titles
        await update_title(user_id)
        await update_title(trade["from_user_id"])

        # Mission: trade (both parties)
        asyncio.create_task(_check_trade_mission(context, user_id))
        asyncio.create_task(_check_trade_mission(context, trade["from_user_id"]))

        # Cancel expire job
        jobs = context.job_queue.get_jobs_by_name(f"gtrade_expire_{trade_id}")
        for job in jobs:
            job.schedule_removal()

        shiny_tag = "✨" if is_shiny else ""
        result_text = (
            f"✅ 교환 성사!\n\n"
            f"{trade['from_name']}님의 {trade['offer_emoji']} {trade['offer_name']}{shiny_tag}\n"
            f"→ {trade['to_name']}님에게 전달되었습니다!"
        )
        if evo_msg:
            result_text += evo_msg

        await query.answer("교환 성사!")
        try:
            await query.edit_message_text(result_text)
        except Exception:
            pass

        # DM notifications
        from utils.helpers import icon_emoji
        _ex = icon_emoji("exchange")
        try:
            await context.bot.send_message(
                chat_id=trade["from_user_id"],
                text=f"{_ex} 그룹 교환 완료!\n{trade['offer_emoji']} {trade['offer_name']}{shiny_tag}을(를) {trade['to_name']}님에게 보냈습니다.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        try:
            recv_msg = f"{_ex} 그룹 교환 완료!\n{trade['offer_emoji']} {trade['offer_name']}{shiny_tag}을(를) 받았습니다!"
            if evo_msg:
                recv_msg += evo_msg
            await context.bot.send_message(chat_id=user_id, text=recv_msg, parse_mode="HTML")
        except Exception:
            pass
        return

    if data.startswith("gtrade_reject_"):
        try:
            trade_id = int(data.split("_")[2])
        except (ValueError, IndexError):
            await query.answer("오류가 발생했습니다.")
            return

        trade = await queries.get_group_trade(trade_id)
        if not trade:
            await query.answer("교환 요청을 찾을 수 없습니다.")
            return

        if trade["to_user_id"] != user_id:
            await query.answer("본인에게 온 교환만 거절할 수 있습니다.", show_alert=True)
            return

        if trade["status"] != "pending":
            await query.answer("이미 처리된 교환입니다.")
            return

        await queries.update_trade_status(trade_id, "rejected")

        # Refund BP
        cost = config.GROUP_TRADE_BP_COST
        if cost > 0:
            await bq.add_bp(trade["from_user_id"], cost)

        # Cancel expire job
        jobs = context.job_queue.get_jobs_by_name(f"gtrade_expire_{trade_id}")
        for job in jobs:
            job.schedule_removal()

        shiny_tag = "✨" if trade.get("offer_is_shiny") else ""
        refund_msg = f"\n💰 {cost:,} BP 환불됨" if cost > 0 else ""
        await query.answer("교환을 거절했습니다.")
        try:
            await query.edit_message_text(
                f"❌ 교환 거절\n\n"
                f"{trade['to_name']}님이 {trade['from_name']}님의\n"
                f"{trade['offer_emoji']} {trade['offer_name']}{shiny_tag} 교환을 거절했습니다.{refund_msg}"
            )
        except Exception:
            pass
        return


async def _check_trade_mission(context, user_id: int):
    """Fire-and-forget: check trade mission progress and DM user."""
    try:
        from services.mission_service import check_mission_progress
        msg = await check_mission_progress(user_id, "trade")
        if msg:
            await context.bot.send_message(
                chat_id=user_id, text=msg, parse_mode="HTML",
            )
    except Exception:
        pass
