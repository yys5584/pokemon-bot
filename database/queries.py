"""All database query functions."""

from datetime import datetime, timedelta
from database.connection import get_db


# ============================================================
# Users
# ============================================================

async def ensure_user(user_id: int, display_name: str, username: str | None = None):
    """Register or update a user."""
    db = await get_db()
    await db.execute(
        """INSERT INTO users (user_id, username, display_name)
           VALUES (?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
               username = excluded.username,
               display_name = excluded.display_name,
               last_active_at = datetime('now')""",
        (user_id, username, display_name),
    )
    await db.commit()


async def get_user(user_id: int) -> dict | None:
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT * FROM users WHERE user_id = ?", (user_id,)
    )
    return dict(row[0]) if row else None


async def update_user_title(user_id: int, title: str, title_emoji: str):
    db = await get_db()
    await db.execute(
        "UPDATE users SET title = ?, title_emoji = ? WHERE user_id = ?",
        (title, title_emoji, user_id),
    )
    await db.commit()


# ============================================================
# Master Balls
# ============================================================

async def get_master_balls(user_id: int) -> int:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT master_balls FROM users WHERE user_id = ?", (user_id,)
    )
    return rows[0][0] if rows else 0


async def add_master_ball(user_id: int, count: int = 1):
    db = await get_db()
    await db.execute(
        "UPDATE users SET master_balls = master_balls + ? WHERE user_id = ?",
        (count, user_id),
    )
    await db.commit()


async def use_master_ball(user_id: int) -> bool:
    """Use one master ball. Returns True if successful (had at least 1)."""
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT master_balls FROM users WHERE user_id = ?", (user_id,)
    )
    if not rows or rows[0][0] < 1:
        return False
    await db.execute(
        "UPDATE users SET master_balls = master_balls - 1 WHERE user_id = ?",
        (user_id,),
    )
    await db.commit()
    return True


# ============================================================
# Pokemon Master
# ============================================================

async def get_pokemon(pokemon_id: int) -> dict | None:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM pokemon_master WHERE id = ?", (pokemon_id,)
    )
    return dict(rows[0]) if rows else None


async def search_pokemon_by_name(name: str) -> dict | None:
    """Search pokemon_master by Korean name (exact or partial)."""
    db = await get_db()
    # Exact match first
    rows = await db.execute_fetchall(
        "SELECT * FROM pokemon_master WHERE name_ko = ?", (name,)
    )
    if rows:
        return dict(rows[0])
    # Partial match
    rows = await db.execute_fetchall(
        "SELECT * FROM pokemon_master WHERE name_ko LIKE ?", (f"%{name}%",)
    )
    return dict(rows[0]) if rows else None


async def get_pokemon_by_rarity(rarity: str) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM pokemon_master WHERE rarity = ?", (rarity,)
    )
    return [dict(r) for r in rows]


async def get_all_pokemon() -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM pokemon_master ORDER BY id"
    )
    return [dict(r) for r in rows]


# ============================================================
# User Pokemon (owned collection)
# ============================================================

async def give_pokemon_to_user(
    user_id: int, pokemon_id: int, chat_id: int | None = None
) -> int:
    """Add a Pokemon to user's collection. Returns instance id."""
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO user_pokemon (user_id, pokemon_id, caught_in_chat_id)
           VALUES (?, ?, ?)""",
        (user_id, pokemon_id, chat_id),
    )
    await db.commit()
    return cursor.lastrowid


async def get_user_pokemon_list(user_id: int) -> list[dict]:
    """Get all active Pokemon owned by a user."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT up.*, pm.name_ko, pm.name_en, pm.emoji, pm.rarity,
                  pm.evolves_to, pm.evolution_method
           FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.user_id = ? AND up.is_active = 1
           ORDER BY up.id""",
        (user_id,),
    )
    return [dict(r) for r in rows]


async def get_user_pokemon_by_index(user_id: int, index: int) -> dict | None:
    """Get user's Nth active Pokemon (1-indexed)."""
    pokemon_list = await get_user_pokemon_list(user_id)
    if 1 <= index <= len(pokemon_list):
        return pokemon_list[index - 1]
    return None


