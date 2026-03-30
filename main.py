"""Pokemon Telegram Bot — Entry Point."""

import asyncio
import logging
import os
from datetime import datetime

import config

from dotenv import load_dotenv
from telegram.ext import Application

from database.connection import get_db, close_db
from database.schema import create_tables, migrate_personality
from database.seed import seed_pokemon_data, seed_battle_data, migrate_18_types, migrate_assign_ivs, migrate_rarity_v2, migrate_ultra_legendary, migrate_catch_rates_v3, migrate_add_nurture_locked, migrate_trade_evo_fix

from database import queries, item_queries
from handlers._register import register_all_handlers
from jobs.midnight import _check_missed_reset
from jobs.scheduler import register_all_jobs

from services.spawn_service import schedule_all_chats
from services.weather_service import update_weather

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
                migrate_personality(),
            ), timeout=120)
            migrated, iv_assigned, _, rarity_migrated, ultra_migrated, catch_migrated, nurture_locked, trade_evo_fixed, personality_assigned = results
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
            if personality_assigned:
                logger.info(f"Personality migration: {personality_assigned} pokemon assigned personalities.")
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

    # 포획 잠금 DB 복원
    try:
        from services.abuse_service import load_locks_from_db
        await load_locks_from_db()
    except Exception as e:
        logger.warning(f"Load catch locks failed: {e}")

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

    # 던전 미지급 보상 복구 (20초 후)
    async def _recover_dungeon_rewards(context):
        from handlers.dm_dungeon import recover_ungranted_rewards
        recovered = await recover_ungranted_rewards()
        if recovered:
            logger.info(f"[startup] Dungeon rewards recovered: {recovered}")

    application.job_queue.run_once(
        _recover_dungeon_rewards, when=20, name="startup_dungeon_recover",
        job_kwargs={"misfire_grace_time": None},
    )

    # 관리자에게 봇 재시작 알림 (10초 후)
    async def _notify_admin_restart(context):
        try:
            await context.bot.send_message(
                chat_id=config.ADMIN_IDS[0],
                text="🔄 봇이 재시작되었습니다.",
            )
            logger.info(f"Admin restart notify sent to {config.ADMIN_IDS[0]}")
        except Exception as e:
            logger.error(f"Admin restart notify failed: {e}")

    application.job_queue.run_once(
        _notify_admin_restart, when=60, name="admin_restart_notify",
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
    register_all_jobs(app)

    # --- Start polling ---
    logger.info("Starting bot...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
