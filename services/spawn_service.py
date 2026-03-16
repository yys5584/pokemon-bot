"""Spawn system: scheduling, rarity rolling, spawn execution."""

import asyncio
import random
import logging
import time as _time
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from database import queries
from services.event_service import get_spawn_boost, get_rarity_weights, get_catch_boost, get_shiny_boost
from services.weather_service import get_weather_pokemon_boost, get_weather_display
from utils.card_generator import generate_card
from utils.helpers import schedule_delete, close_button, rarity_badge, type_badge, ball_emoji, shiny_emoji, icon_emoji

logger = logging.getLogger(__name__)

# 채팅방별 스폰 락: 포획 메시지 전송 완료 전 다음 스폰 방지
_chat_spawn_locks: dict[int, asyncio.Lock] = {}


def _get_chat_lock(chat_id: int) -> asyncio.Lock:
    if chat_id not in _chat_spawn_locks:
        _chat_spawn_locks[chat_id] = asyncio.Lock()
    return _chat_spawn_locks[chat_id]


async def _add_cxp_bg(context, chat_id: int, amount: int, action: str, user_id: int | None = None):
    """Background: award CXP to a chat room and announce level-ups."""
    try:
        # 구독자 채널 CXP 배율 적용
        if user_id:
            try:
                from services.subscription_service import get_benefit_value
                cxp_mult = await get_benefit_value(user_id, "channel_cxp_multiplier", 1.0)
                if cxp_mult > 1.0:
                    amount = int(amount * cxp_mult)
            except Exception:
                pass

        new_level = await queries.add_chat_cxp(chat_id, amount, action, user_id)
        if new_level:
            info = config.get_chat_level_info(0)  # just for display
            # Re-fetch actual info for the new level
            row = await queries.get_chat_level(chat_id)
            info = config.get_chat_level_info(row["cxp"])
            bonus_txt = f"+{info['spawn_bonus']} 스폰" if info["spawn_bonus"] else ""
            shiny_txt = f"+{info['shiny_boost_pct']:.1f}% 이로치" if info["shiny_boost_pct"] else ""
            parts = [p for p in [bonus_txt, shiny_txt] if p]
            perks = f" ({', '.join(parts)})" if parts else ""
            special = ""
            if "daily_shiny" in info["specials"]:
                special = "\n✨ 일일 이로치 스폰 해금!"
            if "auto_arcade" in info["specials"]:
                special = "\n🎰 일일 자동 아케이드 해금!"
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎊 채팅방 레벨 UP! Lv.{new_level}{perks}{special}",
                parse_mode="HTML",
            )
    except Exception as e:
        logger.error(f"CXP add failed for chat {chat_id}: {e}")


# Track attempt messages for cleanup when spawn resolves
# {session_id: (timestamp, [(chat_id, message_id), ...])}
_attempt_messages: dict[int, tuple[float, list[tuple[int, int]]]] = {}


def track_attempt_message(session_id: int, chat_id: int, message_id: int):
    """Store an attempt message for later deletion."""
    if session_id not in _attempt_messages:
        _attempt_messages[session_id] = (_time.time(), [])
    _attempt_messages[session_id][1].append((chat_id, message_id))


def cleanup_old_attempt_messages():
    """Remove _attempt_messages entries older than 1 hour to prevent memory leaks."""
    cutoff = _time.time() - 3600
    expired = [sid for sid, (ts, _) in _attempt_messages.items() if ts < cutoff]
    for sid in expired:
        _attempt_messages.pop(sid, None)
    if expired:
        logger.info(f"Cleaned up {len(expired)} stale attempt_message entries")


async def _delete_attempt_messages(bot, session_id: int):
    """Delete all tracked attempt messages for a resolved spawn."""
    entry = _attempt_messages.pop(session_id, None)
    messages = entry[1] if entry else []
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
    import asyncio
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