async def get_user_pokemon_by_id(instance_id: int) -> dict | None:
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT up.*, pm.name_ko, pm.name_en, pm.emoji, pm.rarity,
                  pm.evolves_to, pm.evolution_method, pm.evolves_from
           FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.id = ? AND up.is_active = 1""",
        (instance_id,),
    )
    return dict(rows[0]) if rows else None


async def update_pokemon_friendship(instance_id: int, friendship: int):
    db = await get_db()
    await db.execute(
        "UPDATE user_pokemon SET friendship = ? WHERE id = ?",
        (friendship, instance_id),
    )
    await db.commit()


async def increment_feed(instance_id: int):
    db = await get_db()
    await db.execute(
        "UPDATE user_pokemon SET fed_today = fed_today + 1 WHERE id = ?",
        (instance_id,),
    )
    await db.commit()


async def increment_play(instance_id: int):
    db = await get_db()
    await db.execute(
        "UPDATE user_pokemon SET played_today = played_today + 1 WHERE id = ?",
        (instance_id,),
    )
    await db.commit()


async def evolve_pokemon(instance_id: int, new_pokemon_id: int):
    """Change a Pokemon's species (evolution). Reset friendship."""
    db = await get_db()
    await db.execute(
        """UPDATE user_pokemon
           SET pokemon_id = ?, friendship = 0
           WHERE id = ?""",
        (new_pokemon_id, instance_id),
    )
    await db.commit()


async def deactivate_pokemon(instance_id: int):
    """Mark a Pokemon as inactive (traded away)."""
    db = await get_db()
    await db.execute(
        "UPDATE user_pokemon SET is_active = 0 WHERE id = ?",
        (instance_id,),
    )
    await db.commit()


async def reset_daily_nurture():
    """Reset daily feed/play counts for all Pokemon. Called at midnight."""
    db = await get_db()
    await db.execute(
        "UPDATE user_pokemon SET fed_today = 0, played_today = 0 WHERE is_active = 1"
    )
    await db.commit()


async def find_user_pokemon_by_name(user_id: int, name: str) -> dict | None:
    """Find a user's active Pokemon by Korean name."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT up.*, pm.name_ko, pm.name_en, pm.emoji, pm.rarity,
                  pm.evolves_to, pm.evolution_method
           FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.user_id = ? AND up.is_active = 1 AND pm.name_ko = ?
           ORDER BY up.id LIMIT 1""",
        (user_id, name),
    )
    return dict(rows[0]) if rows else None


# ============================================================
# Pokedex
# ============================================================

async def register_pokedex(user_id: int, pokemon_id: int, method: str = "catch"):
    """Register a Pokemon in the user's Pokedex."""
    db = await get_db()
    await db.execute(
        """INSERT OR IGNORE INTO pokedex (user_id, pokemon_id, method)
           VALUES (?, ?, ?)""",
        (user_id, pokemon_id, method),
    )
    await db.commit()


async def get_user_pokedex(user_id: int) -> list[dict]:
    """Get all Pokedex entries for a user."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT p.pokemon_id, p.method, p.first_caught_at,
                  pm.name_ko, pm.emoji, pm.rarity
           FROM pokedex p
           JOIN pokemon_master pm ON p.pokemon_id = pm.id
           WHERE p.user_id = ?
           ORDER BY p.pokemon_id""",
        (user_id,),
    )
    return [dict(r) for r in rows]


async def count_pokedex(user_id: int) -> int:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT COUNT(*) FROM pokedex WHERE user_id = ?", (user_id,)
    )
    return rows[0][0] if rows else 0


async def count_pokedex_gen1(user_id: int) -> int:
    """Count Gen 1 pokedex entries (pokemon_id 1~151)."""
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT COUNT(*) FROM pokedex WHERE user_id = ? AND pokemon_id <= 151",
        (user_id,),
    )
    return rows[0][0] if rows else 0


async def count_pokedex_gen2(user_id: int) -> int:
    """Count Gen 2 pokedex entries (pokemon_id 152~251)."""
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT COUNT(*) FROM pokedex WHERE user_id = ? AND pokemon_id >= 152 AND pokemon_id <= 251",
        (user_id,),
    )
    return rows[0][0] if rows else 0


