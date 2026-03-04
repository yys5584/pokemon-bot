"""All database query functions — PostgreSQL / asyncpg version."""

import asyncio
import logging
from datetime import datetime, timedelta
from database.connection import get_db, _force_reconnect
import config as _cfg

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 1.0


async def _retry(fn):
    """Retry a DB operation on transient connection errors."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await fn()
        except (OSError, ConnectionResetError, Exception) as e:
            err_name = type(e).__name__
            # Only retry on connection-related errors
            if any(kw in err_name for kw in ("Connection", "Interface", "Pool")) or \
               any(kw in str(e) for kw in ("connection", "pool", "timeout", "reset", "closed")):
                logger.warning(f"DB retry {attempt}/{MAX_RETRIES}: {err_name}: {e}")
                if attempt == MAX_RETRIES:
                    raise
                await _force_reconnect()
                await asyncio.sleep(RETRY_DELAY * attempt)
            else:
                raise


# ============================================================
# Users
# ============================================================

async def ensure_user(user_id: int, display_name: str, username: str | None = None):
    """Register or update a user. New users get welcome bonus (6 master balls + 500 BP)."""
    async def _do():
        pool = await get_db()
        await pool.execute(
            """INSERT INTO users (user_id, username, display_name, master_balls, battle_points)
               VALUES ($1, $2, $3, 6, 500)
               ON CONFLICT(user_id) DO UPDATE SET
                   username = EXCLUDED.username,
                   display_name = EXCLUDED.display_name,
                   last_active_at = NOW()""",
            user_id, username, display_name,
        )
    await _retry(_do)


async def get_user(user_id: int) -> dict | None:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT * FROM users WHERE user_id = $1", user_id
    )
    return dict(row) if row else None


async def get_all_user_ids() -> list[int]:
    """Get all registered user IDs."""
    pool = await get_db()
    rows = await pool.fetch("SELECT user_id FROM users")
    return [r["user_id"] for r in rows]


async def get_recently_active_user_ids(minutes: int = 10) -> list[int]:
    """Get user IDs active within the last N minutes."""
    pool = await get_db()
    rows = await pool.fetch(
        "SELECT user_id FROM users WHERE last_active_at >= NOW() - $1 * INTERVAL '1 minute'",
        minutes,
    )
    return [r["user_id"] for r in rows]


async def update_user_title(user_id: int, title: str, title_emoji: str):
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET title = $1, title_emoji = $2 WHERE user_id = $3",
        title, title_emoji, user_id,
    )


# ============================================================
# Master Balls
# ============================================================

async def get_master_balls(user_id: int) -> int:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT master_balls FROM users WHERE user_id = $1", user_id
    )
    return row["master_balls"] if row else 0


async def add_master_ball(user_id: int, count: int = 1):
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET master_balls = master_balls + $1 WHERE user_id = $2",
        count, user_id,
    )


async def use_master_ball(user_id: int) -> bool:
    """Use one master ball. Returns True if successful (atomic operation)."""
    pool = await get_db()
    row = await pool.fetchrow(
        "UPDATE users SET master_balls = master_balls - 1 "
        "WHERE user_id = $1 AND master_balls >= 1 "
        "RETURNING master_balls",
        user_id,
    )
    return row is not None


async def get_hyper_balls(user_id: int) -> int:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT hyper_balls FROM users WHERE user_id = $1", user_id
    )
    return row["hyper_balls"] if row else 0


async def add_hyper_ball(user_id: int, count: int = 1):
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET hyper_balls = hyper_balls + $1 WHERE user_id = $2",
        count, user_id,
    )


async def use_hyper_ball(user_id: int) -> bool:
    """Use one hyper ball. Returns True if successful (atomic operation)."""
    pool = await get_db()
    row = await pool.fetchrow(
        "UPDATE users SET hyper_balls = hyper_balls - 1 "
        "WHERE user_id = $1 AND hyper_balls >= 1 "
        "RETURNING hyper_balls",
        user_id,
    )
    return row is not None


# ============================================================
# Force Spawn Tickets
# ============================================================

async def get_force_spawn_tickets(user_id: int) -> int:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT force_spawn_tickets FROM users WHERE user_id = $1", user_id
    )
    return row["force_spawn_tickets"] if row and row["force_spawn_tickets"] else 0


async def add_force_spawn_ticket(user_id: int, count: int = 1):
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET force_spawn_tickets = force_spawn_tickets + $1 WHERE user_id = $2",
        count, user_id,
    )


async def use_force_spawn_ticket(user_id: int) -> bool:
    """Use one force spawn ticket. Returns True if successful (atomic)."""
    pool = await get_db()
    row = await pool.fetchrow(
        "UPDATE users SET force_spawn_tickets = force_spawn_tickets - 1 "
        "WHERE user_id = $1 AND force_spawn_tickets >= 1 "
        "RETURNING force_spawn_tickets",
        user_id,
    )
    return row is not None


# ============================================================
# Arcade Pass
# ============================================================

async def get_arcade_tickets(user_id: int) -> int:
    """Get user's arcade ticket count."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT arcade_tickets FROM users WHERE user_id = $1", user_id
    )
    return row["arcade_tickets"] if row and row["arcade_tickets"] else 0


async def add_arcade_ticket(user_id: int, count: int = 1):
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET arcade_tickets = arcade_tickets + $1 WHERE user_id = $2",
        count, user_id,
    )


async def use_arcade_ticket(user_id: int) -> bool:
    """Use one arcade ticket. Returns True if successful (atomic)."""
    pool = await get_db()
    row = await pool.fetchrow(
        "UPDATE users SET arcade_tickets = arcade_tickets - 1 "
        "WHERE user_id = $1 AND arcade_tickets >= 1 "
        "RETURNING arcade_tickets",
        user_id,
    )
    return row is not None


