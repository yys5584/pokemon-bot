"""Battle system handlers: partner, challenge, accept/decline, result, rankings."""

import asyncio
import logging
import random
import re
import time
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import config

from database import queries, spawn_queries, title_queries
from database import battle_queries as bq
from handlers._common import _is_duplicate_callback, _is_duplicate_message
from utils.battle_calc import calc_battle_stats, format_stats_line, calc_power, format_power, EVO_STAGE_MAP, iv_total, get_normalized_base_stats
from utils.helpers import escape_html, truncate_name, rarity_badge, type_badge, icon_emoji, ball_emoji, iv_grade_tag
from utils.i18n import t, get_user_lang, poke_name

logger = logging.getLogger(__name__)

PARTNER_PAGE_SIZE = 10


# ============================================================
# Partner Pokemon (/파트너)
# ============================================================

def _build_partner_list(user_id: int, pokemon_list: list, page: int,
                        current_partner_id: int | None = None,
                        lang: str = "ko") -> tuple[str, InlineKeyboardMarkup]:
    """Build partner selection list with inline buttons."""
    total = len(pokemon_list)
    total_pages = max(1, (total + PARTNER_PAGE_SIZE - 1) // PARTNER_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    start = page * PARTNER_PAGE_SIZE
    end = min(start + PARTNER_PAGE_SIZE, total)
    page_pokemon = pokemon_list[start:end]

    lines = [f"🤝 {t(lang, 'partner.title')}  [{page + 1}/{total_pages}]\n"]
    for i, p in enumerate(page_pokemon):
        num = start + i + 1
        mark = f" {icon_emoji('check')}" if p["id"] == current_partner_id else ""
        tb = type_badge(p["pokemon_id"], p.get("pokemon_type"))
        lines.append(f"{num}. {tb} {poke_name(p, lang)}{mark}")
    lines.append(f"\n{t(lang, 'partner.select')}")

    # Buttons: 2 per row
    buttons = []
    row = []
    for i, p in enumerate(page_pokemon):
        idx = start + i
        row.append(InlineKeyboardButton(
            f"{idx + 1}. {poke_name(p, lang)}",
            callback_data=f"partner_s_{user_id}_{idx}_{page}",
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Pagination
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(t(lang, "common.prev"), callback_data=f"partner_p_{user_id}_{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(t(lang, "common.next"), callback_data=f"partner_p_{user_id}_{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def partner_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 파트너 command (DM). Show current or set partner."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or t(lang, "common.trainer"),
        update.effective_user.username,
    )

    text = (update.message.text or "").strip()
    # Strip emoji prefix from keyboard button "🤝 파트너"
    text = re.sub(r"^🤝\s*", "", text).strip()
    parts = text.split()

    # "파트너" alone → show current partner + 변경 버튼
    if len(parts) == 1:
        partner = await bq.get_partner(user_id)
        if not partner:
            # 파트너 없음 → 바로 선택 리스트
            pokemon_list = await queries.get_user_pokemon_list(user_id)
            if not pokemon_list:
                await update.message.reply_text(t(lang, "my_pokemon.no_pokemon"))
                return
            text_msg, markup = _build_partner_list(user_id, pokemon_list, 0, lang=lang)
            await update.message.reply_text(text_msg, reply_markup=markup, parse_mode="HTML")
            return

        _p_base = get_normalized_base_stats(partner["pokemon_id"])
        evo_stage = 3 if _p_base else EVO_STAGE_MAP.get(partner["pokemon_id"], 3)
        stats = calc_battle_stats(
            partner["rarity"], partner["stat_type"], partner["friendship"],
            evo_stage=evo_stage,
            iv_hp=partner.get("iv_hp"), iv_atk=partner.get("iv_atk"),
            iv_def=partner.get("iv_def"), iv_spa=partner.get("iv_spa"),
            iv_spdef=partner.get("iv_spdef"), iv_spd=partner.get("iv_spd"),
            **(_p_base or {}),
        )
        base = calc_battle_stats(
            partner["rarity"], partner["stat_type"], partner["friendship"],
            evo_stage=evo_stage, **(_p_base or {}),
        )
        tb = type_badge(partner["pokemon_id"], partner["pokemon_type"])
        from models.pokemon_base_stats import POKEMON_BASE_STATS
        pbs = POKEMON_BASE_STATS.get(partner["pokemon_id"])
        if pbs:
            type_name = "/".join(t(lang, f"type.{tp}") for tp in pbs[-1])
        else:
            type_name = t(lang, f"type.{partner['pokemon_type']}")
        buttons = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"🔄 {t(lang, 'common.change')}", callback_data=f"partner_p_{user_id}_0"),
        ]])
        await update.message.reply_text(
            f"{icon_emoji('pokemon-love')} {t(lang, 'partner.my_partner')}\n\n"
            f"{tb} {poke_name(partner, lang)}  {type_name}  {icon_emoji('bolt')}{format_power(stats, base)}\n"
            f"{icon_emoji('stationery')} {format_stats_line(stats, base)}\n\n"
            f"💡 {t(lang, 'partner.bonus_info', pct=5)}",
            reply_markup=buttons,
            parse_mode="HTML",
        )
        return

    # "파트너 3" (번호) or "파트너 삐삐" (이름) → 직접 지정도 유지
    arg = parts[1] if len(parts) >= 2 else ""
    search_name = " ".join(parts[1:]).strip()

    pokemon_list = await queries.get_user_pokemon_list(user_id)
    if not pokemon_list:
        await update.message.reply_text(t(lang, "my_pokemon.no_pokemon"))
        return

    chosen = None

    # 1) 번호로 시도
    try:
        num = int(arg)
        if 1 <= num <= len(pokemon_list):
            chosen = pokemon_list[num - 1]
    except ValueError:
        pass

    # 2) 이름으로 검색 (한글/영문)
    if chosen is None and search_name:
        name_lower = search_name.lower()
        matches = [
            p for p in pokemon_list
            if name_lower in p["name_ko"].lower() or name_lower in p["name_en"].lower()
        ]
        if len(matches) == 1:
            chosen = matches[0]
        elif len(matches) > 1:
            lines = [t(lang, "partner.search_multiple", name=search_name, count=len(matches)) + "\n"]
            for p in matches:
                idx = pokemon_list.index(p) + 1
                lines.append(f"  {idx}. {poke_name(p, lang)}")
            lines.append(f"\n{t(lang, 'partner.specify_number')}")
            await update.message.reply_text("\n".join(lines))
            return
        else:
            await update.message.reply_text(
                t(lang, "my_pokemon.not_found", name=search_name)
            )
            return

    if chosen is None:
        # 인식 불가 → 선택 리스트 보여주기
        partner = await bq.get_partner(user_id)
        partner_id = partner["instance_id"] if partner else None
        text_msg, markup = _build_partner_list(user_id, pokemon_list, 0, partner_id, lang=lang)
        await update.message.reply_text(text_msg, reply_markup=markup)
        return

    await _set_partner_and_reply(update.message, user_id, chosen)