async def _resolve_overlapping_spawn(context: ContextTypes.DEFAULT_TYPE, active: dict):
    """Quick-resolve an overlapping spawn before starting a new one.
    This prevents catch attempts from being silently discarded in arcade mode."""
    from database.connection import get_db

    session_id = active["id"]
    chat_id = active["chat_id"]

    try:
        pool = await get_db()
        row = await pool.fetchrow(
            "SELECT is_resolved FROM spawn_sessions WHERE id = $1", session_id
        )
        if not row or row["is_resolved"] == 1:
            return  # Already resolved

        # Mark as resolved
        await pool.execute(
            "UPDATE spawn_sessions SET is_resolved = 1 WHERE id = $1", session_id
        )

        # Get pokemon info
        _prow = await pool.fetchrow(
            "SELECT pm.id, pm.name_ko, pm.emoji, pm.rarity, pm.catch_rate, "
            "pm.stat_type, ss.is_shiny "
            "FROM spawn_sessions ss "
            "JOIN pokemon_master pm ON ss.pokemon_id = pm.id "
            "WHERE ss.id = $1", session_id
        )
        if not _prow:
            await queries.close_spawn_session(session_id)
            return
        pokemon = dict(_prow)

        pokemon_id = pokemon["id"]
        pokemon_name = pokemon["name_ko"]
        rarity = pokemon["rarity"]
        is_shiny = bool(pokemon.get("is_shiny"))

        # Get catch attempts
        attempts = await queries.get_session_attempts(session_id)
        _attempt_messages.pop(session_id, None)

        if not attempts:
            # Nobody tried — just close silently (don't spam "ran away" in arcade)
            await queries.close_spawn_session(session_id)
            await queries.log_spawn(
                chat_id, pokemon_id, pokemon_name, pokemon["emoji"],
                rarity, None, None, 0, is_shiny=is_shiny,
            )
            logger.info(f"Overlap resolve {session_id}: no attempts, closed")
            return

        # Get catch rate with event boost
        base_rate = pokemon["catch_rate"]
        catch_boost = await get_catch_boost()
        catch_rate = min(1.0, base_rate * catch_boost)

        # Pre-fetch catch counts for newbie boost (batch)
        normal_user_ids = [
            a["user_id"] for a in attempts
            if not a.get("used_master_ball") and not a.get("used_hyper_ball")
        ]
        catch_counts = await queries.count_total_catches_bulk(normal_user_ids) if normal_user_ids else {}

        # Roll for each catcher
        results = []
        for attempt in attempts:
            if attempt.get("used_master_ball"):
                roll, success = -1.0, True
            elif attempt.get("used_hyper_ball"):
                hyper_rate = min(1.0, catch_rate * config.HYPER_BALL_CATCH_MULTIPLIER)
                roll = random.random()
                success = roll < hyper_rate
            else:
                total = catch_counts.get(attempt["user_id"], 0)
                if total < 2:
                    roll, success = 0.0, True
                else:
                    roll = random.random()
                    success = roll < catch_rate
            results.append({
                "user_id": attempt["user_id"],
                "display_name": attempt["display_name"],
                "username": attempt["username"],
                "roll": roll, "success": success,
                "used_master_ball": bool(attempt.get("used_master_ball")),
                "used_hyper_ball": bool(attempt.get("used_hyper_ball")),
            })

        winners = [r for r in results if r["success"]]
        participants = len(attempts)

        if not winners:
            # Everyone failed
            shiny_tag = f" {shiny_emoji()}이로치" if is_shiny else ""
            rbadge = rarity_badge(rarity)
            tb = type_badge(pokemon_id)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"흔들흔들... {icon_emoji('windy')}{shiny_tag} {rbadge}{tb} {pokemon_name} 도망갔다!",
                parse_mode="HTML",
            )
            await queries.close_spawn_session(session_id)
            await queries.log_spawn(
                chat_id, pokemon_id, pokemon_name, pokemon["emoji"],
                rarity, None, None, participants, is_shiny=is_shiny,
            )
            logger.info(f"Overlap resolve {session_id}: all failed, {pokemon_name} escaped")
            return

        # Pick winner
        winners.sort(key=lambda x: x["roll"])
        winner = winners[0]
        winner_id = winner["user_id"]
        winner_name = winner["display_name"]

        # Refund master balls to losers (batch)
        master_refund_ids = [
            r["user_id"] for r in results
            if r["used_master_ball"] and r["user_id"] != winner_id
        ]
        if master_refund_ids:
            await queries.add_master_balls_bulk(master_refund_ids)
            for loser in results:
                if loser["used_master_ball"] and loser["user_id"] != winner_id:
                    logger.info(f"Refunded master ball to {loser['display_name']} ({loser['user_id']})")
                    try:
                        await context.bot.send_message(
                            chat_id=loser["user_id"],
                            text=f"{ball_emoji('masterball')} 마스터볼이 환불되었습니다. (타 트레이너가 포획)",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass

        # Refund hyper balls when master ball user wins (hyper had no chance)
        if winner.get("used_master_ball"):
            hyper_refund_ids = [
                r["user_id"] for r in results
                if r["used_hyper_ball"] and r["user_id"] != winner_id
            ]
            if hyper_refund_ids:
                await queries.add_hyper_balls_bulk(hyper_refund_ids)
                for loser in results:
                    if loser["used_hyper_ball"] and loser["user_id"] != winner_id:
                        logger.info(f"Refunded hyper ball to {loser['display_name']} (master ball override, overlap)")
                        try:
                            await context.bot.send_message(
                                chat_id=loser["user_id"],
                                text=f"{ball_emoji('hyperball')} 하이퍼볼이 환불되었습니다. (마스터볼 포획으로 자동 환불)",
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass

        # Collect failed user IDs for title tracking
        failed_ids = [r["user_id"] for r in results if not r["success"]]

        # Give Pokemon + register pokedex + close session (transaction)
        _inst_id, caught_ivs = await queries.catch_pokemon_transaction(
            winner_id, pokemon_id, chat_id, is_shiny, session_id,
        )

        # Build result message
        from utils.helpers import get_decorated_name
        from utils.battle_calc import iv_total
        from utils.honorific import honorific_name as _hon_name, honorific_catch_verb as _hon_verb
        user_data = await queries.get_user(winner_id)

        # 구독자 존칭 적용
        _winner_tier = None
        try:
            from services.subscription_service import get_user_tier
            _winner_tier = await get_user_tier(winner_id)
        except Exception:
            pass
        _display = _hon_name(winner_name, _winner_tier) if _winner_tier else winner_name

        decorated = get_decorated_name(
            _display,
            user_data.get("title", "") if user_data else "",
            user_data.get("title_emoji", "") if user_data else "",
            winner.get("username"), html=True,
        )
        iv_sum = iv_total(caught_ivs["iv_hp"], caught_ivs["iv_atk"],
                          caught_ivs["iv_def"], caught_ivs["iv_spa"],
                          caught_ivs["iv_spdef"], caught_ivs["iv_spd"])
        iv_grade, _ = config.get_iv_grade(iv_sum)
        iv_tag = f" [{iv_grade}]"

        rbadge = rarity_badge(rarity)
        tb = type_badge(pokemon_id)
        shiny_label = f"{shiny_emoji()}이로치 " if is_shiny else ""
        be_pokeball = ball_emoji("pokeball")
        be_master = ball_emoji("masterball")
        be_hyper = ball_emoji("hyperball")

        _catch = _hon_verb("포획!", _winner_tier)
        _catch_confirm = _hon_verb("확정 포획!", _winner_tier)
        if winner.get("used_master_ball"):
            msg = f"{be_master} 마스터볼! {decorated} — {shiny_label}{rbadge}{tb} {pokemon_name} {_catch_confirm}{iv_tag}"
            await queries.increment_title_stat(winner_id, "master_ball_used")
        elif winner.get("used_hyper_ball"):
            msg = f"{be_hyper} 하이퍼볼! {decorated} — {shiny_label}{rbadge}{tb} {pokemon_name} {_catch}{iv_tag}"
        else:
            msg = f"딸깍! {be_pokeball} {decorated} — {shiny_label}{rbadge}{tb} {pokemon_name} {_catch}{iv_tag}"

        if is_shiny:
            _se = shiny_emoji()
            _shiny_verb = _hon_verb("잡았다!", _winner_tier) if _winner_tier else "잡았다!"
            msg += f"\n\n{_se}{_se}{_se} 이로치 포켓몬을 {_shiny_verb}"

        # Track midnight catch for title
        hour = config.get_kst_hour()
        if 2 <= hour < 5:
            await queries.increment_title_stat(winner_id, "midnight_catch_count")
        if failed_ids:
            await asyncio.gather(
                *(queries.increment_title_stat(uid, "catch_fail_count") for uid in failed_ids)
            )

        # Catch BP reward (보유 100마리 미만만)
        from database.battle_queries import add_bp
        poke_count = await pool.fetchval(
            "SELECT COUNT(*) FROM user_pokemon WHERE user_id = $1 AND is_active = 1",
            winner_id,
        )
        if poke_count < config.CATCH_BP_POKEMON_LIMIT:
            catch_bp = random.randint(config.CATCH_BP_MIN, config.CATCH_BP_MAX)
            await add_bp(winner_id, catch_bp, "catch")
            msg += f"\n{icon_emoji('coin')} +{catch_bp} BP"

        # Master Ball random drop
        if random.random() < 0.02:
            await queries.add_master_ball(winner_id)
            msg += f"\n\n{ball_emoji('masterball')} 마스터볼을 획득했다!"

        # Journey system check
        from services.journey_service import check_journey
        journey_msg = await check_journey(winner_id)
        if journey_msg:
            msg += f"\n\n{journey_msg}"

        from utils.helpers import close_button
        await context.bot.send_message(
            chat_id=chat_id, text=msg, parse_mode="HTML",
            reply_markup=close_button(),
        )

        # Mission: catch
        asyncio.create_task(_notify_mission(context, winner_id, "catch"))

        # CXP: +1 for catch
        asyncio.create_task(_add_cxp_bg(context, chat_id, config.CXP_PER_CATCH, "catch", winner_id))

        # DM notification
        try:
            from utils.battle_calc import calc_battle_stats, format_stats_line, format_power, EVO_STAGE_MAP, get_normalized_base_stats
            stat_type = pokemon.get("stat_type", "balanced") or "balanced"
            norm = get_normalized_base_stats(pokemon_id)
            evo_stage = 3 if norm else EVO_STAGE_MAP.get(pokemon_id, 3)
            base_kwargs = norm or {}
            stats_with_iv = calc_battle_stats(
                rarity, stat_type, 0, evo_stage=evo_stage,
                iv_hp=caught_ivs["iv_hp"], iv_atk=caught_ivs["iv_atk"],
                iv_def=caught_ivs["iv_def"], iv_spa=caught_ivs["iv_spa"],
                iv_spdef=caught_ivs["iv_spdef"], iv_spd=caught_ivs["iv_spd"],
                **base_kwargs,
            )
            stats_base = calc_battle_stats(
                rarity, stat_type, 0, evo_stage=evo_stage, **base_kwargs,
            )
            shiny_dm = f" {shiny_emoji()}이로치" if is_shiny else ""
            iv_line = (f"IV: {caught_ivs['iv_hp']}/{caught_ivs['iv_atk']}/{caught_ivs['iv_def']}"
                       f"/{caught_ivs['iv_spa']}/{caught_ivs['iv_spdef']}/{caught_ivs['iv_spd']}"
                       f" ({iv_sum}/186)")
            own_count = await queries.count_user_pokemon_species(winner_id, pokemon_id)
            own_tag = f"📦 보유: {own_count}마리" if own_count > 1 else "🆕 새로운 포켓몬!"
            if winner.get("used_master_ball"):
                dm_ball = f"{ball_emoji('masterball')} 마스터볼! "
            elif winner.get("used_hyper_ball"):
                dm_ball = f"{ball_emoji('hyperball')} 하이퍼볼! "
            else:
                dm_ball = f"{ball_emoji('pokeball')} "
            dm_text = (
                f"{dm_ball}{rbadge}{tb} {pokemon_name} 포획!{shiny_dm} [{iv_grade}]\n"
                f"{iv_line}\n"
                f"{icon_emoji('bolt')} {format_power(stats_with_iv, stats_base)}\n"
                f"{format_stats_line(stats_with_iv, stats_base)}\n\n"
                f"{own_tag}"
            )
            catch_buttons = InlineKeyboardMarkup([[
                InlineKeyboardButton("가방에 넣기 ✅", callback_data=f"catch_keep_{_inst_id}"),
                InlineKeyboardButton("방생하기 🔄", callback_data=f"catch_release_{_inst_id}"),
            ]])
            try:
                dm_msg = await context.bot.send_message(
                    chat_id=winner_id, text=dm_text,
                    parse_mode="HTML", reply_markup=catch_buttons,
                )
                logger.info(f"Catch DM sent to {winner_id} for {pokemon_name}")

                # 5분 후 자동 가방 넣기
                context.job_queue.run_once(
                    _auto_keep_pokemon,
                    when=300,
                    data={
                        "chat_id": winner_id,
                        "message_id": dm_msg.message_id,
                        "instance_id": _inst_id,
                    },
                )
            except Exception as dm_err:
                logger.warning(f"Failed to send catch DM to {winner_id}: {dm_err}")
        except Exception as e:
            logger.error(f"Catch DM construction failed for {winner_id}: {e}")

        # Title checks (background)
        from utils.title_checker import check_and_unlock_titles
        from utils.helpers import escape_html
        new_titles = await check_and_unlock_titles(winner_id)
        if new_titles:
            title_msgs = [
                f"🎉 <b>「{icon_emoji(temoji) if temoji in config.ICON_CUSTOM_EMOJI else temoji} {tname}」</b> 칭호 해금!"
                for _, tname, temoji in new_titles
            ]
            safe_name = escape_html(winner_name)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🏷️ {safe_name}의 새 칭호!\n" + "\n".join(title_msgs) + "\nDM에서 '칭호'로 장착하세요!",
                parse_mode="HTML",
            )

        # Log
        await queries.log_spawn(
            chat_id, pokemon_id, pokemon_name, pokemon["emoji"],
            rarity, winner_id, winner_name, participants, is_shiny=is_shiny,
        )
        logger.info(f"Overlap resolve {session_id}: {winner_name} caught {pokemon_name}")

    except Exception as e:
        logger.error(f"Overlap resolve failed for session {session_id}: {e}")
        await queries.close_spawn_session(session_id)


async def _auto_keep_pokemon(context: ContextTypes.DEFAULT_TYPE):
    """5분 경과 시 자동으로 가방에 넣기 (버튼 제거)."""
    data = context.job.data
    chat_id = data["chat_id"]
    message_id = data["message_id"]

    try:
        # 버튼 제거 시도 — 이미 사용자가 버튼을 눌렀으면 reply_markup이 없어서 무시됨
        await context.bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=None,
        )
        logger.info(f"Auto-keep: buttons removed for instance {data.get('instance_id')} (user {chat_id})")
    except Exception:
        # 이미 버튼이 제거된 경우 (사용자가 선택 완료) — 무시
        pass


