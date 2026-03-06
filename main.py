"""Pokemon Telegram Bot — Entry Point."""

import asyncio
import logging
import os
from datetime import time as dt_time, timezone, timedelta

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
from database.seed import seed_pokemon_data, seed_battle_data, migrate_18_types, migrate_assign_ivs, migrate_rarity_v2
from database import queries

from handlers.start import start_handler, help_handler
from handlers.group import catch_handler, master_ball_handler, hyper_ball_handler, love_easter_egg, love_hidden_handler, attendance_handler, ranking_handler, log_handler, dashboard_handler, on_chat_activity, close_message_callback, catch_keep_callback, catch_release_callback
from handlers.dm_pokedex import pokedex_handler, pokedex_callback, my_pokemon_handler, my_pokemon_callback, title_handler, title_callback, title_list_handler, status_handler, appraisal_handler, type_chart_handler
from handlers.battle import (
    partner_handler, partner_callback_handler,
    team_handler, team_register_handler, team_clear_handler, team_select_handler,
    team_callback_handler,
    battle_stats_handler, bp_handler, bp_shop_handler, bp_buy_handler, shop_callback_handler,
    battle_challenge_handler, battle_callback_handler, battle_result_callback_handler,
    battle_ranking_handler, battle_accept_text_handler, battle_decline_text_handler,
    tier_handler,
    ranked_coming_soon_handler,
    yacha_handler, yacha_type_callback, yacha_amount_callback,
    yacha_response_callback, yacha_result_callback,
)
from handlers.dm_nurture import feed_handler, play_handler, evolve_handler, nurture_callback_handler
# DM trade removed — replaced by group reply trade
# from handlers.dm_trade import trade_handler, accept_handler, reject_handler
from handlers.dm_market import (
    market_handler, market_register_handler, market_my_handler,
    market_cancel_handler, market_buy_handler, market_search_handler,
    market_callback_handler,
)
from handlers.group_trade import group_trade_handler, group_trade_callback_handler
from handlers.dm_mission import mission_handler
from handlers.tutorial import tutorial_callback, tutorial_dm_handler, tutorial_dm_catch
from handlers.admin import (
    spawn_rate_handler, force_spawn_handler, force_spawn_reset_handler, ticket_force_spawn_handler,
    pokeball_reset_handler,
    event_start_handler, event_list_handler, event_end_handler,
    stats_handler, channel_list_handler, grant_masterball_handler,
    arcade_handler, force_tournament_reg_handler, force_tournament_run_handler,
)