async def get_active_arcade_pass(chat_id: int) -> dict | None:
    """Get active arcade pass for a chat (temporary 1hr registration)."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT * FROM arcade_passes WHERE chat_id = $1 AND is_active = 1 AND expires_at > NOW() ORDER BY expires_at DESC LIMIT 1",
        chat_id,
    )
    return dict(row) if row else None


async def create_arcade_pass(chat_id: int, user_id: int, duration_seconds: int) -> dict:
    """Activate arcade mode for a chat. Returns the pass record."""
    pool = await get_db()
    row = await pool.fetchrow(
        """INSERT INTO arcade_passes (chat_id, activated_by, expires_at)
           VALUES ($1, $2, NOW() + make_interval(secs => $3))
           RETURNING *""",
        chat_id, user_id, float(duration_seconds),
    )
    return dict(row)


async def expire_arcade_passes():
    """Mark expired arcade passes as inactive. Returns list of expired chat_ids."""
    pool = await get_db()
    rows = await pool.fetch(
        "UPDATE arcade_passes SET is_active = 0 WHERE is_active = 1 AND expires_at <= NOW() RETURNING chat_id"
    )
    return [r["chat_id"] for r in rows]


async def get_all_active_arcade_passes() -> list[dict]:
    """Get all currently active arcade passes (for startup recovery)."""
    pool = await get_db()
    rows = await pool.fetch(
        "SELECT * FROM arcade_passes WHERE is_active = 1 AND expires_at > NOW()"
    )
    return [dict(r) for r in rows]


# ============================================================
# Pokemon Master (with in-memory cache — 251 rows, never changes)
# ============================================================

_pokemon_cache: dict[int, dict] = {}       # id -> pokemon dict
_pokemon_by_name: dict[str, dict] = {}     # name_ko -> pokemon dict
_pokemon_by_rarity: dict[str, list] = {}   # rarity -> [pokemon dicts]


async def _load_pokemon_cache():
    """Load all pokemon_master into memory. Called once at startup."""
    global _pokemon_cache, _pokemon_by_name, _pokemon_by_rarity
    if _pokemon_cache:
        return
    pool = await get_db()
    rows = await pool.fetch("SELECT * FROM pokemon_master ORDER BY id")
    _pokemon_cache = {r["id"]: dict(r) for r in rows}
    _pokemon_by_name = {r["name_ko"]: dict(r) for r in rows}
    _pokemon_by_rarity = {}
    for r in rows:
        d = dict(r)
        _pokemon_by_rarity.setdefault(d["rarity"], []).append(d)
    logger.info(f"Pokemon cache loaded: {len(_pokemon_cache)} species")


async def get_pokemon(pokemon_id: int) -> dict | None:
    await _load_pokemon_cache()
    return _pokemon_cache.get(pokemon_id)


async def search_pokemon_by_name(name: str) -> dict | None:
    """Search pokemon_master by Korean name (exact or partial)."""
    await _load_pokemon_cache()
    # Exact match
    if name in _pokemon_by_name:
        return _pokemon_by_name[name]
    # Partial match
    for k, v in _pokemon_by_name.items():
        if name in k:
            return v
    return None


async def get_pokemon_by_rarity(rarity: str) -> list[dict]:
    await _load_pokemon_cache()
    return _pokemon_by_rarity.get(rarity, [])


async def get_all_pokemon() -> list[dict]:
    await _load_pokemon_cache()
    return list(_pokemon_cache.values())


# ============================================================
# User Pokemon (owned collection)
# ============================================================

async def give_pokemon_to_user(
    user_id: int, pokemon_id: int, chat_id: int | None = None,
    is_shiny: bool = False, ivs: dict | None = None,
) -> tuple[int, dict]:
    """Add a Pokemon to user's collection with IVs.

    If ivs dict provided, uses those IVs (for trades). Otherwise generates random IVs.
    Returns (instance_id, iv_dict).
    iv_dict keys: iv_hp, iv_atk, iv_def, iv_spa, iv_spdef, iv_spd
    """
    if ivs is None:
        from utils.battle_calc import generate_ivs
        ivs = generate_ivs(is_shiny=is_shiny)

    pool = await get_db()
    row = await pool.fetchrow(
        """INSERT INTO user_pokemon
               (user_id, pokemon_id, caught_in_chat_id, is_shiny,
                iv_hp, iv_atk, iv_def, iv_spa, iv_spdef, iv_spd)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) RETURNING id""",
        user_id, pokemon_id, chat_id, 1 if is_shiny else 0,
        ivs["iv_hp"], ivs["iv_atk"], ivs["iv_def"],
        ivs["iv_spa"], ivs["iv_spdef"], ivs["iv_spd"],
    )
    return row["id"], ivs


async def get_user_pokemon_list(user_id: int) -> list[dict]:
    """Get all active Pokemon owned by a user, with battle team info."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT up.*, pm.name_ko, pm.name_en, pm.emoji, pm.rarity,
                  pm.evolves_to, pm.evolution_method,
                  pm.pokemon_type, pm.stat_type,
                  bt.slot AS team_slot, bt.team_number AS team_num
           FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           LEFT JOIN battle_teams bt ON bt.pokemon_instance_id = up.id
           WHERE up.user_id = $1 AND up.is_active = 1
           ORDER BY
               CASE WHEN bt.slot IS NOT NULL THEN 0 ELSE 1 END,
               bt.team_number NULLS LAST, bt.slot NULLS LAST,
               CASE pm.rarity
                   WHEN 'legendary' THEN 1
                   WHEN 'epic' THEN 2
                   WHEN 'rare' THEN 3
                   WHEN 'common' THEN 4
               END, up.id DESC""",
        user_id,
    )
    return [dict(r) for r in rows]


async def get_user_pokemon_by_index(user_id: int, index: int) -> dict | None:
    """Get user's Nth active Pokemon (1-indexed)."""
    pokemon_list = await get_user_pokemon_list(user_id)
    if 1 <= index <= len(pokemon_list):
        return pokemon_list[index - 1]
    return None


async def get_user_pokemon_by_name(user_id: int, name: str) -> dict | None:
    """Get user's Pokemon by name (Korean). Returns first match."""
    pokemon_list = await get_user_pokemon_list(user_id)
    name_lower = name.strip().lower()
    for p in pokemon_list:
        if p["name_ko"].lower() == name_lower:
            return p
    # Partial match fallback
    for p in pokemon_list:
        if name_lower in p["name_ko"].lower():
            return p
    return None


async def get_user_pokemon_by_id(instance_id: int) -> dict | None:
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT up.*, pm.name_ko, pm.name_en, pm.emoji, pm.rarity,
                  pm.evolves_to, pm.evolution_method, pm.evolves_from
           FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.id = $1 AND up.is_active = 1""",
        instance_id,
    )
    return dict(row) if row else None


async def update_pokemon_friendship(instance_id: int, friendship: int):
    pool = await get_db()
    await pool.execute(
        "UPDATE user_pokemon SET friendship = $1 WHERE id = $2",
        friendship, instance_id,
    )


async def increment_feed(instance_id: int):
    pool = await get_db()
    await pool.execute(
        "UPDATE user_pokemon SET fed_today = fed_today + 1 WHERE id = $1",
        instance_id,
    )


async def increment_play(instance_id: int):
    pool = await get_db()
    await pool.execute(
        "UPDATE user_pokemon SET played_today = played_today + 1 WHERE id = $1",
        instance_id,
    )


async def evolve_pokemon(instance_id: int, new_pokemon_id: int):
    """Change a Pokemon's species (evolution). Reset friendship."""
    pool = await get_db()
    await pool.execute(
        """UPDATE user_pokemon
           SET pokemon_id = $1, friendship = 0
           WHERE id = $2""",
        new_pokemon_id, instance_id,
    )


