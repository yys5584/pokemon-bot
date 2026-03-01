"""Spawn system: scheduling, rarity rolling, spawn execution."""

import random
import logging
from datetime import datetime, timedelta, time as dt_time

from telegram.ext import ContextTypes

import config
from database import queries
from services.event_service import get_spawn_boost, get_rarity_weights, get_catch_boost, get_pokemon_boost
from services.weather_service import get_weather_pokemon_boost, get_weather_display
from utils.card_generator import generate_card
from utils.helpers import close_button

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


async def roll_rarity(midnight_bonus: bool = False) -> str:
    """Roll a rarity tier based on weights, with event boosts applied."""
    base_weights = config.RARITY_WEIGHTS_MIDNIGHT if midnight_bonus else config.RARITY_WEIGHTS
    weights_map = await get_rarity_weights(base_weights)
    rarities = list(weights_map.keys())
    weights = list(weights_map.values())
    return random.choices(rarities, weights=weights, k=1)[0]


def is_midnight_bonus() -> bool:
    """Check if current time is in the midnight bonus window (2am-5am KST)."""
    hour = datetime.now().hour
    return config.MIDNIGHT_BONUS_START <= hour < config.MIDNIGHT_BONUS_END


async def pick_random_pokemon(rarity: str) -> dict:
    """Pick a random Pokemon of the given rarity.
    Pokemon with active pokemon_boost events get weighted higher."""
    candidates = await queries.get_pokemon_by_rarity(rarity)
    if not candidates:
        candidates = await queries.get_pokemon_by_rarity("common")

    # Apply pokemon_boost event weights + weather boost
    weights = []
    for p in candidates:
        event_boost = await get_pokemon_boost(p["id"])
        weather_boost = get_weather_pokemon_boost(p["id"])
        weights.append(event_boost * weather_boost)

    return random.choices(candidates, weights=weights, k=1)[0]


async def schedule_spawns_for_chat(app, chat_id: int, member_count: int):
    """Schedule today's spawns for a single chat."""
    # Cancel existing spawn jobs for this chat to prevent duplicates
    for job in app.job_queue.jobs():
        if job.name and job.name.startswith(f"spawn_{chat_id}_"):
            job.schedule_removal()

    base_spawns = calculate_daily_spawns(member_count)
    if base_spawns <= 0:
        return

    # Apply chat-specific multiplier
    chat_mult = await queries.get_spawn_multiplier(chat_id)
    # Apply global event multiplier
    event_mult = await get_spawn_boost()
    num_spawns = max(1, int(base_spawns * chat_mult * event_mult))

    await queries.update_chat_spawn_info(chat_id, num_spawns)

    now = datetime.now()
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

    for st in spawn_times:
        delay = (st - now).total_seconds()
        if delay > 0:
            app.job_queue.run_once(
                execute_spawn,
                when=delay,
                data={"chat_id": chat_id},
                name=f"spawn_{chat_id}_{st.strftime('%H%M%S')}",
            )

    logger.info(
        f"Scheduled {len(spawn_times)} spawns for chat {chat_id} "
        f"(members: {member_count})"
    )


async def schedule_all_chats(app):
    """Schedule spawns for all active chat rooms."""
    chats = await queries.get_all_active_chats()
    for chat in chats:
        try:
            # Try to update member count from Telegram
            try:
                count = await app.bot.get_chat_member_count(chat["chat_id"])
                await queries.update_chat_member_count(chat["chat_id"], count)
            except Exception:
                count = chat["member_count"]

            await schedule_spawns_for_chat(app, chat["chat_id"], count)
        except Exception as e:
            logger.error(f"Failed to schedule for chat {chat['chat_id']}: {e}")