async def count_legendary_caught(user_id: int) -> int:
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT COUNT(*) FROM pokedex p
           JOIN pokemon_master pm ON p.pokemon_id = pm.id
           WHERE p.user_id = ? AND pm.rarity = 'legendary'""",
        (user_id,),
    )
    return rows[0][0] if rows else 0


async def is_first_catch_in_chat(chat_id: int, pokemon_id: int) -> bool:
    """Check if this Pokemon has never been caught in this chat."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT COUNT(*) FROM spawn_log
           WHERE chat_id = ? AND pokemon_id = ? AND caught_by_user_id IS NOT NULL""",
        (chat_id, pokemon_id),
    )
    return rows[0][0] == 0 if rows else True


# ============================================================
# Chat Rooms
# ============================================================

async def ensure_chat_room(chat_id: int, title: str | None = None, member_count: int = 0):
    db = await get_db()
    await db.execute(
        """INSERT INTO chat_rooms (chat_id, chat_title, member_count)
           VALUES (?, ?, ?)
           ON CONFLICT(chat_id) DO UPDATE SET
               chat_title = COALESCE(excluded.chat_title, chat_rooms.chat_title),
               member_count = CASE
                   WHEN excluded.member_count > 0 THEN excluded.member_count
                   ELSE chat_rooms.member_count
               END""",
        (chat_id, title, member_count),
    )
    await db.commit()


async def get_chat_room(chat_id: int) -> dict | None:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM chat_rooms WHERE chat_id = ?", (chat_id,)
    )
    return dict(rows[0]) if rows else None


async def get_all_active_chats() -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM chat_rooms WHERE is_active = 1"
    )
    return [dict(r) for r in rows]


async def update_chat_member_count(chat_id: int, count: int):
    db = await get_db()
    await db.execute(
        "UPDATE chat_rooms SET member_count = ? WHERE chat_id = ?",
        (count, chat_id),
    )
    await db.commit()


async def update_chat_spawn_info(chat_id: int, target: int):
    db = await get_db()
    await db.execute(
        """UPDATE chat_rooms
           SET spawns_today_target = ?, daily_spawn_count = 0
           WHERE chat_id = ?""",
        (target, chat_id),
    )
    await db.commit()


async def record_spawn_in_chat(chat_id: int):
    db = await get_db()
    await db.execute(
        """UPDATE chat_rooms
           SET last_spawn_at = datetime('now'), daily_spawn_count = daily_spawn_count + 1
           WHERE chat_id = ?""",
        (chat_id,),
    )
    await db.commit()


# ============================================================
# Spawn Sessions
# ============================================================

async def create_spawn_session(
    chat_id: int, pokemon_id: int, expires_at: str, message_id: int | None = None
) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO spawn_sessions (chat_id, pokemon_id, expires_at, message_id)
           VALUES (?, ?, ?, ?)""",
        (chat_id, pokemon_id, expires_at, message_id),
    )
    await db.commit()
    return cursor.lastrowid


async def get_active_spawn(chat_id: int) -> dict | None:
    """Get the currently active (unresolved) spawn in a chat."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT ss.*, pm.name_ko, pm.emoji, pm.rarity, pm.catch_rate
           FROM spawn_sessions ss
           JOIN pokemon_master pm ON ss.pokemon_id = pm.id
           WHERE ss.chat_id = ? AND ss.is_resolved = 0
           ORDER BY ss.id DESC LIMIT 1""",
        (chat_id,),
    )
    return dict(rows[0]) if rows else None


async def close_spawn_session(session_id: int, caught_by: int | None = None):
    db = await get_db()
    await db.execute(
        """UPDATE spawn_sessions
           SET is_resolved = 1, caught_by_user_id = ?
           WHERE id = ?""",
        (caught_by, session_id),
    )
    await db.commit()


async def cleanup_expired_sessions():
    """Resolve ALL unresolved sessions on startup (safety net for crashes)."""
    db = await get_db()
    await db.execute(
        """UPDATE spawn_sessions
           SET is_resolved = 1
           WHERE is_resolved = 0"""
    )
    await db.commit()


# ============================================================
# Catch Attempts
# ============================================================

async def record_catch_attempt(session_id: int, user_id: int, used_master_ball: bool = False):
    db = await get_db()
    await db.execute(
        "INSERT INTO catch_attempts (session_id, user_id, used_master_ball) VALUES (?, ?, ?)",
        (session_id, user_id, 1 if used_master_ball else 0),
    )
    await db.commit()


async def has_attempted_session(session_id: int, user_id: int) -> bool:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT 1 FROM catch_attempts WHERE session_id = ? AND user_id = ?",
        (session_id, user_id),
    )
    return len(rows) > 0


async def get_session_attempts(session_id: int) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT ca.*, u.display_name, u.username
           FROM catch_attempts ca
           JOIN users u ON ca.user_id = u.user_id
           WHERE ca.session_id = ?""",
        (session_id,),
    )
    return [dict(r) for r in rows]


# ============================================================
# Catch Limits
# ============================================================

async def get_catch_limit(user_id: int, date: str) -> dict:
    """Get today's catch limit record."""
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM catch_limits WHERE user_id = ? AND date = ?",
        (user_id, date),
    )
    if rows:
        return dict(rows[0])
    return {"user_id": user_id, "date": date, "attempt_count": 0, "consecutive_catches": 0}


async def increment_attempt(user_id: int, date: str):
    db = await get_db()
    await db.execute(
        """INSERT INTO catch_limits (user_id, date, attempt_count)
           VALUES (?, ?, 1)
           ON CONFLICT(user_id, date) DO UPDATE SET
               attempt_count = catch_limits.attempt_count + 1""",
        (user_id, date),
    )
    await db.commit()