async def deactivate_pokemon(instance_id: int):
    """Mark a Pokemon as inactive (traded away)."""
    pool = await get_db()
    await pool.execute(
        "UPDATE user_pokemon SET is_active = 0 WHERE id = $1",
        instance_id,
    )


async def reset_daily_nurture():
    """Reset daily feed/play counts for all Pokemon. Called at midnight."""
    pool = await get_db()
    await pool.execute(
        "UPDATE user_pokemon SET fed_today = 0, played_today = 0 WHERE is_active = 1"
    )


async def find_user_pokemon_by_name(user_id: int, name: str) -> dict | None:
    """Find a user's active Pokemon by Korean name."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT up.*, pm.name_ko, pm.name_en, pm.emoji, pm.rarity,
                  pm.evolves_to, pm.evolution_method
           FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.user_id = $1 AND up.is_active = 1 AND pm.name_ko = $2
           ORDER BY up.id LIMIT 1""",
        user_id, name,
    )
    return dict(row) if row else None


async def find_all_user_pokemon_by_name(user_id: int, name: str) -> list[dict]:
    """Find ALL active Pokemon of a user by Korean name (for duplicates)."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT up.*, pm.name_ko, pm.name_en, pm.emoji, pm.rarity,
                  pm.evolves_to, pm.evolution_method
           FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.user_id = $1 AND up.is_active = 1 AND pm.name_ko = $2
           ORDER BY up.id""",
        user_id, name,
    )
    return [dict(r) for r in rows]


# ============================================================
# Pokedex
# ============================================================

async def register_pokedex(user_id: int, pokemon_id: int, method: str = "catch"):
    """Register a Pokemon in the user's Pokedex."""
    pool = await get_db()
    await pool.execute(
        """INSERT INTO pokedex (user_id, pokemon_id, method)
           VALUES ($1, $2, $3)
           ON CONFLICT (user_id, pokemon_id) DO NOTHING""",
        user_id, pokemon_id, method,
    )


async def get_user_pokedex(user_id: int) -> list[dict]:
    """Get all Pokedex entries for a user."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT p.pokemon_id, p.method, p.first_caught_at,
                  pm.name_ko, pm.emoji, pm.rarity
           FROM pokedex p
           JOIN pokemon_master pm ON p.pokemon_id = pm.id
           WHERE p.user_id = $1
           ORDER BY p.pokemon_id""",
        user_id,
    )
    return [dict(r) for r in rows]


async def count_pokedex(user_id: int) -> int:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM pokedex WHERE user_id = $1", user_id
    )
    return row["cnt"] if row else 0


async def count_pokedex_gen1(user_id: int) -> int:
    """Count Gen 1 pokedex entries (pokemon_id 1~151)."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM pokedex WHERE user_id = $1 AND pokemon_id <= 151",
        user_id,
    )
    return row["cnt"] if row else 0


async def count_pokedex_gen2(user_id: int) -> int:
    """Count Gen 2 pokedex entries (pokemon_id 152~251)."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM pokedex WHERE user_id = $1 AND pokemon_id >= 152 AND pokemon_id <= 251",
        user_id,
    )
    return row["cnt"] if row else 0


async def count_legendary_caught(user_id: int) -> int:
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT COUNT(*) as cnt FROM pokedex p
           JOIN pokemon_master pm ON p.pokemon_id = pm.id
           WHERE p.user_id = $1 AND pm.rarity = 'legendary'""",
        user_id,
    )
    return row["cnt"] if row else 0


async def is_first_catch_in_chat(chat_id: int, pokemon_id: int) -> bool:
    """Check if this Pokemon has never been caught in this chat."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT COUNT(*) as cnt FROM spawn_log
           WHERE chat_id = $1 AND pokemon_id = $2 AND caught_by_user_id IS NOT NULL""",
        chat_id, pokemon_id,
    )
    return row["cnt"] == 0 if row else True


# ============================================================
# Chat Rooms
# ============================================================

async def ensure_chat_room(chat_id: int, title: str | None = None, member_count: int = 0):
    pool = await get_db()
    await pool.execute(
        """INSERT INTO chat_rooms (chat_id, chat_title, member_count)
           VALUES ($1, $2, $3)
           ON CONFLICT(chat_id) DO UPDATE SET
               chat_title = COALESCE(EXCLUDED.chat_title, chat_rooms.chat_title),
               member_count = CASE
                   WHEN EXCLUDED.member_count > 0 THEN EXCLUDED.member_count
                   ELSE chat_rooms.member_count
               END""",
        chat_id, title, member_count,
    )


async def get_chat_room(chat_id: int) -> dict | None:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT * FROM chat_rooms WHERE chat_id = $1", chat_id
    )
    return dict(row) if row else None


async def get_all_active_chats() -> list[dict]:
    pool = await get_db()
    rows = await pool.fetch(
        "SELECT * FROM chat_rooms WHERE is_active = 1"
    )
    return [dict(r) for r in rows]


async def update_chat_member_count(chat_id: int, count: int):
    pool = await get_db()
    await pool.execute(
        "UPDATE chat_rooms SET member_count = $1 WHERE chat_id = $2",
        count, chat_id,
    )


async def update_chat_spawn_info(chat_id: int, target: int):
    pool = await get_db()
    await pool.execute(
        """UPDATE chat_rooms
           SET spawns_today_target = $1
           WHERE chat_id = $2""",
        target, chat_id,
    )


async def record_spawn_in_chat(chat_id: int):
    pool = await get_db()
    await pool.execute(
        """UPDATE chat_rooms
           SET last_spawn_at = NOW(), daily_spawn_count = daily_spawn_count + 1
           WHERE chat_id = $1""",
        chat_id,
    )


# ============================================================
# Spawn Sessions
# ============================================================

async def create_spawn_session(
    chat_id: int, pokemon_id: int, expires_at, message_id: int | None = None,
    is_shiny: bool = False,
) -> int:
    async def _do():
        pool = await get_db()
        # Ensure expires_at is a datetime object for asyncpg
        if isinstance(expires_at, str):
            exp = datetime.fromisoformat(expires_at)
        else:
            exp = expires_at
        row = await pool.fetchrow(
            """INSERT INTO spawn_sessions (chat_id, pokemon_id, expires_at, message_id, is_shiny)
               VALUES ($1, $2, $3, $4, $5) RETURNING id""",
            chat_id, pokemon_id, exp, message_id, 1 if is_shiny else 0,
        )
        return row["id"]
    return await _retry(_do)


async def get_active_spawn(chat_id: int) -> dict | None:
    """Get the currently active (unresolved, not expired) spawn in a chat.
    Only SELECT — expired cleanup is handled by periodic jobs."""
    async def _do():
        pool = await get_db()
        row = await pool.fetchrow(
            """SELECT ss.*, pm.name_ko, pm.emoji, pm.rarity, pm.catch_rate
               FROM spawn_sessions ss
               JOIN pokemon_master pm ON ss.pokemon_id = pm.id
               WHERE ss.chat_id = $1 AND ss.is_resolved = 0
               AND ss.expires_at >= NOW()
               ORDER BY ss.id DESC LIMIT 1""",
            chat_id,
        )
        return dict(row) if row else None
    return await _retry(_do)


async def close_spawn_session(session_id: int, caught_by: int | None = None):
    async def _do():
        pool = await get_db()
        await pool.execute(
            """UPDATE spawn_sessions
               SET is_resolved = 1, caught_by_user_id = $1
               WHERE id = $2""",
            caught_by, session_id,
        )
    await _retry(_do)


async def get_last_spawn_time(chat_id: int):
    """Get the datetime of the most recent spawn in a chat (resolved or not)."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT spawned_at FROM spawn_sessions
           WHERE chat_id = $1
           ORDER BY id DESC LIMIT 1""",
        chat_id,
    )
    if row and row["spawned_at"]:
        ts = row["spawned_at"]
        # asyncpg returns datetime objects directly
        if isinstance(ts, datetime):
            return ts.replace(tzinfo=None)
        try:
            return datetime.fromisoformat(str(ts))
        except (ValueError, TypeError):
            return None
    return None


async def cleanup_expired_sessions():
    """Resolve ALL unresolved sessions on startup (safety net for crashes)."""
    pool = await get_db()
    await pool.execute(
        """UPDATE spawn_sessions
           SET is_resolved = 1
           WHERE is_resolved = 0"""
    )


# ============================================================
# Catch Attempts
# ============================================================

async def record_catch_attempt(session_id: int, user_id: int, used_master_ball: bool = False, used_hyper_ball: bool = False):
    async def _do():
        pool = await get_db()
        await pool.execute(
            "INSERT INTO catch_attempts (session_id, user_id, used_master_ball, used_hyper_ball) VALUES ($1, $2, $3, $4)",
            session_id, user_id, 1 if used_master_ball else 0, 1 if used_hyper_ball else 0,
        )
    await _retry(_do)


async def has_attempted_session(session_id: int, user_id: int) -> bool:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT 1 FROM catch_attempts WHERE session_id = $1 AND user_id = $2",
        session_id, user_id,
    )
    return row is not None


async def get_session_attempts(session_id: int) -> list[dict]:
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT ca.*, u.display_name, u.username
           FROM catch_attempts ca
           JOIN users u ON ca.user_id = u.user_id
           WHERE ca.session_id = $1""",
        session_id,
    )
    return [dict(r) for r in rows]


