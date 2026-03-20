"""Ranked battle handlers: ranked challenge, auto-ranked, season info, ranking, arena."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config

from database import queries, title_queries
from database import battle_queries as bq
from handlers._common import _is_duplicate_callback
from utils.helpers import escape_html, icon_emoji, rarity_badge
from utils.i18n import t, get_user_lang

logger = logging.getLogger(__name__)


# ============================================================
# Ranked Battle (랭전 - Season PvP)
# ============================================================

async def ranked_challenge_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '랭전' command (group → arena only). Ranked battle challenge."""
    if not update.effective_user or not update.message:
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


async def season_info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '시즌' command (DM). Show current season info + user record."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    from services import ranked_service as rs
    from database import ranked_queries as rq

    season = await rs.ensure_current_season()
    if not season:
        await update.message.reply_text(f"🏟️ {t(lang, 'ranked.no_active_season')}")
        return

    season_id = season["season_id"]
    rule_info = config.WEEKLY_RULES.get(season["weekly_rule"], {})

    lines = [
        f"🏟️ <b>{t(lang, 'ranked.season_title', id=season_id)}</b>",
        t(lang, "ranked.season_period", start=season.get("starts_at", "?").strftime("%m/%d") if hasattr(season.get("starts_at", "?"), "strftime") else "?", end=season.get("ends_at", "?").strftime("%m/%d") if hasattr(season.get("ends_at", "?"), "strftime") else "?"),
        f"{t(lang, 'ranked.season_rule', name=rule_info.get('name', season['weekly_rule']))}",
        f"   └ {rule_info.get('desc', '')}",
        "",
        f"💡 {t(lang, 'ranked.season_dm_hint')}",
        "",
    ]

    # My season record
    rec = await rq.get_season_record(user_id, season_id)
    if rec:
        tier_full = rs.tier_display_full(rec)
        total = rec["ranked_wins"] + rec["ranked_losses"]
        wr = round(rec["ranked_wins"] / total * 100, 1) if total > 0 else 0

        placement_done = rec.get("placement_done", False)

        if not placement_done:
            pg = rec.get("placement_games", 0)
            lines.extend([
                t(lang, "ranked.my_season_record"),
                f"{tier_full}",
            ])
            if pg > 0:
                lines.append(f"🏆 {t(lang, 'battle.wins_losses', wins=rec['ranked_wins'], losses=rec['ranked_losses'], rate=wr)}")
            lines.append(t(lang, "ranked.placement_needed"))
        else:
            lines.extend([
                t(lang, "ranked.my_season_record"),
                f"{tier_full}",
                f"🏆 {t(lang, 'battle.wins_losses', wins=rec['ranked_wins'], losses=rec['ranked_losses'], rate=wr)}",
                f"🔥 {t(lang, 'battle.current_streak', n=rec['ranked_streak'])}  |  {t(lang, 'battle.best_streak_label', n=rec['best_ranked_streak'])}",
            ])
            peak_div = config.get_division_info(rec['peak_rp'])
            peak_disp = config.tier_division_display(
                peak_div[0], peak_div[1], peak_div[2],
                placement_done=True, total_rp=rec['peak_rp'])
            lines.append(t(lang, "ranked.peak_label", tier=peak_disp))

            try:
                mmr_rec = await rq.get_user_mmr(user_id)
                lines.append(t(lang, "ranked.mmr_label", mmr=mmr_rec['mmr'], peak=mmr_rec['peak_mmr']))
            except Exception:
                pass
    else:
        lines.append(t(lang, "ranked.no_season_record"))

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def ranked_ranking_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '랭킹' or '시즌랭킹' command (DM). Show season ranking."""
    if not update.effective_user or not update.message:
        return
    lang = await get_user_lang(update.effective_user.id)

    from services import ranked_service as rs
    from database import ranked_queries as rq

    season = await rs.ensure_current_season()
    if not season:
        await update.message.reply_text(f"🏟️ {t(lang, 'ranked.no_active_season')}")
        return

    ranking = await rq.get_ranked_ranking(season["season_id"], limit=15)
    if not ranking:
        await update.message.reply_text(f"🏟️ {t(lang, 'ranked.no_ranking')}")
        return

    lines = [f"🏟️ <b>{t(lang, 'ranked.ranking_header', id=season['season_id'])}</b>\n"]
    medals = ["🥇", "🥈", "🥉"]
    for i, r in enumerate(ranking):
        medal = medals[i] if i < 3 else f"{i+1}."
        te = r.get("title_emoji", "")
        te_str = f"{icon_emoji(te)} " if te and te in config.ICON_CUSTOM_EMOJI else ""
        name = escape_html(r["display_name"] or "???")

        # 배치 중이면 "🎯 배치중" 표시, 아니면 디비전 표시
        placement_done = r.get("placement_done", True)
        if not placement_done:
            tier_str = t(lang, "ranked.placement_tag")
        else:
            div = config.get_division_info(r["rp"])
            tier_str = config.tier_division_display(
                div[0], div[1], div[2],
                placement_done=True, total_rp=r["rp"])

        lines.append(
            f"{medal} {te_str}{name}  {tier_str}  "
            f"({r['ranked_wins']}승 {r['ranked_losses']}패)"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def arena_register_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '/아레나등록' command (group, admin only). Register chat as arena candidate."""
    if not update.effective_user or not update.message:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)

    # Admin check
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ("administrator", "creator"):
            await update.message.reply_text(t(lang, "ranked.arena_admin_only"))
            return
    except Exception:
        await update.message.reply_text(t(lang, "ranked.arena_perm_fail"))
        return

    chat_name = update.effective_chat.title or str(chat_id)

    from database import ranked_queries as rq
    await rq.register_arena(chat_id, chat_name, user_id)
    await update.message.reply_text(f"✅ {t(lang, 'ranked.arena_registered', name=chat_name)}")