async def increment_consecutive(user_id: int, date: str):
    db = await get_db()
    await db.execute(
        """INSERT INTO catch_limits (user_id, date, consecutive_catches)
           VALUES (?, ?, 1)
           ON CONFLICT(user_id, date) DO UPDATE SET
               consecutive_catches = catch_limits.consecutive_catches + 1""",
        (user_id, date),
    )
    await db.commit()


async def reset_consecutive(user_id: int, date: str):
    db = await get_db()
    await db.execute(
        """INSERT INTO catch_limits (user_id, date, consecutive_catches)
           VALUES (?, ?, 0)
           ON CONFLICT(user_id, date) DO UPDATE SET
               consecutive_catches = 0""",
        (user_id, date),
    )
    await db.commit()


async def add_bonus_catches(user_id: int, date: str, bonus: int = 5):
    """Add bonus catch attempts for easter egg."""
    db = await get_db()
    await db.execute(
        """INSERT INTO catch_limits (user_id, date, bonus_catches)
           VALUES (?, ?, ?)
           ON CONFLICT(user_id, date) DO UPDATE SET
               bonus_catches = catch_limits.bonus_catches + ?""",
        (user_id, date, bonus, bonus),
    )
    await db.commit()


async def get_bonus_catches(user_id: int, date: str) -> int:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT bonus_catches FROM catch_limits WHERE user_id = ? AND date = ?",
        (user_id, date),
    )
    return rows[0][0] if rows else 0


# ============================================================
# Force Spawn Count
# ============================================================

async def get_force_spawn_count(chat_id: int) -> int:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT force_spawn_count FROM chat_rooms WHERE chat_id = ?",
        (chat_id,),
    )
    return rows[0][0] if rows else 0


async def increment_force_spawn(chat_id: int):
    db = await get_db()
    await db.execute(
        "UPDATE chat_rooms SET force_spawn_count = force_spawn_count + 1 WHERE chat_id = ?",
        (chat_id,),
    )
    await db.commit()


async def reset_force_spawn_counts():
    """Reset force spawn counts for all chats."""
    db = await get_db()
    await db.execute("UPDATE chat_rooms SET force_spawn_count = 0")
    await db.commit()


async def reset_catch_limits():
    """Reset all catch limits and bonus catches."""
    db = await get_db()
    await db.execute("DELETE FROM catch_limits")
    await db.commit()


async def recharge_catch_limits():
    """Recharge 50% of used catch attempts (reduce attempt_count by half).

    Called every 3 hours between full resets.
    Example: user used 10/10 → after recharge, 5/10 used (5 available).
    """
    db = await get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    await db.execute(
        """UPDATE catch_limits
           SET attempt_count = MAX(0, attempt_count / 2)
           WHERE date = ?""",
        (today,),
    )
    await db.commit()


# ============================================================
# Spawn Log
# ============================================================

async def log_spawn(
    chat_id: int, pokemon_id: int, name: str, emoji: str,
    rarity: str, caught_by_id: int | None, caught_by_name: str | None,
    participants: int
):
    db = await get_db()
    await db.execute(
        """INSERT INTO spawn_log
           (chat_id, pokemon_id, pokemon_name, pokemon_emoji, rarity,
            caught_by_user_id, caught_by_name, participants)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (chat_id, pokemon_id, name, emoji, rarity,
         caught_by_id, caught_by_name, participants),
    )
    await db.commit()


async def get_recent_logs(chat_id: int, limit: int = 10) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT * FROM spawn_log
           WHERE chat_id = ?
           ORDER BY id DESC LIMIT ?""",
        (chat_id, limit),
    )
    return [dict(r) for r in rows]


# ============================================================
# Chat Activity
# ============================================================

async def increment_activity(chat_id: int, hour_bucket: str):
    db = await get_db()
    await db.execute(
        """INSERT INTO chat_activity (chat_id, hour_bucket, message_count)
           VALUES (?, ?, 1)
           ON CONFLICT(chat_id, hour_bucket) DO UPDATE SET
               message_count = chat_activity.message_count + 1""",
        (chat_id, hour_bucket),
    )
    await db.commit()


async def get_recent_activity(chat_id: int, hours: int = 1) -> int:
    """Get total message count in the last N hours."""
    db = await get_db()
    cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d-%H")
    rows = await db.execute_fetchall(
        """SELECT SUM(message_count) FROM chat_activity
           WHERE chat_id = ? AND hour_bucket >= ?""",
        (chat_id, cutoff),
    )
    return rows[0][0] or 0 if rows else 0


