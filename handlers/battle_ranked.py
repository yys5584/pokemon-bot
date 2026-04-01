"""Ranked battle handlers: ranked challenge, callback, title check (hub).

Sub-modules:
  ranked_info  — season_info_handler, ranked_ranking_handler, arena_register_handler
  ranked_auto  — auto_ranked_handler
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config

from database import queries, title_queries
from database import battle_queries as bq
from handlers._common import _is_duplicate_callback, _is_duplicate_message
from utils.helpers import escape_html, icon_emoji, rarity_badge
from utils.i18n import t, get_user_lang

# Re-exports from sub-modules
from handlers.ranked_info import season_info_handler, ranked_ranking_handler, arena_register_handler  # noqa: F401
from handlers.ranked_auto import auto_ranked_handler  # noqa: F401

logger = logging.getLogger(__name__)


# ============================================================
# Ranked Battle (랭전 - Season PvP)
# ============================================================

async def ranked_challenge_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '랭전' command (group → arena only). Ranked battle challenge."""
    if not update.effective_user or not update.message:
        return
    if _is_duplicate_message(update, "랭전", cooldown=5.0):
        return

    chat_id = update.effective_chat.id
    challenger_id = update.effective_user.id
    lang = await get_user_lang(challenger_id)
    challenger_name = update.effective_user.first_name or t(lang, "common.trainer")

    from services.tournament_service import is_tournament_active
    if is_tournament_active(chat_id):
        return

    # 아레나 체크
    from database import ranked_queries as rq
    if not await rq.is_arena(chat_id):
        await update.message.reply_text(f"🏟️ {t(lang, 'ranked.arena_only')}")
        return

    # Must reply
    reply = update.message.reply_to_message
    if not reply or not reply.from_user:
        await update.message.reply_text(
            f"{icon_emoji('battle')} {t(lang, 'ranked.reply_hint')}", parse_mode="HTML"
        )
        return

    defender_id = reply.from_user.id
    defender_name = reply.from_user.first_name or t(lang, "common.trainer")

    if challenger_id == defender_id:
        await update.message.reply_text(t(lang, "ranked.cannot_self"))
        return
    if reply.from_user.is_bot:
        await update.message.reply_text(t(lang, "ranked.cannot_bot"))
        return

    from services import ranked_service as rs

    # ensure_user + 시즌 확인 병렬
    _, _, season = await asyncio.gather(
        queries.ensure_user(challenger_id, challenger_name, update.effective_user.username),
        queries.ensure_user(defender_id, defender_name, reply.from_user.username),
        rs.ensure_current_season(),
    )
    if not season:
        await update.message.reply_text(f"🏟️ {t(lang, 'ranked.no_season')}")
        return

    season_id = season["season_id"]

    # Cooldown checks in parallel
    today_date = config.get_kst_now().date()
    c_today_count, last_vs, last_any = await asyncio.gather(
        rq.get_ranked_battles_today(challenger_id, today_date),
        rq.get_last_ranked_vs(challenger_id, defender_id),
        bq.get_last_battle_time_any(challenger_id),
    )

    if c_today_count >= config.RANKED_DAILY_CAP:
        await update.message.reply_text(t(lang, "ranked.daily_exhausted", cap=config.RANKED_DAILY_CAP))
        return

    # Same opponent cooldown
    if last_vs:
        if hasattr(last_vs, 'tzinfo') and last_vs.tzinfo is None:
            last_vs = last_vs.replace(tzinfo=timezone.utc)
        cooldown = timedelta(seconds=config.RANKED_COOLDOWN_SAME)
        if datetime.now(timezone.utc) - last_vs < cooldown:
            remaining = cooldown - (datetime.now(timezone.utc) - last_vs)
            mins = int(remaining.total_seconds() // 60)
            await update.message.reply_text(
                t(lang, "ranked.cooldown_same_msg", minutes=config.RANKED_COOLDOWN_SAME // 60, remaining=mins)
            )
            return

    # Global cooldown
    if last_any:
        last_time = datetime.fromisoformat(last_any) if isinstance(last_any, str) else last_any
        if hasattr(last_time, 'tzinfo') and last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=timezone.utc)
        cooldown = timedelta(seconds=config.RANKED_COOLDOWN_GLOBAL)
        if datetime.now(timezone.utc) - last_time < cooldown:
            remaining = cooldown - (datetime.now(timezone.utc) - last_time)
            secs = int(remaining.total_seconds())
            await update.message.reply_text(t(lang, "battle.cooldown_global_msg", seconds=secs))
            return

    # Check challenger team
    c_team = await bq.get_battle_team(challenger_id)
    if not c_team:
        await update.message.reply_text(
            f"{icon_emoji('battle')} {t(lang, 'ranked.no_team_hint')}",
            parse_mode="HTML",
        )
        return

    # Team rule validation
    ok, err = await rs.validate_team_for_ranked(challenger_id, season)
    if not ok:
        await update.message.reply_text(f"❌ {t(lang, 'ranked.team_rule_fail', error=err)}")
        return

    # 중복 도전 체크
    existing = await bq.get_pending_challenge(challenger_id, defender_id)
    if existing:
        await update.message.reply_text(t(lang, "battle.already_pending"))
        return

    # 시즌 법칙 표시 텍스트
    rule_info = config.WEEKLY_RULES.get(season["weekly_rule"], {})
    rule_txt = f"🔒 {rule_info.get('name', season['weekly_rule'])}"

    # 도전 생성
    expires = (datetime.now(timezone.utc) + timedelta(seconds=config.BATTLE_CHALLENGE_TIMEOUT))
    challenge_id = await bq.create_challenge(
        challenger_id, defender_id, chat_id, expires,
        battle_type="ranked",
    )

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                t(lang, "battle.accept_btn"),
                callback_data=f"ranked_accept_{challenge_id}_{defender_id}",
            ),
            InlineKeyboardButton(
                t(lang, "battle.decline_btn"),
                callback_data=f"ranked_decline_{challenge_id}_{defender_id}",
            ),
        ]
    ])

    challenge_msg = await update.message.reply_text(
        f"🏟️ {t(lang, 'ranked.challenge_msg', challenger=challenger_name, defender=defender_name, rule=rule_txt, timeout=config.BATTLE_CHALLENGE_TIMEOUT)}",
        reply_markup=buttons,
        parse_mode="HTML",
    )

    async def _ranked_timeout(ctx):
        try:
            challenge = await bq.get_challenge_by_id(challenge_id)
            if challenge and challenge["status"] == "pending":
                await bq.update_challenge_status(challenge_id, "expired")
                await ctx.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=challenge_msg.message_id,
                    text=f"⏰ {t(lang, 'ranked.challenge_timeout_msg', name=challenger_name)}",
                )
        except Exception:
            pass

    context.job_queue.run_once(
        _ranked_timeout,
        when=config.BATTLE_CHALLENGE_TIMEOUT,
        name=f"ranked_timeout_{challenge_id}",
    )