async def _set_partner_and_reply(message, user_id: int, chosen: dict):
    """Set partner and send confirmation."""
    lang = await get_user_lang(user_id)
    await bq.set_partner(user_id, chosen["id"])

    tb = type_badge(chosen["pokemon_id"], chosen.get("pokemon_type"))
    await message.reply_text(
        f"🤝 {tb} {poke_name(chosen, lang)} {t(lang, 'partner.set_success_short')}!\n"
        f"{t(lang, 'partner.bonus_info', pct=5)}",
        parse_mode="HTML",
    )

    # Unlock partner title
    if not await title_queries.has_title(user_id, "partner_set"):
        await title_queries.unlock_title(user_id, "partner_set")


async def partner_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle partner selection inline button callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    if not data.startswith("partner_"):
        return

    await query.answer()

    parts = data.split("_")
    # partner_p_{user_id}_{page}  — page navigation
    # partner_s_{user_id}_{idx}_{page}  — select pokemon
    action = parts[1]
    owner_id = int(parts[2])
    lang = await get_user_lang(query.from_user.id)

    if query.from_user.id != owner_id:
        await query.answer(t(lang, "error.not_your_button"), show_alert=True)
        return

    pokemon_list = await queries.get_user_pokemon_list(owner_id)
    if not pokemon_list:
        try:
            await query.edit_message_text(t(lang, "my_pokemon.no_pokemon"))
        except Exception:
            pass
        return

    if action == "p":
        # Page navigation
        page = int(parts[3])
        partner = await bq.get_partner(owner_id)
        partner_id = partner["instance_id"] if partner else None
        text_msg, markup = _build_partner_list(owner_id, pokemon_list, page, partner_id, lang=lang)
        try:
            await query.edit_message_text(text_msg, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass

    elif action == "s":
        # Select partner
        idx = int(parts[3])
        if idx < 0 or idx >= len(pokemon_list):
            await query.answer(t(lang, "dungeon.invalid_choice"), show_alert=True)
            return

        chosen = pokemon_list[idx]
        await bq.set_partner(owner_id, chosen["id"])

        # Unlock partner title
        if not await title_queries.has_title(owner_id, "partner_set"):
            await title_queries.unlock_title(owner_id, "partner_set")

        tb = type_badge(chosen["pokemon_id"], chosen.get("pokemon_type"))
        _c_base = get_normalized_base_stats(chosen["pokemon_id"])
        evo_stage = 3 if _c_base else EVO_STAGE_MAP.get(chosen["pokemon_id"], 3)
        stats = calc_battle_stats(
            chosen["rarity"], chosen.get("stat_type", "balanced"), chosen["friendship"],
            evo_stage=evo_stage,
            iv_hp=chosen.get("iv_hp"), iv_atk=chosen.get("iv_atk"),
            iv_def=chosen.get("iv_def"), iv_spa=chosen.get("iv_spa"),
            iv_spdef=chosen.get("iv_spdef"), iv_spd=chosen.get("iv_spd"),
            **(_c_base or {}),
        )
        base = calc_battle_stats(
            chosen["rarity"], chosen.get("stat_type", "balanced"), chosen["friendship"],
            evo_stage=evo_stage, **(_c_base or {}),
        )
        try:
            await query.edit_message_text(
                f"{icon_emoji('pokemon-love')} {t(lang, 'partner.set_complete')}!\n\n"
                f"{tb} {poke_name(chosen, lang)}  {icon_emoji('bolt')}{format_power(stats, base)}\n"
                f"{icon_emoji('stationery')} {format_stats_line(stats, base)}\n\n"
                f"💡 {t(lang, 'partner.bonus_info', pct=5)}",
                parse_mode="HTML",
            )
        except Exception:
            pass


# ============================================================
# Battle Challenge (Group: 배틀 @유저)
# ============================================================

async def battle_challenge_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 배틀 command (group). Challenge another user."""
    if not update.effective_user or not update.message:
        return
    if _is_duplicate_message(update, "배틀", cooldown=5.0):
        return

    chat_id = update.effective_chat.id

    from services.tournament_service import is_tournament_active
    if is_tournament_active(chat_id):
        return
    challenger_id = update.effective_user.id
    lang = await get_user_lang(challenger_id)
    challenger_name = update.effective_user.first_name or t(lang, "common.trainer")

    # Must reply to someone or mention
    reply = update.message.reply_to_message
    if not reply or not reply.from_user:
        await update.message.reply_text(
            f"{icon_emoji('battle')} {t(lang, 'battle.challenge_reply_hint')}", parse_mode="HTML"
        )
        return

    defender_id = reply.from_user.id
    defender_name = reply.from_user.first_name or t(lang, "common.trainer")

    # Can't battle yourself
    if challenger_id == defender_id:
        await update.message.reply_text(t(lang, "battle.cannot_self"))
        return

    # Can't battle bots
    if reply.from_user.is_bot:
        await update.message.reply_text(t(lang, "battle.cannot_bot"))
        return

    # Ensure both users exist + check cooldowns (병렬)
    _, _, last_vs, last_any = await asyncio.gather(
        queries.ensure_user(challenger_id, challenger_name, update.effective_user.username),
        queries.ensure_user(defender_id, defender_name, reply.from_user.username),
        bq.get_last_battle_time(challenger_id, defender_id),
        bq.get_last_battle_time_any(challenger_id),
    )

    # Same opponent cooldown
    if last_vs:
        last_time = datetime.fromisoformat(last_vs)
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=timezone.utc)
        cooldown = timedelta(seconds=config.BATTLE_COOLDOWN_SAME)
        if datetime.now(timezone.utc) - last_time < cooldown:
            remaining = cooldown - (datetime.now(timezone.utc) - last_time)
            mins = int(remaining.total_seconds() // 60)
            await update.message.reply_text(
                t(lang, "battle.cooldown_same_msg", minutes=config.BATTLE_COOLDOWN_SAME // 60, remaining=mins)
            )
            return

    # Global cooldown
    if last_any:
        last_time = datetime.fromisoformat(last_any)
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=timezone.utc)
        cooldown = timedelta(seconds=config.BATTLE_COOLDOWN_GLOBAL)
        if datetime.now(timezone.utc) - last_time < cooldown:
            remaining = cooldown - (datetime.now(timezone.utc) - last_time)
            secs = int(remaining.total_seconds())
            await update.message.reply_text(
                t(lang, "battle.cooldown_global_msg", seconds=secs)
            )
            return

    # Check challenger has a team
    c_team = await bq.get_battle_team(challenger_id)
    if not c_team:
        await update.message.reply_text(
            f"{icon_emoji('battle')} {t(lang, 'battle.no_team_hint')}",
            parse_mode="HTML",
        )
        return
    if len(c_team) < config.RANKED_TEAM_SIZE:
        await update.message.reply_text(
            f"❌ {t(lang, 'battle.team_incomplete', count=len(c_team), required=config.RANKED_TEAM_SIZE)}",
            parse_mode="HTML",
        )
        return
    from services.ranked_service import get_current_cost_limit
    _cost_limit = await get_current_cost_limit()
    c_cost = sum(config.RANKED_COST.get(p.get("rarity", ""), 0) for p in c_team)
    if c_cost > _cost_limit:
        await update.message.reply_text(
            f"❌ {t(lang, 'battle.team_cost_over', cost=c_cost, limit=_cost_limit)}",
            parse_mode="HTML",
        )
        return

    # Check for existing pending challenge
    existing = await bq.get_pending_challenge(challenger_id, defender_id)
    if existing:
        await update.message.reply_text(t(lang, "battle.already_pending"))
        return

    # Create challenge
    expires = (datetime.now(timezone.utc) + timedelta(seconds=config.BATTLE_CHALLENGE_TIMEOUT))

    challenge_id = await bq.create_challenge(
        challenger_id, defender_id, chat_id, expires
    )

    # Send challenge message with inline buttons
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                t(lang, "battle.accept_btn"),
                callback_data=f"battle_accept_{challenge_id}_{defender_id}",
            ),
            InlineKeyboardButton(
                t(lang, "battle.decline_btn"),
                callback_data=f"battle_decline_{challenge_id}_{defender_id}",
            ),
        ]
    ])

    challenge_msg = await update.message.reply_text(
        f"{icon_emoji('battle')} {t(lang, 'battle.challenge_msg', challenger=challenger_name, defender=defender_name, timeout=config.BATTLE_CHALLENGE_TIMEOUT)}",
        reply_markup=buttons,
        parse_mode="HTML",
    )

    # Timeout auto-expiry
    async def _battle_timeout(ctx):
        try:
            challenge = await bq.get_challenge_by_id(challenge_id)
            if challenge and challenge["status"] == "pending":
                await bq.update_challenge_status(challenge_id, "expired")
                await ctx.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=challenge_msg.message_id,
                    text=f"⏰ {t(lang, 'battle.challenge_timeout_msg', name=challenger_name)}",
                )
        except Exception:
            pass

    context.job_queue.run_once(
        _battle_timeout,
        when=config.BATTLE_CHALLENGE_TIMEOUT,
        name=f"battle_timeout_{challenge_id}",
    )


# ============================================================
# Battle Accept/Decline Callback
# ============================================================

async def battle_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle battle accept/decline inline button callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    if not data.startswith("battle_"):
        return

    # 중복 클릭 방지
    if _is_duplicate_callback(query):
        await query.answer()
        return

    await query.answer()
    lang = await get_user_lang(query.from_user.id)

    parts = data.split("_")
    # battle_accept_{challenge_id}_{defender_id}
    # battle_decline_{challenge_id}_{defender_id}
    try:
        action = parts[1]
        challenge_id = int(parts[2])
        expected_defender = int(parts[3])
    except (IndexError, ValueError):
        return

    # 타임아웃 job 취소
    jobs = context.job_queue.get_jobs_by_name(f"battle_timeout_{challenge_id}")
    for job in jobs:
        job.schedule_removal()

    # Only the defender can respond
    if query.from_user.id != expected_defender:
        await query.answer(t(lang, "error.not_your_button"), show_alert=True)
        return

    challenge = await bq.get_challenge_by_id(challenge_id)
    if not challenge:
        try:
            await query.edit_message_text(t(lang, "battle.challenge_not_found"))
        except Exception:
            pass
        return

    if challenge["status"] != "pending":
        try:
            await query.edit_message_text(t(lang, "battle.already_processed"))
        except Exception:
            pass
        return

    # Check if expired
    expires = challenge["expires_at"]
    if hasattr(expires, 'tzinfo') and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires:
        await bq.update_challenge_status(challenge_id, "expired")
        try:
            await query.edit_message_text(f"⏰ {t(lang, 'battle.challenge_expired_msg')}")
        except Exception:
            pass
        return

    if action == "decline":
        await bq.update_challenge_status(challenge_id, "declined")
        try:
            await query.edit_message_text(t(lang, "battle.challenge_declined_msg"))
        except Exception:
            pass
        return

    if action == "accept":
        # Check defender has a team
        d_team = await bq.get_battle_team(expected_defender)
        if not d_team:
            try:
                await query.edit_message_text(
                    f"{icon_emoji('battle')} {t(lang, 'battle.defender_no_team')}",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return
        if len(d_team) < config.RANKED_TEAM_SIZE:
            try:
                await query.edit_message_text(
                    f"❌ {t(lang, 'battle.defender_incomplete', count=len(d_team), required=config.RANKED_TEAM_SIZE)}",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return
        from services.ranked_service import get_current_cost_limit
        _cost_limit = await get_current_cost_limit()
        d_cost = sum(config.RANKED_COST.get(p.get("rarity", ""), 0) for p in d_team)
        if d_cost > _cost_limit:
            try:
                await query.edit_message_text(
                    f"❌ {t(lang, 'battle.defender_cost_over', cost=d_cost, limit=_cost_limit)}",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return

        c_team = await bq.get_battle_team(challenge["challenger_id"])
        if not c_team:
            try:
                await query.edit_message_text(f"{icon_emoji('battle')} {t(lang, 'battle.challenger_no_team')}", parse_mode="HTML")
            except Exception:
                pass
            return
        if len(c_team) < config.RANKED_TEAM_SIZE:
            try:
                await query.edit_message_text(
                    f"❌ {t(lang, 'battle.challenger_incomplete', count=len(c_team), required=config.RANKED_TEAM_SIZE)}",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return
        c_cost = sum(config.RANKED_COST.get(p.get("rarity", ""), 0) for p in c_team)
        if c_cost > _cost_limit:
            try:
                await query.edit_message_text(
                    f"❌ {t(lang, 'battle.challenger_cost_over', cost=c_cost, limit=_cost_limit)}",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return

        await bq.update_challenge_status(challenge_id, "accepted")

        # Run the battle!
        from services.battle_service import execute_battle
        result = await execute_battle(
            challenger_id=challenge["challenger_id"],
            defender_id=expected_defender,
            challenger_team=c_team,
            defender_team=d_team,
            challenge_id=challenge_id,
            chat_id=challenge["chat_id"],
            bot=context.bot,
        )

        # Add detail / skip / teabag buttons
        winner_id = result["winner_id"]
        loser_id = result["loser_id"]
        cache_key = result["cache_key"]
        battle_buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    t(lang, "battle.btn_detail"),
                    callback_data=f"bdetail_{cache_key}_{winner_id}_{loser_id}",
                ),
                InlineKeyboardButton(
                    t(lang, "battle.btn_skip"),
                    callback_data=f"bskip_{winner_id}_{loser_id}",
                ),
                InlineKeyboardButton(
                    t(lang, "battle.btn_teabag"),
                    callback_data=f"btbag_{winner_id}_{loser_id}",
                ),
            ]
        ])

        try:
            await query.edit_message_text(
                result["display_text"],
                parse_mode="HTML",
                reply_markup=battle_buttons,
            )
        except Exception:
            # If message too long, try sending new message
            try:
                await context.bot.send_message(
                    chat_id=challenge["chat_id"],
                    text=result["display_text"],
                    parse_mode="HTML",
                    reply_markup=battle_buttons,
                )
            except Exception:
                pass


# ============================================================
# Battle Result Buttons (Teabag / Delete)
# ============================================================

async def battle_result_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle detail / skip / teabag buttons on battle results."""
    query = update.callback_query
    if not query or not query.data:
        return

    # 중복 클릭 방지 (티배깅·상세보기 연타 차단)
    if _is_duplicate_callback(query):
        await query.answer()
        return

    data = query.data
    parts = data.split("_")
    prefix = parts[0]
    lang = await get_user_lang(query.from_user.id)

    if prefix == "bdetail":
        # Detail DM: bdetail_{cache_key}_{winner_id}_{loser_id}
        try:
            cache_key = int(parts[1])
            winner_id = int(parts[2])
            loser_id = int(parts[3])
        except (IndexError, ValueError):
            await query.answer()
            return

        # Only participants can view
        if query.from_user.id not in (winner_id, loser_id):
            await query.answer(t(lang, "battle.participants_only"), show_alert=True)
            return

        from services.battle_service import get_battle_detail
        detail = get_battle_detail(cache_key)
        if not detail:
            await query.answer(f"⏰ {t(lang, 'battle.detail_expired')}", show_alert=True)
            return

        await query.answer(f"📋 {t(lang, 'battle.detail_sending')}")
        try:
            await context.bot.send_message(
                chat_id=query.from_user.id,
                text=detail["detail_dm"],
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Battle detail DM failed for user {query.from_user.id}: {e}")
            try:
                await query.answer(f"❌ {t(lang, 'battle.detail_dm_fail')}", show_alert=True)
            except Exception:
                pass

    elif prefix == "bskip":
        # Skip (delete message): bskip_{winner_id}_{loser_id}
        try:
            winner_id = int(parts[1])
            loser_id = int(parts[2])
        except (IndexError, ValueError):
            await query.answer()
            return

        # Both winner and loser can skip
        if query.from_user.id not in (winner_id, loser_id):
            await query.answer(t(lang, "battle.participants_only"), show_alert=True)
            return

        await query.answer()
        try:
            await query.message.delete()
        except Exception:
            pass

    elif prefix == "btbag":
        # Teabag: btbag_{winner_id}_{loser_id}
        try:
            winner_id = int(parts[1])
            loser_id = int(parts[2])
        except (IndexError, ValueError):
            await query.answer()
            return

        if query.from_user.id != winner_id:
            await query.answer(t(lang, "battle.winner_only"), show_alert=True)
            return

        from utils.honorific import honorific_name as _hon_name, _get_honorific
        from services.subscription_service import get_user_tier
        winner_user, loser_user, w_tier, l_tier = await asyncio.gather(
            queries.get_user(winner_id),
            queries.get_user(loser_id),
            get_user_tier(winner_id),
            get_user_tier(loser_id),
        )
        w_name = winner_user["display_name"] if winner_user else "???"
        l_name = loser_user["display_name"] if loser_user else "???"
        l_name = _hon_name(l_name, l_tier)

        # 승자 구독 티어에 따라 멘트풀 분기
        w_honorific = _get_honorific(w_tier)
        if w_honorific == "supreme":
            pool = config.TEABAG_MESSAGES_SUPREME
        elif w_honorific == "polite":
            pool = config.TEABAG_MESSAGES_POLITE
        else:
            pool = config.YACHA_TEABAG_MESSAGES

        await query.answer()

        # Remove only the teabag button, keep detail/skip
        try:
            old_kb = query.message.reply_markup
            if old_kb:
                new_rows = []
                for row in old_kb.inline_keyboard:
                    new_btns = [b for b in row if not (b.callback_data and b.callback_data.startswith("btbag"))]
                    if new_btns:
                        new_rows.append(new_btns)
                await query.edit_message_reply_markup(
                    reply_markup=InlineKeyboardMarkup(new_rows) if new_rows else None
                )
        except Exception:
            pass

        # Send random teabag message
        msg = random.choice(pool).format(
            winner=w_name, loser=l_name,
        )
        msg = msg.replace("님님", "님")
        msg = msg.replace("💀", icon_emoji("skull"))
        try:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=msg,
                parse_mode="HTML",
            )
        except Exception:
            pass


# ============================================================
# Battle Ranking (Group: 배틀랭킹)
# ============================================================

async def battle_ranking_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 배틀랭킹 command (group). Show battle leaderboard."""
    lang = await get_user_lang(update.effective_user.id) if update.effective_user else "ko"
    rankings = await bq.get_battle_ranking(10)

    if not rankings:
        await update.message.reply_text(t(lang, "battle.no_records"))
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = [f"{icon_emoji('battle')} <b>{t(lang, 'battle.ranking_title')}</b>\n"]

    for i, r in enumerate(rankings):
        rank = medals[i] if i < 3 else f"<b>{i + 1}.</b>"
        name = escape_html(truncate_name(r['display_name'], 5))
        total = r["battle_wins"] + r["battle_losses"]
        rate = round(r["battle_wins"] / total * 100) if total > 0 else 0

        streak_text = f" {t(lang, 'battle.ranking_streak', n=r['best_streak'])}" if r.get('best_streak', 0) >= 2 else ""

        lines.append(
            f"{rank} {name} — {t(lang, 'battle.wins_losses', wins=r['battle_wins'], losses=r['battle_losses'], rate=rate)}{streak_text}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ============================================================
# Text command aliases for accept/decline
# ============================================================

async def battle_accept_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '배틀수락' text command in group."""
    if not update.effective_user or not update.message:
        return
    lang = await get_user_lang(update.effective_user.id) if update.effective_user else "ko"
    await update.message.reply_text(t(lang, "battle.accept_text_hint"))


async def battle_decline_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '배틀거절' text command in group."""
    if not update.effective_user or not update.message:
        return
    lang = await get_user_lang(update.effective_user.id) if update.effective_user else "ko"
    await update.message.reply_text(t(lang, "battle.decline_text_hint"))