# ============================================================
# DM Auto-Ranked Battle (랭전 — DM 자동매칭)
# ============================================================


async def auto_ranked_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '랭전' command (DM). Auto-match ranked battle."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    display_name = update.effective_user.first_name or t(lang, "common.trainer")
    await queries.ensure_user(user_id, display_name, update.effective_user.username)

    from services import ranked_service as rs
    from database import ranked_queries as rq

    # 시즌 확인/생성
    season = await rs.ensure_current_season()
    if not season:
        await update.message.reply_text(f"🏟️ {t(lang, 'ranked.no_active_season')}")
        return

    season_id = season["season_id"]
    rule_info = config.WEEKLY_RULES.get(season["weekly_rule"], {})

    # Check team
    my_team = await bq.get_battle_team(user_id)
    if not my_team:
        await update.message.reply_text(
            f"{icon_emoji('battle')} {t(lang, 'ranked.no_team_hint')}",
            parse_mode="HTML",
        )
        return

    # Team rule validation
    ok, err = await rs.validate_team_for_ranked(user_id, season)
    if not ok:
        await update.message.reply_text(f"❌ {t(lang, 'ranked.team_rule_fail_short', error=err)}")
        return

    # COST 검증
    total_cost = 0
    ultra_count = 0
    for p in my_team:
        cost = config.RANKED_COST.get(p["rarity"], 1)
        total_cost += cost
        if p["rarity"] == "ultra_legendary":
            ultra_count += 1
    if total_cost > config.RANKED_COST_LIMIT:
        await update.message.reply_text(
            f"❌ {t(lang, 'ranked.cost_over_msg', cost=total_cost, limit=config.RANKED_COST_LIMIT)}"
        )
        return
    if ultra_count > config.RANKED_ULTRA_MAX:
        await update.message.reply_text(
            f"❌ {t(lang, 'ranked.ultra_max_msg', max=config.RANKED_ULTRA_MAX)}"
        )
        return

    # 일일 상한 체크
    today_date = config.get_kst_now().date()
    today_count = await rq.get_ranked_battles_today(user_id, today_date)
    if today_count >= config.RANKED_DAILY_CAP:
        await update.message.reply_text(t(lang, "ranked.daily_exhausted", cap=config.RANKED_DAILY_CAP))
        return

    # 전체 쿨다운 체크
    last_any = await bq.get_last_battle_time_any(user_id)
    if last_any:
        last_time = datetime.fromisoformat(last_any) if isinstance(last_any, str) else last_any
        if hasattr(last_time, 'tzinfo') and last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=timezone.utc)
        cooldown = timedelta(seconds=config.RANKED_COOLDOWN_GLOBAL)
        if datetime.now(timezone.utc) - last_time < cooldown:
            remaining = cooldown - (datetime.now(timezone.utc) - last_time)
            secs = int(remaining.total_seconds())
            await update.message.reply_text(f"⏳ {t(lang, 'ranked.cooldown_msg', seconds=secs)}")
            return

    # 방어 패배 리셋 (유저가 직접 랭전을 걸었으므로)
    await rq.reset_defense_losses(user_id, season_id)

    # 승급 보호 해제 (랭전 재진입 시)
    await rq.clear_promo_shield(user_id, season_id)

    # 시즌 기록 조회 (배치 상태 확인)
    my_rec = await rq.get_season_record(user_id, season_id)
    if not my_rec:
        # 첫 랭전: 언랭으로 생성
        await rq.upsert_season_record(user_id, season_id, 0, "unranked",
                                       placement_done=False, placement_games=0)
        my_rec = await rq.get_season_record(user_id, season_id)

    placement_done = my_rec.get("placement_done", False)
    placement_games = my_rec.get("placement_games", 0)

    # 매칭 메시지 (배치 상태 반영)
    if not placement_done:
        if placement_games > 0:
            status_txt = f"🎯 {t(lang, 'ranked.placement_status', current=placement_games, total=config.PLACEMENT_GAMES_REQUIRED)}"
        else:
            status_txt = f"❓ {t(lang, 'ranked.unranked_status')}"
        matching_msg = await update.message.reply_text(f"{status_txt}\n🔍 {t(lang, 'ranked.matching')}")
    else:
        tier_full = rs.tier_display_full(my_rec)
        matching_msg = await update.message.reply_text(f"{tier_full}\n🔍 {t(lang, 'ranked.matching')}")

    # 상대 찾기
    opponent_id = await rs.find_ranked_opponent(user_id, season_id)
    if not opponent_id:
        try:
            await matching_msg.edit_text(f"😢 {t(lang, 'ranked.match_fail')}")
        except Exception:
            pass
        return

    # 상대 팀 로드
    opp_team = await bq.get_battle_team(opponent_id)
    if not opp_team or len(opp_team) < config.RANKED_TEAM_SIZE:
        try:
            await matching_msg.edit_text(f"😢 {t(lang, 'ranked.opp_team_fail')}")
        except Exception:
            pass
        return
    opp_cost = sum(config.RANKED_COST.get(p.get("rarity", ""), 0) for p in opp_team)
    if opp_cost > config.RANKED_COST_LIMIT:
        try:
            await matching_msg.edit_text(f"😢 {t(lang, 'ranked.opp_cost_fail')}")
        except Exception:
            pass
        return

    # 상대 이름 조회
    opp_user = await queries.get_user(opponent_id)
    opp_name = opp_user["display_name"] if opp_user else "???"

    # 매칭 성공 메시지
    try:
        await matching_msg.edit_text(
            f"🏟️ 매칭 완료!\n"
            f"🔒 시즌 법칙: {rule_info.get('name', season['weekly_rule'])}\n"
            f"상대: {escape_html(opp_name)}\n\n"
            f"⚔️ 배틀 시작!",
            parse_mode="HTML",
        )
    except Exception:
        pass

    # 배틀 실행!
    from services.battle_service import execute_battle
    result = await execute_battle(
        challenger_id=user_id,
        defender_id=opponent_id,
        challenger_team=my_team,
        defender_team=opp_team,
        challenge_id=None,
        chat_id=user_id,  # DM이므로 chat_id = user_id
        bot=context.bot,
        battle_type="ranked",
        season_id=season_id,
    )

    # 결과 처리
    ranked_info = result.get("ranked_info")
    winner_id = result["winner_id"]
    loser_id = result["loser_id"]
    cache_key = result["cache_key"]

    # 방어 패배 카운트: 상대(방어자)가 졌으면 +1
    if loser_id == opponent_id:
        await rq.increment_defense_losses(opponent_id, season_id)
    else:
        # 도전자(나)가 졌어도 상대의 defense_losses는 안 건드림
        # 내가 졌으면 상대 방어 패배 리셋 (상대가 이겼으니)
        pass

    # RP 정보 조합
    rp_lines = []
    if ranked_info:
        w_is_placement = ranked_info.get("w_is_placement", False)
        l_is_placement = ranked_info.get("l_is_placement", False)
        w_placement_result = ranked_info.get("w_placement_result")
        l_placement_result = ranked_info.get("l_placement_result")

        # --- 배치 완료 알림 ---
        if w_placement_result and winner_id == user_id:
            rp_lines.append(f"🎉 배치 완료! {w_placement_result['tier_display']} 배정!")
        elif l_placement_result and loser_id == user_id:
            rp_lines.append(f"🎉 배치 완료! {l_placement_result['tier_display']} 배정!")

        # --- RP / 배치 표시 ---
        if winner_id == user_id:
            if w_is_placement:
                # 배치 중: 진행 상태만 표시 (MMR 숨김)
                pg = ranked_info.get("w_placement_games", 0)
                wins_after = ranked_info.get("w_wins_after", 0)
                losses_after = ranked_info.get("w_losses_after", 0)
                rp_lines.append(f"🎯 배치 {pg}/{config.PLACEMENT_GAMES_REQUIRED} — {wins_after}승 {losses_after}패")
            else:
                w_div = config.get_division_info(ranked_info['winner_rp_after'])
                w_tier_str = config.tier_division_display(
                    w_div[0], w_div[1], w_div[2],
                    placement_done=True, total_rp=ranked_info['winner_rp_after'])
                rp_lines.append(
                    f"📈 RP +{ranked_info['winner_rp_gain']} "
                    f"({ranked_info['winner_rp_before']} → {ranked_info['winner_rp_after']})")
                rp_lines.append(f"   {w_tier_str}")
        else:
            if l_is_placement:
                # 배치 중: 진행 상태만 표시 (MMR 숨김)
                pg = ranked_info.get("l_placement_games", 0)
                wins_after = ranked_info.get("l_wins_after", 0)
                losses_after = ranked_info.get("l_losses_after", 0)
                rp_lines.append(f"🎯 배치 {pg}/{config.PLACEMENT_GAMES_REQUIRED} — {wins_after}승 {losses_after}패")
            else:
                l_div = config.get_division_info(ranked_info['loser_rp_after'])
                l_tier_str = config.tier_division_display(
                    l_div[0], l_div[1], l_div[2],
                    placement_done=True, total_rp=ranked_info['loser_rp_after'])
                rp_lines.append(
                    f"📉 RP -{ranked_info['loser_rp_loss']} "
                    f"({ranked_info['loser_rp_before']} → {ranked_info['loser_rp_after']})")
                rp_lines.append(f"   {l_tier_str}")

        # 윈트레이딩 감지
        pair_decay = ranked_info.get("pair_decay", 1.0)
        if pair_decay < 1.0 and pair_decay > 0:
            rp_lines.append(f"⚠️ 같은 상대 반복 — RP {int(pair_decay*100)}%")
        elif pair_decay == 0:
            rp_lines.append("🚫 같은 상대 한도 초과 — RP 미적용")

        # 승급 보호
        if ranked_info.get("l_shield_protected") and loser_id == user_id:
            rp_lines.append("🛡️ 승급 보호로 강등이 방지되었습니다!")

        # 승급/강등 (디비전 기준)
        if ranked_info.get("w_promoted"):
            w_div_after = config.get_division_info(ranked_info["winner_rp_after"])
            new_t = config.tier_division_display(
                w_div_after[0], w_div_after[1], w_div_after[2], placement_done=True)
            if winner_id == user_id:
                rp_lines.append(f"🎉 승급! → {new_t}  🛡️ {config.PROMO_SHIELD_HOURS}시간 보호 (랭전 시 해제)")
            else:
                rp_lines.append(f"🎉 상대 승급! → {new_t}")
        if ranked_info.get("l_demoted") and not ranked_info.get("l_shield_protected"):
            l_div_after = config.get_division_info(ranked_info["loser_rp_after"])
            new_lt = config.tier_division_display(
                l_div_after[0], l_div_after[1], l_div_after[2], placement_done=True)
            if loser_id == user_id:
                rp_lines.append(f"⬇️ 강등 → {new_lt}")
            else:
                rp_lines.append(f"⬇️ 상대 강등 → {new_lt}")

    # 도전자에게 결과 DM
    rule_txt = f"🔒 시즌 법칙: {rule_info.get('name', season['weekly_rule'])}"
    winner_name = result["winner_name"]
    is_win = winner_id == user_id

    display = result["display_text"].replace(
        f"{icon_emoji('battle')} 배틀 결과!",
        f"🏟️ 랭크전 결과!\n{rule_txt}"
    )
    if rp_lines:
        display += "\n" + "\n".join(rp_lines)

    battle_buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📋 상세보기",
                callback_data=f"bdetail_{cache_key}_{winner_id}_{loser_id}",
            ),
        ]
    ])

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=display,
            parse_mode="HTML",
            reply_markup=battle_buttons,
        )
    except Exception as e:
        logger.error(f"Ranked DM result send failed: {e}")

    # 상대에게 알림 DM
    try:
        if is_win:
            opp_result = "패배"
            opp_icon = "📉"
            if ranked_info and not ranked_info.get("l_is_placement"):
                l_div = config.get_division_info(ranked_info['loser_rp_after'])
                l_tier_str = config.tier_division_display(
                    l_div[0], l_div[1], l_div[2],
                    placement_done=True, total_rp=ranked_info['loser_rp_after'])
                opp_rp_txt = (
                    f"RP -{ranked_info['loser_rp_loss']} "
                    f"({ranked_info['loser_rp_before']} → {ranked_info['loser_rp_after']})\n"
                    f"{l_tier_str}"
                )
            else:
                opp_rp_txt = ""
        else:
            opp_result = "승리"
            opp_icon = "📈"
            if ranked_info and not ranked_info.get("w_is_placement"):
                w_div = config.get_division_info(ranked_info['winner_rp_after'])
                w_tier_str = config.tier_division_display(
                    w_div[0], w_div[1], w_div[2],
                    placement_done=True, total_rp=ranked_info['winner_rp_after'])
                opp_rp_txt = (
                    f"RP +{ranked_info['winner_rp_gain']} "
                    f"({ranked_info['winner_rp_before']} → {ranked_info['winner_rp_after']})\n"
                    f"{w_tier_str}"
                )
            else:
                opp_rp_txt = ""

        # 배치 완료 알림
        opp_placement_txt = ""
        if ranked_info:
            if is_win and ranked_info.get("l_placement_result"):
                opp_placement_txt = f"\n🎉 배치 완료! {ranked_info['l_placement_result']['tier_display']} 배정!"
            elif not is_win and ranked_info.get("w_placement_result"):
                opp_placement_txt = f"\n🎉 배치 완료! {ranked_info['w_placement_result']['tier_display']} 배정!"

        # MMR 표시
        opp_mmr_txt = ""
        if ranked_info:
            if is_win:
                opp_mmr_txt = (
                    f"\n📊 MMR: {ranked_info['l_mmr_before']} → {ranked_info['l_mmr_after']} "
                    f"({ranked_info['l_mmr_after'] - ranked_info['l_mmr_before']:+d})")
            else:
                opp_mmr_txt = (
                    f"\n📊 MMR: {ranked_info['w_mmr_before']} → {ranked_info['w_mmr_after']} "
                    f"({ranked_info['w_mmr_after'] - ranked_info['w_mmr_before']:+d})")

        await context.bot.send_message(
            chat_id=opponent_id,
            text=(
                f"🏟️ {escape_html(display_name)}님이 랭크전에서 도전했습니다!\n"
                f"결과: {opp_result} {opp_icon} {opp_rp_txt}"
                f"{opp_placement_txt}{opp_mmr_txt}"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.debug(f"Ranked opponent DM failed (may have blocked bot): {e}")

    # 랭크 칭호 체크
    if ranked_info:
        await _check_ranked_titles(winner_id, ranked_info, is_winner=True)
        await _check_ranked_titles(loser_id, ranked_info, is_winner=False)
