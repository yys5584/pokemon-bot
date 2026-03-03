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
from database.seed import seed_pokemon_data, seed_battle_data
from database import queries

from handlers.start import start_handler, help_handler
from handlers.group import catch_handler, master_ball_handler, hyper_ball_handler, love_easter_egg, love_hidden_handler, ranking_handler, log_handler, dashboard_handler, on_chat_activity, close_message_callback
from handlers.dm_pokedex import pokedex_handler, pokedex_callback, my_pokemon_handler, my_pokemon_callback, title_handler, title_callback, title_list_handler, status_handler
from handlers.battle import (
    partner_handler, partner_callback_handler,
    team_handler, team_register_handler, team_clear_handler, team_select_handler,
    team_callback_handler,
    battle_stats_handler, bp_handler, bp_shop_handler, bp_buy_handler, shop_callback_handler,
    battle_challenge_handler, battle_callback_handler, battle_result_callback_handler,
    battle_ranking_handler, battle_accept_text_handler, battle_decline_text_handler,
    tier_handler,
)
from handlers.dm_nurture import feed_handler, play_handler, evolve_handler
from handlers.dm_trade import trade_handler, accept_handler, reject_handler
from handlers.admin import (
    spawn_rate_handler, force_spawn_handler, force_spawn_reset_handler, ticket_force_spawn_handler,
    pokeball_reset_handler,
    event_start_handler, event_list_handler, event_end_handler,
    stats_handler, channel_list_handler, grant_masterball_handler,
    arcade_handler,
)

from services.spawn_service import schedule_all_chats
from services.weather_service import update_weather, get_current_weather, WEATHER_BOOSTS
from services.tournament_service import start_registration, start_tournament
from handlers.tournament import tournament_join_handler
from dashboard.server import start_dashboard

load_dotenv()

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
)
logger = logging.getLogger(__name__)


# --- Lifecycle hooks ---

async def post_init(application: Application):
    """Called after Application.initialize() — set up DB, seed, schedule."""
    logger.info("Initializing database...")
    await get_db()
    await create_tables()
    await seed_pokemon_data()
    await seed_battle_data()
    logger.info("Database ready. 251 Pokemon seeded.")

    # Cleanup expired sessions and events from previous runs
    await queries.cleanup_expired_sessions()
    await queries.cleanup_expired_events()

    # Fetch initial weather
    weather_city = os.getenv("WEATHER_CITY", "Seoul")
    await update_weather(weather_city)

    # Schedule spawns for all active chats
    await schedule_all_chats(application)
    logger.info("Spawn scheduling complete.")

    # Start dashboard web server
    await start_dashboard()
    logger.info("Dashboard server started.")

    # Notify recently active users about restart
    asyncio.create_task(_notify_restart(application.bot))


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


# --- Midnight reset job ---

async def midnight_reset(context):
    """Reset at 9AM/9PM KST: catch limits, bonus, nurture, force spawn, spawns."""
    logger.info("Running scheduled reset...")

    # Reset daily feed/play counts
    await queries.reset_daily_nurture()

    # Reset catch limits & bonus catches
    await queries.reset_catch_limits()

    # Reset force spawn counts
    await queries.reset_force_spawn_counts()

    # Clean old activity data
    await queries.cleanup_old_activity(days=7)

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

    # Korean commands via MessageHandler + Regex (DM only)
    app.add_handler(MessageHandler(dm & filters.Regex(r"^도움말$"), help_handler))
    app.add_handler(MessageHandler((dm | group) & filters.Regex(r"^(📖\s*)?도감"), pokedex_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^날씨$"), weather_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(📦\s*)?내포켓몬\s*\d*$"), my_pokemon_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^밥(\s+.+)?$"), feed_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^놀기(\s+.+)?$"), play_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^진화(\s+.+)?$"), evolve_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^교환\s"), trade_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^수락"), accept_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^거절"), reject_handler))
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

    # Pokeball recharge
    app.add_handler(MessageHandler(group & filters.Regex(r"^포켓볼\s*충전$"), love_easter_egg))

    # Hidden easter egg
    app.add_handler(MessageHandler(group & filters.Regex(r"^문유\s*사랑해$"), love_hidden_handler))

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

    # Admin group commands
    app.add_handler(MessageHandler(group & filters.Regex(r"^스폰배율"), spawn_rate_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^\s*강제스폰\s*$"), force_spawn_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^\s*강스\s*$"), ticket_force_spawn_handler))
    app.add_handler(MessageHandler(filters.Regex(r"^\s*강제스폰초기화\s*$"), force_spawn_reset_handler))
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

    # Pokedex pagination callback
    app.add_handler(CallbackQueryHandler(pokedex_callback, pattern=r"^dex_\d+$"))

    # My Pokemon pagination callback
    app.add_handler(CallbackQueryHandler(my_pokemon_callback, pattern=r"^mypoke_"))

    # Title selection callback
    app.add_handler(CallbackQueryHandler(title_callback, pattern=r"^title_"))

    # Partner selection callback
    app.add_handler(CallbackQueryHandler(partner_callback_handler, pattern=r"^partner_"))

    # Team selection callback
    app.add_handler(CallbackQueryHandler(team_callback_handler, pattern=r"^t(s|p|ok|cl|del|no)_"))

    # Battle accept/decline callback
    app.add_handler(CallbackQueryHandler(battle_callback_handler, pattern=r"^battle_"))

    # Battle result teabag/delete callback
    app.add_handler(CallbackQueryHandler(battle_result_callback_handler, pattern=r"^b(tbag|del)_"))

    # Shop purchase callback
    app.add_handler(CallbackQueryHandler(shop_callback_handler, pattern=r"^shop_"))

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
        time=dt_time(9, 0, 0, tzinfo=kst),
        name="reset_9am",
    )
    app.job_queue.run_daily(
        midnight_reset,
        time=dt_time(21, 0, 0, tzinfo=kst),
        name="reset_9pm",
    )

    # 3-hourly catch recharge (50%) at 0, 3, 6, 12, 15, 18 KST
    # (9 KST and 21 KST already do full reset via midnight_reset)
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

    # Tournament schedule (21:00 registration, 22:00 start — KST)
    app.job_queue.run_daily(
        start_registration,
        time=dt_time(config.TOURNAMENT_REG_HOUR, 0, 0, tzinfo=kst),
        name="tournament_reg",
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