# ============================================================
# Catch Limits
# ============================================================

async def get_catch_limit(user_id: int, date: str) -> dict:
    """Get today's catch limit record."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT * FROM catch_limits WHERE user_id = $1 AND date = $2",
        user_id, date,
    )
    if row:
        return dict(row)
    return {"user_id": user_id, "date": date, "attempt_count": 0, "consecutive_catches": 0}


async def increment_attempt(user_id: int, date: str):
    pool = await get_db()
    await pool.execute(
        """INSERT INTO catch_limits (user_id, date, attempt_count)
           VALUES ($1, $2, 1)
           ON CONFLICT(user_id, date) DO UPDATE SET
               attempt_count = catch_limits.attempt_count + 1""",
        user_id, date,
    )


async def increment_consecutive(user_id: int, date: str):
    pool = await get_db()
    await pool.execute(
        """INSERT INTO catch_limits (user_id, date, consecutive_catches)
           VALUES ($1, $2, 1)
           ON CONFLICT(user_id, date) DO UPDATE SET
               consecutive_catches = catch_limits.consecutive_catches + 1""",
        user_id, date,
    )


async def reset_consecutive(user_id: int, date: str):
    pool = await get_db()
    await pool.execute(
        """INSERT INTO catch_limits (user_id, date, consecutive_catches)
           VALUES ($1, $2, 0)
           ON CONFLICT(user_id, date) DO UPDATE SET
               consecutive_catches = 0""",
        user_id, date,
    )


async def add_bonus_catches(user_id: int, date: str, bonus: int = 5):
    """Add bonus catch attempts for easter egg."""
    pool = await get_db()
    await pool.execute(
        """INSERT INTO catch_limits (user_id, date, bonus_catches)
           VALUES ($1, $2, $3)
           ON CONFLICT(user_id, date) DO UPDATE SET
               bonus_catches = catch_limits.bonus_catches + $3""",
        user_id, date, bonus,
    )


async def get_bonus_catches(user_id: int, date: str) -> int:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT bonus_catches FROM catch_limits WHERE user_id = $1 AND date = $2",
        user_id, date,
    )
    return row["bonus_catches"] if row else 0


async def reset_bonus_catches(user_id: int, date: str):
    """Reset bonus catches to 0 (shop pokeball reset)."""
    pool = await get_db()
    await pool.execute(
        "UPDATE catch_limits SET bonus_catches = 0 WHERE user_id = $1 AND date = $2",
        user_id, date,
    )


# ============================================================
# Force Spawn Count
# ============================================================

async def get_force_spawn_count(chat_id: int) -> int:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT force_spawn_count FROM chat_rooms WHERE chat_id = $1",
        chat_id,
    )
    return row["force_spawn_count"] if row else 0


async def increment_force_spawn(chat_id: int):
    pool = await get_db()
    await pool.execute(
        "UPDATE chat_rooms SET force_spawn_count = force_spawn_count + 1 WHERE chat_id = $1",
        chat_id,
    )


async def reset_force_spawn_counts():
    """Reset force spawn counts for all chats."""
    pool = await get_db()
    await pool.execute("UPDATE chat_rooms SET force_spawn_count = 0")


async def reset_force_spawn_for_chat(chat_id: int):
    """Reset force spawn count for a specific chat."""
    pool = await get_db()
    await pool.execute(
        "UPDATE chat_rooms SET force_spawn_count = 0 WHERE chat_id = $1",
        chat_id,
    )


async def get_chats_with_force_spawns() -> list[dict]:
    """Get chat rooms that have used force spawns (count > 0)."""
    pool = await get_db()
    rows = await pool.fetch(
        "SELECT chat_id, chat_title, force_spawn_count FROM chat_rooms "
        "WHERE force_spawn_count > 0 ORDER BY chat_title"
    )
    return [dict(r) for r in rows]


async def reset_catch_limits():
    """Reset all catch limits and bonus catches."""
    pool = await get_db()
    await pool.execute("DELETE FROM catch_limits")


async def recharge_catch_limits():
    """Recharge 50% of used catch attempts (reduce attempt_count by half).

    Called every 3 hours between full resets.
    Example: user used 10/10 → after recharge, 5/10 used (5 available).
    """
    pool = await get_db()
    today = _cfg.get_kst_today()
    await pool.execute(
        """UPDATE catch_limits
           SET attempt_count = GREATEST(0, attempt_count / 2)
           WHERE date = $1""",
        today,
    )


# ============================================================
# Spawn Log
# ============================================================

async def log_spawn(
    chat_id: int, pokemon_id: int, name: str, emoji: str,
    rarity: str, caught_by_id: int | None, caught_by_name: str | None,
    participants: int, is_shiny: bool = False,
):
    pool = await get_db()
    await pool.execute(
        """INSERT INTO spawn_log
           (chat_id, pokemon_id, pokemon_name, pokemon_emoji, rarity,
            caught_by_user_id, caught_by_name, participants, is_shiny)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
        chat_id, pokemon_id, name, emoji, rarity,
        caught_by_id, caught_by_name, participants, 1 if is_shiny else 0,
    )