async def execute_spawn(context: ContextTypes.DEFAULT_TYPE):
    """Execute a single spawn event. Called by JobQueue."""
    chat_id = context.job.data["chat_id"]
    force = context.job.data.get("force", False)

    try:
        # 1. Activity check (skip if force spawn)
        if not force:
            activity = await queries.get_recent_activity(chat_id, hours=1)
            if activity < 1:
                # No activity — retry later
                retry_delay = random.randint(
                    config.SPAWN_RETRY_MIN_SECONDS,
                    config.SPAWN_RETRY_MAX_SECONDS,
                )
                context.job_queue.run_once(
                    execute_spawn,
                    when=retry_delay,
                    data={"chat_id": chat_id},
                    name=f"spawn_retry_{chat_id}",
                )
                logger.info(f"No activity in {chat_id}, retrying in {retry_delay}s")
                return

        # 2. Check if there's already an active spawn
        active = await queries.get_active_spawn(chat_id)
        if active:
            return

        # 3. Roll rarity with midnight bonus + event boosts
        midnight = is_midnight_bonus()
        rarity = await roll_rarity(midnight_bonus=midnight)

        # 4. Pick random Pokemon
        pokemon = await pick_random_pokemon(rarity)

        # 5. Generate card image FIRST (before creating session)
        bonus_text = " 🌙" if midnight else ""

        # Check for active event indicator
        from services.event_service import get_active_event_summary
        event_summary = await get_active_event_summary()
        event_tag = " 🎪" if event_summary else ""

        # Weather indicator
        weather_tag = get_weather_display()

        caption = (
            f"🌿 야생의 {pokemon['emoji']} {pokemon['name_ko']}이(가) 나타났다!{bonus_text}{event_tag}{weather_tag}\n"
            f"ㅊ 입력으로 잡기 ({config.SPAWN_WINDOW_SECONDS}초)"
        )

        # Generate card image
        card_buf = generate_card(pokemon["id"], pokemon["name_ko"], rarity, pokemon["emoji"])

        # Send photo BEFORE creating session (so catch isn't possible without image)
        message = await context.bot.send_photo(
            chat_id=chat_id,
            photo=card_buf,
            caption=caption,
            reply_markup=close_button(),
        )

        # 6. Create spawn session AFTER image is sent
        expires = (datetime.now() + timedelta(seconds=config.SPAWN_WINDOW_SECONDS))
        expires_str = expires.strftime("%Y-%m-%d %H:%M:%S")

        session_id = await queries.create_spawn_session(
            chat_id, pokemon["id"], expires_str
        )

        # Update session with message_id
        from database.connection import get_db
        db = await get_db()
        await db.execute(
            "UPDATE spawn_sessions SET message_id = ? WHERE id = ?",
            (message.message_id, session_id),
        )
        await db.commit()

        # 7. Record spawn
        await queries.record_spawn_in_chat(chat_id)

        # 8. Schedule resolution after 30 seconds
        context.job_queue.run_once(
            resolve_spawn,
            when=config.SPAWN_WINDOW_SECONDS,
            data={
                "chat_id": chat_id,
                "session_id": session_id,
                "pokemon_id": pokemon["id"],
                "pokemon_name": pokemon["name_ko"],
                "pokemon_emoji": pokemon["emoji"],
                "rarity": rarity,
            },
            name=f"resolve_{session_id}",
        )

        logger.info(
            f"Spawned {pokemon['name_ko']} ({rarity}) in chat {chat_id}"
        )

    except Exception as e:
        logger.error(f"Spawn execution failed for chat {chat_id}: {e}")


