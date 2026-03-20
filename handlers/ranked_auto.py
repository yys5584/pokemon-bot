"""DM auto-ranked battle handler."""

import logging
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config

from database import queries
from database import battle_queries as bq
from utils.helpers import escape_html, icon_emoji
from utils.i18n import t, get_user_lang

logger = logging.getLogger(__name__)


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
    from handlers.battle_ranked import _check_ranked_titles
    if ranked_info:
        await _check_ranked_titles(winner_id, ranked_info, is_winner=True)
        await _check_ranked_titles(loser_id, ranked_info, is_winner=False)
