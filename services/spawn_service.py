"""Spawn system: scheduling, rarity rolling, spawn execution."""

import asyncio
import random
import logging
from datetime import datetime, timedelta, time as dt_time

from telegram.ext import ContextTypes

import config
from database import queries
from services.event_service import get_spawn_boost, get_rarity_weights, get_catch_boost, get_pokemon_boost
from services.weather_service import get_weather_pokemon_boost, get_weather_display
from utils.card_generator import generate_card
from utils.helpers import schedule_delete, close_button, rarity_badge, type_badge

logger = logging.getLogger(__name__)

# Track attempt messages for cleanup when spawn resolves
# {session_id: [(chat_id, message_id), ...]}
_attempt_messages: dict[int, list[tuple[int, int]]] = {}


def track_attempt_message(session_id: int, chat_id: int, message_id: int):
    """Store an attempt message for later deletion."""
    if session_id not in _attempt_messages:
        _attempt_messages[session_id] = []
    _attempt_messages[session_id].append((chat_id, message_id))


async def _delete_attempt_messages(bot, session_id: int):
    """Delete all tracked attempt messages for a resolved spawn."""
    messages = _attempt_messages.pop(session_id, [])
    for cid, mid in messages:
        try:
            await bot.delete_message(chat_id=cid, message_id=mid)
        except Exception:
            pass


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
    # Load arcade channels from DB into config
    config.ARCADE_CHAT_IDS = await queries.get_arcade_chat_ids()
    if config.ARCADE_CHAT_IDS:
        logger.info(f"Loaded arcade channels from DB: {config.ARCADE_CHAT_IDS}")

    chats = await queries.get_all_active_chats()
    for chat in chats:
        try:
            cid = chat["chat_id"]
            # Skip arcade channels (they use their own scheduler)
            if cid in config.ARCADE_CHAT_IDS:
                continue

            # Try to update member count from Telegram
            try:
                count = await app.bot.get_chat_member_count(cid)
                await queries.update_chat_member_count(cid, count)
            except Exception:
                count = chat["member_count"]

            await schedule_spawns_for_chat(app, cid, count)
        except Exception as e:
            logger.error(f"Failed to schedule for chat {chat['chat_id']}: {e}")

    # Schedule permanent arcade channels (repeating every N seconds)
    schedule_arcade_spawns(app)

    # Restore temporary arcade passes from DB
    await restore_temp_arcades(app)


def schedule_arcade_spawns(app):
    """Set up repeating spawn jobs for arcade channels."""
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
        data={"chat_id": chat_id, "force": True},
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

        from datetime import datetime, timezone
        expires = ap["expires_at"]
        if hasattr(expires, 'tzinfo') and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        remaining = max(0, int((expires - datetime.now(timezone.utc)).total_seconds()))

        if remaining > 30:  # At least 30 seconds left
            start_temp_arcade(app, chat_id, remaining, interval=config.ARCADE_TICKET_SPAWN_INTERVAL)
            logger.info(f"Restored temp arcade for chat {chat_id} ({remaining}s remaining)")