async def execute_spawn(context: ContextTypes.DEFAULT_TYPE):
    """Execute a single spawn event. Called by JobQueue."""
    chat_id = context.job.data["chat_id"]
    force = context.job.data.get("force", False)
    force_shiny = context.job.data.get("force_shiny", False)
    # Arcade = permanent OR temp arcade (job name starts with arcade_)
    job_name = getattr(context.job, "name", None) or ""
    arcade = chat_id in config.ARCADE_CHAT_IDS or job_name.startswith(f"arcade_{chat_id}")

    # Skip spawns in tournament chat while tournament is active
    from services.tournament_service import is_tournament_active
    if is_tournament_active(chat_id) and not context.job.data.get("admin_force"):
        return

    try:
        # 1. Activity check (skip if force spawn or arcade)
        if not force and not arcade:
            activity = await queries.get_recent_activity(chat_id, hours=1)
            if activity < 1:
                # No activity — retry later
                # Cancel existing retry jobs for this chat to prevent accumulation
                retry_name = f"spawn_retry_{chat_id}"
                for job in context.job_queue.jobs():
                    if job.name == retry_name:
                        job.schedule_removal()
                retry_delay = random.randint(
                    config.SPAWN_RETRY_MIN_SECONDS,
                    config.SPAWN_RETRY_MAX_SECONDS,
                )
                context.job_queue.run_once(
                    execute_spawn,
                    when=retry_delay,
                    data={"chat_id": chat_id},
                    name=retry_name,
                )
                logger.info(f"No activity in {chat_id}, retrying in {retry_delay}s")
                return

        # 2. Check if there's already an active spawn
        active = await queries.get_active_spawn(chat_id)
        if active:
            if not arcade and not force:
                return  # Normal spawn: skip if active spawn exists
            # Arcade/force: resolve old spawn before creating new one
            old_session_id = active["id"]
            old_resolve_name = f"resolve_{old_session_id}"

            # Cancel the scheduled resolve job (we'll resolve inline)
            for job in context.job_queue.jobs():
                if job.name == old_resolve_name:
                    job.schedule_removal()
                    break

            # Quick-resolve the overlapping spawn (determine catch, send result)
            await _resolve_overlapping_spawn(context, active)

            # Note: don't delete old spawn image — keep it as context
            # (normal resolve_spawn also doesn't delete the photo)

        # 2.5 Cooldown: skip if last spawn was within 5 minutes (skip for arcade and force)
        if not arcade and not force:
            last_spawn = await queries.get_last_spawn_time(chat_id)
            if last_spawn:
                if last_spawn.tzinfo is None:
                    import datetime as _dt
                    last_spawn = last_spawn.replace(tzinfo=_dt.timezone.utc)
                elapsed = (config.get_kst_now() - last_spawn).total_seconds()
                if elapsed < 300:  # 5 minutes cooldown
                    # Re-schedule after remaining cooldown instead of dropping
                    remaining = int(300 - elapsed) + 10  # +10s buffer
                    retry_name = f"spawn_retry_{chat_id}"
                    for job in context.job_queue.jobs():
                        if job.name == retry_name:
                            job.schedule_removal()
                    context.job_queue.run_once(
                        execute_spawn,
                        when=remaining,
                        data={"chat_id": chat_id},
                        name=retry_name,
                    )
                    logger.debug(f"Spawn cooldown for {chat_id}: {elapsed:.0f}s elapsed, retrying in {remaining}s")
                    return

        # 3. Roll rarity with midnight bonus + event boosts + chat level boosts
        midnight = is_midnight_bonus()
        _level_rarity_boosts = None
        try:
            _lr = await queries.get_chat_level(chat_id)
            if _lr:
                _li = config.get_chat_level_info(_lr["cxp"])
                if _li["rarity_boosts"]:
                    _level_rarity_boosts = _li["rarity_boosts"]
        except Exception:
            pass
        rarity = await roll_rarity(midnight_bonus=midnight, rarity_boosts=_level_rarity_boosts)

        # 4. Pick random Pokemon
        pokemon = await pick_random_pokemon(rarity)

        # 4.5 Shiny determination (자연 스폰은 확정만, 강스/아케이드는 랜덤 유지)
        if force_shiny:
            is_shiny = True
        else:
            if arcade:
                shiny_rate = config.SHINY_RATE_ARCADE
            elif force:
                shiny_rate = config.SHINY_RATE_FORCE
            else:
                shiny_rate = config.SHINY_RATE_NATURAL

            # Anti-abuse: 강스/아케이드 이로치 차단 조건
            # 1) 최근 30분간 포획 참여자 1명 이하 (단, 최소 2회 이상 스폰 이력 필요)
            # 2) 최근 10회 스폰 전부 미포획(도망)
            if (force or arcade) and shiny_rate > 0:
                try:
                    catch_users = await queries.get_recent_catch_user_count(chat_id, minutes=30)
                    caught, total = await queries.get_recent_spawn_catch_rate(chat_id, limit=10)
                    if total >= 2 and catch_users <= 1:
                        shiny_rate = 0.0
                        logger.info(f"Shiny blocked in {chat_id}: only {catch_users} catcher(s) in last 30min")
                    elif total >= 10 and caught == 0:
                        shiny_rate = 0.0
                        logger.info(f"Shiny blocked in {chat_id}: 0/{total} caught in last {total} spawns")
                except Exception as e:
                    logger.warning(f"Anti-abuse check failed for {chat_id}: {e}")

            # Chat level shiny boost (강스/아케이드에만 의미 있음)
            level_shiny_add = 0.0
            try:
                _lrow = await queries.get_chat_level(chat_id)
                if _lrow:
                    _linfo = config.get_chat_level_info(_lrow["cxp"])
                    level_shiny_add = _linfo["shiny_boost_pct"] / 100.0
            except Exception:
                pass
            shiny_mult = await get_shiny_boost()
            is_shiny = random.random() < min(1.0, shiny_rate * shiny_mult + level_shiny_add)

        # 5. Generate card image FIRST (before creating session)
        shiny_text = f" {shiny_emoji()}이로치" if is_shiny else ""
        from utils.helpers import _type_emoji
        bonus_text = f" {_type_emoji('dark')}" if midnight else ""

        # Check for active event indicator
        from services.event_service import get_active_event_summary
        event_summary = await get_active_event_summary()
        event_tag = ""

        # Weather indicator
        weather_tag = get_weather_display()

        # Catch window: arcade uses interval-based, force spawn = 30s, normal = 60s
        spawn_interval = context.job.data.get("interval")
        if arcade and spawn_interval:
            window = max(spawn_interval - 10, config.ARCADE_SPAWN_WINDOW)
        elif arcade:
            window = config.ARCADE_SPAWN_WINDOW
        elif force:
            window = 30
        else:
            window = config.SPAWN_WINDOW_SECONDS

        tb = type_badge(pokemon["id"], pokemon.get("pokemon_type"))
        caption = (
            f"{icon_emoji('footsteps')} 야생의{shiny_text} {tb} {pokemon['name_ko']}이(가) 나타났다!{bonus_text}{weather_tag}\n"
            f"ㅊ 입력으로 잡기 ({window}초)"
        )

        # Generate card image (run in executor to avoid blocking event loop)
        loop = asyncio.get_event_loop()
        card_buf = await loop.run_in_executor(
            None, generate_card, pokemon["id"], pokemon["name_ko"], rarity, pokemon["emoji"], is_shiny
        )

        # 이전 스폰의 포획 메시지가 완전히 전송될 때까지 대기
        lock = _get_chat_lock(chat_id)
        await asyncio.wait_for(lock.acquire(), timeout=10)
        lock.release()

        # Send photo BEFORE creating session (so catch isn't possible without image)
        message = await context.bot.send_photo(
            chat_id=chat_id,
            photo=card_buf,
            caption=caption,
            parse_mode="HTML",
        )

        # Auto-delete spawn image after 1 hour to reduce chat clutter
        schedule_delete(message, 3600)

        # 6. Create spawn session AFTER image is sent
        expires = (config.get_kst_now() + timedelta(seconds=window))

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
        # Handle group → supergroup migration
        if "migrate" in str(e).lower() and hasattr(e, "new_chat_id"):
            new_id = e.new_chat_id
            logger.info(f"Chat {chat_id} migrated to {new_id}, updating DB...")
            try:
                pool = await queries.get_db()
                await pool.execute(
                    "UPDATE chat_rooms SET chat_id = $1 WHERE chat_id = $2",
                    new_id, chat_id,
                )
                logger.info(f"Chat migration {chat_id} → {new_id} done.")
            except Exception as me:
                logger.error(f"Chat migration update failed: {me}")
        elif "kicked" in str(e).lower() or "forbidden" in str(e).lower():
            logger.info(f"Bot kicked from chat {chat_id}, deactivating...")
            try:
                pool = await queries.get_db()
                await pool.execute(
                    "UPDATE chat_rooms SET is_active = 0 WHERE chat_id = $1",
                    chat_id,
                )
                logger.info(f"Chat {chat_id} deactivated.")
            except Exception as de:
                logger.error(f"Chat deactivation failed: {de}")
        else:
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

    # 포획 메시지 전송 완료까지 다음 스폰 차단
    lock = _get_chat_lock(chat_id)
    await lock.acquire()

    try:
        # Check if session is already resolved (avoid duplicate resolution)
        from database.connection import get_db
        pool = await get_db()
        row = await pool.fetchrow(
            "SELECT is_resolved FROM spawn_sessions WHERE id = $1", session_id
        )
        if not row or row["is_resolved"] == 1:
            logger.debug(f"Session {session_id} already resolved, skipping")
            lock.release()
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
            shiny_tag = f" {shiny_emoji()}이로치" if is_shiny else ""
            rbadge = rarity_badge(rarity)
            tb = type_badge(pokemon_id)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"흔들흔들... {icon_emoji('windy')}{shiny_tag} {rbadge}{tb} {pokemon_name} 도망갔다!",
                parse_mode="HTML",
            )
            lock.release()  # 도망 메시지 전송 완료 → 다음 스폰 허용
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

        # Pre-fetch catch counts for newbie boost (batch)
        normal_user_ids2 = [
            a["user_id"] for a in attempts
            if not a.get("used_master_ball") and not a.get("used_hyper_ball")
        ]
        catch_counts2 = await queries.count_total_catches_bulk(normal_user_ids2) if normal_user_ids2 else {}

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
                total = catch_counts2.get(attempt["user_id"], 0)
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
            shiny_tag = f" {shiny_emoji()}이로치" if is_shiny else ""
            rbadge = rarity_badge(rarity)
            tb = type_badge(pokemon_id)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"흔들흔들... {icon_emoji('windy')}{shiny_tag} {rbadge}{tb} {pokemon_name} 도망갔다!",
                parse_mode="HTML",
            )
            lock.release()  # 도망 메시지 전송 완료 → 다음 스폰 허용
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

        # Refund master balls to losers (batch)
        master_refund_ids2 = [
            r["user_id"] for r in results
            if r["used_master_ball"] and r["user_id"] != winner_id
        ]
        if master_refund_ids2:
            await queries.add_master_balls_bulk(master_refund_ids2)
            for loser in results:
                if loser["used_master_ball"] and loser["user_id"] != winner_id:
                    logger.info(f"Refunded master ball to {loser['display_name']} ({loser['user_id']})")
                    try:
                        await context.bot.send_message(
                            chat_id=loser["user_id"],
                            text=f"{ball_emoji('masterball')} 마스터볼이 환불되었습니다. (타 트레이너가 포획)",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass

        # Refund hyper balls when master ball user wins (hyper had no chance)
        if winner.get("used_master_ball"):
            hyper_refund_ids = [
                r["user_id"] for r in results
                if r["used_hyper_ball"] and r["user_id"] != winner_id
            ]
            if hyper_refund_ids:
                await queries.add_hyper_balls_bulk(hyper_refund_ids)
                for loser in results:
                    if loser["used_hyper_ball"] and loser["user_id"] != winner_id:
                        logger.info(f"Refunded hyper ball to {loser['display_name']} (master ball override)")
                        try:
                            await context.bot.send_message(
                                chat_id=loser["user_id"],
                                text=f"{ball_emoji('hyperball')} 하이퍼볼이 환불되었습니다. (마스터볼 포획으로 자동 환불)",
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass

        # Collect failed user IDs for title tracking
        failed_ids = [r["user_id"] for r in results if not r["success"]]

        # Give Pokemon + register pokedex + close session (transaction)
        _inst_id, caught_ivs = await queries.catch_pokemon_transaction(
            winner_id, pokemon_id, chat_id, is_shiny, session_id,
        )

        # Mission: catch
        asyncio.create_task(_notify_mission(context, winner_id, "catch"))

        # CXP: +1 for catch
        asyncio.create_task(_add_cxp_bg(context, chat_id, config.CXP_PER_CATCH, "catch", winner_id))

        # 복귀 유저 환영
        asyncio.create_task(_check_returning_user(context, chat_id, winner_id, winner_name))

        # Check if first catch in chat (for rare+ announcement)
        is_first = await queries.is_first_catch_in_chat(chat_id, pokemon_id)

        # Build message with decorated name (HTML bold for titled users)
        from utils.helpers import get_decorated_name
        from utils.honorific import honorific_name as _hon_name, honorific_catch_verb as _hon_verb
        user_data = await queries.get_user(winner_id)

        # 구독자 존칭 적용
        _winner_tier = None
        try:
            from services.subscription_service import get_user_tier
            _winner_tier = await get_user_tier(winner_id)
        except Exception:
            pass
        _display = _hon_name(winner_name, _winner_tier) if _winner_tier else winner_name

        decorated = get_decorated_name(
            _display,
            user_data.get("title", "") if user_data else "",
            user_data.get("title_emoji", "") if user_data else "",
            winner.get("username"),
            html=True,
        )

        shiny_label = f"{shiny_emoji()}이로치 " if is_shiny else ""

        # IV grade display
        from utils.battle_calc import iv_total
        iv_sum = iv_total(caught_ivs["iv_hp"], caught_ivs["iv_atk"],
                          caught_ivs["iv_def"], caught_ivs["iv_spa"],
                          caught_ivs["iv_spdef"], caught_ivs["iv_spd"])
        iv_grade, _stars = config.get_iv_grade(iv_sum)
        iv_tag = f" [{iv_grade}]"

        rbadge = rarity_badge(rarity)
        tb = type_badge(pokemon_id)
        be_pokeball = ball_emoji("pokeball")
        be_master = ball_emoji("masterball")
        be_hyper = ball_emoji("hyperball")
        _catch = _hon_verb("포획!", _winner_tier)
        _catch_confirm = _hon_verb("확정 포획!", _winner_tier)
        if winner.get("used_master_ball"):
            msg = f"{be_master} 마스터볼! {decorated} — {shiny_label}{rbadge}{tb} {pokemon_name} {_catch_confirm}{iv_tag}"
            await queries.increment_title_stat(winner_id, "master_ball_used")
        elif winner.get("used_hyper_ball"):
            msg = f"{be_hyper} 하이퍼볼! {decorated} — {shiny_label}{rbadge}{tb} {pokemon_name} {_catch}{iv_tag}"
        elif rarity in ("epic", "legendary", "ultra_legendary") and is_first:
            msg = f"🌟 {decorated} — {shiny_label}{rbadge}{tb} {pokemon_name} {_catch} (이 방 최초){iv_tag}"
        else:
            msg = f"딸깍! {be_pokeball} {decorated} — {shiny_label}{rbadge}{tb} {pokemon_name} {_catch}{iv_tag}"

        # Shiny catch announcement
        if is_shiny:
            _se = shiny_emoji()
            _shiny_verb = _hon_verb("잡았다!", _winner_tier) if _winner_tier else "잡았다!"
            msg += f"\n\n{_se}{_se}{_se} 이로치 포켓몬을 {_shiny_verb}"

        # Track midnight catch for title
        hour = config.get_kst_hour()
        if 2 <= hour < 5:
            await queries.increment_title_stat(winner_id, "midnight_catch_count")

        # Track catch failures for title (batch)
        if failed_ids:
            await asyncio.gather(
                *(queries.increment_title_stat(uid, "catch_fail_count") for uid in failed_ids)
            )

        # Catch BP reward (보유 100마리 미만만)
        from database.battle_queries import add_bp
        poke_count = await pool.fetchval(
            "SELECT COUNT(*) FROM user_pokemon WHERE user_id = $1 AND is_active = 1",
            winner_id,
        )
        if poke_count < config.CATCH_BP_POKEMON_LIMIT:
            catch_bp = random.randint(config.CATCH_BP_MIN, config.CATCH_BP_MAX)
            await add_bp(winner_id, catch_bp, "catch")
            msg += f"\n{icon_emoji('coin')} +{catch_bp} BP"

        # Master Ball random drop (2% chance on catch)
        master_ball_drop = random.random() < 0.02
        if master_ball_drop:
            await queries.add_master_ball(winner_id)
            msg += f"\n\n{ball_emoji('masterball')} 마스터볼을 획득했다!"

        # Journey system check
        from services.journey_service import check_journey
        journey_msg = await check_journey(winner_id)
        if journey_msg:
            msg += f"\n\n{journey_msg}"

        catch_msg = await context.bot.send_message(
            chat_id=chat_id, text=msg, parse_mode="HTML",
            reply_markup=close_button(),
        )
        lock.release()  # 포획 메시지 전송 완료 → 다음 스폰 허용

        # DM notification to catcher (with stats + power)
        try:
            from utils.battle_calc import calc_battle_stats, format_stats_line, format_power, EVO_STAGE_MAP, get_normalized_base_stats
            stat_type = pokemon.get("stat_type", "balanced") if pokemon else "balanced"

            # Base stats (without IV)
            norm = get_normalized_base_stats(pokemon_id)
            evo_stage = 3 if norm else EVO_STAGE_MAP.get(pokemon_id, 3)
            base_kwargs = norm or {}

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

            shiny_dm = f" {shiny_emoji()}이로치" if is_shiny else ""
            iv_line = (f"IV: {caught_ivs['iv_hp']}/{caught_ivs['iv_atk']}/{caught_ivs['iv_def']}"
                       f"/{caught_ivs['iv_spa']}/{caught_ivs['iv_spdef']}/{caught_ivs['iv_spd']}"
                       f" ({iv_sum}/186)")
            own_count = await queries.count_user_pokemon_species(winner_id, pokemon_id)
            own_tag = f"📦 보유: {own_count}마리" if own_count > 1 else "🆕 새로운 포켓몬!"
            if winner.get("used_master_ball"):
                dm_ball = f"{ball_emoji('masterball')} 마스터볼! "
            elif winner.get("used_hyper_ball"):
                dm_ball = f"{ball_emoji('hyperball')} 하이퍼볼! "
            else:
                dm_ball = f"{ball_emoji('pokeball')} "
            dm_text = (
                f"{dm_ball}{rbadge}{tb} {pokemon_name} 포획!{shiny_dm} [{iv_grade}]\n"
                f"{iv_line}\n"
                f"{icon_emoji('bolt')} {format_power(stats_with_iv, stats_base)}\n"
                f"{format_stats_line(stats_with_iv, stats_base)}\n\n"
                f"{own_tag}"
            )
            catch_buttons = InlineKeyboardMarkup([[
                InlineKeyboardButton("가방에 넣기 ✅", callback_data=f"catch_keep_{_inst_id}"),
                InlineKeyboardButton("방생하기 🔄", callback_data=f"catch_release_{_inst_id}"),
            ]])

            try:
                dm_msg = await context.bot.send_message(
                    chat_id=winner_id, text=dm_text,
                    parse_mode="HTML", reply_markup=catch_buttons,
                )
                logger.info(f"Catch DM sent to {winner_id} for {pokemon_name}")

                # 5분 후 자동 가방 넣기
                context.job_queue.run_once(
                    _auto_keep_pokemon,
                    when=300,
                    data={
                        "chat_id": winner_id,
                        "message_id": dm_msg.message_id,
                        "instance_id": _inst_id,
                    },
                )
            except Exception as dm_err:
                logger.warning(f"Failed to send catch DM to {winner_id}: {dm_err}")
        except Exception as e:
            logger.error(f"Catch DM construction failed for {winner_id}: {e}")

        # Check and unlock titles
        from utils.title_checker import check_and_unlock_titles
        from utils.helpers import escape_html
        new_titles = await check_and_unlock_titles(winner_id)
        if new_titles:
            title_msgs = [
                f"🎉 <b>「{icon_emoji(temoji) if temoji in config.ICON_CUSTOM_EMOJI else temoji} {tname}」</b> 칭호 해금!"
                for _, tname, temoji in new_titles
            ]
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
    finally:
        # 어떤 경로로든 락이 아직 잡혀있으면 해제
        if lock.locked():
            lock.release()


async def resolve_unresolved_sessions(bot) -> list[tuple[int, str]]:
    """Resolve pending spawn sessions on startup instead of just cleaning up.
    Returns list of (user_id, ball_type) for refunded balls."""
    from database.connection import get_db

    pool = await get_db()
    # Find unresolved sessions with pokemon info
    sessions = await pool.fetch("""
        SELECT ss.id, ss.chat_id, ss.pokemon_id, pm.name_ko, pm.emoji,
               pm.rarity, pm.catch_rate, ss.is_shiny,
               CASE WHEN ss.spawned_at < NOW() - INTERVAL '5 minutes' THEN 1 ELSE 0 END as too_old
        FROM spawn_sessions ss
        JOIN pokemon_master pm ON ss.pokemon_id = pm.id
        WHERE ss.is_resolved = 0
    """)

    if not sessions:
        return []

    refunded = []
    for sess in sessions:
        session_id = sess["id"]
        chat_id = sess["chat_id"]
        pokemon_id = sess["pokemon_id"]
        pokemon_name = sess["name_ko"]
        rarity = sess["rarity"]
        catch_rate = sess["catch_rate"]
        is_shiny = bool(sess.get("is_shiny"))

        try:
            # Mark resolved
            await pool.execute(
                "UPDATE spawn_sessions SET is_resolved = 1 WHERE id = $1", session_id
            )

            # Too old (>5min) — just refund balls, skip resolve
            if sess["too_old"]:
                refund_rows = await pool.fetch(
                    """SELECT user_id, used_master_ball, used_hyper_ball
                       FROM catch_attempts WHERE session_id = $1
                       AND (used_master_ball = 1 OR used_hyper_ball = 1)""",
                    session_id,
                )
                for r in refund_rows:
                    if r["used_master_ball"]:
                        await pool.execute(
                            "UPDATE users SET master_balls = master_balls + 1 WHERE user_id = $1",
                            r["user_id"],
                        )
                        refunded.append((r["user_id"], "master"))
                    if r["used_hyper_ball"]:
                        await pool.execute(
                            "UPDATE users SET hyper_balls = hyper_balls + 1 WHERE user_id = $1",
                            r["user_id"],
                        )
                        refunded.append((r["user_id"], "hyper"))
                continue

            # Get attempts
            attempts = await queries.get_session_attempts(session_id)
            if not attempts:
                rbadge = rarity_badge(rarity)
                tb = type_badge(pokemon_id)
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"흔들흔들... {icon_emoji('windy')} {rbadge}{tb} {pokemon_name} 도망갔다!",
                    parse_mode="HTML",
                )
                await queries.log_spawn(
                    chat_id, pokemon_id, pokemon_name, sess["emoji"],
                    rarity, None, None, 0,
                )
                continue

            # Roll catches
            catch_boost = await get_catch_boost()
            effective_rate = min(1.0, catch_rate * catch_boost)

            # Pre-fetch catch counts for newbie boost (batch)
            normal_ids_r = [
                a["user_id"] for a in attempts
                if not a.get("used_master_ball") and not a.get("used_hyper_ball")
            ]
            cc_r = await queries.count_total_catches_bulk(normal_ids_r) if normal_ids_r else {}

            results = []
            for attempt in attempts:
                if attempt.get("used_master_ball"):
                    roll, success = -1.0, True
                elif attempt.get("used_hyper_ball"):
                    hyper_rate = min(1.0, effective_rate * config.HYPER_BALL_CATCH_MULTIPLIER)
                    roll = random.random()
                    success = roll < hyper_rate
                else:
                    total = cc_r.get(attempt["user_id"], 0)
                    if total < 2:
                        roll, success = 0.0, True
                    else:
                        roll = random.random()
                        success = roll < effective_rate
                results.append({
                    "user_id": attempt["user_id"],
                    "display_name": attempt["display_name"],
                    "username": attempt["username"],
                    "roll": roll, "success": success,
                    "used_master_ball": bool(attempt.get("used_master_ball")),
                    "used_hyper_ball": bool(attempt.get("used_hyper_ball")),
                })

            winners = [r for r in results if r["success"]]
            participants = len(attempts)

            if not winners:
                rbadge = rarity_badge(rarity)
                tb = type_badge(pokemon_id)
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"흔들흔들... {icon_emoji('windy')} {rbadge}{tb} {pokemon_name} 도망갔다!",
                    parse_mode="HTML",
                )
                await queries.log_spawn(
                    chat_id, pokemon_id, pokemon_name, sess["emoji"],
                    rarity, None, None, participants,
                )
                continue

            # Pick winner
            winners.sort(key=lambda x: x["roll"])
            winner = winners[0]
            winner_id = winner["user_id"]
            winner_name = winner["display_name"]

            # Refund master balls to losers (batch)
            mr_ids = [r["user_id"] for r in results
                      if r["used_master_ball"] and r["user_id"] != winner_id]
            if mr_ids:
                await queries.add_master_balls_bulk(mr_ids)
                refunded.extend((uid, "master") for uid in mr_ids)

            # Refund hyper balls when master ball user wins
            if winner.get("used_master_ball"):
                hr_ids = [r["user_id"] for r in results
                          if r["used_hyper_ball"] and r["user_id"] != winner_id]
                if hr_ids:
                    await queries.add_hyper_balls_bulk(hr_ids)
                    refunded.extend((uid, "hyper") for uid in hr_ids)

            # Give pokemon (transaction)
            _inst_id, caught_ivs = await queries.catch_pokemon_transaction(
                winner_id, pokemon_id, chat_id, is_shiny, session_id,
            )

            # Build message
            from utils.helpers import get_decorated_name
            from utils.battle_calc import iv_total
            user_data = await queries.get_user(winner_id)
            decorated = get_decorated_name(
                winner_name,
                user_data.get("title", "") if user_data else "",
                user_data.get("title_emoji", "") if user_data else "",
                winner.get("username"), html=True,
            )
            iv_sum = iv_total(caught_ivs["iv_hp"], caught_ivs["iv_atk"],
                              caught_ivs["iv_def"], caught_ivs["iv_spa"],
                              caught_ivs["iv_spdef"], caught_ivs["iv_spd"])
            iv_grade, _ = config.get_iv_grade(iv_sum)
            iv_tag = f" [{iv_grade}]"
            rbadge = rarity_badge(rarity)
            tb = type_badge(pokemon_id)
            be = ball_emoji("masterball") if winner["used_master_ball"] else \
                 ball_emoji("hyperball") if winner["used_hyper_ball"] else \
                 ball_emoji("pokeball")
            shiny_label = f"{shiny_emoji()}이로치 " if is_shiny else ""
            msg = f"🔄 서버 복구 — {be} {decorated} — {shiny_label}{rbadge}{tb} {pokemon_name} 포획!{iv_tag}"

            # Catch BP reward (보유 100마리 미만만)
            from database.battle_queries import add_bp
            poke_count = await pool.fetchval(
                "SELECT COUNT(*) FROM user_pokemon WHERE user_id = $1 AND is_active = 1",
                winner_id,
            )
            if poke_count < config.CATCH_BP_POKEMON_LIMIT:
                catch_bp = random.randint(config.CATCH_BP_MIN, config.CATCH_BP_MAX)
                await add_bp(winner_id, catch_bp, "catch")
                msg += f"\n+{catch_bp} BP"

            # Journey system check
            from services.journey_service import check_journey
            journey_msg = await check_journey(winner_id)
            if journey_msg:
                msg += f"\n\n{journey_msg}"

            await bot.send_message(
                chat_id=chat_id, text=msg, parse_mode="HTML",
            )
            await queries.log_spawn(
                chat_id, pokemon_id, pokemon_name, sess["emoji"],
                rarity, winner_id, winner_name, participants,
            )

            # Mission: catch (startup resolve - no context, use bot directly)
            try:
                from services.mission_service import check_mission_progress
                mission_msg = await check_mission_progress(winner_id, "catch")
                if mission_msg:
                    await bot.send_message(chat_id=winner_id, text=mission_msg, parse_mode="HTML")
            except Exception:
                pass

            logger.info(f"[startup resolve] {winner_name} caught {pokemon_name} in {chat_id}")

        except Exception as e:
            logger.error(f"[startup resolve] session {session_id} failed: {e}")
            # 실패해도 볼 환불은 해줘야 함
            try:
                refund_rows = await pool.fetch(
                    """SELECT user_id, used_master_ball, used_hyper_ball
                       FROM catch_attempts WHERE session_id = $1
                       AND (used_master_ball = 1 OR used_hyper_ball = 1)""",
                    session_id,
                )
                for r in refund_rows:
                    if r["used_master_ball"]:
                        await pool.execute(
                            "UPDATE users SET master_balls = master_balls + 1 WHERE user_id = $1",
                            r["user_id"],
                        )
                        refunded.append((r["user_id"], "master"))
                    if r["used_hyper_ball"]:
                        await pool.execute(
                            "UPDATE users SET hyper_balls = hyper_balls + 1 WHERE user_id = $1",
                            r["user_id"],
                        )
                        refunded.append((r["user_id"], "hyper"))
                logger.info(f"[startup resolve] session {session_id}: refunded {len(refund_rows)} balls on error")
            except Exception as refund_err:
                logger.error(f"[startup resolve] session {session_id} refund also failed: {refund_err}")
            await queries.close_spawn_session(session_id)

    if refunded:
        logger.info(f"[startup resolve] Refunded {len(refunded)} balls")
    return refunded


