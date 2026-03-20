"""Spawn scheduling: daily spawn scheduling, arcade management, rarity rolling."""

import asyncio
import random
import logging
from datetime import timedelta

from telegram.ext import ContextTypes

import config

from database import queries, spawn_queries
from services.event_service import get_spawn_boost, get_rarity_weights
from services.weather_service import get_weather_pokemon_boost

logger = logging.getLogger(__name__)


def calculate_daily_spawns(member_count: int) -> int:
    """Calculate how many spawns per day based on member count.
    Optimized for small groups (10~50 members)."""
    if member_count < config.SPAWN_MIN_MEMBERS:
        return 0

    for min_m, max_m, spawns in config.SPAWN_TIERS:
        if min_m <= member_count <= max_m:
            return spawns

    # 500+ members: original formula
    return 2 + (member_count - 10) // 500


async def roll_rarity(midnight_bonus: bool = False, rarity_boosts: dict | None = None) -> str:
    """Roll a rarity tier based on weights, with event + chat level boosts applied."""
    base_weights = config.RARITY_WEIGHTS_MIDNIGHT if midnight_bonus else config.RARITY_WEIGHTS
    weights_map = await get_rarity_weights(base_weights)
    # Apply chat level rarity boosts (e.g. {"epic": 1.15, "legendary": 1.10})
    if rarity_boosts:
        for r, mult in rarity_boosts.items():
            if r in weights_map:
                weights_map[r] *= mult
    rarities = list(weights_map.keys())
    weights = list(weights_map.values())
    return random.choices(rarities, weights=weights, k=1)[0]


def is_midnight_bonus() -> bool:
    """Check if current time is in the midnight bonus window (2am-5am KST)."""
    hour = config.get_kst_hour()
    return config.MIDNIGHT_BONUS_START <= hour < config.MIDNIGHT_BONUS_END


async def pick_random_pokemon(rarity: str) -> dict:
    """Pick a random Pokemon of the given rarity.
    Pokemon with active pokemon_boost events get weighted higher."""
    candidates = await queries.get_pokemon_by_rarity(rarity)
    if not candidates:
        candidates = await queries.get_pokemon_by_rarity("common")

    # Get ALL pokemon boosts in one call (instead of N separate DB queries)
    from services.event_service import get_all_pokemon_boosts
    pokemon_boosts = await get_all_pokemon_boosts()

    # Apply pokemon_boost event weights + weather boost
    weights = []
    for p in candidates:
        event_boost = pokemon_boosts.get(p["id"], 1.0)
        weather_boost = get_weather_pokemon_boost(p["id"])
        weights.append(event_boost * weather_boost)

    return random.choices(candidates, weights=weights, k=1)[0]


async def schedule_spawns_for_chat(app, chat_id: int, member_count: int):
    """Schedule today's spawns for a single chat."""
    from services.spawn_execute import execute_spawn

    # Cancel ALL spawn-related jobs for this chat (scheduled, retries, welcome)
    chat_str = str(chat_id)
    for job in app.job_queue.jobs():
        if job.name and chat_str in job.name and (
            job.name.startswith("spawn_") or job.name.startswith("welcome_spawn_")
        ):
            job.schedule_removal()

    base_spawns = calculate_daily_spawns(member_count)
    if base_spawns <= 0:
        return

    # Apply chat-specific multiplier
    chat_mult = await queries.get_spawn_multiplier(chat_id)
    # Apply global event multiplier
    event_mult = await get_spawn_boost()
    num_spawns = min(config.SPAWN_MAX_DAILY, max(1, int(base_spawns * chat_mult * event_mult)))

    # Chat level bonus spawns
    level_info = None
    try:
        level_row = await queries.get_chat_level(chat_id)
        if level_row:
            level_info = config.get_chat_level_info(level_row["cxp"])
            if level_info["spawn_bonus"] > 0:
                num_spawns = min(config.SPAWN_MAX_DAILY, num_spawns + level_info["spawn_bonus"])
    except Exception as e:
        logger.error(f"Chat level lookup failed for {chat_id}: {e}")

    await queries.update_chat_spawn_info(chat_id, num_spawns)

    now = config.get_kst_now()
    end_of_day = now.replace(hour=23, minute=59, second=59)

    remaining_seconds = (end_of_day - now).total_seconds()
    if remaining_seconds < 3600:  # Less than 1 hour left in the day
        return

    min_gap = config.SPAWN_MIN_GAP_HOURS * 3600
    spawn_times = []

    for _ in range(num_spawns * 20):  # Try up to 20x to find valid times
        offset = random.uniform(300, remaining_seconds)  # At least 5 min from now
        candidate = now + timedelta(seconds=offset)

        if all(abs((candidate - t).total_seconds()) >= min_gap for t in spawn_times):
            spawn_times.append(candidate)
            if len(spawn_times) >= num_spawns:
                break

    spawn_times.sort()

    # Determine which spawn index should be force_shiny (Lv.4+ daily shiny)
    force_shiny_idx = -1
    if level_info and "daily_shiny" in level_info.get("specials", []):
        force_shiny_idx = random.randrange(len(spawn_times)) if spawn_times else -1

    for i, st in enumerate(spawn_times):
        delay = (st - now).total_seconds()
        if delay > 0:
            job_data = {"chat_id": chat_id}
            if i == force_shiny_idx:
                job_data["force_shiny"] = True
            app.job_queue.run_once(
                execute_spawn,
                when=delay,
                data=job_data,
                name=f"spawn_{chat_id}_{st.strftime('%H%M%S')}",
            )

    logger.info(
        f"Scheduled {len(spawn_times)} spawns for chat {chat_id} "
        f"(members: {member_count}, level_bonus: {level_info['spawn_bonus'] if level_info else 0})"
    )