async def execute_spawn(context: ContextTypes.DEFAULT_TYPE):
    """Execute a single spawn event. Called by JobQueue."""
    chat_id = context.job.data["chat_id"]
    force = context.job.data.get("force", False)
    # Arcade = permanent OR temp arcade (job name starts with arcade_)
    job_name = getattr(context.job, "name", None) or ""
    arcade = chat_id in config.ARCADE_CHAT_IDS or job_name.startswith(f"arcade_{chat_id}")

    try:
        # 1. Activity check (skip if force spawn or arcade)
        if not force and not arcade:
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
            if not arcade and not force:
                return  # Normal spawn: skip if active spawn exists
            # Arcade/force: close old spawn before creating new one
            await queries.close_spawn_session(active["id"])
            old_resolve_name = f"resolve_{active['id']}"
            for job in context.job_queue.jobs():
                if job.name == old_resolve_name:
                    job.schedule_removal()
                    break
            # Delete old spawn message from chat
            old_msg_id = active.get("message_id")
            if old_msg_id:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=old_msg_id)
                except Exception:
                    pass  # Message may already be deleted
            logger.info(f"Closed overlapping spawn {active['id']} in {chat_id}")

        # 2.5 Cooldown: skip if last spawn was within 5 minutes (skip for arcade and force)
        if not arcade and not force:
            last_spawn = await queries.get_last_spawn_time(chat_id)
            if last_spawn:
                elapsed = (datetime.now() - last_spawn).total_seconds()
                if elapsed < 300:  # 5 minutes cooldown
                    logger.debug(f"Spawn cooldown for {chat_id}: {elapsed:.0f}s since last spawn")
                    return

        # 3. Roll rarity with midnight bonus + event boosts
        midnight = is_midnight_bonus()
        rarity = await roll_rarity(midnight_bonus=midnight)

        # 4. Pick random Pokemon
        pokemon = await pick_random_pokemon(rarity)

        # 4.5 Shiny determination
        shiny_rate = config.SHINY_RATE_ARCADE if arcade else config.SHINY_RATE_NATURAL
        is_shiny = random.random() < shiny_rate

        # 5. Generate card image FIRST (before creating session)
        shiny_text = " ✨이로치" if is_shiny else ""
        bonus_text = " 🌙" if midnight else ""

        # Check for active event indicator
        from services.event_service import get_active_event_summary
        event_summary = await get_active_event_summary()
        event_tag = " 🎪" if event_summary else ""

        # Weather indicator
        weather_tag = get_weather_display()

        # Arcade channels use shorter window to avoid overlap
        window = config.ARCADE_SPAWN_WINDOW if arcade else config.SPAWN_WINDOW_SECONDS

        tb = type_badge(pokemon["id"], pokemon.get("pokemon_type"))
        caption = (
            f"🌿 야생의{shiny_text} {tb} {pokemon['name_ko']}이(가) 나타났다!{bonus_text}{event_tag}{weather_tag}\n"
            f"ㅊ 입력으로 잡기 ({window}초)"
        )

        # Generate card image (run in executor to avoid blocking event loop)
        loop = asyncio.get_event_loop()
        card_buf = await loop.run_in_executor(
            None, generate_card, pokemon["id"], pokemon["name_ko"], rarity, pokemon["emoji"]
        )

        # Send photo BEFORE creating session (so catch isn't possible without image)
        message = await context.bot.send_photo(
            chat_id=chat_id,
            photo=card_buf,
            caption=caption,
            parse_mode="HTML",
        )

        # 6. Create spawn session AFTER image is sent
        expires = (datetime.now() + timedelta(seconds=window))

        session_id = await queries.create_spawn_session(
            chat_id, pokemon["id"], expires, is_shiny=is_shiny,
        )

        # Update session with message_id
        from database.connection import get_db
        pool = await get_db()
        await pool.execute(
            "UPDATE spawn_sessions SET message_id = $1 WHERE id = $2",
            message.message_id, session_id,
        )

        # 7. Record spawn
        await queries.record_spawn_in_chat(chat_id)

        # 8. Schedule resolution
        context.job_queue.run_once(
            resolve_spawn,
            when=window,
            data={
                "chat_id": chat_id,
                "session_id": session_id,
                "pokemon_id": pokemon["id"],
                "pokemon_name": pokemon["name_ko"],
                "pokemon_emoji": pokemon["emoji"],
                "rarity": rarity,
                "is_shiny": is_shiny,
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
    is_shiny = data.get("is_shiny", False)

    try:
        # Check if session is already resolved (avoid duplicate resolution)
        from database.connection import get_db
        pool = await get_db()
        row = await pool.fetchrow(
            "SELECT is_resolved FROM spawn_sessions WHERE id = $1", session_id
        )
        if not row or row["is_resolved"] == 1:
            logger.debug(f"Session {session_id} already resolved, skipping")
            return

        # Mark as resolved FIRST to prevent race condition with catch/master ball handlers
        await pool.execute(
            "UPDATE spawn_sessions SET is_resolved = 1 WHERE id = $1",
            session_id,
        )

        # Get all catch attempts
        attempts = await queries.get_session_attempts(session_id)

        # Clean up tracking (but keep messages visible)
        _attempt_messages.pop(session_id, None)

        if not attempts:
            # Nobody tried
            shiny_tag = " ✨이로치" if is_shiny else ""
            rbadge = rarity_badge(rarity)
            tb = type_badge(pokemon_id)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"흔들흔들... 💨{shiny_tag} {rbadge}{tb} {pokemon_name} 도망갔다!",
                parse_mode="HTML",
            )
            await queries.close_spawn_session(session_id)
            await queries.log_spawn(
                chat_id, pokemon_id, pokemon_name, pokemon_emoji,
                rarity, None, None, 0, is_shiny=is_shiny,
            )
            return

        # Get catch rate with event boost
        pokemon = await queries.get_pokemon(pokemon_id)
        base_rate = pokemon["catch_rate"] if pokemon else 0.5
        catch_boost = await get_catch_boost()
        catch_rate = min(1.0, base_rate * catch_boost)

        # Roll for each catcher (master ball > hyper ball > newbie > regular)
        results = []
        for attempt in attempts:
            if attempt.get("used_master_ball"):
                roll = -1.0  # Highest priority
                success = True
            elif attempt.get("used_hyper_ball"):
                # Hyper ball: 3x catch rate
                hyper_rate = min(1.0, catch_rate * config.HYPER_BALL_CATCH_MULTIPLIER)
                roll = random.random()
                success = roll < hyper_rate
            else:
                # Newbie boost: first 2 catches are guaranteed
                total = await queries.count_total_catches(attempt["user_id"])
                if total < 2:
                    roll = 0.0  # Lower priority than master ball
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
                "used_hyper_ball": bool(attempt.get("used_hyper_ball")),
            })

        winners = [r for r in results if r["success"]]
        participants = len(attempts)

        if not winners:
            # Everyone failed
            shiny_tag = " ✨이로치" if is_shiny else ""
            rbadge = rarity_badge(rarity)
            tb = type_badge(pokemon_id)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"흔들흔들... 💨{shiny_tag} {rbadge}{tb} {pokemon_name} 도망갔다!",
                parse_mode="HTML",
            )
            await queries.close_spawn_session(session_id)
            await queries.log_spawn(
                chat_id, pokemon_id, pokemon_name, pokemon_emoji,
                rarity, None, None, participants, is_shiny=is_shiny,
            )
            return

        # Pick winner (lowest roll = luckiest)
        winners.sort(key=lambda x: x["roll"])
        winner = winners[0]
        winner_id = winner["user_id"]
        winner_name = winner["display_name"]

        # Refund master balls to losers who used one but didn't win
        master_ball_losers = [
            r for r in results
            if r["used_master_ball"] and r["user_id"] != winner_id
        ]
        for loser in master_ball_losers:
            await queries.add_master_ball(loser["user_id"])
            logger.info(f"Refunded master ball to {loser['display_name']} ({loser['user_id']})")

        # Give Pokemon (with IV generation)
        _inst_id, caught_ivs = await queries.give_pokemon_to_user(
            winner_id, pokemon_id, chat_id, is_shiny=is_shiny,
        )
        await queries.register_pokedex(winner_id, pokemon_id, "catch")
        await queries.close_spawn_session(session_id, caught_by=winner_id)

        # Update consecutive catches
        today = config.get_kst_today()
        await queries.increment_consecutive(winner_id, today)

        # Reset consecutive for everyone who failed (batch)
        failed_ids = [r["user_id"] for r in results if not r["success"]]
        if failed_ids:
            await asyncio.gather(
                *(queries.reset_consecutive(uid, today) for uid in failed_ids)
            )

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

        shiny_label = "✨이로치 " if is_shiny else ""

        # IV grade display
        from utils.battle_calc import iv_total
        iv_sum = iv_total(caught_ivs["iv_hp"], caught_ivs["iv_atk"],
                          caught_ivs["iv_def"], caught_ivs["iv_spa"],
                          caught_ivs["iv_spdef"], caught_ivs["iv_spd"])
        iv_grade, _stars = config.get_iv_grade(iv_sum)
        iv_tag = f" [{iv_grade}]" if iv_grade in ("S", "A") else f" [{iv_grade}]"

        rbadge = rarity_badge(rarity)
        tb = type_badge(pokemon_id)
        if winner.get("used_master_ball"):
            msg = f"🟣 마스터볼! {decorated} — {shiny_label}{rbadge}{tb} {pokemon_name} 확정 포획!{iv_tag}"
            await queries.increment_title_stat(winner_id, "master_ball_used")
        elif winner.get("used_hyper_ball"):
            msg = f"🔵 하이퍼볼! {decorated} — {shiny_label}{rbadge}{tb} {pokemon_name} 포획!{iv_tag}"
        elif rarity in ("epic", "legendary") and is_first:
            msg = f"🌟 {decorated} — {shiny_label}{rbadge}{tb} {pokemon_name} 포획! (이 방 최초){iv_tag}"
        else:
            msg = f"딸깍! ✨ {decorated} — {shiny_label}{rbadge}{tb} {pokemon_name} 포획!{iv_tag}"

        # Shiny catch announcement
        if is_shiny:
            msg += "\n\n✨✨✨ 이로치 포켓몬을 잡았다!"

        # Track midnight catch for title
        hour = config.get_kst_hour()
        if 2 <= hour < 5:
            await queries.increment_title_stat(winner_id, "midnight_catch_count")

        # Track catch failures for title (batch)
        if failed_ids:
            await asyncio.gather(
                *(queries.increment_title_stat(uid, "catch_fail_count") for uid in failed_ids)
            )

        # Master Ball random drop (2% chance on catch)
        master_ball_drop = random.random() < 0.02
        if master_ball_drop:
            await queries.add_master_ball(winner_id)
            msg += "\n\n🟣 마스터볼을 획득했다!"

        catch_msg = await context.bot.send_message(
            chat_id=chat_id, text=msg, parse_mode="HTML",
            reply_markup=close_button(),
        )
        # catch result stays visible

        # DM notification to catcher (with stats + power)
        try:
            from utils.battle_calc import calc_battle_stats, EVO_STAGE_MAP, get_normalized_base_stats
            evo_stage = EVO_STAGE_MAP.get(pokemon_id, 3)
            stat_type = pokemon.get("stat_type", "balanced") if pokemon else "balanced"

            # Base stats (without IV)
            base_kwargs = {}
            norm = get_normalized_base_stats(pokemon_id)
            if norm:
                base_kwargs = norm

            stats_with_iv = calc_battle_stats(
                rarity, stat_type, 0, evo_stage=evo_stage,
                iv_hp=caught_ivs["iv_hp"], iv_atk=caught_ivs["iv_atk"],
                iv_def=caught_ivs["iv_def"], iv_spa=caught_ivs["iv_spa"],
                iv_spdef=caught_ivs["iv_spdef"], iv_spd=caught_ivs["iv_spd"],
                **base_kwargs,
            )
            stats_base = calc_battle_stats(
                rarity, stat_type, 0, evo_stage=evo_stage,
                **base_kwargs,
            )
            power_with_iv = stats_with_iv["hp"] + stats_with_iv["atk"] + stats_with_iv["def"] + stats_with_iv["spd"]
            power_base = stats_base["hp"] + stats_base["atk"] + stats_base["def"] + stats_base["spd"]
            iv_bonus = power_with_iv - power_base

            shiny_dm = " ✨이로치" if is_shiny else ""
            iv_sign = f"+{iv_bonus}" if iv_bonus >= 0 else str(iv_bonus)
            dm_text = (
                f"🎉 {rbadge}{tb} {pokemon_name} 포획!{shiny_dm} [{iv_grade}]\n"
                f"HP:{stats_with_iv['hp']} ATK:{stats_with_iv['atk']} DEF:{stats_with_iv['def']} SPD:{stats_with_iv['spd']}\n"
                f"전투력: {power_base} ({iv_sign})"
            )
            asyncio.create_task(context.bot.send_message(chat_id=winner_id, text=dm_text, parse_mode="HTML"))
        except Exception:
            pass

        # Check and unlock titles
        from utils.title_checker import check_and_unlock_titles
        from utils.helpers import escape_html
        new_titles = await check_and_unlock_titles(winner_id)
        if new_titles:
            title_msgs = [f"🎉 <b>「{temoji} {tname}」</b> 칭호 해금!" for _, tname, temoji in new_titles]
            safe_name = escape_html(winner_name)
            title_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"🏷️ {safe_name}의 새 칭호!\n" + "\n".join(title_msgs) + "\nDM에서 '칭호'로 장착하세요!",
                parse_mode="HTML",
            )
            # title msg stays visible

        # Also check titles for failed catchers (background, non-blocking)
        async def _bg_check_failed():
            try:
                for uid in failed_ids:
                    await check_and_unlock_titles(uid)
            except Exception:
                pass
        if failed_ids:
            asyncio.create_task(_bg_check_failed())

        # Log
        await queries.log_spawn(
            chat_id, pokemon_id, pokemon_name, pokemon_emoji,
            rarity, winner_id, winner_name, participants, is_shiny=is_shiny,
        )

        logger.info(
            f"{winner_name} caught {pokemon_name} in chat {chat_id}"
        )

    except Exception as e:
        logger.error(f"Spawn resolution failed for session {session_id}: {e}")
        await queries.close_spawn_session(session_id)
