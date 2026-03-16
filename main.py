"""Pokemon Telegram Bot — Entry Point."""

import asyncio
import logging
import os
from datetime import datetime, time as dt_time, timezone, timedelta

import config

from dotenv import load_dotenv
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from database.connection import get_db, close_db
from database.schema import create_tables
from database.seed import seed_pokemon_data, seed_battle_data, migrate_18_types, migrate_assign_ivs, migrate_rarity_v2, migrate_ultra_legendary, migrate_catch_rates_v3, migrate_add_nurture_locked, migrate_trade_evo_fix
from database import queries

from handlers.start import start_handler, help_handler, help_callback_handler
from handlers.group import catch_handler, master_ball_handler, hyper_ball_handler, love_easter_egg, love_hidden_handler, attendance_handler, ranking_handler, log_handler, dashboard_handler, room_info_handler, my_pokemon_group_handler, on_chat_activity, close_message_callback, catch_keep_callback, catch_release_callback, shiny_ticket_spawn_handler, challenge_answer_handler, challenge_callback_handler
from handlers.dm_pokedex import pokedex_handler, pokedex_callback, my_pokemon_handler, my_pokemon_callback, title_handler, title_callback, title_list_handler, title_list_callback, title_page_callback, status_handler, appraisal_handler, type_chart_handler
from handlers.battle import (
    partner_handler, partner_callback_handler,
    team_handler, team_register_handler, team_clear_handler, team_select_handler,
    team_swap_handler, team_edit_menu_handler, team_callback_handler,
    battle_stats_handler, bp_handler, bp_shop_handler, bp_buy_handler, shop_callback_handler,
    battle_challenge_handler, battle_callback_handler, battle_result_callback_handler,
    battle_ranking_handler, battle_accept_text_handler, battle_decline_text_handler,
    tier_handler,
    ranked_callback_handler,
    season_info_handler, ranked_ranking_handler,
    auto_ranked_handler,
    yacha_handler, yacha_type_callback, yacha_amount_callback,
    yacha_response_callback, yacha_result_callback,
)
from handlers.dm_nurture import feed_handler, play_handler, evolve_handler, nurture_callback_handler, nurture_menu_handler
# DM trade removed — replaced by group reply trade
# from handlers.dm_trade import trade_handler, accept_handler, reject_handler
from handlers.dm_trade import trade_evo_choice_handler
from handlers.dm_market import (
    market_handler, market_register_handler, market_my_handler,
    market_cancel_handler, market_buy_handler, market_search_handler,
    market_callback_handler,
)
from handlers.group_trade import group_trade_handler, group_trade_callback_handler
from handlers.dm_mission import mission_handler
from handlers.dm_release import release_handler, release_callback
from handlers.dm_fusion import fusion_handler, fusion_callback
from handlers.tutorial import tutorial_callback, tutorial_dm_handler, tutorial_dm_catch
from handlers.admin import (
    spawn_rate_handler, force_spawn_handler, force_spawn_reset_handler, ticket_force_spawn_handler,
    pokeball_reset_handler,
    event_start_handler, event_list_handler, event_end_handler, event_dm_callback,
    stats_handler, channel_list_handler, grant_masterball_handler, grant_bp_handler, grant_subscription_handler,
    arcade_handler, tournament_chat_handler, force_tournament_reg_handler, force_tournament_run_handler,
    manual_subscription_handler,
    abuse_list_handler, abuse_detail_handler, abuse_reset_handler,
)
from handlers.dm_subscription import (
    subscription_handler, subscription_callback_handler,
    subscription_status_handler, premium_shop_handler, channel_shop_handler,
    premium_hub_handler, premium_hub_callback_handler,
)

from services.spawn_service import schedule_all_chats
from services.weather_service import update_weather, get_current_weather, WEATHER_BOOSTS
from services.tournament_service import start_registration, start_tournament, snapshot_teams
from handlers.tournament import tournament_join_handler
try:
    from handlers.camp import camp_handler, camp_callback_handler, camp_round_job, camp_create_handler, camp_settings_handler, camp_map_handler, camp_visit_handler
    from handlers.dm_camp import my_camp_handler, shiny_convert_handler, decompose_handler, camp_dm_callback_handler, home_camp_handler, camp_notify_handler, camp_guide_handler, camp_hub_handler, camp_welcome_input_handler
    HAS_CAMP = True
except ImportError:
    HAS_CAMP = False

from handlers.dm_gacha import gacha_handler, gacha_callback_handler, item_handler, item_callback_handler
# Dashboard now runs as separate process (pokemon-dashboard.service)
# from dashboard.server import start_dashboard

load_dotenv()

# Sentry error monitoring (disabled if SENTRY_DSN is not set)
_sentry_dsn = os.getenv("SENTRY_DSN", "")
if _sentry_dsn:
    import sentry_sdk
    sentry_sdk.init(
        dsn=_sentry_dsn,
        traces_sample_rate=0.1,
        environment="production",
        send_default_pii=False,
    )

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
)
logger = logging.getLogger(__name__)


# --- Lifecycle hooks ---

async def post_init(application: Application):
    """Called after Application.initialize() — set up DB, seed, schedule."""
    import time
    t0 = time.monotonic()

    # Phase 1: DB 연결 + 테이블 생성 + 포켓몬 시드 (순차 필수)
    logger.info("Initializing database...")
    await get_db()

    skip_init = os.getenv("SKIP_INIT", "").strip().lower() in ("1", "true", "yes")
    if skip_init:
        logger.info("SKIP_INIT=1 — DDL/seed/migration 전부 스킵")
    else:
        try:
            await asyncio.wait_for(create_tables(), timeout=30)
        except Exception as e:
            logger.warning(f"create_tables skipped ({e.__class__.__name__}) — tables already exist in prod")
        try:
            await asyncio.wait_for(seed_pokemon_data(), timeout=30)
        except Exception as e:
            logger.warning(f"seed_pokemon_data skipped ({e.__class__.__name__})")
    logger.info(f"[{time.monotonic()-t0:.1f}s] DB + schema + seed done")

    if not skip_init:
        # Phase 2: 배틀데이터 시드 + 마이그레이션 (병렬, 전체 타임아웃)
        try:
            results = await asyncio.wait_for(asyncio.gather(
                migrate_18_types(),
                migrate_assign_ivs(),
                seed_battle_data(),
                migrate_rarity_v2(),
                migrate_ultra_legendary(),
                migrate_catch_rates_v3(),
                migrate_add_nurture_locked(),
                migrate_trade_evo_fix(),
            ), timeout=60)
            migrated, iv_assigned, _, rarity_migrated, ultra_migrated, catch_migrated, nurture_locked, trade_evo_fixed = results
            if migrated:
                logger.info(f"18-type migration applied: {migrated} pokemon updated.")
            if iv_assigned:
                logger.info(f"IV migration: {iv_assigned} pokemon received random IVs.")
            if rarity_migrated:
                logger.info(f"Rarity v2 migration: {rarity_migrated} pokemon rarity updated (종족값 기반).")
            if ultra_migrated:
                logger.info(f"Ultra-legendary migration: {ultra_migrated} pokemon promoted to ultra_legendary.")
            if catch_migrated:
                logger.info(f"Catch rate v3 migration: {catch_migrated} pokemon catch_rate unified by rarity.")
            if nurture_locked:
                logger.info("Nurture locked column added to user_pokemon.")
            if trade_evo_fixed:
                logger.info("Trade evolution routes fixed (롱스톤/시드라/스라크/폴리곤).")
        except Exception as e:
            logger.warning(f"Phase 2 migrations skipped ({e.__class__.__name__}) — already applied in prod")
    logger.info(f"[{time.monotonic()-t0:.1f}s] Database ready.")

    # Phase 3: 독립 작업 병렬 (cleanup + missed_reset)
    # NOTE: resolve_unresolved_sessions는 bot HTTP가 초기화된 후 실행해야 하므로
    # job_queue.run_once로 지연 실행 (post_init 시점에선 bot HTTP 미초기화)
    try:
        await asyncio.wait_for(asyncio.gather(
            queries.cleanup_expired_events(),
            _check_missed_reset(),
        ), timeout=30)
    except Exception as e:
        logger.warning(f"Phase 3 cleanup skipped ({e.__class__.__name__})")
    logger.info(f"[{time.monotonic()-t0:.1f}s] Cleanup done")

    # 봇 시작 후 5초 뒤 미해결 세션 resolve (HTTP 초기화 보장)
    async def _delayed_resolve(context):
        from services.spawn_service import resolve_unresolved_sessions
        refunded_balls = await resolve_unresolved_sessions(context.bot)
        if refunded_balls:
            from utils.helpers import ball_emoji
            for uid, ball_type in refunded_balls:
                try:
                    be = ball_emoji("masterball") if ball_type == "master" else ball_emoji("hyperball")
                    bname = "마스터볼" if ball_type == "master" else "하이퍼볼"
                    msg = f"{be} 서버 점검으로 인해 {bname}이 환불되었습니다."
                    await context.bot.send_message(chat_id=uid, text=msg, parse_mode="HTML")
                except Exception:
                    pass
            logger.info(f"Sent {len(refunded_balls)} ball refund DMs")
        logger.info(f"[startup resolve] Done: {len(refunded_balls) if refunded_balls else 0} refunds")

    application.job_queue.run_once(_delayed_resolve, when=5, name="startup_resolve")

    # 가챠 미전달 보상 복구 — 재시작 직전 2분 이내 뽑기 기록이 있으면 DM 발송
    try:
        recent_gacha = await queries.get_recent_gacha_by_user(minutes=2)
        if recent_gacha:
            _GACHA_NAMES = {item[1]: item[2] for item in config.GACHA_TABLE}
            for uid, keys in recent_gacha.items():
                items = ", ".join(_GACHA_NAMES.get(k, k) for k in keys)
                try:
                    await application.bot.send_message(
                        chat_id=uid,
                        text=(
                            f"🔔 서버 점검 중 뽑기 결과를 전달하지 못했을 수 있습니다.\n\n"
                            f"최근 뽑기 결과: {items}\n"
                            f"보상은 정상 지급되어 있습니다. '아이템'과 '상태창'을 확인해주세요."
                        ),
                    )
                except Exception:
                    pass
            logger.info(f"Sent gacha recovery DMs to {len(recent_gacha)} users")
    except Exception:
        logger.warning("Gacha recovery check failed", exc_info=True)

    # Weather는 느릴 수 있으므로 백그라운드로 (시작 차단 안 함)
    weather_city = os.getenv("WEATHER_CITY", "Seoul")
    asyncio.create_task(update_weather(weather_city))

    # 구독 블록체인 모니터 (Base 체인 USDC/USDT Transfer 폴링)
    if config.SUBSCRIPTION_WALLET:
        from services.subscription_service import chain_monitor_loop
        asyncio.create_task(chain_monitor_loop(application.bot))
        logger.info("Subscription chain monitor started")

    # Load tournament chat ID from DB
    config.TOURNAMENT_CHAT_ID = await queries.get_tournament_chat_id()
    if config.TOURNAMENT_CHAT_ID:
        logger.info(f"Tournament chat loaded: {config.TOURNAMENT_CHAT_ID}")

    # Phase 4: 스폰 스케줄링 (Telegram API 호출 필요, 마지막)
    await schedule_all_chats(application)
    logger.info(f"[{time.monotonic()-t0:.1f}s] Startup complete.")

    # Auto-start tournament registration if flag file exists
    if os.path.exists("/tmp/auto_tournament_reg"):
        os.remove("/tmp/auto_tournament_reg")
        from services.tournament_service import start_registration
        asyncio.create_task(start_registration(application))
        logger.info("Auto-started tournament registration (flag file)")

    # Recover tournament registration if restarted during reg window (21:00~22:00 KST)
    from zoneinfo import ZoneInfo
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    reg_hour = config.TOURNAMENT_REG_HOUR      # 21
    if now_kst.hour == reg_hour and not os.path.exists("/tmp/auto_tournament_reg"):
        from services.tournament_service import (
            _tournament_state, _load_registrations_db,
        )
        if not _tournament_state["registering"] and not _tournament_state["running"]:
            # Restore state without re-broadcasting
            chat_id = config.TOURNAMENT_CHAT_ID
            if not chat_id:
                logger.warning("No tournament chat configured, skip recovery")
            else:
                _tournament_state["registering"] = True
                _tournament_state["chat_id"] = chat_id
                # Load previously registered participants from DB
                saved = await _load_registrations_db()
                _tournament_state["participants"] = saved
                logger.info(
                    f"Recovered tournament registration (restarted at {now_kst.strftime('%H:%M')} KST, "
                    f"{len(saved)} participants restored)"
                )

    # Notify recently active users about restart
    # asyncio.create_task(_notify_restart(application.bot))  # DM 알림 비활성화