async def cleanup_old_activity(days: int = 7):
    """Remove activity records older than N days."""
    db = await get_db()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d-00")
    await db.execute(
        "DELETE FROM chat_activity WHERE hour_bucket < ?", (cutoff,)
    )
    await db.commit()


# ============================================================
# Rankings
# ============================================================

async def get_rankings(limit: int = 5) -> list[dict]:
    """Get top N users by pokedex count."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT u.user_id, u.display_name, u.username, u.title, u.title_emoji,
                  COUNT(p.pokemon_id) as caught_count
           FROM users u
           LEFT JOIN pokedex p ON u.user_id = p.user_id
           GROUP BY u.user_id
           HAVING caught_count > 0
           ORDER BY caught_count DESC
           LIMIT ?""",
        (limit,),
    )
    return [dict(r) for r in rows]


# ============================================================
# Trades
# ============================================================

async def create_trade(
    from_user_id: int, to_user_id: int,
    offer_instance_id: int, request_name: str | None = None
) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO trades
           (from_user_id, to_user_id, offer_pokemon_instance_id, request_pokemon_name)
           VALUES (?, ?, ?, ?)""",
        (from_user_id, to_user_id, offer_instance_id, request_name),
    )
    await db.commit()
    return cursor.lastrowid


async def get_pending_trades_for_user(user_id: int) -> list[dict]:
    """Get all pending trade offers received by a user."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT t.*, u.display_name as from_name,
                  pm.name_ko as offer_name, pm.emoji as offer_emoji
           FROM trades t
           JOIN users u ON t.from_user_id = u.user_id
           JOIN user_pokemon up ON t.offer_pokemon_instance_id = up.id
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE t.to_user_id = ? AND t.status = 'pending'
           ORDER BY t.created_at DESC""",
        (user_id,),
    )
    return [dict(r) for r in rows]


async def get_trade(trade_id: int) -> dict | None:
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT t.*, up.pokemon_id as offer_pokemon_id,
                  pm.name_ko as offer_name, pm.emoji as offer_emoji,
                  pm.evolution_method, pm.evolves_to
           FROM trades t
           JOIN user_pokemon up ON t.offer_pokemon_instance_id = up.id
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE t.id = ?""",
        (trade_id,),
    )
    return dict(rows[0]) if rows else None


async def update_trade_status(trade_id: int, status: str):
    db = await get_db()
    await db.execute(
        "UPDATE trades SET status = ?, resolved_at = datetime('now') WHERE id = ?",
        (status, trade_id),
    )
    await db.commit()


async def get_pending_trade_for_pokemon(instance_id: int) -> dict | None:
    """Check if a Pokemon instance is already in a pending trade."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT * FROM trades
           WHERE offer_pokemon_instance_id = ? AND status = 'pending'
           LIMIT 1""",
        (instance_id,),
    )
    return dict(rows[0]) if rows else None


async def get_pending_trade_between(from_user: int, to_user: int) -> dict | None:
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT * FROM trades
           WHERE from_user_id = ? AND to_user_id = ? AND status = 'pending'
           LIMIT 1""",
        (from_user, to_user),
    )
    return dict(rows[0]) if rows else None


# ============================================================
# Chat Spawn Multiplier
# ============================================================

async def set_spawn_multiplier(chat_id: int, multiplier: float):
    db = await get_db()
    await db.execute(
        "UPDATE chat_rooms SET spawn_multiplier = ? WHERE chat_id = ?",
        (multiplier, chat_id),
    )
    await db.commit()


async def get_spawn_multiplier(chat_id: int) -> float:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT spawn_multiplier FROM chat_rooms WHERE chat_id = ?", (chat_id,)
    )
    return rows[0][0] if rows else 1.0


# ============================================================
# Events
# ============================================================

async def create_event(
    name: str, event_type: str, multiplier: float,
    target: str | None, description: str, end_time: str,
    created_by: int | None = None,
) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO events (name, event_type, multiplier, target, description, end_time, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (name, event_type, multiplier, target, description, end_time, created_by),
    )
    await db.commit()
    return cursor.lastrowid


async def get_active_events() -> list[dict]:
    """Get all currently active events that haven't expired."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT * FROM events
           WHERE active = 1 AND end_time > datetime('now')
           ORDER BY start_time"""
    )
    return [dict(r) for r in rows]


async def get_active_events_by_type(event_type: str) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT * FROM events
           WHERE active = 1 AND event_type = ? AND end_time > datetime('now')""",
        (event_type,),
    )
    return [dict(r) for r in rows]


async def end_event(event_id: int):
    db = await get_db()
    await db.execute(
        "UPDATE events SET active = 0 WHERE id = ?", (event_id,)
    )
    await db.commit()


