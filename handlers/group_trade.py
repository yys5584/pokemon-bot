"""Group reply-based Pokemon trade handler.

Usage: Reply to someone's message with '교환 [포켓몬이름]' to offer a trade.
"""

import asyncio
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from database import queries, market_queries
from database import trade_queries as tq
from database import battle_queries as bq
from services.evolution_service import build_trade_evo_info
from utils.helpers import update_title, iv_grade_tag as _iv_tag, type_badge

logger = logging.getLogger(__name__)


def _hearts(friendship: int, pokemon: dict | None = None) -> str:
    max_f = config.get_max_friendship(pokemon) if pokemon else config.MAX_FRIENDSHIP
    return "♥" * friendship + "○" * (max_f - friendship)


async def group_trade_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '교환 [포켓몬이름]' as a reply in group chat."""
    msg = update.message
    if not msg or not update.effective_user:
        return

    # Must be a reply — 답장이 아니면 무응답 (일반 대화 방해 방지)
    if not msg.reply_to_message or not msg.reply_to_message.from_user:
        return

    from_user = update.effective_user
    to_user = msg.reply_to_message.from_user
    chat_id = msg.chat_id

    # 밴 체크
    if await queries.is_user_banned(from_user.id):
        return

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
        return

    pokemon_name = parts[1]

    # 포켓몬 이름이 아닌 일반 문장 필터링 (6글자 초과 또는 특수문자 포함)
    import re
    if len(pokemon_name) > 6 or re.search(r"[.!?~…,;:ㅋㅎㅠㅜㄷㄱ]", pokemon_name):
        return

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
        return

    if len(matches) > 1:
        if select_idx is None:
            # 버튼으로 선택
            if not msg.reply_to_message or not msg.reply_to_message.from_user:
                await msg.reply_text("교환하려면 상대방의 메시지에 답장으로 사용하세요.")
                return
            to_uid = msg.reply_to_message.from_user.id
            lines = [f"⚠️ {pokemon_name} {len(matches)}마리 보유 중", "교환할 포켓몬을 선택하세요:"]
            buttons = []
            for i, p in enumerate(matches[:10], 1):  # 최대 10개
                shiny = "✨" if p.get("is_shiny") else ""
                iv = _iv_tag(p)
                lines.append(f"  #{i} {p['name_ko']}{shiny} {iv} {_hearts(p.get('friendship', 0), p)}")
                buttons.append([InlineKeyboardButton(
                    f"#{i} {p['name_ko']}{shiny} {iv}",
                    callback_data=f"gtrade_sel_{from_user.id}_{to_uid}_{p['id']}",
                )])
            buttons.append([InlineKeyboardButton("취소", callback_data=f"gtrade_selcancel_{from_user.id}")])
            await msg.reply_text(
                "\n".join(lines),
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            return
        if select_idx < 1 or select_idx > len(matches):
            await msg.reply_text(f"1~{len(matches)} 사이의 번호를 입력하세요.")
            return
        pokemon = matches[select_idx - 1]
    else:
        pokemon = matches[0]

    # Check pokemon lock
    locked, reason = await market_queries.is_pokemon_locked(pokemon["id"])
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
    trade_id = await tq.create_group_trade(
        from_user_id=from_user.id,
        to_user_id=to_user.id,
        offer_instance_id=pokemon["id"],
        chat_id=chat_id,
    )

    # Build trade message
    shiny = "✨" if pokemon.get("is_shiny") else ""
    iv = _iv_tag(pokemon)
    hearts = _hearts(pokemon.get("friendship", 0), pokemon)

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
        f"제안: {type_badge(pokemon['pokemon_id'])} {pokemon['name_ko']}{shiny} {iv} {hearts}\n"
        f"{to_name}님만 응답할 수 있습니다. (5분 내)",
        reply_markup=buttons,
        parse_mode="HTML",
    )

    # Save message_id for later editing
    await tq.update_group_trade_message_id(trade_id, trade_msg.message_id)

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

    trade = await tq.get_group_trade(trade_id)
    if not trade or trade["status"] != "pending":
        return

    await tq.update_trade_status(trade_id, "cancelled")

    # Refund BP
    cost = config.GROUP_TRADE_BP_COST
    if cost > 0:
        await bq.add_bp(trade["from_user_id"], cost, "trade_refund")

    try:
        refund_msg = f"\n💰 {cost:,} BP 환불됨" if cost > 0 else ""
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"⏰ 교환 시간 초과\n\n"
                 f"{trade['from_name']}님의 {type_badge(trade['offer_pokemon_id'])} {trade['offer_name']} 교환 제안이 만료되었습니다.{refund_msg}",
            parse_mode="HTML",
        )
    except Exception:
        pass


async def group_trade_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle gtrade_* callbacks."""
    query = update.callback_query
    if not query:
        return

    user_id = query.from_user.id
    data = query.data or ""

    # ── 중복 포켓몬 선택 버튼 ──
    if data.startswith("gtrade_sel_"):
        # gtrade_sel_{from_uid}_{to_uid}_{instance_id}
        parts = data.split("_")
        try:
            from_uid = int(parts[2])
            to_uid = int(parts[3])
            instance_id = int(parts[4])
        except (ValueError, IndexError):
            await query.answer("오류가 발생했습니다.")
            return
        if user_id != from_uid:
            await query.answer("본인만 선택할 수 있습니다!", show_alert=True)
            return
        await query.answer()
        # 포켓몬 조회 + 잠금 체크
        pokemon = await queries.get_user_pokemon_by_id(instance_id)
        if not pokemon or pokemon.get("user_id") != from_uid:
            try:
                await query.edit_message_text("포켓몬을 찾을 수 없습니다.")
            except Exception:
                pass
            return
        locked, reason = await market_queries.is_pokemon_locked(instance_id)
        if locked:
            try:
                await query.edit_message_text(reason)
            except Exception:
                pass
            return
        if pokemon.get("team_slot") is not None:
            try:
                await query.edit_message_text("배틀 팀에 등록된 포켓몬은 교환할 수 없습니다.")
            except Exception:
                pass
            return
        # BP 차감
        cost = config.GROUP_TRADE_BP_COST
        if cost > 0:
            current_bp = await bq.get_bp(from_uid)
            if current_bp < cost:
                try:
                    await query.edit_message_text(f"BP가 부족합니다! (필요: {cost:,} BP, 보유: {current_bp:,} BP)")
                except Exception:
                    pass
                return
            spent = await bq.spend_bp(from_uid, cost)
            if not spent:
                try:
                    await query.edit_message_text("BP 차감에 실패했습니다.")
                except Exception:
                    pass
                return
        # 교환 생성
        chat_id = query.message.chat_id
        trade_id = await tq.create_group_trade(
            from_user_id=from_uid,
            to_user_id=to_uid,
            offer_instance_id=instance_id,
            chat_id=chat_id,
        )
        shiny = "✨" if pokemon.get("is_shiny") else ""
        iv = _iv_tag(pokemon)
        hearts = _hearts(pokemon.get("friendship", 0), pokemon)
        from_user = query.from_user
        try:
            to_chat_member = await context.bot.get_chat_member(chat_id, to_uid)
            to_name = to_chat_member.user.first_name or "트레이너"
        except Exception:
            to_name = "트레이너"
        from_name = from_user.first_name or "트레이너"
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("수락 ✅", callback_data=f"gtrade_accept_{trade_id}"),
                InlineKeyboardButton("거절 ❌", callback_data=f"gtrade_reject_{trade_id}"),
            ]
        ])
        try:
            await query.edit_message_text(
                f"🔄 {from_name}님이 {to_name}님에게 교환을 제안합니다!\n\n"
                f"제안: {type_badge(pokemon['pokemon_id'])} {pokemon['name_ko']}{shiny} {iv} {hearts}\n"
                f"{to_name}님만 응답할 수 있습니다. (5분 내)",
                reply_markup=buttons,
                parse_mode="HTML",
            )
        except Exception:
            pass
        # 메시지 ID 저장 + 자동 만료
        await tq.update_group_trade_message_id(trade_id, query.message.message_id)
        context.job_queue.run_once(
            _expire_group_trade,
            when=config.GROUP_TRADE_TIMEOUT,
            data={"trade_id": trade_id, "chat_id": chat_id, "message_id": query.message.message_id},
            name=f"gtrade_expire_{trade_id}",
        )
        return

    if data.startswith("gtrade_selcancel_"):
        parts = data.split("_")
        try:
            from_uid = int(parts[2])
        except (ValueError, IndexError):
            await query.answer()
            return
        if user_id != from_uid:
            await query.answer("본인만 취소할 수 있습니다!", show_alert=True)
            return
        await query.answer("취소되었습니다.")
        try:
            await query.edit_message_text("교환이 취소되었습니다.")
        except Exception:
            pass
        return

    if data.startswith("gtrade_accept_"):
        try:
            trade_id = int(data.split("_")[2])
        except (ValueError, IndexError):
            await query.answer("오류가 발생했습니다.")
            return

        trade = await tq.get_group_trade(trade_id)
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
            await tq.update_trade_status(trade_id, "cancelled")
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
            personality=offer_pokemon.get("personality"),
        )

        # Register in pokedex
        await queries.register_pokedex(user_id, trade["offer_pokemon_id"], "trade")

        # Check trade evolution eligibility (don't auto-evolve)
        pending_evo = build_trade_evo_info(trade["offer_pokemon_id"], new_instance_id)

        # Update trade status
        await tq.update_trade_status(trade_id, "accepted")

        # Update titles
        await update_title(user_id)
        await update_title(trade["from_user_id"])

        # Mission: trade (both parties)
        asyncio.create_task(_check_trade_mission(context, user_id))
        asyncio.create_task(_check_trade_mission(context, trade["from_user_id"]))

        # CXP: +1 for trade (group trade)
        trade_chat_id = query.message.chat_id
        async def _trade_cxp():
            try:
                new_level = await queries.add_chat_cxp(trade_chat_id, config.CXP_PER_TRADE, "trade", user_id)
                if new_level:
                    info = config.get_chat_level_info(
                        (await queries.get_chat_level(trade_chat_id))["cxp"]
                    )
                    bonus_txt = f"+{info['spawn_bonus']} 스폰" if info["spawn_bonus"] else ""
                    shiny_txt = f"+{info['shiny_boost_pct']:.1f}% 이로치" if info["shiny_boost_pct"] else ""
                    parts = [p for p in [bonus_txt, shiny_txt] if p]
                    perks = f" ({', '.join(parts)})" if parts else ""
                    await context.bot.send_message(
                        chat_id=trade_chat_id,
                        text=f"🎊 채팅방 레벨 UP! Lv.{new_level}{perks}",
                        parse_mode="HTML",
                    )
            except Exception:
                pass
        asyncio.create_task(_trade_cxp())

        # Cancel expire job
        jobs = context.job_queue.get_jobs_by_name(f"gtrade_expire_{trade_id}")
        for job in jobs:
            job.schedule_removal()

        shiny_tag = "✨" if is_shiny else ""
        result_text = (
            f"✅ 교환 성사!\n\n"
            f"{trade['from_name']}님의 {type_badge(trade['offer_pokemon_id'])} {trade['offer_name']}{shiny_tag}\n"
            f"→ {trade['to_name']}님에게 전달되었습니다!"
        )

        await query.answer("교환 성사!")
        try:
            await query.edit_message_text(result_text, parse_mode="HTML")
        except Exception:
            pass

        # DM notifications
        from utils.helpers import icon_emoji
        _ex = icon_emoji("exchange")
        try:
            await context.bot.send_message(
                chat_id=trade["from_user_id"],
                text=f"{_ex} 그룹 교환 완료!\n{type_badge(trade['offer_pokemon_id'])} {trade['offer_name']}{shiny_tag}을(를) {trade['to_name']}님에게 보냈습니다.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        try:
            recv_msg = f"{_ex} 그룹 교환 완료!\n{type_badge(trade['offer_pokemon_id'])} {trade['offer_name']}{shiny_tag}을(를) 받았습니다!"
            await context.bot.send_message(chat_id=user_id, text=recv_msg, parse_mode="HTML")
        except Exception:
            pass

        # Send trade evolution choice DM to receiver
        if pending_evo:
            try:
                source = await queries.get_pokemon(pending_evo["source_id"])
                target = await queries.get_pokemon(pending_evo["target_id"])
                if source and target:
                    evo_text = (
                        f"✨ 교환 진화 가능!\n\n"
                        f"{type_badge(source['id'])} {source['name_ko']}을(를)\n"
                        f"{type_badge(target['id'])} {target['name_ko']}(으)로 진화시킬 수 있습니다!\n\n"
                        f"진화하시겠습니까?"
                    )
                    evo_buttons = [[
                        InlineKeyboardButton("✨ 진화시키기", callback_data=f"tevo_yes_{pending_evo['instance_id']}"),
                        InlineKeyboardButton("❌ 그대로 유지", callback_data=f"tevo_no_{pending_evo['instance_id']}"),
                    ]]
                    await context.bot.send_message(
                        chat_id=user_id, text=evo_text,
                        reply_markup=InlineKeyboardMarkup(evo_buttons),
                    )
            except Exception:
                pass
        return

    if data.startswith("gtrade_reject_"):
        try:
            trade_id = int(data.split("_")[2])
        except (ValueError, IndexError):
            await query.answer("오류가 발생했습니다.")
            return

        trade = await tq.get_group_trade(trade_id)
        if not trade:
            await query.answer("교환 요청을 찾을 수 없습니다.")
            return

        if trade["to_user_id"] != user_id:
            await query.answer("본인에게 온 교환만 거절할 수 있습니다.", show_alert=True)
            return

        if trade["status"] != "pending":
            await query.answer("이미 처리된 교환입니다.")
            return

        await tq.update_trade_status(trade_id, "rejected")

        # Refund BP
        cost = config.GROUP_TRADE_BP_COST
        if cost > 0:
            await bq.add_bp(trade["from_user_id"], cost, "trade_refund")

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
                f"{type_badge(trade['offer_pokemon_id'])} {trade['offer_name']}{shiny_tag} 교환을 거절했습니다.{refund_msg}",
                parse_mode="HTML",
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