async def _notify_restart(bot):
    """Send restart notification to recently active users."""
    try:
        active_ids = await queries.get_recently_active_user_ids(minutes=10)
        if not active_ids:
            return
        msg = "🔄 패치가 진행되어 봇이 재시작되었습니다. 정상 운영 중!"
        sent = 0
        for uid in active_ids:
            try:
                await bot.send_message(chat_id=uid, text=msg)
                sent += 1
            except Exception:
                pass
            if sent % 25 == 0 and sent > 0:
                await asyncio.sleep(1)
        logger.info(f"Restart notification sent to {sent}/{len(active_ids)} active users")
    except Exception as e:
        logger.error(f"Restart notification error: {e}")


async def post_shutdown(application: Application):
    """Called on shutdown — resolve active spawns, then close DB."""
    try:
        from services.spawn_service import resolve_unresolved_sessions
        refunded = await resolve_unresolved_sessions(application.bot)
        if refunded:
            for uid, ball_type in refunded:
                try:
                    from utils.helpers import ball_emoji
                    be = ball_emoji("masterball") if ball_type == "master" else ball_emoji("hyperball")
                    bname = "마스터볼" if ball_type == "master" else "하이퍼볼"
                    await application.bot.send_message(
                        chat_id=uid,
                        text=f"{be} 서버 점검으로 인해 {bname}이 환불되었습니다.",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
            logger.info(f"[shutdown] Resolved spawns, refunded {len(refunded)} balls")
        else:
            logger.info("[shutdown] No pending spawns to resolve")
    except Exception as e:
        logger.error(f"[shutdown] Failed to resolve spawns: {e}")
    await close_db()
    logger.info("Database closed.")


async def _check_missed_reset():
    """Run daily reset if it was missed (bot was down at midnight).
    Compares last_daily_reset marker with today's KST date.
    """
    from database.connection import get_db
    pool = await get_db()
    marker = await pool.fetchval(
        "SELECT value FROM bot_settings WHERE key = 'last_daily_reset'"
    )
    today = config.get_kst_today()
    if marker == today:
        logger.info(f"Daily reset already ran for {today}, skipping.")
        return

    logger.info(f"Missed daily reset detected (last={marker}, today={today}). Running now...")
    await asyncio.gather(
        queries.reset_daily_nurture(),
        queries.reset_catch_limits(),
        queries.reset_force_spawn_counts(),
        queries.reset_daily_spawn_counts(),
        queries.cleanup_old_activity(days=7),
    )
    await pool.execute(
        """INSERT INTO bot_settings (key, value) VALUES ('last_daily_reset', $1)
           ON CONFLICT (key) DO UPDATE SET value = $1""",
        today,
    )
    logger.info("Missed daily reset completed.")


# --- Midnight reset job ---

async def _grant_title_buffs():
    """칭호 버프: 일일 마스터볼 지급."""
    if not config.BUFF_TITLE_NAMES:
        return
    from database.connection import get_db
    pool = await get_db()
    buff_users = await pool.fetch(
        "SELECT user_id, title FROM users WHERE title = ANY($1)",
        config.BUFF_TITLE_NAMES,
    )
    for bu in buff_users:
        buff = config.get_title_buff_by_name(bu["title"])
        if buff and buff.get("daily_masterball"):
            await queries.add_master_ball(bu["user_id"], buff["daily_masterball"])
            logger.info(f"Title buff: +{buff['daily_masterball']} masterball to user {bu['user_id']} ({bu['title']})")


async def _grant_subscription_daily(bot):
    """구독자 일일 혜택 지급 + DM 알림."""
    try:
        from database import subscription_queries as sq
        subs = await sq.get_all_active_subscriptions()
        if not subs:
            return
        for sub in subs:
            uid = sub["user_id"]
            tier_cfg = config.SUBSCRIPTION_TIERS.get(sub["tier"], {})
            benefits = tier_cfg.get("benefits", {})
            tier_name = tier_cfg.get("name", "프리미엄")

            reward_lines = []

            # 일일 마스터볼 +1
            daily_master = benefits.get("daily_masterball", 0)
            if daily_master:
                await queries.add_master_ball(uid, daily_master)
                reward_lines.append(f"🔴 마스터볼 +{daily_master}")

            # 일일 하이퍼볼 +5
            daily_hyper = benefits.get("daily_hyperball", 0)
            if daily_hyper:
                await queries.add_hyper_ball(uid, daily_hyper)
                reward_lines.append(f"🔵 하이퍼볼 +{daily_hyper}")

            # 채널장: 일일 아케이드 패스 +1
            daily_arcade = benefits.get("daily_free_arcade_pass", 0)
            if daily_arcade:
                await queries.add_arcade_ticket(uid, daily_arcade)
                reward_lines.append(f"🎰 아케이드 이용권 +{daily_arcade}")

            # 채널장: 일일 이로치 강스권
            daily_shiny_ticket = benefits.get("daily_shiny_ticket", 0)
            if daily_shiny_ticket:
                await queries.add_shiny_spawn_ticket(uid, daily_shiny_ticket)
                reward_lines.append(f"✨ 이로치 강스권 +{daily_shiny_ticket}")

            # DM 알림
            if reward_lines:
                text = (
                    f"💎 <b>{tier_name}</b> 일일 혜택 지급!\n"
                    "━━━━━━━━━━━━━━━\n"
                    + "\n".join(reward_lines)
                )
                try:
                    await bot.send_message(chat_id=uid, text=text, parse_mode="HTML")
                except Exception:
                    pass  # 유저가 봇 차단 등

        logger.info(f"Subscription daily benefits granted to {len(subs)} subscribers")
    except Exception as e:
        logger.error(f"Subscription daily grant error: {e}")


def _kpi_html_template(title: str, body: str, date_str: str) -> str:
    """KPI 리포트용 HTML 템플릿."""
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f0f2f5;color:#1a1a2e;padding:24px;line-height:1.6}}
.report{{max-width:640px;margin:0 auto;background:#fff;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.08);overflow:hidden}}
.header{{background:linear-gradient(135deg,#e53935,#ff6f61);color:#fff;padding:28px 32px;text-align:center}}
.header h1{{font-size:22px;font-weight:700;margin-bottom:4px}}
.header .date{{font-size:14px;opacity:.85}}
.body{{padding:24px 28px}}
.section{{margin-bottom:20px}}
.section-title{{font-size:15px;font-weight:700;color:#e53935;margin-bottom:10px;display:flex;align-items:center;gap:8px;border-bottom:2px solid #fce4ec;padding-bottom:6px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.grid-3{{grid-template-columns:1fr 1fr 1fr}}
.card{{background:#fafafa;border-radius:10px;padding:14px;text-align:center;border:1px solid #f0f0f0}}
.card .label{{font-size:11px;color:#888;margin-bottom:4px;text-transform:uppercase;letter-spacing:.5px}}
.card .value{{font-size:22px;font-weight:700;color:#1a1a2e}}
.card .value.accent{{color:#e53935}}
.card .sub{{font-size:11px;color:#999;margin-top:2px}}
.channel-list{{list-style:none}}
.channel-list li{{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-radius:8px;margin-bottom:4px;background:#fafafa;font-size:13px}}
.channel-list li:nth-child(1){{background:#fff3e0;font-weight:600}}
.channel-list li:nth-child(2){{background:#fce4ec}}
.channel-list .rank{{font-weight:700;color:#e53935;min-width:24px}}
.channel-list .cnt{{color:#666;font-size:12px}}
.footer{{text-align:center;padding:16px;color:#aaa;font-size:11px;border-top:1px solid #f0f0f0}}
</style></head><body>
<div class="report">
<div class="header"><h1>{title}</h1><div class="date">{date_str}</div></div>
<div class="body">{body}</div>
<div class="footer">TGPoke KPI Report &mdash; auto-generated</div>
</div></body></html>"""


def _delta_badge(today, yesterday, suffix="", reverse=False):
    """전일 대비 변화 뱃지 HTML. reverse=True면 감소가 긍정(예: 마볼 소비)."""
    if yesterday is None or yesterday == 0:
        return ""
    diff = today - yesterday
    pct = round(diff / yesterday * 100)
    if diff == 0:
        return '<span style="color:#888;font-size:11px">→ 0%</span>'
    color = "#4caf50" if (diff > 0) != reverse else "#e53935"
    arrow = "▲" if diff > 0 else "▼"
    return f'<span style="color:{color};font-size:11px;font-weight:600">{arrow} {abs(pct)}%{suffix}</span>'


def _bp_daily_chart(bp_daily: list[dict]) -> str:
    """주간 BP 뽑기 소비 일별 바 차트 HTML."""
    if not bp_daily:
        return ""
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    max_spent = max((d.get("spent", 0) for d in bp_daily), default=1) or 1
    bars = ""
    for d in bp_daily:
        spent = d.get("spent", 0)
        pulls = d.get("pulls", 0)
        pct = round(spent / max_spent * 100)
        try:
            from datetime import datetime as _dt
            day_dt = _dt.strptime(d["date"], "%Y-%m-%d")
            day_label = weekdays[day_dt.weekday()]
            date_label = day_dt.strftime("%m/%d")
        except Exception:
            day_label = "?"
            date_label = d["date"][-5:]
        bars += (
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">'
            f'<span style="min-width:50px;font-size:12px;color:#888">{date_label}({day_label})</span>'
            f'<div style="background:linear-gradient(90deg,#e53935,#ff6f61);height:22px;border-radius:4px;width:{pct}%;min-width:2px"></div>'
            f'<span style="font-size:13px;font-weight:600">-{spent:,} ({pulls}회)</span>'
            f'</div>'
        )
    return f"""<div class="section">
<div class="section-title">🎰 일별 BP 뽑기 소비</div>
{bars}
</div>"""


def _get_today_patches() -> list[str]:
    """오늘 날짜의 git 커밋 메시지 목록 (feat/fix만), 주요 패치 우선 정렬."""
    import subprocess
    try:
        today_str = config.get_kst_now().strftime("%Y-%m-%d")
        result = subprocess.run(
            ["git", "log", f"--since={today_str} 00:00", f"--until={today_str} 23:59",
             "--pretty=format:%s", "--no-merges"],
            capture_output=True, text=True, timeout=5, cwd="/home/ubuntu/pokemon-bot",
        )
        lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
        patches = [l for l in lines if any(l.startswith(p) for p in ("feat:", "fix:", "refactor:"))]
        # 주요 패치 우선 정렬: feat > fix > refactor, 내용이 긴 것(상세한 것) 우선
        def _patch_priority(p: str) -> tuple:
            prefix = p.split(":")[0]
            type_score = {"feat": 0, "fix": 1, "refactor": 2}.get(prefix, 3)
            msg = p.split(":", 1)[1].strip() if ":" in p else p
            # 주요 키워드 부스트
            boost = 0
            for kw in ("시스템", "추가", "도입", "신규", "개편", "리뉴얼", "엔진"):
                if kw in msg:
                    boost -= 1
            return (type_score + boost, -len(msg))
        patches.sort(key=_patch_priority)
        return patches
    except Exception:
        return []


async def _build_gen4_report_section(pool) -> str:
    """Gen4(4세대) 업데이트 전후 비교 섹션 HTML 생성. 업데이트일(2026-03-16) 이후에만 표시."""
    from datetime import timezone, timedelta as _td
    _KST = timezone(_td(hours=9))
    _now = config.get_kst_now()
    _today_start = _now.replace(hour=0, minute=0, second=0, microsecond=0)
    _today_end = _today_start + _td(days=1)
    _before_start = _today_start - _td(days=7)

    rarity_ko = {"common": "커먼", "rare": "레어", "epic": "에픽",
                  "legendary": "전설", "ultra_legendary": "초전설"}
    rarity_cls = {"common": "#888", "rare": "#2196f3", "epic": "#9c27b0",
                  "legendary": "#ff9800", "ultra_legendary": "#e53935"}

    # ── Gen4 스폰/포획 (오늘) ──
    g4_row = await pool.fetchrow(
        """SELECT COUNT(*) as s, COUNT(caught_by_user_id) as c
           FROM spawn_log WHERE spawned_at >= $1 AND spawned_at < $2
           AND pokemon_id >= 387 AND pokemon_id <= 493""",
        _today_start, _today_end)
    g4_spawns = g4_row["s"] if g4_row else 0
    g4_catches = g4_row["c"] if g4_row else 0
    g4_catch_rate = round(g4_catches / max(g4_spawns, 1) * 100, 1)

    total_row = await pool.fetchrow(
        "SELECT COUNT(*) as s FROM spawn_log WHERE spawned_at >= $1 AND spawned_at < $2",
        _today_start, _today_end)
    total_spawns = total_row["s"] if total_row else 1
    g4_pct = round(g4_spawns / max(total_spawns, 1) * 100, 1)

    # 7일 평균 (before)
    avg7_row = await pool.fetchrow(
        "SELECT COUNT(*)::float/7 as s, COUNT(caught_by_user_id)::float/7 as c FROM spawn_log WHERE spawned_at >= $1 AND spawned_at < $2",
        _before_start, _today_start)
    avg7_spawns = round(avg7_row["s"]) if avg7_row else 0
    avg7_catches = round(avg7_row["c"]) if avg7_row else 0
    avg7_rate = round(avg7_catches / max(avg7_spawns, 1) * 100, 1)

    # ── Gen4 인기 Top 10 ──
    g4_popular = await pool.fetch(
        """SELECT sl.pokemon_id, pm.name_ko, pm.rarity, COUNT(*) as cnt
           FROM spawn_log sl JOIN pokemon_master pm ON pm.id = sl.pokemon_id
           WHERE sl.spawned_at >= $1 AND sl.spawned_at < $2
           AND sl.pokemon_id >= 387 AND sl.pokemon_id <= 493
           AND sl.caught_by_user_id IS NOT NULL
           GROUP BY sl.pokemon_id, pm.name_ko, pm.rarity ORDER BY cnt DESC LIMIT 10""",
        _today_start, _today_end)

    popular_html = ""
    for i, p in enumerate(g4_popular, 1):
        r_color = rarity_cls.get(p["rarity"], "#888")
        r_name = rarity_ko.get(p["rarity"], p["rarity"])
        popular_html += (
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:6px 10px;background:#fafafa;border-radius:6px;margin-bottom:3px;font-size:13px">'
            f'<span><b style="color:#e53935;margin-right:6px">{i}</b>'
            f'#{p["pokemon_id"]} <b>{p["name_ko"]}</b> '
            f'<span style="color:{r_color};font-size:11px">{r_name}</span></span>'
            f'<span style="font-weight:700">{p["cnt"]}마리</span></div>')
    if not popular_html:
        popular_html = '<div style="font-size:13px;color:#888;text-align:center;padding:12px">아직 포획 데이터 없음</div>'

    # ── Gen4 레어리티 분포 ──
    g4_rarity = await pool.fetch(
        """SELECT pm.rarity, COUNT(*) as cnt
           FROM spawn_log sl JOIN pokemon_master pm ON pm.id = sl.pokemon_id
           WHERE sl.spawned_at >= $1 AND sl.spawned_at < $2
           AND sl.pokemon_id >= 387 AND sl.pokemon_id <= 493
           GROUP BY pm.rarity ORDER BY cnt DESC""",
        _today_start, _today_end)
    g4_rarity_map = {r["rarity"]: r["cnt"] for r in g4_rarity}
    g4_total = sum(g4_rarity_map.values()) or 1

    rarity_bars = ""
    for rk in ["common", "rare", "epic", "legendary", "ultra_legendary"]:
        cnt = g4_rarity_map.get(rk, 0)
        pct = round(cnt / g4_total * 100, 1)
        color = rarity_cls.get(rk, "#888")
        rarity_bars += (
            f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">'
            f'<span style="min-width:50px;font-size:11px;color:{color};font-weight:700;text-align:right">{rarity_ko.get(rk, rk)}</span>'
            f'<div style="flex:1;height:16px;background:#f5f5f5;border-radius:3px;overflow:hidden">'
            f'<div style="height:100%;width:{pct}%;background:{color};border-radius:3px;opacity:.7"></div></div>'
            f'<span style="font-size:11px;min-width:60px">{cnt:,} ({pct}%)</span></div>')

    # ── Gen4 보유 현황 ──
    g4_owners = await pool.fetchval(
        "SELECT COUNT(DISTINCT user_id) FROM user_pokemon WHERE pokemon_id >= 387 AND pokemon_id <= 493") or 0
    g4_total_owned = await pool.fetchval(
        "SELECT COUNT(*) FROM user_pokemon WHERE pokemon_id >= 387 AND pokemon_id <= 493") or 0
    g4_shiny = await pool.fetchval(
        "SELECT COUNT(*) FROM user_pokemon WHERE pokemon_id >= 387 AND pokemon_id <= 493 AND is_shiny = true") or 0

    # ── Gen4 전설/초전설 ──
    g4_legends = await pool.fetch(
        """SELECT pm.name_ko, pm.rarity, COUNT(*) as cnt
           FROM user_pokemon up JOIN pokemon_master pm ON pm.id = up.pokemon_id
           WHERE up.pokemon_id >= 387 AND up.pokemon_id <= 493
           AND pm.rarity IN ('legendary', 'ultra_legendary')
           GROUP BY pm.name_ko, pm.rarity ORDER BY pm.rarity DESC, cnt DESC""")
    legend_items = ""
    for p in g4_legends:
        r_color = rarity_cls.get(p["rarity"], "#888")
        r_name = rarity_ko.get(p["rarity"], "")
        legend_items += (
            f'<span style="display:inline-block;padding:3px 8px;background:#fafafa;border-radius:6px;'
            f'margin:2px;font-size:12px;border:1px solid #f0f0f0">'
            f'<b style="color:{r_color}">{p["name_ko"]}</b> ×{p["cnt"]}</span>')
    if not legend_items:
        legend_items = '<span style="font-size:12px;color:#888">아직 포획 기록 없음</span>'

    # ── 세대별 도감 현황 ──
    dex_stats = await pool.fetch(
        """SELECT
             CASE WHEN pokemon_id <= 151 THEN 1 WHEN pokemon_id <= 251 THEN 2
                  WHEN pokemon_id <= 386 THEN 3 ELSE 4 END as gen,
             COUNT(DISTINCT pokemon_id) as species, COUNT(*) as total
           FROM user_pokemon GROUP BY gen ORDER BY gen""")
    gen_totals = {1: 151, 2: 100, 3: 135, 4: 107}
    dex_cards = ""
    for row in dex_stats:
        g = row["gen"]
        total = gen_totals.get(g, 0)
        species = row["species"]
        comp = round(species / max(total, 1) * 100, 1)
        is_g4 = g == 4
        style = 'border:2px solid #e53935' if is_g4 else ''
        dex_cards += (
            f'<div class="card" style="{style}">'
            f'<div class="label">{"🌟 " if is_g4 else ""}{g}세대</div>'
            f'<div class="value" style="font-size:18px;{"color:#e53935" if is_g4 else ""}">{species}/{total}</div>'
            f'<div class="sub">{comp}% · {row["total"]:,}마리</div></div>')

    # ── 조립 ──
    section = f"""
<div class="section" style="border:2px solid #e8eaf6;border-radius:12px;padding:16px;margin-bottom:20px;background:linear-gradient(135deg,#fafafa,#f3e5f5 50%,#e8eaf6)">
<div class="section-title" style="color:#4a148c;border-bottom-color:#ce93d8">🌟 v3.0 — 4세대(신오) 업데이트 보고서</div>

<div style="font-size:12px;color:#666;margin-bottom:12px;padding:8px;background:rgba(255,255,255,.7);border-radius:6px">
📌 <b>업데이트 내용:</b> 107종 추가(387~493), 분기진화 2종, 크로스세대 진화 18종, 한카리아스/레지기가스 에픽 조정, 커스텀이모지 전면 적용, 챌린지 3분
</div>

<div style="font-size:11px;color:#888;margin-bottom:8px">Before = 7일 평균 | After = 오늘 | Gen4 = 387~493번</div>

<div class="grid grid-3" style="margin-bottom:12px">
<div class="card"><div class="label">Gen4 스폰</div><div class="value accent">{g4_spawns:,}</div><div class="sub">전체의 {g4_pct}%</div></div>
<div class="card"><div class="label">Gen4 포획</div><div class="value" style="color:#4caf50">{g4_catches:,}</div><div class="sub">포획률 {g4_catch_rate}%</div></div>
<div class="card"><div class="label">Gen4 이로치</div><div class="value" style="color:#ff9800">{g4_shiny}</div></div>
</div>

<div class="grid" style="margin-bottom:12px">
<div class="card"><div class="label">포획률 변화</div><div class="value" style="font-size:16px">{avg7_rate}% → {g4_catch_rate}%</div><div class="sub">7일 평균 → Gen4</div></div>
<div class="card"><div class="label">Gen4 보유자</div><div class="value" style="color:#1565c0">{g4_owners:,}명</div><div class="sub">총 {g4_total_owned:,}마리</div></div>
</div>

<div style="margin-bottom:12px">
<div style="font-size:13px;font-weight:700;color:#4a148c;margin-bottom:6px">🏆 Gen4 인기 포켓몬 Top 10</div>
{popular_html}
</div>

<div style="margin-bottom:12px">
<div style="font-size:13px;font-weight:700;color:#4a148c;margin-bottom:6px">📊 Gen4 레어리티 분포</div>
{rarity_bars}
</div>

<div style="margin-bottom:12px">
<div style="font-size:13px;font-weight:700;color:#4a148c;margin-bottom:6px">👑 Gen4 전설 / 초전설</div>
<div>{legend_items}</div>
</div>

<div style="margin-bottom:8px">
<div style="font-size:13px;font-weight:700;color:#4a148c;margin-bottom:6px">📖 세대별 도감 현황</div>
<div class="grid" style="grid-template-columns:1fr 1fr 1fr 1fr">{dex_cards}</div>
</div>

</div>"""

    return section


async def _send_daily_kpi_report(context):
    """매일 23:55 KST: 일일 KPI 리포트를 HTML 파일로 관리자 DM 발송."""
    import io
    try:
        d = await queries.kpi_daily_snapshot()
        eco = d["economy"]

        # 스냅샷 저장 + D+1/D+7 리텐션 계산
        retention = await queries.save_kpi_snapshot(d)
        d1_ret = retention.get("d1_retention")
        d7_ret = retention.get("d7_retention")

        # 전일 스냅샷 조회
        prev = await queries.get_previous_snapshot()

        catch_rate = d["catch_rate"]

        # ── 전일 대비 섹션 ──
        if prev:
            delta_html = f"""
<div class="section">
<div class="section-title">📊 전일 대비</div>
<div class="grid grid-3">
<div class="card"><div class="label">DAU</div><div class="value">{d['dau']}</div>{_delta_badge(d['dau'], prev.get('dau'))}</div>
<div class="card"><div class="label">스폰</div><div class="value">{d['spawns']:,}</div>{_delta_badge(d['spawns'], prev.get('spawns'))}</div>
<div class="card"><div class="label">포획</div><div class="value">{d['catches']:,}</div>{_delta_badge(d['catches'], prev.get('catches'))}</div>
<div class="card"><div class="label">배틀</div><div class="value">{d['battles']}</div>{_delta_badge(d['battles'], prev.get('battles'))}</div>
<div class="card"><div class="label">신규가입</div><div class="value">{d['new_users']}</div>{_delta_badge(d['new_users'], prev.get('new_users'))}</div>
<div class="card"><div class="label">이로치</div><div class="value">{d['shiny_caught']}</div>{_delta_badge(d['shiny_caught'], prev.get('shiny_caught'))}</div>
</div></div>"""
        else:
            delta_html = ""

        # ── 오늘 패치 섹션 ──
        patches = _get_today_patches()
        if patches:
            patch_items = ""
            feat_count = sum(1 for p in patches if p.startswith("feat:"))
            fix_count = sum(1 for p in patches if p.startswith("fix:"))
            # 중복 메시지 제거 (같은 기능 반복 커밋 시)
            seen_msgs = set()
            unique_patches = []
            for p in patches:
                msg = p.split(":", 1)[1].strip() if ":" in p else p
                # 핵심 키워드로 중복 판별 (앞 10자 기준)
                key = msg[:10]
                if key not in seen_msgs:
                    seen_msgs.add(key)
                    unique_patches.append(p)
            max_show = 5
            for p in unique_patches[:max_show]:
                prefix = p.split(":")[0]
                emoji = "🆕" if prefix == "feat" else "🔧" if prefix == "fix" else "♻️"
                msg = p.split(":", 1)[1].strip() if ":" in p else p
                patch_items += f'<div style="display:flex;gap:6px;align-items:start;margin-bottom:6px;font-size:13px"><span>{emoji}</span><span>{msg}</span></div>'
            remaining = len(patches) - max_show
            if remaining > 0:
                patch_items += f'<div style="font-size:12px;color:#888;margin-top:4px">외 {remaining}건</div>'
            patch_html = f"""
<div class="section">
<div class="section-title">🛠️ 오늘 패치 ({feat_count} feat / {fix_count} fix)</div>
{patch_items}
</div>"""
        else:
            patch_html = '<div class="section"><div class="section-title">🛠️ 오늘 패치</div><div style="font-size:13px;color:#888">배포 없음</div></div>'

        # ── Gen4 업데이트 보고서 섹션 ──
        gen4_html = ""
        try:
            # Gen4가 DB에 시딩되어 있을 때만 표시
            _pool = await get_db()
            g4_count = await _pool.fetchval(
                "SELECT COUNT(*) FROM pokemon_master WHERE id >= 387 AND id <= 493")
            if g4_count and g4_count >= 100:
                gen4_html = await _build_gen4_report_section(_pool)
        except Exception as _e:
            logger.warning(f"Gen4 report section skipped: {_e}")

        # ── 마일스톤 로드 ──
        milestones_today = []
        milestones_recent = []
        try:
            import json as _json
            ms_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "milestones.json")
            with open(ms_path, "r", encoding="utf-8") as f:
                all_ms = _json.load(f)
            today_str_ms = d["date"]
            from datetime import datetime as _dt, timedelta as _td
            for ms in all_ms:
                if ms["date"] == today_str_ms:
                    milestones_today.append(ms)
                # 최근 7일 이내 마일스톤
                ms_date = _dt.strptime(ms["date"], "%Y-%m-%d")
                today_date = _dt.strptime(today_str_ms, "%Y-%m-%d")
                if 0 < (today_date - ms_date).days <= 7:
                    milestones_recent.append(ms)
        except Exception:
            pass

        # ── 인사이트 섹션 ──
        insights = []

        # 오늘 마일스톤
        for ms in milestones_today:
            tag_emoji = {"content": "🎮", "system": "⚙️", "balance": "⚖️", "monetization": "💎", "event": "🎪"}.get(ms["tag"], "📌")
            insights.append(f"{tag_emoji} <b>오늘 마일스톤:</b> {ms['title']}")

        # ── 1. 유저 활성도 분석 ──
        if prev:
            dau_diff = d["dau"] - prev.get("dau", 0)
            dau_pct = round(dau_diff / max(prev.get("dau", 1), 1) * 100, 1)
            new_users = d.get("new_users", 0)
            prev_new = prev.get("new_users", 0)

            # 최근 마일스톤 영향 분석
            if milestones_recent:
                recent_titles = [ms["title"] for ms in milestones_recent[:3]]
                context_str = " / ".join(recent_titles)
                if dau_diff > 0:
                    insights.append(
                        f"📈 <b>DAU +{dau_diff}명({dau_pct:+.1f}%)</b>. "
                        f"최근 업데이트({context_str}) 영향. "
                        f"신규 {new_users}명 유입, 복귀 유저 확인 필요.")
                elif dau_diff < 0:
                    insights.append(
                        f"📉 <b>DAU {dau_diff}명({dau_pct:+.1f}%)</b>. "
                        f"최근 업데이트({context_str}) 이후 안정화 구간. "
                        f"신규 {new_users}명(전일 {prev_new}명).")
            elif patches:
                if dau_diff > 0:
                    insights.append(
                        f"📈 <b>DAU +{dau_diff}명({dau_pct:+.1f}%)</b>. "
                        f"오늘 패치 {len(patches)}건 영향 가능. "
                        f"신규 {new_users}명 유입.")
                elif dau_diff < 0:
                    insights.append(
                        f"📉 <b>DAU {dau_diff}명({dau_pct:+.1f}%)</b>. "
                        f"자연 이탈 또는 콘텐츠 소진 구간. "
                        f"신규 {new_users}명(전일 {prev_new}명), 활성 유저 유지 전략 필요.")
                else:
                    insights.append(f"📊 DAU 전일 동일({d['dau']}명). 안정 구간.")
            else:
                if dau_diff != 0:
                    direction = "증가" if dau_diff > 0 else "감소"
                    insights.append(f"📊 DAU {dau_diff:+d}명 {direction}({dau_pct:+.1f}%). 신규 {new_users}명.")

        # ── 2. 리텐션 분석 ──
        if d1_ret is not None or d7_ret is not None:
            ret_parts = []
            if d1_ret is not None:
                d1_status = "🟢 양호" if d1_ret >= 70 else "🟡 보통" if d1_ret >= 50 else "🔴 주의"
                ret_parts.append(f"D+1 {d1_ret}%({d1_status})")
            if d7_ret is not None:
                d7_status = "🟢 양호" if d7_ret >= 40 else "🟡 보통" if d7_ret >= 25 else "🔴 주의"
                ret_parts.append(f"D+7 {d7_ret}%({d7_status})")
            ret_str = " / ".join(ret_parts)
            insights.append(f"🔄 <b>리텐션:</b> {ret_str}")
            if d1_ret is not None and d1_ret < 50:
                insights.append("  └ D+1 50% 미만 — 첫날 경험 개선 또는 복귀 인센티브 검토.")
            if d7_ret is not None and d7_ret >= 40:
                insights.append("  └ D+7 40%+ — 핵심 루프가 잘 작동하는 신호. 장기 콘텐츠 준비 시점.")

        # ── 3. 포획/배틀 활성도 ──
        if prev:
            catch_prev = prev.get("catches", 0)
            battle_prev = prev.get("battles", 0)

            # 포획률 변동
            if catch_prev and d["catches"]:
                prev_rate = round(catch_prev / max(prev.get("spawns", 1), 1) * 100, 1)
                rate_diff = round(catch_rate - prev_rate, 1)
                if abs(rate_diff) > 2:
                    direction = "상승" if rate_diff > 0 else "하락"
                    insights.append(
                        f"🎯 <b>포획률 {prev_rate}% → {catch_rate}%({rate_diff:+.1f}%p {direction})</b>. "
                        f"스폰 {d['spawns']}회 중 {d['catches']}회 포획.")

            # 배틀 활성도
            if d["battles"] > 0:
                if battle_prev:
                    bt_diff = d["battles"] - battle_prev
                    bt_pct = round(bt_diff / max(battle_prev, 1) * 100, 1)
                    if abs(bt_pct) > 20:
                        insights.append(
                            f"⚔️ 배틀 {battle_prev} → {d['battles']}건({bt_pct:+.1f}%). "
                            f"{'배틀 수요 증가 — 보상/콘텐츠 효과.' if bt_diff > 0 else '배틀 감소 — 매칭 소요시간 또는 보상 점검.'}")
            elif d["dau"] > 0:
                insights.append("⚔️ <b>배틀 0건</b> — 매칭 시스템 점검 또는 배틀 동기 부여 필요.")

            # 1인당 활동량
            if d["dau"] > 0 and prev.get("dau", 0) > 0:
                actions_per_user = round((d["catches"] + d["battles"]) / d["dau"], 1)
                prev_actions = round((catch_prev + battle_prev) / max(prev.get("dau", 1), 1), 1)
                if abs(actions_per_user - prev_actions) > 1:
                    insights.append(
                        f"👤 1인당 활동량 {prev_actions} → {actions_per_user}회/일 "
                        f"({'참여도 상승' if actions_per_user > prev_actions else '참여도 하락'}).")

        # ── 4. BP 경제 분석 ──
        bp_earned = d.get("bp_earned", 0)
        bp_total_spent = d.get("bp_total_spent", 0)
        gacha_spent = d.get("gacha_bp_spent", 0)
        gacha_pulls = d.get("gacha_pulls", 0)
        bp_circulation = eco.get("bp_circulation", 0)
        bp_avg = eco.get("bp_avg", 0)
        bp_sources = d.get("bp_sources", {})
        bp_net = bp_earned - bp_total_spent

        source_labels = {
            "battle": "⚔️ 배틀", "ranked_battle": "🏟️ 랭크전", "catch": "🎯 포획",
            "tournament": "🏆 토너먼트", "mission": "📋 미션", "bet_win": "🎲 야차(승)",
            "gacha_refund": "🎰 뽑기환급", "gacha_jackpot": "💎 뽑기잭팟",
            "ranked_reward": "🏅 시즌보상", "admin": "🔧 관리자",
            "shop_masterball": "🔴 상점(마볼)", "shop_hyperball": "🔵 상점(하볼)",
            "shop_gacha_ticket": "🎫 상점(뽑기권)", "shop_arcade_speed": "⚡ 상점(속도)",
            "shop_arcade_extend": "⏱️ 상점(연장)",
            "bet_refund": "🎲 야차(환불)", "trade_refund": "🔄 교환(환불)",
        }

        # BP 소스별 카드 HTML 생성
        _bp_src_order = ["battle", "ranked_battle", "catch", "tournament", "mission", "bet_win",
                         "gacha_refund", "gacha_jackpot", "ranked_reward", "admin"]
        _bp_src_cards = []
        for _src in _bp_src_order:
            if _src in bp_sources and bp_sources[_src]["earned"] > 0:
                _lbl = source_labels.get(_src, _src)
                _val = bp_sources[_src]["earned"]
                _bp_src_cards.append(
                    f'<div class="card"><div class="label">{_lbl}</div>'
                    f'<div class="value" style="font-size:18px;color:#4caf50">+{_val:,}</div></div>')
        # 나머지 소스 (위 목록에 없는 것)
        for _src, _v in sorted(bp_sources.items(), key=lambda x: x[1]["earned"], reverse=True):
            if _src not in _bp_src_order and _v["earned"] > 0:
                _lbl = source_labels.get(_src, _src)
                _bp_src_cards.append(
                    f'<div class="card"><div class="label">{_lbl}</div>'
                    f'<div class="value" style="font-size:18px;color:#4caf50">+{_v["earned"]:,}</div></div>')
        if _bp_src_cards:
            _cols = "1fr 1fr 1fr" if len(_bp_src_cards) >= 3 else "1fr " * len(_bp_src_cards)
            bp_source_cards_html = (
                f'<div style="margin-top:6px;font-size:11px;color:#888;margin-bottom:4px">📈 소스별 생성</div>'
                f'<div class="grid" style="grid-template-columns:{_cols.strip()}">'
                + "".join(_bp_src_cards) + '</div>')
        else:
            bp_source_cards_html = ""

        # 전일 BP 유통량 (스냅샷에서)
        prev_bp_circulation = prev.get("bp_circulation") if prev else None
        bp_circ_delta = bp_circulation - prev_bp_circulation if prev_bp_circulation is not None else None
        prev_bp_earned = prev.get("bp_earned", 0) if prev else 0

        # --- BP 경제 요약 ---
        insights.append(f"💰 <b>BP 경제:</b>")

        # 유통량 + 전일 대비
        circ_delta_str = ""
        if bp_circ_delta is not None:
            circ_pct = round(bp_circ_delta / max(prev_bp_circulation, 1) * 100, 1)
            circ_delta_str = f" ({bp_circ_delta:+,}, {circ_pct:+.1f}%)"
        insights.append(
            f"  └ 총 유통량 <b>{bp_circulation:,}</b>BP{circ_delta_str}, "
            f"보유자 평균 {bp_avg:,}BP")

        # 당일 생성/소각
        if bp_earned > 0 or bp_total_spent > 0:
            insights.append(
                f"  └ 당일 생성 <b>+{bp_earned:,}</b> / 소각 <b>-{bp_total_spent:,}</b> / "
                f"순변동 <b>{bp_net:+,}</b>BP")

            # 전일 대비 생성량 변화
            if prev_bp_earned > 0:
                earn_diff = bp_earned - prev_bp_earned
                earn_pct = round(earn_diff / max(prev_bp_earned, 1) * 100, 1)
                if abs(earn_pct) > 10:
                    insights.append(
                        f"  └ BP 생성 전일 대비 {earn_pct:+.1f}% "
                        f"({'📈 증가' if earn_diff > 0 else '📉 감소'})")

        # 소스별 상세
        if bp_sources:
            earn_parts = []
            spend_parts = []
            for src, vals in sorted(bp_sources.items(), key=lambda x: x[1]["earned"], reverse=True):
                label = source_labels.get(src, src)
                if vals["earned"] > 0:
                    earn_parts.append(f"{label} +{vals['earned']:,}")
                if vals["spent"] > 0:
                    spend_parts.append(f"{label} -{vals['spent']:,}")
            if earn_parts:
                insights.append(f"  └ 📈 <b>생성 상세:</b> {' / '.join(earn_parts[:6])}")
            if spend_parts:
                insights.append(f"  └ 📉 <b>소각 상세:</b> {' / '.join(spend_parts[:5])}")

            # 생성 비중 분석: 가장 큰 소스
            total_earned = sum(v["earned"] for v in bp_sources.values())
            if total_earned > 0:
                top_src = max(bp_sources.items(), key=lambda x: x[1]["earned"])
                top_pct = round(top_src[1]["earned"] / total_earned * 100, 1)
                top_label = source_labels.get(top_src[0], top_src[0])
                if top_pct > 60:
                    insights.append(
                        f"  └ ⚠️ <b>{top_label}</b>이 생성의 {top_pct}% 차지 — 소스 편중 주의")

        # 소각률 평가
        if bp_total_spent > 0:
            sink_ratio = round(bp_total_spent / max(bp_earned, 1) * 100, 1)
            if sink_ratio > 150:
                insights.append(
                    f"  └ 🔴 <b>소각률 {sink_ratio}%</b> (생성 대비) — 디플레이션 위험. "
                    f"유저 BP 고갈 → 활동 저하 우려.")
            elif sink_ratio > 100:
                insights.append(
                    f"  └ 🟡 소각률 {sink_ratio}% — 건전한 싱크 작동 중. 인플레 억제 ✓")
            else:
                insights.append(
                    f"  └ 🟢 소각률 {sink_ratio}% — 생성 우세. 추가 싱크 검토 가능.")

        # 1인당 BP 경제
        if d["dau"] > 0:
            bp_per_dau = round(bp_circulation / d["dau"], 0)
            earn_per_dau = round(bp_earned / d["dau"], 1) if bp_earned > 0 else 0
            spend_per_dau = round(bp_total_spent / d["dau"], 1) if bp_total_spent > 0 else 0
            insights.append(
                f"  └ 👤 DAU당 보유 {bp_per_dau:,.0f}BP, "
                f"생성 +{earn_per_dau:.0f}, 소각 -{spend_per_dau:.0f}")
            if bp_per_dau > 2000:
                insights.append(f"     └ ⚠️ 고인플레 구간. 추가 싱크 필요.")
            elif bp_per_dau < 300:
                insights.append(f"     └ ⚠️ BP 부족 우려. 획득 경로 확인.")

        # 뽑기 분석
        gacha_dist = d.get("gacha_distribution", {})
        if gacha_pulls > 0:
            avg_cost = gacha_spent // max(gacha_pulls, 1)
            gacha_per_dau = round(gacha_pulls / max(d["dau"], 1), 1)
            insights.append(
                f"🎰 <b>뽑기:</b> {gacha_pulls:,}회 ({gacha_spent:,}BP), "
                f"회당 {avg_cost}BP, DAU당 {gacha_per_dau:.1f}회")
            if gacha_dist:
                top_items = sorted(gacha_dist.items(), key=lambda x: x[1], reverse=True)[:3]
                dist_str = ", ".join(f"{k}({v}회)" for k, v in top_items)
                rare_items = {k: v for k, v in gacha_dist.items() if k in ("shiny_ticket", "shiny_egg", "bp_jackpot", "iv_reroll_one")}
                if rare_items:
                    rare_str = ", ".join(f"{k}({v})" for k, v in rare_items.items())
                    insights.append(f"  └ TOP: {dist_str} | 레어: {rare_str}")
                else:
                    insights.append(f"  └ TOP: {dist_str}")
        elif gacha_dist:
            insights.append(f"🎰 뽑기 {gacha_pulls}회 (뽑기 활동 없음)")

        insight_html = ""
        if insights:
            items = "".join(f'<li style="margin-bottom:6px;font-size:13px">{ins}</li>' for ins in insights)
            insight_html = f"""
<div class="section">
<div class="section-title">💡 인사이트</div>
<ul style="list-style:none;padding:0">{items}</ul>
</div>"""

        # ── 시간대별 활성 그래프 ──
        hourly = d.get("hourly", {})
        hourly_html = ""
        if hourly:
            max_users = max(hourly.values()) or 1
            peak_hr = max(hourly, key=hourly.get)
            bars = ""
            for hr in range(24):
                users = hourly.get(hr, 0)
                pct = round(users / max_users * 100) if max_users else 0
                is_peak = hr == peak_hr and users > 0
                bar_color = "#e53935" if is_peak else "#ffcdd2" if pct > 0 else "#f5f5f5"
                label_style = "font-weight:700;color:#e53935" if is_peak else "color:#888"
                bars += (
                    f'<div style="display:flex;flex-direction:column;align-items:center;flex:1;min-width:0">'
                    f'<div style="width:100%;background:{bar_color};height:{max(pct, 2)}px;border-radius:2px 2px 0 0;min-height:2px"></div>'
                    f'<div style="font-size:9px;{label_style};margin-top:2px">{hr}</div>'
                    f'</div>'
                )
            hourly_html = f"""
<div class="section">
<div class="section-title">🕐 시간대별 활성 (피크: {peak_hr}시, {hourly.get(peak_hr, 0)}명)</div>
<div style="display:flex;gap:1px;align-items:flex-end;height:80px;padding:0 4px">{bars}</div>
</div>"""

        # ── Top 채널 ──
        top_html = ""
        if d["top_chats"]:
            items = ""
            for i, ch in enumerate(d["top_chats"], 1):
                title = ch.get("chat_title", "?")[:15]
                members = ch.get("member_count", 0)
                items += f'<li><span class="rank">{i}</span><span>{title}</span><span class="cnt">{ch["today_spawns"]}회 · {members}명</span></li>'
            top_html = f"""<div class="section">
<div class="section-title">📈 Top 채널 (스폰 기준)</div>
<ul class="channel-list">{items}</ul></div>"""

        body = f"""
{delta_html}

<div class="section">
<div class="section-title">👥 유저</div>
<div class="grid grid-3">
<div class="card"><div class="label">DAU</div><div class="value accent">{d['dau']}</div></div>
<div class="card"><div class="label">신규가입</div><div class="value">{d['new_users']}</div></div>
<div class="card"><div class="label">실시간(1h)</div><div class="value">{d['active_1h']}</div></div>
</div>
<div class="grid" style="margin-top:8px">
<div class="card"><div class="label">총 유저</div><div class="value">{d['total_users']}</div></div>
<div class="card"><div class="label">D+1 리텐션</div><div class="value accent">{f'{d1_ret}%' if d1_ret is not None else '-'}</div></div>
</div>
<div style="margin-top:8px"><div class="card"><div class="label">D+7 리텐션</div><div class="value" style="color:#ff9800">{f'{d7_ret}%' if d7_ret is not None else '수집 중'}</div><div class="sub">7일 후부터 표시</div></div></div>
</div>

<div class="section">
<div class="section-title">🎯 스폰 / 포획</div>
<div class="grid">
<div class="card"><div class="label">총 스폰</div><div class="value">{d['spawns']:,}</div></div>
<div class="card"><div class="label">포획</div><div class="value accent">{d['catches']:,}</div><div class="sub">포획률 {catch_rate}%</div></div>
<div class="card"><div class="label">이로치 포획</div><div class="value" style="color:#ff9800">{d['shiny_caught']}</div></div>
<div class="card"><div class="label">마스터볼 사용</div><div class="value">{d['mb_used']}</div></div>
</div></div>

<div class="section">
<div class="section-title">⚔️ 배틀</div>
<div class="grid grid-3">
<div class="card"><div class="label">총 배틀</div><div class="value">{d['battles']}</div></div>
<div class="card"><div class="label">랭크전</div><div class="value">{d['ranked_battles']}</div></div>
<div class="card"><div class="label">BP 생성</div><div class="value">+{d['bp_earned']:,}</div></div>
</div></div>

<div class="section">
<div class="section-title">💰 BP 흐름 (당일)</div>
<div class="grid grid-3">
<div class="card"><div class="label">생성</div><div class="value" style="color:#4caf50">+{bp_earned:,}</div></div>
<div class="card"><div class="label">소각</div><div class="value accent">-{bp_total_spent:,}</div></div>
<div class="card"><div class="label">순변동</div><div class="value" style="color:{'#4caf50' if bp_net >= 0 else '#e53935'}">{bp_net:+,}</div></div>
</div>
{bp_source_cards_html}
<div class="grid" style="margin-top:6px">
<div class="card"><div class="label">총 유통량</div><div class="value">{bp_circulation:,}</div>{_delta_badge(bp_circulation, prev_bp_circulation) if prev_bp_circulation else ''}<div class="sub">보유자 평균 {bp_avg:,}BP</div></div>
<div class="card"><div class="label">뽑기</div><div class="value">{gacha_pulls:,}회</div><div class="sub">-{gacha_spent:,}BP</div></div>
</div></div>

<div class="section">
<div class="section-title">💰 경제</div>
<div class="grid">
<div class="card"><div class="label">마스터볼 보유</div><div class="value">{eco['master_balls_circulation']}</div></div>
<div class="card"><div class="label">하이퍼볼 보유</div><div class="value">{eco['hyper_balls_circulation']}</div></div>
<div class="card"><div class="label">거래소</div><div class="value">{d['market_sold']}</div><div class="sub">신규 {d['market_new']}건</div></div>
<div class="card"><div class="label">구독 매출</div><div class="value accent">${d['sub_revenue_today']:.1f}</div><div class="sub">활성 {d['sub_active']}명</div></div>
</div></div>

{hourly_html}
{top_html}
{patch_html}
{gen4_html}
{insight_html}"""

        date_str = f"{d['date']} ({d['weekday']})"
        html = _kpi_html_template("📊 일일 KPI 리포트", body, date_str)
        filename = f"kpi_daily_{d['date'].replace('-', '')}.html"

        for admin_id in config.ADMIN_IDS:
            try:
                buf = io.BytesIO(html.encode("utf-8"))
                buf.name = filename
                await context.bot.send_document(
                    chat_id=admin_id, document=buf,
                    caption=f"📊 일일 KPI 리포트 — {date_str}",
                )
            except Exception:
                pass
        logger.info("Daily KPI report (HTML) sent to admins.")
    except Exception as e:
        logger.error(f"Daily KPI report error: {e}")


async def _send_weekly_kpi_report(context):
    """매주 월요일 00:01 KST: 주간 KPI 리포트를 HTML 파일로 관리자 DM 발송."""
    import io
    now = config.get_kst_now()
    if now.weekday() != 0:
        return
    try:
        w = await queries.kpi_weekly_snapshot()

        dau_hist = w.get("dau_history", [])
        weekdays = ["월", "화", "수", "목", "금", "토", "일"]
        avg_dau = round(sum(h.get("dau", 0) for h in dau_hist) / max(len(dau_hist), 1), 1)
        max_dau = max((h.get("dau", 0) for h in dau_hist), default=1) or 1

        # DAU bar chart HTML
        bars = ""
        for i, h in enumerate(dau_hist):
            dau = h.get("dau", 0)
            pct = round(dau / max_dau * 100)
            day = weekdays[i % 7]
            bars += f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px"><span style="min-width:20px;font-size:12px;color:#888">{day}</span><div style="background:linear-gradient(90deg,#e53935,#ff6f61);height:22px;border-radius:4px;width:{pct}%;min-width:2px"></div><span style="font-size:13px;font-weight:600">{dau}</span></div>'

        body = f"""
<div class="section">
<div class="section-title">📈 DAU 트렌드</div>
{bars}
<div class="card" style="margin-top:10px"><div class="label">주간 평균 DAU</div><div class="value accent">{avg_dau}</div></div>
</div>

<div class="section">
<div class="section-title">👥 유저</div>
<div class="grid">
<div class="card"><div class="label">WAU (주간 활성)</div><div class="value accent">{w['wau']}</div></div>
<div class="card"><div class="label">신규가입</div><div class="value">{w['new_users']}</div></div>
</div></div>

<div class="section">
<div class="section-title">🎯 스폰 / 포획</div>
<div class="grid">
<div class="card"><div class="label">총 스폰</div><div class="value">{w['spawns']:,}</div></div>
<div class="card"><div class="label">포획</div><div class="value accent">{w['catches']:,}</div><div class="sub">포획률 {w['catch_rate']}%</div></div>
<div class="card"><div class="label">이로치</div><div class="value" style="color:#ff9800">{w['shiny_caught']}</div></div>
<div class="card"><div class="label">마볼 소비</div><div class="value">{w['mb_used']}</div></div>
</div></div>

<div class="section">
<div class="section-title">⚔️ 배틀</div>
<div class="grid">
<div class="card"><div class="label">총 배틀</div><div class="value">{w['battles']}</div></div>
<div class="card"><div class="label">BP 획득</div><div class="value">+{w['bp_earned']:,}</div></div>
<div class="card"><div class="label">BP 뽑기소비</div><div class="value" style="color:#e53935">-{w['gacha_bp_spent']:,}</div></div>
<div class="card"><div class="label">뽑기 횟수</div><div class="value">{w['gacha_pulls']:,}</div></div>
</div></div>

{_bp_daily_chart(w.get('bp_daily', []))}

<div class="section">
<div class="section-title">💰 경제</div>
<div class="grid">
<div class="card"><div class="label">거래소 체결</div><div class="value">{w['market_sold']}</div></div>
<div class="card"><div class="label">구독 매출</div><div class="value accent">${w['sub_revenue']:.1f}</div></div>
</div></div>"""

        period = w["period"]
        html = _kpi_html_template("📊 주간 KPI 리포트", body, period)
        filename = f"kpi_weekly_{now.strftime('%Y%m%d')}.html"

        for admin_id in config.ADMIN_IDS:
            try:
                buf = io.BytesIO(html.encode("utf-8"))
                buf.name = filename
                await context.bot.send_document(
                    chat_id=admin_id, document=buf,
                    caption=f"📊 주간 KPI 리포트 — {period}",
                )
            except Exception:
                pass
        logger.info("Weekly KPI report (HTML) sent to admins.")
    except Exception as e:
        logger.error(f"Weekly KPI report error: {e}")


async def midnight_reset(context):
    """자정(0시 KST) 일일 리셋: 잡기횟수, 보너스, 밥/놀기, 강제스폰, 스폰카운트."""
    from database.connection import get_db
    pool = await get_db()
    today = config.get_kst_today()

    # 중복 실행 방지: 이미 오늘 리셋했으면 스킵
    marker = await pool.fetchval(
        "SELECT value FROM bot_settings WHERE key = 'last_daily_reset'"
    )
    if marker == today:
        logger.info(f"midnight_reset: already ran for {today}, skipping.")
        return

    logger.info("Running scheduled reset...")

    # 모든 리셋 작업 병렬 실행
    await asyncio.gather(
        queries.reset_daily_nurture(),
        queries.reset_catch_limits(),
        queries.reset_force_spawn_counts(),
        queries.cleanup_expired_listings(),
        queries.reset_daily_spawn_counts(),
        queries.cleanup_old_activity(days=7),
        queries.cleanup_old_missions(days=7),
        queries.reset_daily_cxp(),
        _grant_title_buffs(),
        _grant_subscription_daily(context.bot),
    )

    # Record reset timestamp
    await pool.execute(
        """INSERT INTO bot_settings (key, value) VALUES ('last_daily_reset', $1)
           ON CONFLICT (key) DO UPDATE SET value = $1""",
        today,
    )

    # Reschedule spawns for all chats
    await schedule_all_chats(context.application)

    # Activate auto arcade for Lv.8+ chats
    await _activate_auto_arcades(context.application)

    logger.info("Scheduled reset complete.")


async def _activate_auto_arcades(app):
    """Lv.8+ 채팅방에 일일 자동 아케이드 (1시간) 가동."""
    try:
        lv8_chats = await queries.get_lv8_plus_chats()
        if not lv8_chats:
            return
        from services.spawn_service import start_temp_arcade
        for cid in lv8_chats:
            start_temp_arcade(app, cid, config.AUTO_ARCADE_DURATION)
        logger.info(f"Auto arcade activated for {len(lv8_chats)} Lv.8+ chats")
    except Exception as e:
        logger.error(f"Auto arcade activation failed: {e}")


# --- 3-hourly catch recharge job ---

async def catch_recharge_job(context):
    """Recharge 50% of used catches every 3 hours (between full resets)."""
    logger.info("Running 3-hourly catch recharge (50%)...")
    await queries.recharge_catch_limits()
    logger.info("Catch recharge complete.")


# --- Weather update job ---

async def weather_update_job(context):
    """Periodic weather update (every hour)."""
    weather_city = os.getenv("WEATHER_CITY", "Seoul")
    await update_weather(weather_city)


# --- Ranked season jobs ---

async def ranked_weekly_reset_job(context):
    """매주 목요일 00:05 KST: 시즌 보상 → 소프트 리셋 → 새 시즌 공지."""
    try:
        from services import ranked_service as rs
        from database import ranked_queries as rq

        # 목요일(3)만 실행
        now = config.get_kst_now()
        if now.weekday() != config.SEASON_START_WEEKDAY:
            return

        prev_season = await rq.get_current_season()

        # 2주 시즌: 시즌 종료 여부 확인 (시즌이 아직 진행 중이면 스킵)
        if prev_season:
            ends_at = prev_season["ends_at"]
            # ends_at가 datetime 객체면 직접 비교, naive면 KST로 가정
            if ends_at.tzinfo is None:
                ends_at = ends_at.replace(tzinfo=config.KST)
            if now < ends_at:
                # 시즌 아직 진행 중 → 리셋 안 함
                logger.info(f"Season {prev_season['season_id']} still active, skipping reset")
                return

        # 이전 시즌 보상 처리
        if prev_season and not prev_season["rewards_distributed"]:
            rewarded = await rs.process_season_rewards(prev_season["season_id"])
            logger.info(f"Season rewards: {len(rewarded)} users rewarded")

            # 시즌 1위 → 챔피언 칭호 해금
            champion_uid = await rs.get_season_champion(prev_season["season_id"])
            if champion_uid:
                try:
                    await queries.unlock_title(champion_uid, "ranked_champion")
                    logger.info(f"Season champion title unlocked for {champion_uid}")
                except Exception:
                    pass

            # 보상 DM 발송
            for r in rewarded:
                try:
                    tier_d = rs.tier_display(r["tier"])
                    parts = []
                    if r.get("masterball", 0):
                        parts.append(f"마스터볼 x{r['masterball']}")
                    if r.get("bp", 0):
                        parts.append(f"BP {r['bp']}")
                    reward_txt = " + ".join(parts)
                    champ_note = ""
                    if r["user_id"] == champion_uid:
                        champ_note = "\n🏆 <b>시즌 챔피언!</b> '시즌 챔피언' 칭호 해금!"
                    await context.bot.send_message(
                        chat_id=r["user_id"],
                        text=f"🏟️ 시즌 {prev_season['season_id']} 보상!\n"
                             f"최고 티어: {tier_d}\n🎁 {reward_txt}{champ_note}",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

        # 새 시즌 생성 (소프트 리셋 포함)
        if prev_season:
            new_season = await rs.soft_reset_new_season(prev_season["season_id"])
        else:
            new_season = await rs.ensure_current_season()

        if not new_season:
            logger.error("Failed to create new ranked season")
            return

        # 새 시즌 공지 (DM 방식: season_records 보유 유저에게)
        rule_info = config.WEEKLY_RULES.get(new_season["weekly_rule"], {})

        # 지난 시즌 TOP 3
        top3_lines = []
        if prev_season:
            top3 = await rq.get_ranked_ranking(prev_season["season_id"], limit=3)
            medals = ["🥇", "🥈", "🥉"]
            for i, r in enumerate(top3):
                td = rs.tier_display(r["tier"])
                name = r.get("display_name") or "???"
                top3_lines.append(f"  {medals[i]} {name} ({td} {r['rp']} RP)")

        announce = [
            f"🏟️ 시즌 {new_season['season_id']} 시작!",
            f"🔒 시즌 법칙: {rule_info.get('name', new_season['weekly_rule'])}",
            f"   └ {rule_info.get('desc', '')}",
        ]

        if top3_lines:
            announce.append(f"\n🏆 지난 시즌 TOP 3")
            announce.extend(top3_lines)

        announce.append("\n💡 DM에서 '랭전'으로 자동 매칭 대전!")

        text = "\n".join(announce)

        # 시즌 기록 있는 유저에게 DM 알림
        if prev_season:
            all_records = await rq.get_all_season_records(prev_season["season_id"])
            for rec in all_records:
                try:
                    await context.bot.send_message(
                        chat_id=rec["user_id"], text=text, parse_mode="HTML",
                    )
                except Exception:
                    pass
                await asyncio.sleep(0.05)

        logger.info(f"New ranked season started: {new_season['season_id']}")
    except Exception as e:
        logger.error(f"Ranked weekly reset failed: {e}")


async def ranked_mid_season_check_job(context):
    """매일 00:10 KST: 7일차 중간 리셋 체크."""
    try:
        from services import ranked_service as rs
        from database import ranked_queries as rq

        season = await rq.get_current_season()
        if not season:
            return

        # 시즌 시작 후 경과 일수 계산
        starts_at = season["starts_at"]
        if starts_at.tzinfo is None:
            starts_at = starts_at.replace(tzinfo=config.KST)
        now = config.get_kst_now()
        days_elapsed = (now - starts_at).days

        # 7일차에만 중간 리셋 실행
        if days_elapsed == 7 and not season.get("mid_reset_done", False):
            reset_count = await rs.process_mid_season_reset(season)
            logger.info(f"Mid-season reset: {reset_count} users reset in {season['season_id']}")

            # DM 알림 (배치 완료 유저)
            records = await rq.get_all_placed_records(season["season_id"])
            for rec in records:
                try:
                    div_info = config.get_division_info(rec["rp"])
                    tier_disp = config.tier_division_display(
                        div_info[0], div_info[1], div_info[2],
                        placement_done=True, total_rp=rec["rp"])
                    await context.bot.send_message(
                        chat_id=rec["user_id"],
                        text=(
                            f"⚡ 중간 리셋!\n"
                            f"RP가 60%로 조정되었습니다.\n"
                            f"현재: {tier_disp}\n"
                            f"연승이 초기화되었습니다."
                        ),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
                await asyncio.sleep(0.05)
    except Exception as e:
        logger.error(f"Mid-season check job failed: {e}")


async def ranked_decay_job(context):
    """매일 00:15 KST: 마스터+ 디케이 처리."""
    try:
        from services import ranked_service as rs
        from database import ranked_queries as rq

        season = await rq.get_current_season()
        if not season:
            return

        results = await rs.process_ranked_decay(season["season_id"])

        # 디케이된 유저에게 DM 알림
        for r in results:
            try:
                decay_amount = r["rp_before"] - r["rp_after"]
                div_info = config.get_division_info(r["rp_after"])
                tier_disp = config.tier_division_display(
                    div_info[0], div_info[1], div_info[2],
                    placement_done=True, total_rp=r["rp_after"])
                await context.bot.send_message(
                    chat_id=r["user_id"],
                    text=(
                        f"⏰ 디케이 알림!\n"
                        f"RP -{decay_amount} ({r['rp_before']} → {r['rp_after']})\n"
                        f"현재: {tier_disp}\n"
                        f"랭크전으로 디케이를 막으세요!"
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Ranked decay job failed: {e}")


# --- Weather command handler ---

async def _optout_handler(update, context):
    """Handle '수신거부' DM command — toggle patch note opt-out."""
    user_id = update.effective_user.id
    await queries.ensure_user(user_id, update.effective_user.first_name or "트레이너")
    opted_out = await queries.toggle_patch_optout(user_id)
    if opted_out:
        await update.message.reply_text("🔕 패치노트 수신이 거부되었습니다.\n포획/미션 등 일반 DM은 정상 수신됩니다.\n\n다시 '수신거부'를 입력하면 해제됩니다.")
    else:
        await update.message.reply_text("🔔 패치노트 수신이 다시 활성화되었습니다!")


async def weather_handler(update, context):
    """Handle '날씨' command — show current weather and active boost."""
    weather = get_current_weather()
    if not weather.get("condition"):
        await update.message.reply_text("날씨 데이터를 아직 불러오지 못했습니다.")
        return

    boost_info = WEATHER_BOOSTS.get(weather["condition"], {})
    label = boost_info.get("label", "보통")
    emoji = boost_info.get("emoji", "")
    temp = weather.get("temp")
    temp_text = f" ({temp}°C)" if temp is not None else ""

    # 캐시가 2시간 이상 오래되면 안내
    from datetime import timedelta
    stale_text = ""
    updated_at = weather.get("updated_at")
    if updated_at and config.get_kst_now() - updated_at > timedelta(hours=2):
        stale_text = "\n⚠️ 날씨 데이터가 오래되었습니다. 곧 업데이트됩니다."

    await update.message.reply_text(
        f"🌍 현재 날씨{temp_text}\n"
        f"{emoji} {label}{stale_text}"
    )


# --- Main ---

def main():
    token = os.getenv("BOT_TOKEN")
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        logger.error("BOT_TOKEN not set in .env file!")
        return

    # Build application
    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .concurrent_updates(True)
        .build()
    )

    # --- Register handlers ---

    dm = filters.ChatType.PRIVATE
    group = filters.ChatType.GROUPS

    # Latin commands (CommandHandler supports only [a-z0-9_])
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("pokedex", pokedex_handler, filters=dm))

    # Tutorial DM handlers (MUST be before other DM handlers)
    app.add_handler(MessageHandler(dm & filters.Regex(r"^튜토$"), tutorial_dm_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^[ㅊㅎㅁ]$"), tutorial_dm_catch))

    # Patch note opt-out (수신거부)
    app.add_handler(MessageHandler(dm & filters.Regex(r"^수신거부$"), _optout_handler))

    # Korean commands via MessageHandler + Regex (DM only)
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(❓\s*)?도움말$"), help_handler))
    app.add_handler(MessageHandler((dm | group) & filters.Regex(r"^(📖\s*)?도감(\s+\S+)?$"), pokedex_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^날씨$"), weather_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(📦\s*)?내포켓몬(\s+.+)?$"), my_pokemon_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(💪\s*)?친밀도강화$"), nurture_menu_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^밥(\s+.+)?$"), feed_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^놀기(\s+.+)?$"), play_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^진화(\s+.+)?$"), evolve_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^감정(\s+.+)?$"), appraisal_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^상성(\s+.+)?$"), type_chart_handler))
    # DM trade removed — replaced by group reply trade

    # Marketplace (DM) — 구체적 서브커맨드 먼저 등록
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🛒\s*)?거래소\s*등록\s+.+$"), market_register_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🛒\s*)?거래소\s*취소\s+.+$"), market_cancel_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🛒\s*)?거래소\s*구매\s+.+$"), market_buy_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🛒\s*)?거래소\s*검색\s+.+$"), market_search_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🛒\s*)?거래소\s*내꺼$"), market_my_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🛒\s*)?거래소$"), market_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^방생$"), release_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^합성$"), fusion_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(📋\s*|📌\s*)?미션$"), mission_handler))

    # Subscription / Premium system (DM + Group)
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(💎\s*)?프리미엄$"), premium_hub_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(💎\s*)?구독$"), subscription_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^구독정보$"), subscription_status_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(💎\s*)?프리미엄상점$"), premium_shop_handler))
    app.add_handler(MessageHandler((dm | group) & filters.Regex(r"^채팅상점$"), channel_shop_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(📋\s*)?칭호목록$"), title_list_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🏷️\s*)?칭호$"), title_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(📋\s*)?상태창$"), status_handler))

    # ── 봇방지: 챌린지 응답 핸들러 (최우선 DM 핸들러) ──
    app.add_handler(MessageHandler(dm & filters.TEXT & ~filters.COMMAND, challenge_answer_handler), group=-3)

    # Camp system v2 (DM)
    if HAS_CAMP:
        # 환영 멘트 입력 (가장 먼저 — 상태가 아니면 무시)
        app.add_handler(MessageHandler(dm & filters.TEXT & ~filters.COMMAND, camp_welcome_input_handler), group=-2)
        app.add_handler(MessageHandler(dm & filters.Regex(r"^(🏕\s*)?캠프$"), camp_hub_handler))
        app.add_handler(MessageHandler(dm & filters.Regex(r"^내캠프$"), my_camp_handler))
        app.add_handler(MessageHandler(dm & filters.Regex(r"^거점캠프$"), home_camp_handler))
        app.add_handler(MessageHandler(dm & filters.Regex(r"^캠프알림$"), camp_notify_handler))
        app.add_handler(MessageHandler(dm & filters.Regex(r"^캠프가이드$"), camp_guide_handler))
        app.add_handler(MessageHandler(dm & filters.Regex(r"^이로치전환$"), shiny_convert_handler))
        app.add_handler(MessageHandler(dm & filters.Regex(r"^분해$"), decompose_handler))

    # Battle system (DM)
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🤝\s*)?파트너(\s+.+)?$"), partner_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(✏️\s*)?팀편집$"), team_edit_menu_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^팀등록[12]?(\s+.+)?$"), team_register_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^팀해제[12]?$"), team_clear_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^팀선택(\s+.+)?$"), team_select_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^팀스왑$"), team_swap_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(⚔️\s*)?팀[12]?$"), team_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🏆\s*)?배틀전적$"), battle_stats_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(⚔️\s*)?랭크전$"), battle_stats_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"(?i)^(bp)?구매(\s+.+)?$"), bp_buy_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"(?i)^(🏪\s*)?(bp)?상점$"), bp_shop_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"(?i)^bp$"), bp_handler))
    # 가챠 (뽑기) + 아이템
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🎰\s*)?(뽑기|가챠)$"), gacha_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🎒\s*)?아이템$"), item_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^티어$"), tier_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^시즌$"), season_info_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(시즌)?랭킹$"), ranked_ranking_handler))

    # Admin commands (DM)
    app.add_handler(MessageHandler(dm & filters.Regex(r"^통계$"), stats_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^채널목록$"), channel_list_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^이벤트시작(\s+.+)?$"), event_start_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^이벤트목록$"), event_list_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^이벤트종료(\s+.+)?$"), event_end_handler))
    app.add_handler(MessageHandler((dm | group) & filters.Regex(r"^마볼지급\s+.+$"), grant_masterball_handler))
    app.add_handler(MessageHandler((dm | group) & filters.Regex(r"^BP지급\s+.+$"), grant_bp_handler))
    app.add_handler(MessageHandler((dm | group) & filters.Regex(r"^구독권지급\s+.+$"), grant_subscription_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^아케이드(\s+.+)?$"), arcade_handler))
    app.add_handler(MessageHandler((dm | group) & filters.Regex(r"^대회방(등록|해제)$"), tournament_chat_handler))
    app.add_handler(MessageHandler((dm | group) & filters.Regex(r"^대회시작$"), force_tournament_reg_handler))
    app.add_handler(MessageHandler((dm | group) & filters.Regex(r"^대회진행$"), force_tournament_run_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^구독승인\s+.+$"), manual_subscription_handler))

    # 어뷰징 관리 명령어 (관리자 전용)
    app.add_handler(MessageHandler(dm & filters.Regex(r"^어뷰징$"), abuse_list_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^어뷰징상세\s+\d+$"), abuse_detail_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^어뷰징초기화\s+\d+$"), abuse_reset_handler))

    # Group trade (reply with '교환')
    app.add_handler(MessageHandler(group & filters.Regex(r"^교환\s+.+$"), group_trade_handler))

    # Pokeball recharge
    app.add_handler(MessageHandler(group & filters.Regex(r"^포켓볼\s*충전$"), love_easter_egg))

    # Hidden easter egg
    app.add_handler(MessageHandler(group & filters.Regex(r"^문유\s*사랑해$"), love_hidden_handler))

    # Attendance
    app.add_handler(MessageHandler(group & filters.Regex(r"^출석$"), attendance_handler))

    # Group Korean commands
    app.add_handler(MessageHandler(group & filters.Regex(r"^랭킹$"), ranking_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^로그$"), log_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^날씨$"), weather_handler))
    app.add_handler(MessageHandler((group | dm) & filters.Regex(r"^대시보드$"), dashboard_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^방정보$"), room_info_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^내포켓몬\s+\S+$"), my_pokemon_group_handler))

    # Camp system v2 (Group)
    if HAS_CAMP:
        app.add_handler(MessageHandler(group & filters.Regex(r"^캠프$"), camp_handler))
        app.add_handler(MessageHandler(group & filters.Regex(r"^캠프개설$"), camp_create_handler))
        app.add_handler(MessageHandler(group & filters.Regex(r"^캠프설정$"), camp_settings_handler))
        app.add_handler(MessageHandler(group & filters.Regex(r"^캠프맵$"), camp_map_handler))
        app.add_handler(MessageHandler(group & filters.Regex(r"^방문$"), camp_visit_handler))

    # Battle system (Group)
    app.add_handler(MessageHandler(group & filters.Regex(r"^배틀$"), battle_challenge_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^배틀랭킹$"), battle_ranking_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^배틀수락$"), battle_accept_text_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^배틀거절$"), battle_decline_text_handler))

    # DM auto-ranked battle
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🏟️\s*)?랭전$"), auto_ranked_handler))

    # Yacha (Betting Battle) — group only
    app.add_handler(MessageHandler(group & filters.Regex(r"^야차$"), yacha_handler))

    # Admin group commands
    app.add_handler(MessageHandler(group & filters.Regex(r"^스폰배율(\s+.+)?$"), spawn_rate_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^\s*강스\s*$"), force_spawn_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^\s*강스권\s*$"), ticket_force_spawn_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^\s*이로치강스\s*$"), shiny_ticket_spawn_handler))
    app.add_handler(MessageHandler(filters.Regex(r"^\s*강제스폰 채널 초기화\s*$"), force_spawn_reset_handler))
    app.add_handler(MessageHandler(filters.Regex(r"^\s*포켓볼초기화\s*$"), pokeball_reset_handler))

    # "ㅊ" catch handler (group only, exact match)
    app.add_handler(MessageHandler(
        group & filters.TEXT & filters.Regex(r"^ㅊ$"),
        catch_handler,
    ))

    # "ㅁ" master ball handler (group only, exact match)
    app.add_handler(MessageHandler(
        group & filters.TEXT & filters.Regex(r"^ㅁ$"),
        master_ball_handler,
    ))

    # "ㅎ" hyper ball handler (group only, exact match)
    app.add_handler(MessageHandler(
        group & filters.TEXT & filters.Regex(r"^ㅎ$"),
        hyper_ball_handler,
    ))

    # "ㄷ" tournament join (group only, arcade channels)
    app.add_handler(MessageHandler(
        group & filters.TEXT & filters.Regex(r"^ㄷ$"),
        tournament_join_handler,
    ))

    # Anti-bot challenge callback (4지선다 버튼)
    app.add_handler(CallbackQueryHandler(challenge_callback_handler, pattern=r"^abot_"))

    # Close message callback (❌ button)
    app.add_handler(CallbackQueryHandler(close_message_callback, pattern=r"^close_msg$"))

    # Catch DM: keep / release callbacks
    app.add_handler(CallbackQueryHandler(catch_keep_callback, pattern=r"^catch_keep_\d+$"))
    app.add_handler(CallbackQueryHandler(catch_release_callback, pattern=r"^catch_release_\d+$"))

    # Pokedex pagination callback
    app.add_handler(CallbackQueryHandler(pokedex_callback, pattern=r"^dex_"))

    # My Pokemon pagination callback
    app.add_handler(CallbackQueryHandler(my_pokemon_callback, pattern=r"^mypoke_"))

    # Release (방생) callback
    app.add_handler(CallbackQueryHandler(release_callback, pattern=r"^rel_"))

    # Fusion (합성) callback
    app.add_handler(CallbackQueryHandler(fusion_callback, pattern=r"^fus_"))

    # Title selection callback
    app.add_handler(CallbackQueryHandler(title_callback, pattern=r"^title_"))
    # Title list pagination callback
    app.add_handler(CallbackQueryHandler(title_list_callback, pattern=r"^tlist_"))
    # Title selection pagination callback
    app.add_handler(CallbackQueryHandler(title_page_callback, pattern=r"^titlep_"))

    # Partner selection callback
    app.add_handler(CallbackQueryHandler(partner_callback_handler, pattern=r"^partner_"))

    # Team selection callback
    app.add_handler(CallbackQueryHandler(team_callback_handler, pattern=r"^t(edit|slot_view|pick|rem|p|f|cl|done|cancel|del|swap|swap_cancel|sw)_"))

    # Battle accept/decline callback
    app.add_handler(CallbackQueryHandler(battle_callback_handler, pattern=r"^battle_"))

    # Ranked battle accept/decline callback
    app.add_handler(CallbackQueryHandler(ranked_callback_handler, pattern=r"^ranked_"))

    # Battle result detail/skip/teabag callback
    app.add_handler(CallbackQueryHandler(battle_result_callback_handler, pattern=r"^b(detail|skip|tbag)_"))

    # Shop purchase callback
    app.add_handler(CallbackQueryHandler(shop_callback_handler, pattern=r"^shop_"))

    # 가챠 (뽑기) callbacks
    app.add_handler(CallbackQueryHandler(gacha_callback_handler, pattern=r"^gacha_"))
    # 아이템 사용 callbacks
    app.add_handler(CallbackQueryHandler(item_callback_handler, pattern=r"^(item_|ivr_)"))

    # Nurture (feed/play/evolve) duplicate selection callbacks
    app.add_handler(CallbackQueryHandler(nurture_callback_handler, pattern=r"^nurt_"))

    # Marketplace callbacks
    app.add_handler(CallbackQueryHandler(market_callback_handler, pattern=r"^mkt_"))

    # Trade evolution choice callbacks
    app.add_handler(CallbackQueryHandler(trade_evo_choice_handler, pattern=r"^tevo_"))

    # Group trade callbacks
    app.add_handler(CallbackQueryHandler(group_trade_callback_handler, pattern=r"^gtrade_"))

    # Tutorial onboarding callbacks
    app.add_handler(CallbackQueryHandler(tutorial_callback, pattern=r"^tut_"))

    # Yacha (betting battle) callbacks
    app.add_handler(CallbackQueryHandler(yacha_type_callback, pattern=r"^yc_"))
    app.add_handler(CallbackQueryHandler(yacha_amount_callback, pattern=r"^ya_"))
    app.add_handler(CallbackQueryHandler(yacha_response_callback, pattern=r"^yacha_"))
    app.add_handler(CallbackQueryHandler(yacha_result_callback, pattern=r"^yres_"))

    # Help navigation callbacks
    app.add_handler(CallbackQueryHandler(help_callback_handler, pattern=r"^help_"))

    # Premium hub callbacks (pmenu_subscribe, pmenu_shop, pmenu_guide, pmenu_status)
    app.add_handler(CallbackQueryHandler(premium_hub_callback_handler, pattern=r"^pmenu_"))

    # Subscription callbacks (sub_tier_, sub_token_, sub_check_, sub_cancel_, sub_back, sub_status, sub_pshop_, sub_cshop_)
    app.add_handler(CallbackQueryHandler(subscription_callback_handler, pattern=r"^sub_"))

    # Event DM broadcast callback
    app.add_handler(CallbackQueryHandler(event_dm_callback, pattern=r"^evt_dm_"))

    # Camp callbacks
    if HAS_CAMP:
        app.add_handler(CallbackQueryHandler(camp_callback_handler, pattern=r"^camp_"))
        app.add_handler(CallbackQueryHandler(camp_dm_callback_handler, pattern=r"^cdm_"))

    # Activity tracker — runs for every group text message (handler group -1)
    app.add_handler(
        MessageHandler(group & filters.TEXT, on_chat_activity),
        group=-1,
    )

    # --- Schedule jobs ---
    # KST = UTC+9
    kst = timezone(timedelta(hours=9))
    # KPI 일일 리포트 (23:55 KST — 리셋 전 데이터 캡처)
    app.job_queue.run_daily(
        _send_daily_kpi_report,
        time=dt_time(23, 55, 0, tzinfo=kst),
        name="daily_kpi_report",
    )

    app.job_queue.run_daily(
        midnight_reset,
        time=dt_time(0, 0, 0, tzinfo=kst),
        name="reset_midnight",
    )

    # KPI 주간 리포트 (월요일 00:01 KST)
    app.job_queue.run_daily(
        _send_weekly_kpi_report,
        time=dt_time(0, 1, 0, tzinfo=kst),
        name="weekly_kpi_report",
    )

    # 3-hourly catch recharge at 3, 6, 9, 12, 15, 18, 21 KST
    # (0 KST is full reset via midnight_reset)
    for hour in (0, 3, 6, 12, 15, 18):
        app.job_queue.run_daily(
            catch_recharge_job,
            time=dt_time(hour, 0, 0, tzinfo=kst),
            name=f"recharge_{hour:02d}",
        )

    # Weather update every hour
    app.job_queue.run_repeating(
        weather_update_job,
        interval=3600,
        first=3600,
        name="weather_update",
    )

    # Ranked season: weekly reset at Thursday 00:05 KST
    app.job_queue.run_daily(
        ranked_weekly_reset_job,
        time=dt_time(0, 5, 0, tzinfo=kst),
        name="ranked_weekly_reset",
    )

    # Ranked: mid-season reset check (매일 00:10 KST)
    app.job_queue.run_daily(
        ranked_mid_season_check_job,
        time=dt_time(0, 10, 0, tzinfo=kst),
        name="ranked_mid_season_check",
    )

    # Ranked: decay (마스터+ 디케이, 매일 00:15 KST)
    app.job_queue.run_daily(
        ranked_decay_job,
        time=dt_time(0, 15, 0, tzinfo=kst),
        name="ranked_decay",
    )

    # Subscription: 결제 폴링 (60초마다)
    async def _subscription_poll_job(context):
        try:
            from services.subscription_service import poll_chain_transfers
            await poll_chain_transfers(context.bot)
        except Exception as e:
            logger.error(f"Subscription poll job error: {e}")

    app.job_queue.run_repeating(
        _subscription_poll_job,
        interval=60,
        first=10,
        name="subscription_poll",
    )

    # Subscription: 만료 체크 + 갱신 알림 (매일 09:00 KST)
    async def _subscription_expiry_job(context):
        try:
            from services.subscription_service import check_expiry_and_notify
            await check_expiry_and_notify(context.bot)
        except Exception as e:
            logger.error(f"Subscription expiry job error: {e}")

    app.job_queue.run_daily(
        _subscription_expiry_job,
        time=dt_time(9, 0, 0, tzinfo=kst),
        name="subscription_expiry",
    )

    # Tournament schedule (21:00 registration, 21:50 snapshot, 22:00 start — KST)
    app.job_queue.run_daily(
        start_registration,
        time=dt_time(config.TOURNAMENT_REG_HOUR, 0, 0, tzinfo=kst),
        name="tournament_reg",
    )
    app.job_queue.run_daily(
        snapshot_teams,
        time=dt_time(config.TOURNAMENT_REG_HOUR, 50, 0, tzinfo=kst),
        name="tournament_snapshot",
    )
    app.job_queue.run_daily(
        start_tournament,
        time=dt_time(config.TOURNAMENT_START_HOUR, 0, 0, tzinfo=kst),
        name="tournament_start",
    )

    # Camp v2 — 라운드 스케줄러 (3시간 간격, KST 09/12/15/18/21/00시)
    if HAS_CAMP:
        for hour in config.CAMP_ROUND_HOURS:
            app.job_queue.run_daily(
                camp_round_job,
                time=dt_time(hour, 0, 0, tzinfo=kst),
                name=f"camp_round_{hour:02d}",
            )

    # 이로치 알 부화 체크 (10분마다)
    async def _egg_hatch_job(context):
        try:
            from services.gacha_service import hatch_ready_eggs
            hatched = await hatch_ready_eggs(context.bot)
            for h in hatched:
                try:
                    rarity_labels = {"common": "일반", "rare": "레어", "epic": "에픽",
                                     "legendary": "전설", "ultra_legendary": "초전설"}
                    rarity_name = rarity_labels.get(h["rarity"], h["rarity"])
                    iv_sum = sum(h["ivs"].values())
                    await context.bot.send_message(
                        chat_id=h["user_id"],
                        text=(
                            f"🥚✨ <b>알이 부화했습니다!</b>\n\n"
                            f"✨ <b>{h['name_ko']}</b> (이로치)\n"
                            f"등급: {rarity_name}\n"
                            f"IV 합계: {iv_sum}/186\n\n"
                            f"🎉 도감에 자동 등록되었습니다!"
                        ),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.error(f"Egg hatch DM failed for {h['user_id']}: {e}")
        except Exception as e:
            logger.error(f"Egg hatch job failed: {e}")

    app.job_queue.run_repeating(
        _egg_hatch_job,
        interval=600,  # 10분마다
        first=60,
        name="egg_hatch_check",
    )

    # --- Start polling ---
    logger.info("Starting bot...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