async def cleanup_expired_events():
    """Deactivate events past their end_time."""
    db = await get_db()
    await db.execute(
        "UPDATE events SET active = 0 WHERE active = 1 AND end_time <= datetime('now')"
    )
    await db.commit()


# ============================================================
# Dashboard / Stats Queries
# ============================================================

async def get_total_stats() -> dict:
    """Get overall bot statistics."""
    db = await get_db()
    users = await db.execute_fetchall("SELECT COUNT(*) FROM users")
    chats = await db.execute_fetchall("SELECT COUNT(*) FROM chat_rooms WHERE is_active = 1")
    total_spawns = await db.execute_fetchall("SELECT COUNT(*) FROM spawn_log")
    total_catches = await db.execute_fetchall(
        "SELECT COUNT(*) FROM spawn_log WHERE caught_by_user_id IS NOT NULL"
    )
    total_trades = await db.execute_fetchall(
        "SELECT COUNT(*) FROM trades WHERE status = 'accepted'"
    )
    return {
        "total_users": users[0][0] if users else 0,
        "total_chats": chats[0][0] if chats else 0,
        "total_spawns": total_spawns[0][0] if total_spawns else 0,
        "total_catches": total_catches[0][0] if total_catches else 0,
        "total_trades": total_trades[0][0] if total_trades else 0,
    }


async def get_today_stats() -> dict:
    """Get today's spawn/catch counts."""
    db = await get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    spawns = await db.execute_fetchall(
        "SELECT COUNT(*) FROM spawn_log WHERE spawned_at >= ?", (today,)
    )
    catches = await db.execute_fetchall(
        "SELECT COUNT(*) FROM spawn_log WHERE caught_by_user_id IS NOT NULL AND spawned_at >= ?",
        (today,),
    )
    return {
        "today_spawns": spawns[0][0] if spawns else 0,
        "today_catches": catches[0][0] if catches else 0,
    }


async def get_all_chat_rooms() -> list[dict]:
    """Get all chat rooms (active and inactive)."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT chat_id, chat_title, member_count, is_active,
                  joined_at, last_spawn_at, daily_spawn_count,
                  spawns_today_target, spawn_multiplier
           FROM chat_rooms ORDER BY joined_at DESC"""
    )
    return [dict(r) for r in rows]


async def get_top_pokemon_caught(limit: int = 10) -> list[dict]:
    """Get most caught Pokemon across all users."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT sl.pokemon_id, sl.pokemon_name, sl.pokemon_emoji, sl.rarity,
                  COUNT(*) as catch_count
           FROM spawn_log sl
           WHERE sl.caught_by_user_id IS NOT NULL
           GROUP BY sl.pokemon_id
           ORDER BY catch_count DESC
           LIMIT ?""",
        (limit,),
    )
    return [dict(r) for r in rows]


async def get_recent_spawns_global(limit: int = 50) -> list[dict]:
    """Get recent spawn logs across all chats."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT sl.*, cr.chat_title
           FROM spawn_log sl
           LEFT JOIN chat_rooms cr ON sl.chat_id = cr.chat_id
           ORDER BY sl.id DESC LIMIT ?""",
        (limit,),
    )
    return [dict(r) for r in rows]


async def get_user_rankings(limit: int = 20) -> list[dict]:
    """Get user rankings by pokedex count for dashboard."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT u.user_id, u.display_name, u.username,
                  u.title, u.title_emoji, u.last_active_at,
                  COUNT(p.pokemon_id) as pokedex_count
           FROM users u
           LEFT JOIN pokedex p ON u.user_id = p.user_id
           GROUP BY u.user_id
           HAVING pokedex_count > 0
           ORDER BY pokedex_count DESC
           LIMIT ?""",
        (limit,),
    )
    return [dict(r) for r in rows]


# ============================================================
# Title System
# ============================================================

async def get_user_titles(user_id: int) -> list[dict]:
    """Get all unlocked titles for a user."""
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT title_id, unlocked_at FROM user_titles WHERE user_id = ? ORDER BY unlocked_at",
        (user_id,),
    )
    return [dict(r) for r in rows]


async def has_title(user_id: int, title_id: str) -> bool:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT 1 FROM user_titles WHERE user_id = ? AND title_id = ?",
        (user_id, title_id),
    )
    return bool(rows)


async def unlock_title(user_id: int, title_id: str) -> bool:
    """Unlock a title. Returns True if newly unlocked."""
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR IGNORE INTO user_titles (user_id, title_id) VALUES (?, ?)",
            (user_id, title_id),
        )
        await db.commit()
        return True
    except Exception:
        return False


