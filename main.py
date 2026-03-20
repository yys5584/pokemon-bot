"""Pokemon Telegram Bot — Entry Point."""

import asyncio
import logging
import os
from datetime import datetime, time as dt_time, timezone, timedelta

import config

from dotenv import load_dotenv
from telegram.ext import Application

from database.connection import get_db, close_db
from database.schema import create_tables
from database.seed import seed_pokemon_data, seed_battle_data, migrate_18_types, migrate_assign_ivs, migrate_rarity_v2, migrate_ultra_legendary, migrate_catch_rates_v3, migrate_add_nurture_locked, migrate_trade_evo_fix

from database import queries, item_queries, mission_queries, spawn_queries, title_queries
from jobs.kpi_report import _send_daily_kpi_report, _send_weekly_kpi_report
from handlers._register import register_all_handlers, HAS_CAMP
if HAS_CAMP:
    from handlers._register import camp_round_job

from services.spawn_service import schedule_all_chats
from services.weather_service import update_weather
from services.tournament_service import start_registration, start_tournament, snapshot_teams

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

    application.job_queue.run_once(
        _delayed_resolve, when=15, name="startup_resolve",
        job_kwargs={"misfire_grace_time": None},  # 절대 스킵 방지
    )

    # 던전 진행 중 유저에게 재시작 안내 (봇 시작 20초 후)
    async def _notify_dungeon_users(context):
        from database import dungeon_queries as dq_notify
        from database.connection import get_db as _get_db
        pool = await _get_db()
        try:
            active_runs = await pool.fetch(
                "SELECT DISTINCT user_id, pokemon_name, floor_reached FROM dungeon_runs "
                "WHERE status = 'active'"
            )
            for run in active_runs:
                try:
                    await context.bot.send_message(
                        chat_id=run["user_id"],
                        text=(
                            f"🏰 서버 점검이 완료되었습니다!\n\n"
                            f"진행 중이던 던전 ({run['pokemon_name']}, {run['floor_reached']}층)이 "
                            f"저장되어 있습니다.\n"
                            f"\"던전\"을 입력하면 이어서 진행할 수 있어요!"
                        ),
                    )
                except Exception:
                    pass
            if active_runs:
                logger.info(f"Notified {len(active_runs)} dungeon users about restart")
        except Exception as e:
            logger.warning(f"dungeon restart notify skipped: {e}")

    application.job_queue.run_once(
        _notify_dungeon_users, when=20, name="dungeon_restart_notify",
        job_kwargs={"misfire_grace_time": None},
    )

    # 가챠 미전달 보상 복구 — 재시작 직전 2분 이내 뽑기 기록이 있으면 DM 발송
    try:
        recent_gacha = await item_queries.get_recent_gacha_by_user(minutes=2)
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
    """Called on shutdown — close DB only. Spawn resolve는 startup에서 처리.
    (shutdown 시 HTTP 클라이언트가 이미 닫혀서 DM 발송 불가하므로)"""
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
    from database import dungeon_queries as dq
    await asyncio.gather(
        queries.reset_daily_nurture(),
        spawn_queries.reset_catch_limits(),
        spawn_queries.reset_force_spawn_counts(),
        spawn_queries.reset_daily_spawn_counts(),
        spawn_queries.cleanup_old_activity(days=7),
        mission_queries.cleanup_old_missions(days=7),
        queries.cleanup_expired_listings(),
        queries.reset_daily_cxp(),
        _grant_title_buffs(),
        _grant_subscription_daily_no_dm(),
        dq.grant_daily_tickets_by_tier(),
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


async def _grant_subscription_daily_no_dm():
    """구독자 일일 혜택 지급 (DM 없이 — missed reset용)."""
    try:
        from database import subscription_queries as sq
        subs = await sq.get_all_active_subscriptions()
        if not subs:
            return
        for sub in subs:
            uid = sub["user_id"]
            tier_cfg = config.SUBSCRIPTION_TIERS.get(sub["tier"], {})
            benefits = tier_cfg.get("benefits", {})
            daily_master = benefits.get("daily_masterball", 0)
            if daily_master:
                await queries.add_master_ball(uid, daily_master)
            daily_hyper = benefits.get("daily_hyperball", 0)
            if daily_hyper:
                await queries.add_hyper_ball(uid, daily_hyper)
            daily_arcade = benefits.get("daily_free_arcade_pass", 0)
            if daily_arcade:
                await queries.add_arcade_ticket(uid, daily_arcade)
            daily_shiny = benefits.get("daily_shiny_ticket", 0)
            if daily_shiny:
                await item_queries.add_shiny_spawn_ticket(uid, daily_shiny)
        logger.info(f"Subscription daily benefits granted (no DM) to {len(subs)} subscribers")
    except Exception as e:
        logger.error(f"Subscription daily grant (no DM) error: {e}")


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
                await item_queries.add_shiny_spawn_ticket(uid, daily_shiny_ticket)
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
    from database import dungeon_queries as dq
    await asyncio.gather(
        queries.reset_daily_nurture(),
        spawn_queries.reset_catch_limits(),
        spawn_queries.reset_force_spawn_counts(),
        queries.cleanup_expired_listings(),
        spawn_queries.reset_daily_spawn_counts(),
        spawn_queries.cleanup_old_activity(days=7),
        mission_queries.cleanup_old_missions(days=7),
        queries.reset_daily_cxp(),
        _grant_title_buffs(),
        _grant_subscription_daily(context.bot),
        dq.grant_daily_tickets_by_tier(),
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
    await spawn_queries.recharge_catch_limits()
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
                    await title_queries.unlock_title(champion_uid, "ranked_champion")
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
    register_all_handlers(app)

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