async def ranked_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle ranked battle accept/decline inline button callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    if not data.startswith("ranked_"):
        return

    if _is_duplicate_callback(query):
        await query.answer()
        return

    await query.answer()
    lang = await get_user_lang(query.from_user.id)

    # ranked_auto_{uid} — 배틀전적 화면에서 랭전 버튼
    if data.startswith("ranked_auto_"):
        uid = int(data.split("_")[2])
        if query.from_user.id != uid:
            return
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        # auto_ranked_handler와 동일한 흐름을 메시지로 트리거
        await query.message.reply_text(f"🏟️ {t(lang, 'ranked.auto_start')}", parse_mode="HTML")
        return

    parts = data.split("_")
    # ranked_accept_{challenge_id}_{defender_id}
    try:
        action = parts[1]
        challenge_id = int(parts[2])
        expected_defender = int(parts[3])
    except (IndexError, ValueError):
        return

    # 타임아웃 job 취소
    jobs = context.job_queue.get_jobs_by_name(f"ranked_timeout_{challenge_id}")
    for job in jobs:
        job.schedule_removal()

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

    expires = challenge["expires_at"]
    if hasattr(expires, 'tzinfo') and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires:
        await bq.update_challenge_status(challenge_id, "expired")
        try:
            await query.edit_message_text(f"⏰ {t(lang, 'ranked.expired_msg')}")
        except Exception:
            pass
        return

    if action == "decline":
        await bq.update_challenge_status(challenge_id, "declined")
        try:
            await query.edit_message_text(t(lang, "ranked.declined"))
        except Exception:
            pass
        return

    if action == "accept":
        from services import ranked_service as rs
        from database import ranked_queries as rq

        # Check defender team
        d_team = await bq.get_battle_team(expected_defender)
        if not d_team:
            try:
                await query.edit_message_text(
                    f"{icon_emoji('battle')} {t(lang, 'ranked.defender_no_team')}",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return

        c_team = await bq.get_battle_team(challenge["challenger_id"])
        if not c_team:
            try:
                await query.edit_message_text(f"{icon_emoji('battle')} {t(lang, 'ranked.challenger_no_team')}", parse_mode="HTML")
            except Exception:
                pass
            return

        # Re-validate both teams at accept time
        season = await rs.ensure_current_season()
        if not season:
            try:
                await query.edit_message_text(f"🏟️ {t(lang, 'ranked.no_season')}")
            except Exception:
                pass
            return

        ok_c, err_c = await rs.validate_team_for_ranked(challenge["challenger_id"], season)
        if not ok_c:
            try:
                await query.edit_message_text(f"❌ {t(lang, 'ranked.challenger_rule_fail', error=err_c)}")
            except Exception:
                pass
            return

        ok_d, err_d = await rs.validate_team_for_ranked(expected_defender, season)
        if not ok_d:
            try:
                await query.edit_message_text(f"❌ {t(lang, 'ranked.defender_rule_fail', error=err_d)}")
            except Exception:
                pass
            return

        await bq.update_challenge_status(challenge_id, "accepted")

        # 배틀 실행!
        from services.battle_service import execute_battle
        result = await execute_battle(
            challenger_id=challenge["challenger_id"],
            defender_id=expected_defender,
            challenger_team=c_team,
            defender_team=d_team,
            challenge_id=challenge_id,
            chat_id=challenge["chat_id"],
            bot=context.bot,
            battle_type="ranked",
            season_id=season["season_id"],
        )

        # 랭크전 결과 텍스트 조합
        ranked_info = result.get("ranked_info")
        winner_id = result["winner_id"]
        loser_id = result["loser_id"]
        cache_key = result["cache_key"]

        rp_lines = []
        if ranked_info:
            w_is_placement = ranked_info.get("w_is_placement", False)
            l_is_placement = ranked_info.get("l_is_placement", False)

            # 배치 완료 알림
            if ranked_info.get("w_placement_result"):
                rp_lines.append(f"🎉 {result['winner_name']} 배치 완료! {ranked_info['w_placement_result']['tier_display']}")
            if ranked_info.get("l_placement_result"):
                rp_lines.append(f"🎉 {result['loser_name']} 배치 완료! {ranked_info['l_placement_result']['tier_display']}")

            # RP 표시 (배치 중이면 미표시, 그룹이므로 MMR 미표시)
            if not w_is_placement:
                w_div = config.get_division_info(ranked_info['winner_rp_after'])
                w_tier_str = config.tier_division_display(
                    w_div[0], w_div[1], w_div[2],
                    placement_done=True, total_rp=ranked_info['winner_rp_after'])
                rp_lines.append(
                    f"📈 RP +{ranked_info['winner_rp_gain']} "
                    f"({ranked_info['winner_rp_before']} → {ranked_info['winner_rp_after']} {w_tier_str})")
            if not l_is_placement:
                l_div = config.get_division_info(ranked_info['loser_rp_after'])
                l_tier_str = config.tier_division_display(
                    l_div[0], l_div[1], l_div[2],
                    placement_done=True, total_rp=ranked_info['loser_rp_after'])
                rp_lines.append(
                    f"📉 RP -{ranked_info['loser_rp_loss']} "
                    f"({ranked_info['loser_rp_before']} → {ranked_info['loser_rp_after']} {l_tier_str})")

            # 윈트레이딩 감지 경고
            pair_decay = ranked_info.get("pair_decay", 1.0)
            if pair_decay < 1.0 and pair_decay > 0:
                rp_lines.append(f"⚠️ 같은 상대 반복 대전 — RP {int(pair_decay*100)}% 적용")
            elif pair_decay == 0:
                rp_lines.append("🚫 같은 상대 일일 한도 초과 — RP 미적용")

            # 승급/강등
            if ranked_info.get("w_promoted"):
                w_div_after = config.get_division_info(ranked_info["winner_rp_after"])
                new_t = config.tier_division_display(
                    w_div_after[0], w_div_after[1], w_div_after[2], placement_done=True)
                rp_lines.append(f"🎉 승급! → {new_t}")
            if ranked_info.get("l_demoted") and not ranked_info.get("l_shield_protected"):
                l_div_after = config.get_division_info(ranked_info["loser_rp_after"])
                new_lt = config.tier_division_display(
                    l_div_after[0], l_div_after[1], l_div_after[2], placement_done=True)
                rp_lines.append(f"⬇️ 강등 → {new_lt}")
            if ranked_info.get("l_shield_protected"):
                rp_lines.append("🛡️ 승급 보호 발동!")

        # 법칙 헤더
        rule_info = config.WEEKLY_RULES.get(season["weekly_rule"], {})
        header = f"🏟️ 랭크전 결과!\n🔒 {rule_info.get('name', '')}"

        display = result["display_text"].replace(f"{icon_emoji('battle')} 배틀 결과!", header)
        if rp_lines:
            display += "\n" + "\n".join(rp_lines)

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
            ]
        ])

        try:
            await query.edit_message_text(
                display, parse_mode="HTML", reply_markup=battle_buttons,
            )
        except Exception:
            try:
                await context.bot.send_message(
                    chat_id=challenge["chat_id"],
                    text=display, parse_mode="HTML", reply_markup=battle_buttons,
                )
            except Exception:
                pass

        # Check ranked titles
        if ranked_info:
            await _check_ranked_titles(winner_id, ranked_info, is_winner=True)
            await _check_ranked_titles(loser_id, ranked_info, is_winner=False)


async def _check_ranked_titles(user_id: int, ranked_info: dict, is_winner: bool):
    """Check and unlock ranked battle titles."""
    from database import ranked_queries as rq
    from services.ranked_service import current_season_id

    season_id = current_season_id()
    rec = await rq.get_season_record(user_id, season_id)
    if not rec:
        return

    total = rec["ranked_wins"] + rec["ranked_losses"]
    tier = rec["tier"]
    streak = rec["ranked_streak"] if is_winner else 0

    best_streak = rec.get("best_ranked_streak", 0)
    checks = [
        ("ranked_first", total >= 1),
        # 티어 도달 칭호는 뱃지 자동표시로 대체 → 삭제
        ("ranked_streak5", best_streak >= 5),
        ("ranked_streak10", best_streak >= 10),
    ]

    for title_id, condition in checks:
        if condition and title_id in config.RANKED_TITLES:
            already = await title_queries.has_title(user_id, title_id)
            if not already:
                await title_queries.unlock_title(user_id, title_id)
                logger.info(f"Ranked title unlocked: {user_id} -> {title_id}")