async def equip_title(user_id: int, title: str, emoji: str):
    """Set the user's equipped title."""
    db = await get_db()
    await db.execute(
        "UPDATE users SET title = ?, title_emoji = ? WHERE user_id = ?",
        (title, emoji, user_id),
    )
    await db.commit()


async def ensure_title_stats(user_id: int):
    """Ensure user_title_stats row exists."""
    db = await get_db()
    await db.execute(
        "INSERT OR IGNORE INTO user_title_stats (user_id) VALUES (?)",
        (user_id,),
    )
    await db.commit()


async def get_title_stats(user_id: int) -> dict:
    """Get title stats for unlock condition checks."""
    db = await get_db()
    await ensure_title_stats(user_id)
    rows = await db.execute_fetchall(
        "SELECT * FROM user_title_stats WHERE user_id = ?",
        (user_id,),
    )
    return dict(rows[0]) if rows else {}


async def increment_title_stat(user_id: int, stat: str, amount: int = 1):
    """Increment a stat in user_title_stats."""
    db = await get_db()
    await ensure_title_stats(user_id)
    valid_stats = {"catch_fail_count", "midnight_catch_count", "master_ball_used", "love_count"}
    if stat not in valid_stats:
        return
    await db.execute(
        f"UPDATE user_title_stats SET {stat} = {stat} + ? WHERE user_id = ?",
        (amount, user_id),
    )
    await db.commit()


async def update_login_streak(user_id: int):
    """Update login streak. Call on any user activity."""
    db = await get_db()
    await ensure_title_stats(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    stats = await get_title_stats(user_id)
    last_date = stats.get("last_active_date")

    if last_date == today:
        return

    if last_date:
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        new_streak = (stats.get("login_streak", 0) + 1) if last_date == yesterday else 1
    else:
        new_streak = 1

    await db.execute(
        "UPDATE user_title_stats SET login_streak = ?, last_active_date = ? WHERE user_id = ?",
        (new_streak, today, user_id),
    )
    await db.commit()


async def count_total_catches(user_id: int) -> int:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT COUNT(*) FROM spawn_log WHERE caught_by_user_id = ?",
        (user_id,),
    )
    return rows[0][0] if rows else 0


async def count_common_catches(user_id: int) -> int:
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT COUNT(*) FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.user_id = ? AND pm.rarity = 'common' AND up.is_active = 1""",
        (user_id,),
    )
    return rows[0][0] if rows else 0


async def count_rare_epic_legendary(user_id: int) -> int:
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT COUNT(*) FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.user_id = ? AND pm.rarity IN ('epic', 'legendary') AND up.is_active = 1""",
        (user_id,),
    )
    return rows[0][0] if rows else 0