async def schedule_all_chats(app):
    """Schedule spawns for all active chat rooms."""
    from services.spawn_service import cleanup_old_attempt_messages

    # Clean up stale attempt messages from previous run
    cleanup_old_attempt_messages()
    # Load arcade channels from DB into config
    config.ARCADE_CHAT_IDS = await queries.get_arcade_chat_ids()
    if config.ARCADE_CHAT_IDS:
        logger.info(f"Loaded arcade channels from DB: {config.ARCADE_CHAT_IDS}")

    chats = await queries.get_all_active_chats()

    # 채팅방별 멤버수 조회 + 스폰 스케줄링 병렬 처리
    async def _schedule_one(chat):
        cid = chat["chat_id"]
        if cid in config.ARCADE_CHAT_IDS:
            return
        try:
            count = await app.bot.get_chat_member_count(cid)
            await queries.update_chat_member_count(cid, count)
        except Exception:
            count = chat["member_count"]
        await schedule_spawns_for_chat(app, cid, count)

    # 동시 5개씩 배치 (Telegram API rate limit 방지)
    sem = asyncio.Semaphore(5)
    async def _limited(chat):
        async with sem:
            try:
                await _schedule_one(chat)
            except Exception as e:
                logger.error(f"Failed to schedule for chat {chat['chat_id']}: {e}")

    await asyncio.gather(*[_limited(c) for c in chats])

    # Schedule permanent arcade channels (repeating every N seconds)
    schedule_arcade_spawns(app)

    # Restore temporary arcade passes from DB
    await restore_temp_arcades(app)


def schedule_arcade_spawns(app):
    """Set up repeating spawn jobs for arcade channels."""
    from services.spawn_execute import execute_spawn

    for chat_id in config.ARCADE_CHAT_IDS:
        job_name = f"arcade_{chat_id}"
        # Remove existing arcade jobs for this chat
        for job in app.job_queue.jobs():
            if job.name == job_name:
                job.schedule_removal()

        app.job_queue.run_repeating(
            execute_spawn,
            interval=config.ARCADE_SPAWN_INTERVAL,
            first=10,  # 10초 후 첫 스폰
            data={"chat_id": chat_id, "force": True},
            name=job_name,
        )
        logger.info(f"Arcade spawns scheduled for chat {chat_id} "
                     f"(every {config.ARCADE_SPAWN_INTERVAL}s)")


def start_temp_arcade(app, chat_id: int, duration_seconds: int, interval: int | None = None):
    """Start temporary arcade spawns for a chat. Auto-stops after duration."""
    from services.spawn_execute import execute_spawn

    spawn_interval = interval or config.ARCADE_SPAWN_INTERVAL
    job_name = f"arcade_{chat_id}"
    # Remove any existing arcade job for this chat
    for job in app.job_queue.jobs():
        if job.name == job_name:
            job.schedule_removal()

    app.job_queue.run_repeating(
        execute_spawn,
        interval=spawn_interval,
        first=10,
        data={"chat_id": chat_id, "force": True, "interval": spawn_interval},
        name=job_name,
    )

    # Schedule auto-stop after duration
    app.job_queue.run_once(
        _expire_temp_arcade,
        when=duration_seconds,
        data={"chat_id": chat_id},
        name=f"arcade_expire_{chat_id}",
    )

    logger.info(f"Temp arcade started for chat {chat_id} ({duration_seconds}s)")