async def get_recent_logs(chat_id: int, limit: int = 10) -> list[dict]:
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT * FROM spawn_log
           WHERE chat_id = $1
           ORDER BY id DESC LIMIT $2""",
        chat_id, limit,
    )
    return [dict(r) for r in rows]


# ============================================================
# Chat Activity
# ============================================================

async def increment_activity(chat_id: int, hour_bucket: str):
    pool = await get_db()
    await pool.execute(
        """INSERT INTO chat_activity (chat_id, hour_bucket, message_count)
           VALUES ($1, $2, 1)
           ON CONFLICT(chat_id, hour_bucket) DO UPDATE SET
               message_count = chat_activity.message_count + 1""",
        chat_id, hour_bucket,
    )


async def get_recent_activity(chat_id: int, hours: int = 1) -> int:
    """Get total message count in the last N hours."""
    pool = await get_db()
    cutoff = (_cfg.get_kst_now() - timedelta(hours=hours)).strftime("%Y-%m-%d-%H")
    row = await pool.fetchrow(
        """SELECT COALESCE(SUM(message_count), 0) as total FROM chat_activity
           WHERE chat_id = $1 AND hour_bucket >= $2""",
        chat_id, cutoff,
    )
    return row["total"] if row else 0


async def cleanup_old_activity(days: int = 7):
    """Remove activity records older than N days."""
    pool = await get_db()
    cutoff = (_cfg.get_kst_now() - timedelta(days=days)).strftime("%Y-%m-%d-00")
    await pool.execute(
        "DELETE FROM chat_activity WHERE hour_bucket < $1", cutoff
    )


# ============================================================
# Rankings
# ============================================================

async def get_rankings(limit: int = 5) -> list[dict]:
    """Get top N users by pokedex count."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT u.user_id, u.display_name, u.username, u.title, u.title_emoji,
                  COUNT(p.pokemon_id) as caught_count
           FROM users u
           LEFT JOIN pokedex p ON u.user_id = p.user_id
           GROUP BY u.user_id, u.display_name, u.username, u.title, u.title_emoji
           HAVING COUNT(p.pokemon_id) > 0
           ORDER BY caught_count DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


# ============================================================
# Trades
# ============================================================

async def create_trade(
    from_user_id: int, to_user_id: int,
    offer_instance_id: int, request_name: str | None = None
) -> int:
    pool = await get_db()
    row = await pool.fetchrow(
        """INSERT INTO trades
           (from_user_id, to_user_id, offer_pokemon_instance_id, request_pokemon_name)
           VALUES ($1, $2, $3, $4) RETURNING id""",
        from_user_id, to_user_id, offer_instance_id, request_name,
    )
    return row["id"]


async def get_pending_trades_for_user(user_id: int) -> list[dict]:
    """Get all pending trade offers received by a user."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT t.*, u.display_name as from_name,
                  pm.name_ko as offer_name, pm.emoji as offer_emoji,
                  up.is_shiny as offer_is_shiny
           FROM trades t
           JOIN users u ON t.from_user_id = u.user_id
           JOIN user_pokemon up ON t.offer_pokemon_instance_id = up.id
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE t.to_user_id = $1 AND t.status = 'pending'
           ORDER BY t.created_at DESC""",
        user_id,
    )
    return [dict(r) for r in rows]


async def get_trade(trade_id: int) -> dict | None:
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT t.*, up.pokemon_id as offer_pokemon_id,
                  pm.name_ko as offer_name, pm.emoji as offer_emoji,
                  pm.evolution_method, pm.evolves_to,
                  up.is_shiny as offer_is_shiny
           FROM trades t
           JOIN user_pokemon up ON t.offer_pokemon_instance_id = up.id
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE t.id = $1""",
        trade_id,
    )
    return dict(row) if row else None


async def update_trade_status(trade_id: int, status: str):
    pool = await get_db()
    await pool.execute(
        "UPDATE trades SET status = $1, resolved_at = NOW() WHERE id = $2",
        status, trade_id,
    )


async def get_pending_trade_for_pokemon(instance_id: int) -> dict | None:
    """Check if a Pokemon instance is already in a pending trade."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT * FROM trades
           WHERE offer_pokemon_instance_id = $1 AND status = 'pending'
           LIMIT 1""",
        instance_id,
    )
    return dict(row) if row else None


async def get_pending_trade_between(from_user: int, to_user: int) -> dict | None:
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT * FROM trades
           WHERE from_user_id = $1 AND to_user_id = $2 AND status = 'pending'
           LIMIT 1""",
        from_user, to_user,
    )
    return dict(row) if row else None


# ============================================================
# Chat Spawn Multiplier
# ============================================================

async def set_spawn_multiplier(chat_id: int, multiplier: float):
    pool = await get_db()
    await pool.execute(
        "UPDATE chat_rooms SET spawn_multiplier = $1 WHERE chat_id = $2",
        multiplier, chat_id,
    )


async def get_spawn_multiplier(chat_id: int) -> float:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT spawn_multiplier FROM chat_rooms WHERE chat_id = $1", chat_id
    )
    return row["spawn_multiplier"] if row else 1.0


async def set_arcade(chat_id: int, enabled: bool):
    pool = await get_db()
    await pool.execute(
        "UPDATE chat_rooms SET is_arcade = $1 WHERE chat_id = $2",
        1 if enabled else 0, chat_id,
    )


async def get_arcade_chat_ids() -> set[int]:
    """Get all chat IDs with arcade mode enabled."""
    pool = await get_db()
    rows = await pool.fetch("SELECT chat_id FROM chat_rooms WHERE is_arcade = 1")
    return {r["chat_id"] for r in rows}