async def count_completed_trades(user_id: int) -> int:
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT COUNT(*) FROM trades
           WHERE (from_user_id = ? OR to_user_id = ?) AND status = 'accepted'""",
        (user_id, user_id),
    )
    return rows[0][0] if rows else 0


# ============================================================
# Fun KPI Queries (Dashboard)
# ============================================================

async def get_rare_pokemon_holders(limit: int = 20) -> list[dict]:
    """에픽+전설 보유자 랭킹 — 보유 수 기준."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT u.display_name, u.title, u.title_emoji,
                  SUM(CASE WHEN pm.rarity = 'epic' THEN 1 ELSE 0 END) as epic_count,
                  SUM(CASE WHEN pm.rarity = 'legendary' THEN 1 ELSE 0 END) as legendary_count,
                  COUNT(*) as total
           FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           JOIN users u ON up.user_id = u.user_id
           WHERE pm.rarity IN ('epic', 'legendary') AND up.is_active = 1
           GROUP BY up.user_id
           ORDER BY legendary_count DESC, epic_count DESC
           LIMIT ?""",
        (limit,),
    )
    return [dict(r) for r in rows]


async def get_global_catch_rate() -> float:
    """전체 포획률 (%)."""
    db = await get_db()
    total = await db.execute_fetchall("SELECT COUNT(*) FROM spawn_log")
    caught = await db.execute_fetchall(
        "SELECT COUNT(*) FROM spawn_log WHERE caught_by_user_id IS NOT NULL"
    )
    t = total[0][0] if total else 0
    c = caught[0][0] if caught else 0
    return round(c / t * 100, 1) if t > 0 else 0.0


async def get_escape_masters(limit: int = 5) -> list[dict]:
    """도망 장인 TOP N — 잡기 실패 많은 유저."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT u.display_name, ts.catch_fail_count
           FROM user_title_stats ts
           JOIN users u ON ts.user_id = u.user_id
           WHERE ts.catch_fail_count > 0
           ORDER BY ts.catch_fail_count DESC
           LIMIT ?""",
        (limit,),
    )
    return [dict(r) for r in rows]


async def get_night_owls(limit: int = 5) -> list[dict]:
    """올빼미족 TOP N — 심야 포획 많은 유저."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT u.display_name, ts.midnight_catch_count
           FROM user_title_stats ts
           JOIN users u ON ts.user_id = u.user_id
           WHERE ts.midnight_catch_count > 0
           ORDER BY ts.midnight_catch_count DESC
           LIMIT ?""",
        (limit,),
    )
    return [dict(r) for r in rows]


async def get_masterball_rich(limit: int = 5) -> list[dict]:
    """마볼 부자 TOP N."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT display_name, master_balls
           FROM users
           WHERE master_balls > 0
           ORDER BY master_balls DESC
           LIMIT ?""",
        (limit,),
    )
    return [dict(r) for r in rows]


async def get_pokeball_addicts(limit: int = 5) -> list[dict]:
    """포볼 중독자 TOP N — 오늘 보너스 캐치 많은 유저."""
    db = await get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    rows = await db.execute_fetchall(
        """SELECT u.display_name, cl.bonus_catches
           FROM catch_limits cl
           JOIN users u ON cl.user_id = u.user_id
           WHERE cl.date = ? AND cl.bonus_catches > 0
           ORDER BY cl.bonus_catches DESC
           LIMIT ?""",
        (today, limit),
    )
    return [dict(r) for r in rows]


async def get_user_catch_rates(limit: int = 10) -> list[dict]:
    """개인 포획률 — 시도 대비 성공률 (최소 5회 이상 시도)."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT u.display_name,
                  COUNT(*) as attempts,
                  SUM(CASE WHEN sl.caught_by_user_id = ca.user_id THEN 1 ELSE 0 END) as catches,
                  ROUND(
                      CAST(SUM(CASE WHEN sl.caught_by_user_id = ca.user_id THEN 1 ELSE 0 END) AS REAL)
                      / COUNT(*) * 100, 1
                  ) as catch_rate
           FROM catch_attempts ca
           JOIN spawn_sessions ss ON ca.session_id = ss.id
           JOIN spawn_log sl ON sl.chat_id = ss.chat_id
               AND sl.pokemon_id = ss.pokemon_id
               AND sl.spawned_at >= ss.spawned_at
               AND sl.spawned_at <= COALESCE(ss.expires_at, datetime(ss.spawned_at, '+5 minutes'))
           JOIN users u ON ca.user_id = u.user_id
           GROUP BY ca.user_id
           HAVING attempts >= 5
           ORDER BY catch_rate DESC
           LIMIT ?""",
        (limit,),
    )
    return [dict(r) for r in rows]


async def get_trade_kings(limit: int = 5) -> list[dict]:
    """교환왕 TOP N."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT u.display_name, COUNT(*) as trade_count
           FROM (
               SELECT from_user_id as uid FROM trades WHERE status = 'accepted'
               UNION ALL
               SELECT to_user_id as uid FROM trades WHERE status = 'accepted'
           ) t
           JOIN users u ON t.uid = u.user_id
           GROUP BY t.uid
           ORDER BY trade_count DESC
           LIMIT ?""",
        (limit,),
    )
    return [dict(r) for r in rows]


async def get_most_escaped_pokemon(limit: int = 5) -> list[dict]:
    """도망 많은 포켓몬 TOP N."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT pokemon_name, pokemon_emoji, rarity,
                  COUNT(*) as escape_count
           FROM spawn_log
           WHERE caught_by_user_id IS NULL
           GROUP BY pokemon_id
           ORDER BY escape_count DESC
           LIMIT ?""",
        (limit,),
    )
    return [dict(r) for r in rows]


async def get_love_leaders(limit: int = 5) -> list[dict]:
    """사랑꾼 TOP N — love_count 높은 유저."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT u.display_name, ts.love_count
           FROM user_title_stats ts
           JOIN users u ON ts.user_id = u.user_id
           WHERE ts.love_count > 0
           ORDER BY ts.love_count DESC
           LIMIT ?""",
        (limit,),
    )
    return [dict(r) for r in rows]


async def get_total_master_balls_used() -> int:
    """총 마스터볼 사용량."""
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT COUNT(*) FROM catch_attempts WHERE used_master_ball = 1"
    )
    return rows[0][0] if rows else 0


async def get_longest_streak_user() -> dict | None:
    """최장 연속출석 유저."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT u.display_name, ts.login_streak
           FROM user_title_stats ts
           JOIN users u ON ts.user_id = u.user_id
           WHERE ts.login_streak > 0
           ORDER BY ts.login_streak DESC
           LIMIT 1"""
    )
    return dict(rows[0]) if rows else None