def stop_arcade_for_chat(app, chat_id: int):
    """Stop arcade spawns for a specific chat."""
    for job in app.job_queue.jobs():
        if job.name in (f"arcade_{chat_id}", f"arcade_expire_{chat_id}"):
            job.schedule_removal()
    logger.info(f"Arcade stopped for chat {chat_id}")


def get_arcade_state(app, chat_id: int) -> dict | None:
    """아케이드 상태 조회. active=True이면 interval, speed_boosted 포함."""
    for job in app.job_queue.jobs():
        if job.name == f"arcade_{chat_id}" and job.removed is False:
            data = job.data or {}
            return {
                "active": True,
                "interval": data.get("interval", config.ARCADE_SPAWN_INTERVAL),
                "speed_boosted": data.get("speed_boosted", False),
            }
    return None


def set_arcade_interval(app, chat_id: int, new_interval: int):
    """활성 아케이드의 스폰 간격 변경."""
    from services.spawn_execute import execute_spawn

    job_name = f"arcade_{chat_id}"
    for job in app.job_queue.jobs():
        if job.name == job_name:
            job.schedule_removal()

    app.job_queue.run_repeating(
        execute_spawn,
        interval=new_interval,
        first=new_interval,
        data={"chat_id": chat_id, "force": True, "interval": new_interval, "speed_boosted": True},
        name=job_name,
    )
    logger.info(f"Arcade interval changed for {chat_id}: {new_interval}s")


async def extend_arcade_time(app, chat_id: int, extend_minutes: int):
    """활성 아케이드 시간 연장 (DB 업데이트 → 만료 잡 재스케줄)."""
    # DB 먼저 업데이트 — 실패 시 잡 스케줄 변경 방지
    from database.queries import extend_arcade_pass
    await extend_arcade_pass(chat_id, extend_minutes)

    expire_name = f"arcade_expire_{chat_id}"
    remaining = 0

    for job in app.job_queue.jobs():
        if job.name == expire_name and job.removed is False:
            if job.next_t:
                from datetime import datetime, timezone as tz
                now = datetime.now(tz.utc)
                remaining = max(0, int((job.next_t - now).total_seconds()))
            job.schedule_removal()
            break

    new_remaining = remaining + (extend_minutes * 60)
    app.job_queue.run_once(
        _expire_temp_arcade,
        when=new_remaining,
        data={"chat_id": chat_id},
        name=expire_name,
    )

    logger.info(f"Arcade extended for {chat_id}: +{extend_minutes}m (total remaining: {new_remaining}s)")


async def _expire_temp_arcade(context: ContextTypes.DEFAULT_TYPE):
    """Auto-expire a temporary arcade session."""
    chat_id = context.job.data["chat_id"]

    # Don't stop if it's a permanent arcade channel
    if chat_id in config.ARCADE_CHAT_IDS:
        return

    # Stop arcade spawns
    stop_arcade_for_chat(context.application, chat_id)

    # Deactivate pass in DB
    await queries.expire_arcade_passes()

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text="🕹️ 아케이드 시간 종료! 일반 스폰으로 복구됩니다.",
        )
    except Exception:
        pass

    logger.info(f"Temp arcade expired for chat {chat_id}")


async def restore_temp_arcades(app):
    """On bot restart, restore any active temp arcade passes."""
    active_passes = await queries.get_all_active_arcade_passes()
    for ap in active_passes:
        chat_id = ap["chat_id"]
        if chat_id in config.ARCADE_CHAT_IDS:
            continue  # Skip permanent arcades

        expires = ap["expires_at"]
        if hasattr(expires, 'tzinfo') and expires.tzinfo is None:
            expires = expires.replace(tzinfo=config.KST)
        remaining = max(0, int((expires - config.get_kst_now()).total_seconds()))

        if remaining > 30:  # At least 30 seconds left
            start_temp_arcade(app, chat_id, remaining, interval=config.ARCADE_TICKET_SPAWN_INTERVAL)
            logger.info(f"Restored temp arcade for chat {chat_id} ({remaining}s remaining)")