async def resolve_spawn(context: ContextTypes.DEFAULT_TYPE):
    """Resolve a spawn after 30 seconds. Determine who catches the Pokemon."""
    data = context.job.data
    chat_id = data["chat_id"]
    session_id = data["session_id"]
    pokemon_id = data["pokemon_id"]
    pokemon_name = data["pokemon_name"]
    pokemon_emoji = data["pokemon_emoji"]
    rarity = data["rarity"]

    try:
        # Get all catch attempts
        attempts = await queries.get_session_attempts(session_id)

        if not attempts:
            # Nobody tried
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"흔들흔들... 💨 도망갔다!",
                reply_markup=close_button(),
            )
            await queries.close_spawn_session(session_id)
            await queries.log_spawn(
                chat_id, pokemon_id, pokemon_name, pokemon_emoji,
                rarity, None, None, 0,
            )
            return

        # Get catch rate with event boost
        pokemon = await queries.get_pokemon(pokemon_id)
        base_rate = pokemon["catch_rate"] if pokemon else 0.5
        catch_boost = await get_catch_boost()
        catch_rate = min(1.0, base_rate * catch_boost)

        # Roll for each catcher (master ball = guaranteed success)
        results = []
        for attempt in attempts:
            if attempt.get("used_master_ball"):
                roll = 0.0
                success = True
            else:
                roll = random.random()
                success = roll < catch_rate
            results.append({
                "user_id": attempt["user_id"],
                "display_name": attempt["display_name"],
                "username": attempt["username"],
                "roll": roll,
                "success": success,
                "used_master_ball": bool(attempt.get("used_master_ball")),
            })

        winners = [r for r in results if r["success"]]
        participants = len(attempts)

        if not winners:
            # Everyone failed
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"흔들흔들... 💨 도망갔다!",
                reply_markup=close_button(),
            )
            await queries.close_spawn_session(session_id)
            await queries.log_spawn(
                chat_id, pokemon_id, pokemon_name, pokemon_emoji,
                rarity, None, None, participants,
            )
            return

        # Pick winner (lowest roll = luckiest)
        winners.sort(key=lambda x: x["roll"])
        winner = winners[0]
        winner_id = winner["user_id"]
        winner_name = winner["display_name"]

        # Give Pokemon
        await queries.give_pokemon_to_user(winner_id, pokemon_id, chat_id)
        await queries.register_pokedex(winner_id, pokemon_id, "catch")
        await queries.close_spawn_session(session_id, caught_by=winner_id)

        # Update consecutive catches
        today = datetime.now().strftime("%Y-%m-%d")
        await queries.increment_consecutive(winner_id, today)

        # Reset consecutive for everyone who failed
        for r in results:
            if not r["success"]:
                await queries.reset_consecutive(r["user_id"], today)

        # Check if first catch in chat (for rare+ announcement)
        is_first = await queries.is_first_catch_in_chat(chat_id, pokemon_id)

        # Build message with decorated name (HTML bold for titled users)
        from utils.helpers import get_decorated_name
        user_data = await queries.get_user(winner_id)
        decorated = get_decorated_name(
            winner_name,
            user_data.get("title", "") if user_data else "",
            user_data.get("title_emoji", "") if user_data else "",
            winner.get("username"),
            html=True,
        )

        if winner.get("used_master_ball"):
            msg = f"🟣 마스터볼! {decorated} — {pokemon_emoji} {pokemon_name} 확정 포획!"
            await queries.increment_title_stat(winner_id, "master_ball_used")
        elif rarity in ("epic", "legendary") and is_first:
            msg = f"🌟 {decorated} — {pokemon_emoji} {pokemon_name} 포획! (이 방 최초)"
        else:
            msg = f"딸깍! ✨ {decorated} — {pokemon_emoji} {pokemon_name} 포획!"

        # Track midnight catch for title
        hour = datetime.now().hour
        if 2 <= hour < 5:
            await queries.increment_title_stat(winner_id, "midnight_catch_count")

        # Track catch failures for title
        for r in results:
            if not r["success"]:
                await queries.increment_title_stat(r["user_id"], "catch_fail_count")

        # Master Ball random drop (2% chance on catch)
        master_ball_drop = random.random() < 0.02
        if master_ball_drop:
            await queries.add_master_ball(winner_id)
            msg += "\n\n🟣 마스터볼을 획득했다!"

        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML", reply_markup=close_button())

        # Check and unlock titles
        from utils.title_checker import check_and_unlock_titles
        from utils.helpers import escape_html
        new_titles = await check_and_unlock_titles(winner_id)
        if new_titles:
            title_msgs = [f"🎉 <b>「{temoji} {tname}」</b> 칭호 해금!" for _, tname, temoji in new_titles]
            safe_name = escape_html(winner_name)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🏷️ {safe_name}의 새 칭호!\n" + "\n".join(title_msgs) + "\nDM에서 '칭호'로 장착하세요!",
                parse_mode="HTML",
                reply_markup=close_button(),
            )

        # Also check titles for failed catchers
        for r in results:
            if not r["success"]:
                await check_and_unlock_titles(r["user_id"])

        # Log
        await queries.log_spawn(
            chat_id, pokemon_id, pokemon_name, pokemon_emoji,
            rarity, winner_id, winner_name, participants,
        )

        logger.info(
            f"{winner_name} caught {pokemon_name} in chat {chat_id}"
        )

    except Exception as e:
        logger.error(f"Spawn resolution failed for session {session_id}: {e}")
        await queries.close_spawn_session(session_id)