from services.spawn_service import schedule_all_chats
from services.weather_service import update_weather, get_current_weather, WEATHER_BOOSTS
from services.tournament_service import start_registration, start_tournament, snapshot_teams
from handlers.tournament import tournament_join_handler
from dashboard.server import start_dashboard

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
    await create_tables()
    await seed_pokemon_data()
    logger.info(f"[{time.monotonic()-t0:.1f}s] DB + schema + seed done")

    # Phase 2: 배틀데이터 시드 + 마이그레이션 (병렬)
    migrated, iv_assigned, _, rarity_migrated = await asyncio.gather(
        migrate_18_types(),
        migrate_assign_ivs(),
        seed_battle_data(),
        migrate_rarity_v2(),
    )
    if migrated:
        logger.info(f"18-type migration applied: {migrated} pokemon updated.")
    if iv_assigned:
        logger.info(f"IV migration: {iv_assigned} pokemon received random IVs.")
    if rarity_migrated:
        logger.info(f"Rarity v2 migration: {rarity_migrated} pokemon rarity updated (종족값 기반).")
    logger.info(f"[{time.monotonic()-t0:.1f}s] Database ready. 251 Pokemon seeded.")

    # Phase 3: 독립 작업 병렬 (cleanup + missed_reset + dashboard)
    from services.spawn_service import resolve_unresolved_sessions
    refunded_balls, *_ = await asyncio.gather(
        resolve_unresolved_sessions(application.bot),
        queries.cleanup_expired_events(),
        _check_missed_reset(),
        start_dashboard(),
    )
    # 환불된 마볼/하이퍼볼 DM 알림
    if refunded_balls:
        for uid, ball_type in refunded_balls:
            try:
                msg = ("🟣 서버 점검으로 인해 마스터볼이 환불되었습니다."
                       if ball_type == "master" else
                       "🔵 서버 점검으로 인해 하이퍼볼이 환불되었습니다.")
                await application.bot.send_message(chat_id=uid, text=msg)
            except Exception:
                pass
        logger.info(f"Sent {len(refunded_balls)} ball refund DMs")
    logger.info(f"[{time.monotonic()-t0:.1f}s] Cleanup + dashboard done")

    # Weather는 느릴 수 있으므로 백그라운드로 (시작 차단 안 함)
    weather_city = os.getenv("WEATHER_CITY", "Seoul")
    asyncio.create_task(update_weather(weather_city))

    # Phase 4: 스폰 스케줄링 (Telegram API 호출 필요, 마지막)
    await schedule_all_chats(application)
    logger.info(f"[{time.monotonic()-t0:.1f}s] Startup complete.")

    # Auto-start tournament registration if flag file exists
    if os.path.exists("/tmp/auto_tournament_reg"):
        os.remove("/tmp/auto_tournament_reg")
        from services.tournament_service import start_registration
        asyncio.create_task(start_registration(application))
        logger.info("Auto-started tournament registration (flag file)")

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
    """Called on shutdown — close DB."""
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
        _grant_title_buffs(),
    )

    # Record reset timestamp
    await pool.execute(
        """INSERT INTO bot_settings (key, value) VALUES ('last_daily_reset', $1)
           ON CONFLICT (key) DO UPDATE SET value = $1""",
        today,
    )

    # Reschedule spawns for all chats
    await schedule_all_chats(context.application)

    logger.info("Scheduled reset complete.")


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

    await update.message.reply_text(
        f"🌍 현재 날씨{temp_text}\n"
        f"{emoji} {label}"
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
    app.add_handler(MessageHandler(dm & filters.Regex(r"^도움말$"), help_handler))
    app.add_handler(MessageHandler((dm | group) & filters.Regex(r"^(📖\s*)?도감"), pokedex_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^날씨$"), weather_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(📦\s*)?내포켓몬\s*\d*$"), my_pokemon_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^밥(\s+.+)?$"), feed_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^놀기(\s+.+)?$"), play_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^진화(\s+.+)?$"), evolve_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^감정(\s+.+)?$"), appraisal_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^상성(\s+.+)?$"), type_chart_handler))
    # DM trade removed — replaced by group reply trade

    # Marketplace (DM) — 구체적 서브커맨드 먼저 등록
    app.add_handler(MessageHandler(dm & filters.Regex(r"^거래소\s*등록\s"), market_register_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^거래소\s*취소\s"), market_cancel_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^거래소\s*구매\s"), market_buy_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^거래소\s*검색\s"), market_search_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^거래소\s*내꺼"), market_my_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^거래소"), market_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(📋\s*)?미션$"), mission_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(📋\s*)?칭호목록$"), title_list_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🏷️\s*)?칭호$"), title_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(📋\s*)?상태창$"), status_handler))

    # Battle system (DM)
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🤝\s*)?파트너(\s+.+)?$"), partner_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^팀등록[12]?(\s|$)"), team_register_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^팀해제[12]?$"), team_clear_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^팀선택"), team_select_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(⚔️\s*)?팀[12]?$"), team_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🏆\s*)?배틀전적$"), battle_stats_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"(?i)^(bp)?구매"), bp_buy_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"(?i)^(🏪\s*)?(bp)?상점$"), bp_shop_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"(?i)^bp$"), bp_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^티어$"), tier_handler))

    # Admin commands (DM)
    app.add_handler(MessageHandler(dm & filters.Regex(r"^통계$"), stats_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^채널목록$"), channel_list_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^이벤트시작"), event_start_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^이벤트목록$"), event_list_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^이벤트종료"), event_end_handler))
    app.add_handler(MessageHandler((dm | group) & filters.Regex(r"^마볼지급"), grant_masterball_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^아케이드"), arcade_handler))
    app.add_handler(MessageHandler((dm | group) & filters.Regex(r"^대회시작$"), force_tournament_reg_handler))
    app.add_handler(MessageHandler((dm | group) & filters.Regex(r"^대회진행$"), force_tournament_run_handler))

    # Group trade (reply with '교환')
    app.add_handler(MessageHandler(group & filters.Regex(r"^교환\s"), group_trade_handler))

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

    # Battle system (Group)
    app.add_handler(MessageHandler(group & filters.Regex(r"^배틀$"), battle_challenge_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^배틀랭킹$"), battle_ranking_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^배틀수락$"), battle_accept_text_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^배틀거절$"), battle_decline_text_handler))

    # Ranked battle (Coming Soon) & Yacha (Betting Battle)
    app.add_handler(MessageHandler(group & filters.Regex(r"^랭전$"), ranked_coming_soon_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^야차$"), yacha_handler))

    # Admin group commands
    app.add_handler(MessageHandler(group & filters.Regex(r"^스폰배율"), spawn_rate_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^\s*강스\s*$"), force_spawn_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^\s*강스권\s*$"), ticket_force_spawn_handler))
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

    # Close message callback (❌ button)
    app.add_handler(CallbackQueryHandler(close_message_callback, pattern=r"^close_msg$"))

    # Catch DM: keep / release callbacks
    app.add_handler(CallbackQueryHandler(catch_keep_callback, pattern=r"^catch_keep_\d+$"))
    app.add_handler(CallbackQueryHandler(catch_release_callback, pattern=r"^catch_release_\d+$"))

    # Pokedex pagination callback
    app.add_handler(CallbackQueryHandler(pokedex_callback, pattern=r"^dex_\d+$"))

    # My Pokemon pagination callback
    app.add_handler(CallbackQueryHandler(my_pokemon_callback, pattern=r"^mypoke_"))

    # Title selection callback
    app.add_handler(CallbackQueryHandler(title_callback, pattern=r"^title_"))

    # Partner selection callback
    app.add_handler(CallbackQueryHandler(partner_callback_handler, pattern=r"^partner_"))

    # Team selection callback
    app.add_handler(CallbackQueryHandler(team_callback_handler, pattern=r"^t(edit|slot_view|pick|rem|p|cl|done|cancel|del)_"))

    # Battle accept/decline callback
    app.add_handler(CallbackQueryHandler(battle_callback_handler, pattern=r"^battle_"))

    # Battle result teabag/delete callback
    app.add_handler(CallbackQueryHandler(battle_result_callback_handler, pattern=r"^b(tbag|del)_"))

    # Shop purchase callback
    app.add_handler(CallbackQueryHandler(shop_callback_handler, pattern=r"^shop_"))

    # Nurture (feed/play/evolve) duplicate selection callbacks
    app.add_handler(CallbackQueryHandler(nurture_callback_handler, pattern=r"^nurt_"))

    # Marketplace callbacks
    app.add_handler(CallbackQueryHandler(market_callback_handler, pattern=r"^mkt_"))

    # Group trade callbacks
    app.add_handler(CallbackQueryHandler(group_trade_callback_handler, pattern=r"^gtrade_"))

    # Tutorial onboarding callbacks
    app.add_handler(CallbackQueryHandler(tutorial_callback, pattern=r"^tut_"))

    # Yacha (betting battle) callbacks
    app.add_handler(CallbackQueryHandler(yacha_type_callback, pattern=r"^yc_"))
    app.add_handler(CallbackQueryHandler(yacha_amount_callback, pattern=r"^ya_"))
    app.add_handler(CallbackQueryHandler(yacha_response_callback, pattern=r"^yacha_"))
    app.add_handler(CallbackQueryHandler(yacha_result_callback, pattern=r"^yres_"))

    # Activity tracker — runs for every group text message (handler group -1)
    app.add_handler(
        MessageHandler(group & filters.TEXT, on_chat_activity),
        group=-1,
    )

    # --- Schedule jobs ---
    # KST = UTC+9
    kst = timezone(timedelta(hours=9))
    app.job_queue.run_daily(
        midnight_reset,
        time=dt_time(0, 0, 0, tzinfo=kst),
        name="reset_midnight",
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

    # --- Start polling ---
    logger.info("Starting bot...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