async def _notify_mission(context, user_id: int, mission_key: str):
    """Fire-and-forget: check mission progress and DM user on completion."""
    try:
        from services.mission_service import check_mission_progress
        msg = await check_mission_progress(user_id, mission_key)
        if msg:
            await context.bot.send_message(
                chat_id=user_id, text=msg, parse_mode="HTML",
            )
    except Exception:
        pass


async def _check_returning_user(context, chat_id: int, user_id: int, display_name: str):
    """7일+ 미포획 후 복귀한 유저를 캠프 채팅방에 환영."""
    try:
        last_catch = await queries.get_last_catch_time(user_id)
        if not last_catch:
            return  # 첫 포획이거나 데이터 없음

        import datetime as dt
        now = config.get_kst_now()
        if last_catch.tzinfo is None:
            last_catch = last_catch.replace(tzinfo=dt.timezone.utc)

        days_away = (now - last_catch).days
        if days_away < config.CAMP_RETURN_DAYS:
            return

        # 캠프가 있는 채팅방인지 확인
        from database import camp_queries as cq
        camp = await cq.get_camp(chat_id)
        if not camp:
            return

        from utils.helpers import icon_emoji
        msg = (
            f"{icon_emoji('pokecenter')} <b>복귀 트레이너 환영!</b>\n\n"
            f"{display_name}님이 {days_away}일 만에 돌아왔습니다!\n"
            f"다시 만나서 반갑습니다 {icon_emoji('heart')}"
        )
        await context.bot.send_message(
            chat_id=chat_id, text=msg, parse_mode="HTML",
        )
    except Exception:
        logger.debug(f"Returning user check failed for {user_id}", exc_info=True)