# ============================================================
# Events
# ============================================================

async def create_event(
    name: str, event_type: str, multiplier: float,
    target: str | None, description: str, end_time,
    created_by: int | None = None,
) -> int:
    pool = await get_db()
    # Ensure end_time is a datetime object for asyncpg
    if isinstance(end_time, str):
        et = datetime.fromisoformat(end_time)
    else:
        et = end_time
    row = await pool.fetchrow(
        """INSERT INTO events (name, event_type, multiplier, target, description, end_time, created_by)
           VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
        name, event_type, multiplier, target, description, et, created_by,
    )
    return row["id"]


async def get_active_events() -> list[dict]:
    """Get all currently active events that haven't expired."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT * FROM events
           WHERE active = 1 AND end_time > NOW()
           ORDER BY start_time"""
    )
    return [dict(r) for r in rows]


async def get_active_events_by_type(event_type: str) -> list[dict]:
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT * FROM events
           WHERE active = 1 AND event_type = $1 AND end_time > NOW()""",
        event_type,
    )
    return [dict(r) for r in rows]


async def end_event(event_id: int):
    pool = await get_db()
    await pool.execute(
        "UPDATE events SET active = 0 WHERE id = $1", event_id
    )


async def cleanup_expired_events():
    """Deactivate events past their end_time."""
    pool = await get_db()
    await pool.execute(
        "UPDATE events SET active = 0 WHERE active = 1 AND end_time <= NOW()"
    )


# ============================================================
# Dashboard / Stats Queries
# ============================================================

async def get_total_stats() -> dict:
    """Get overall bot statistics."""
    pool = await get_db()
    users = await pool.fetchrow("SELECT COUNT(*) as cnt FROM users")
    chats = await pool.fetchrow("SELECT COUNT(*) as cnt FROM chat_rooms WHERE is_active = 1")
    total_spawns = await pool.fetchrow("SELECT COUNT(*) as cnt FROM spawn_log")
    total_catches = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM spawn_log WHERE caught_by_user_id IS NOT NULL"
    )
    total_trades = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM trades WHERE status = 'accepted'"
    )
    return {
        "total_users": users["cnt"] if users else 0,
        "total_chats": chats["cnt"] if chats else 0,
        "total_spawns": total_spawns["cnt"] if total_spawns else 0,
        "total_catches": total_catches["cnt"] if total_catches else 0,
        "total_trades": total_trades["cnt"] if total_trades else 0,
    }


async def get_today_stats() -> dict:
    """Get today's spawn/catch counts."""
    pool = await get_db()
    today = _cfg.get_kst_now().replace(hour=0, minute=0, second=0, microsecond=0)
    spawns = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM spawn_log WHERE spawned_at >= $1", today
    )
    catches = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM spawn_log WHERE caught_by_user_id IS NOT NULL AND spawned_at >= $1",
        today,
    )
    return {
        "today_spawns": spawns["cnt"] if spawns else 0,
        "today_catches": catches["cnt"] if catches else 0,
    }


async def get_all_chat_rooms() -> list[dict]:
    """Get all chat rooms (active and inactive)."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT chat_id, chat_title, member_count, is_active,
                  joined_at, last_spawn_at, daily_spawn_count,
                  spawns_today_target, spawn_multiplier
           FROM chat_rooms ORDER BY joined_at DESC"""
    )
    return [dict(r) for r in rows]


async def get_top_pokemon_caught(limit: int = 10) -> list[dict]:
    """Get most caught Pokemon across all users."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT sl.pokemon_id, sl.pokemon_name, sl.pokemon_emoji, sl.rarity,
                  COUNT(*) as catch_count
           FROM spawn_log sl
           WHERE sl.caught_by_user_id IS NOT NULL
           GROUP BY sl.pokemon_id, sl.pokemon_name, sl.pokemon_emoji, sl.rarity
           ORDER BY catch_count DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_recent_spawns_global(limit: int = 50) -> list[dict]:
    """Get recent spawn logs across all chats."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT sl.*, cr.chat_title
           FROM spawn_log sl
           LEFT JOIN chat_rooms cr ON sl.chat_id = cr.chat_id
           ORDER BY sl.id DESC LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_user_rankings(limit: int = 20) -> list[dict]:
    """Get user rankings by pokedex count for dashboard (gen1, gen2, total)."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT u.user_id, u.display_name, u.username,
                  u.title, u.title_emoji, u.last_active_at,
                  COUNT(p.pokemon_id) FILTER (WHERE p.pokemon_id <= 151) as gen1_count,
                  COUNT(p.pokemon_id) FILTER (WHERE p.pokemon_id >= 152 AND p.pokemon_id <= 251) as gen2_count,
                  COUNT(p.pokemon_id) as pokedex_count
           FROM users u
           LEFT JOIN pokedex p ON u.user_id = p.user_id
           GROUP BY u.user_id, u.display_name, u.username, u.title, u.title_emoji, u.last_active_at
           HAVING COUNT(p.pokemon_id) > 0
           ORDER BY pokedex_count DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


# ============================================================
# Title System
# ============================================================

async def get_user_titles(user_id: int) -> list[dict]:
    """Get all unlocked titles for a user."""
    pool = await get_db()
    rows = await pool.fetch(
        "SELECT title_id, unlocked_at FROM user_titles WHERE user_id = $1 ORDER BY unlocked_at",
        user_id,
    )
    return [dict(r) for r in rows]


async def has_title(user_id: int, title_id: str) -> bool:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT 1 FROM user_titles WHERE user_id = $1 AND title_id = $2",
        user_id, title_id,
    )
    return row is not None


async def unlock_title(user_id: int, title_id: str) -> bool:
    """Unlock a title. Returns True if newly unlocked."""
    pool = await get_db()
    try:
        await pool.execute(
            """INSERT INTO user_titles (user_id, title_id)
               VALUES ($1, $2)
               ON CONFLICT (user_id, title_id) DO NOTHING""",
            user_id, title_id,
        )
        return True
    except Exception:
        return False


async def equip_title(user_id: int, title: str, emoji: str):
    """Set the user's equipped title."""
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET title = $1, title_emoji = $2 WHERE user_id = $3",
        title, emoji, user_id,
    )


async def ensure_title_stats(user_id: int):
    """Ensure user_title_stats row exists."""
    pool = await get_db()
    await pool.execute(
        """INSERT INTO user_title_stats (user_id)
           VALUES ($1)
           ON CONFLICT (user_id) DO NOTHING""",
        user_id,
    )


