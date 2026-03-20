"""자정 리셋 + 관련 헬퍼 함수들."""

import asyncio
import logging

import config
from database import queries, item_queries, mission_queries, spawn_queries

logger = logging.getLogger(__name__)


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
    from services.spawn_service import schedule_all_chats
    await schedule_all_chats(context.application)

    # Activate auto arcade for Lv.8+ chats
    await _activate_auto_arcades(context.application)

    logger.info("Scheduled reset complete.")