async def get_title_stats(user_id: int) -> dict:
    """Get title stats for unlock condition checks."""
    pool = await get_db()
    await ensure_title_stats(user_id)
    row = await pool.fetchrow(
        "SELECT * FROM user_title_stats WHERE user_id = $1",
        user_id,
    )
    return dict(row) if row else {}


async def increment_title_stat(user_id: int, stat: str, amount: int = 1):
    """Increment a stat in user_title_stats (single upsert, no separate ensure)."""
    valid_stats = {"catch_fail_count", "midnight_catch_count", "master_ball_used", "love_count", "tournament_wins"}
    if stat not in valid_stats:
        return
    pool = await get_db()
    await pool.execute(
        f"""INSERT INTO user_title_stats (user_id, {stat})
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET {stat} = user_title_stats.{stat} + $2""",
        user_id, amount,
    )


async def update_login_streak(user_id: int):
    """Update login streak. Call on any user activity."""
    pool = await get_db()
    await ensure_title_stats(user_id)
    today = _cfg.get_kst_today()
    stats = await get_title_stats(user_id)
    last_date = stats.get("last_active_date")

    if last_date == today:
        return

    if last_date:
        yesterday = (_cfg.get_kst_now() - timedelta(days=1)).strftime("%Y-%m-%d")
        new_streak = (stats.get("login_streak", 0) + 1) if last_date == yesterday else 1
    else:
        new_streak = 1

    await pool.execute(
        "UPDATE user_title_stats SET login_streak = $1, last_active_date = $2 WHERE user_id = $3",
        new_streak, today, user_id,
    )


async def count_total_catches(user_id: int) -> int:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM spawn_log WHERE caught_by_user_id = $1",
        user_id,
    )
    return row["cnt"] if row else 0


async def count_common_catches(user_id: int) -> int:
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT COUNT(*) as cnt FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.user_id = $1 AND pm.rarity = 'common' AND up.is_active = 1""",
        user_id,
    )
    return row["cnt"] if row else 0


async def count_shiny_pokemon(user_id: int) -> int:
    """Count user's shiny pokemon."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM user_pokemon WHERE user_id = $1 AND is_shiny = 1 AND is_active = 1",
        user_id,
    )
    return row["cnt"] if row else 0


async def count_shiny_legendary(user_id: int) -> int:
    """Count user's shiny legendary pokemon."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT COUNT(*) as cnt FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.user_id = $1 AND up.is_shiny = 1 AND pm.rarity = 'legendary' AND up.is_active = 1""",
        user_id,
    )
    return row["cnt"] if row else 0


async def count_rare_epic_legendary(user_id: int) -> int:
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT COUNT(*) as cnt FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.user_id = $1 AND pm.rarity IN ('epic', 'legendary') AND up.is_active = 1""",
        user_id,
    )
    return row["cnt"] if row else 0


async def count_completed_trades(user_id: int) -> int:
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT COUNT(*) as cnt FROM trades
           WHERE (from_user_id = $1 OR to_user_id = $1) AND status = 'accepted'""",
        user_id,
    )
    return row["cnt"] if row else 0


# ============================================================
# Fun KPI Queries (Dashboard)
# ============================================================

async def get_rare_pokemon_holders(limit: int = 20) -> list[dict]:
    """에픽+전설 보유자 랭킹 — 보유 수 기준."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT u.display_name, u.title, u.title_emoji,
                  SUM(CASE WHEN pm.rarity = 'epic' THEN 1 ELSE 0 END) as epic_count,
                  SUM(CASE WHEN pm.rarity = 'legendary' THEN 1 ELSE 0 END) as legendary_count,
                  COUNT(*) as total
           FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           JOIN users u ON up.user_id = u.user_id
           WHERE pm.rarity IN ('epic', 'legendary') AND up.is_active = 1
           GROUP BY up.user_id, u.display_name, u.title, u.title_emoji
           ORDER BY legendary_count DESC, epic_count DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_shiny_holders(limit: int = 20) -> list[dict]:
    """이로치 보유자 랭킹."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT u.display_name, COUNT(*) as shiny_count
           FROM user_pokemon up
           JOIN users u ON up.user_id = u.user_id
           WHERE up.is_shiny = 1 AND up.is_active = 1
           GROUP BY up.user_id, u.display_name
           HAVING COUNT(*) > 0
           ORDER BY shiny_count DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_global_catch_rate() -> float:
    """전체 포획률 (%)."""
    pool = await get_db()
    total = await pool.fetchrow("SELECT COUNT(*) as cnt FROM spawn_log")
    caught = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM spawn_log WHERE caught_by_user_id IS NOT NULL"
    )
    t = total["cnt"] if total else 0
    c = caught["cnt"] if caught else 0
    return round(c / t * 100, 1) if t > 0 else 0.0


async def get_escape_masters(limit: int = 5) -> list[dict]:
    """도망 장인 TOP N — 잡기 실패 많은 유저."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT u.display_name, ts.catch_fail_count
           FROM user_title_stats ts
           JOIN users u ON ts.user_id = u.user_id
           WHERE ts.catch_fail_count > 0
           ORDER BY ts.catch_fail_count DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_night_owls(limit: int = 5) -> list[dict]:
    """올빼미족 TOP N — 심야 포획 많은 유저."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT u.display_name, ts.midnight_catch_count
           FROM user_title_stats ts
           JOIN users u ON ts.user_id = u.user_id
           WHERE ts.midnight_catch_count > 0
           ORDER BY ts.midnight_catch_count DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_masterball_rich(limit: int = 5) -> list[dict]:
    """마볼 부자 TOP N."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT display_name, master_balls
           FROM users
           WHERE master_balls > 0
           ORDER BY master_balls DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_pokeball_addicts(limit: int = 5) -> list[dict]:
    """포볼 중독자 TOP N — 오늘 보너스 캐치 많은 유저."""
    pool = await get_db()
    today = _cfg.get_kst_today()
    rows = await pool.fetch(
        """SELECT u.display_name, cl.bonus_catches
           FROM catch_limits cl
           JOIN users u ON cl.user_id = u.user_id
           WHERE cl.date = $1 AND cl.bonus_catches > 0
           ORDER BY cl.bonus_catches DESC
           LIMIT $2""",
        today, limit,
    )
    return [dict(r) for r in rows]


async def get_user_catch_rates(limit: int = 10) -> list[dict]:
    """개인 포획률 — 시도 대비 성공률 (최소 5회 이상 시도)."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT u.display_name,
                  COUNT(*) as attempts,
                  SUM(CASE WHEN sl.caught_by_user_id = ca.user_id THEN 1 ELSE 0 END) as catches,
                  ROUND(
                      (CAST(SUM(CASE WHEN sl.caught_by_user_id = ca.user_id THEN 1 ELSE 0 END) AS NUMERIC)
                      / COUNT(*) * 100)::NUMERIC, 1
                  ) as catch_rate
           FROM catch_attempts ca
           JOIN spawn_sessions ss ON ca.session_id = ss.id
           JOIN spawn_log sl ON sl.chat_id = ss.chat_id
               AND sl.pokemon_id = ss.pokemon_id
               AND sl.spawned_at >= ss.spawned_at
               AND sl.spawned_at <= COALESCE(ss.expires_at, ss.spawned_at + INTERVAL '5 minutes')
           JOIN users u ON ca.user_id = u.user_id
           GROUP BY ca.user_id, u.display_name
           HAVING COUNT(*) >= 5
           ORDER BY catch_rate DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_trade_kings(limit: int = 5) -> list[dict]:
    """교환왕 TOP N."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT u.display_name, COUNT(*) as trade_count
           FROM (
               SELECT from_user_id as uid FROM trades WHERE status = 'accepted'
               UNION ALL
               SELECT to_user_id as uid FROM trades WHERE status = 'accepted'
           ) t
           JOIN users u ON t.uid = u.user_id
           GROUP BY t.uid, u.display_name
           ORDER BY trade_count DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_most_escaped_pokemon(limit: int = 5) -> list[dict]:
    """도망 많은 포켓몬 TOP N."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT pokemon_name, pokemon_emoji, rarity,
                  COUNT(*) as escape_count
           FROM spawn_log
           WHERE caught_by_user_id IS NULL
           GROUP BY pokemon_id, pokemon_name, pokemon_emoji, rarity
           ORDER BY escape_count DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_love_leaders(limit: int = 5) -> list[dict]:
    """사랑꾼 TOP N — love_count 높은 유저."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT u.display_name, ts.love_count
           FROM user_title_stats ts
           JOIN users u ON ts.user_id = u.user_id
           WHERE ts.love_count > 0
           ORDER BY ts.love_count DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_total_master_balls_used() -> int:
    """총 마스터볼 사용량."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM catch_attempts WHERE used_master_ball = 1"
    )
    return row["cnt"] if row else 0


async def get_longest_streak_user() -> dict | None:
    """최장 연속출석 유저."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT u.display_name, ts.login_streak
           FROM user_title_stats ts
           JOIN users u ON ts.user_id = u.user_id
           WHERE ts.login_streak > 0
           ORDER BY ts.login_streak DESC
           LIMIT 1"""
    )
    return dict(row) if row else None


# ─── Dashboard: DAU / Retention / Economy ───

async def get_dau() -> int:
    """오늘 활동한 유저 수 (포획 시도 기준)."""
    pool = await get_db()
    today = _cfg.get_kst_now().replace(hour=0, minute=0, second=0, microsecond=0)
    row = await pool.fetchrow(
        "SELECT COUNT(DISTINCT user_id) as cnt FROM catch_attempts WHERE attempted_at >= $1",
        today,
    )
    return row["cnt"] if row else 0


async def get_dau_history(days: int = 7) -> list[dict]:
    """최근 N일 DAU 추이."""
    pool = await get_db()
    since = _cfg.get_kst_now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)
    rows = await pool.fetch(
        """SELECT attempted_at::date as day, COUNT(DISTINCT user_id) as dau
           FROM catch_attempts
           WHERE attempted_at >= $1
           GROUP BY day ORDER BY day""",
        since,
    )
    return [{"day": str(r["day"]), "dau": r["dau"]} for r in rows]


async def get_retention_d1() -> dict:
    """D+1 리텐션: 출시일(3/1) 이후 가입자 중 다음날도 활동한 비율.
    오늘 가입자는 아직 D+1이 안 왔으므로 어제까지만 대상."""
    pool = await get_db()
    from datetime import date as dt_date
    launch = dt_date(2026, 3, 1)
    yesterday = datetime.now().date() - __import__('datetime').timedelta(days=1)
    row = await pool.fetchrow(
        """WITH new_users AS (
               SELECT user_id, registered_at::date as reg_date
               FROM users
               WHERE registered_at::date >= $1
                 AND registered_at::date <= $2
           ),
           next_day_active AS (
               SELECT DISTINCT nu.user_id
               FROM new_users nu
               JOIN catch_attempts ca ON nu.user_id = ca.user_id
                   AND ca.attempted_at::date = nu.reg_date + INTERVAL '1 day'
           )
           SELECT
               (SELECT COUNT(*) FROM new_users) as total_new,
               (SELECT COUNT(*) FROM next_day_active) as retained
        """,
        launch, yesterday,
    )
    total = row["total_new"] if row else 0
    retained = row["retained"] if row else 0
    rate = round(retained / total * 100, 1) if total > 0 else 0
    return {"total_new": total, "retained": retained, "rate": rate}


async def get_economy_health() -> dict:
    """경제 건강도: 마볼 유통량, BP 총합, 평균 등."""
    pool = await get_db()
    mb = await pool.fetchrow(
        "SELECT SUM(master_balls) as total, AVG(master_balls) as avg FROM users WHERE master_balls > 0"
    )
    bp = await pool.fetchrow(
        "SELECT SUM(battle_points) as total, AVG(battle_points) as avg FROM users WHERE battle_points > 0"
    )
    mb_used = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM catch_attempts WHERE used_master_ball = 1"
    )
    total_pokemon = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM user_pokemon WHERE is_active = 1"
    )
    return {
        "master_balls_circulation": int(mb["total"]) if mb and mb["total"] else 0,
        "master_balls_avg": round(float(mb["avg"]), 1) if mb and mb["avg"] else 0,
        "master_balls_used_total": mb_used["cnt"] if mb_used else 0,
        "bp_circulation": int(bp["total"]) if bp and bp["total"] else 0,
        "bp_avg": round(float(bp["avg"]), 1) if bp and bp["avg"] else 0,
        "total_pokemon_owned": total_pokemon["cnt"] if total_pokemon else 0,
    }


async def get_active_chat_rooms_top(limit: int = 5) -> list[dict]:
    """오늘 스폰이 가장 많은 활성 채팅방 TOP N."""
    pool = await get_db()
    today = _cfg.get_kst_now().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = await pool.fetch(
        """SELECT cr.chat_id, cr.chat_title, cr.member_count,
                  COUNT(sl.id) as today_spawns,
                  COUNT(sl.caught_by_user_id) as today_catches
           FROM chat_rooms cr
           LEFT JOIN spawn_log sl ON cr.chat_id = sl.chat_id AND sl.spawned_at >= $1
           WHERE cr.is_active = 1 AND cr.member_count >= 10 AND cr.chat_title IS NOT NULL
           GROUP BY cr.chat_id, cr.chat_title, cr.member_count
           ORDER BY today_spawns DESC
           LIMIT $2""",
        today, limit,
    )
    return [dict(r) for r in rows]
