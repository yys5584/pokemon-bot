"""Spawn / catch related database queries."""

import logging
from datetime import datetime, timedelta
from database.connection import get_db, _retry
import config as _cfg

logger = logging.getLogger(__name__)


# ============================================================
# Spawn Sessions
# ============================================================

async def create_spawn_session(
    chat_id: int, pokemon_id: int, expires_at, message_id: int | None = None,
    is_shiny: bool = False, is_newbie_spawn: bool = False,
    pre_ivs: dict | None = None, personality: str | None = None,
) -> int:
    async def _do():
        pool = await get_db()
        # Ensure expires_at is a datetime object for asyncpg
        if isinstance(expires_at, str):
            exp = datetime.fromisoformat(expires_at)
        else:
            exp = expires_at
        import json as _json
        _ivs_json = _json.dumps(pre_ivs) if pre_ivs else None
        row = await pool.fetchrow(
            """INSERT INTO spawn_sessions (chat_id, pokemon_id, expires_at, message_id, is_shiny, is_newbie_spawn, pre_ivs, personality)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id""",
            chat_id, pokemon_id, exp, message_id, 1 if is_shiny else 0, 1 if is_newbie_spawn else 0, _ivs_json, personality,
        )
        return row["id"]
    return await _retry(_do)


async def get_active_spawn(chat_id: int) -> dict | None:
    """Get the currently active (unresolved, not expired) spawn in a chat.
    Only SELECT — expired cleanup is handled by periodic jobs."""
    async def _do():
        pool = await get_db()
        row = await pool.fetchrow(
            """SELECT ss.*, pm.name_ko, pm.name_en, pm.emoji, pm.rarity, pm.catch_rate
               FROM spawn_sessions ss
               JOIN pokemon_master pm ON ss.pokemon_id = pm.id
               WHERE ss.chat_id = $1 AND ss.is_resolved = 0
               AND ss.expires_at >= NOW()
               ORDER BY ss.id DESC LIMIT 1""",
            chat_id,
        )
        return dict(row) if row else None
    return await _retry(_do)


async def get_spawn_session_by_id(session_id: int) -> dict | None:
    """Get spawn session by ID (for challenge verification)."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT * FROM spawn_sessions WHERE id = $1", session_id,
    )
    return dict(row) if row else None


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


async def cleanup_expired_sessions() -> list[tuple[int, str]]:
    """Resolve ALL unresolved sessions on startup (safety net for crashes).
    Returns list of (user_id, ball_type) for refunded balls.
    """
    pool = await get_db()
    # 미해결 세션에서 마볼/하이퍼볼 사용자 찾아서 환불 (배치 처리)
    refunds = await pool.fetch(
        """SELECT ca.user_id, ca.used_master_ball, ca.used_hyper_ball
           FROM catch_attempts ca
           JOIN spawn_sessions ss ON ca.session_id = ss.id
           WHERE ss.is_resolved = 0
             AND (ca.used_master_ball = 1 OR ca.used_hyper_ball = 1)"""
    )
    refunded = []
    for r in refunds:
        if r["used_master_ball"]:
            refunded.append((r["user_id"], "master"))
        if r["used_hyper_ball"]:
            refunded.append((r["user_id"], "hyper"))

    if refunded:
        # 배치 UPDATE: 마스터볼
        await pool.execute("""
            UPDATE users u SET master_balls = master_balls + sub.cnt
            FROM (
                SELECT ca.user_id, COUNT(*) as cnt
                FROM catch_attempts ca
                JOIN spawn_sessions ss ON ca.session_id = ss.id
                WHERE ss.is_resolved = 0 AND ca.used_master_ball = 1
                GROUP BY ca.user_id
            ) sub
            WHERE u.user_id = sub.user_id
        """)
        # 배치 UPDATE: 하이퍼볼
        await pool.execute("""
            UPDATE users u SET hyper_balls = hyper_balls + sub.cnt
            FROM (
                SELECT ca.user_id, COUNT(*) as cnt
                FROM catch_attempts ca
                JOIN spawn_sessions ss ON ca.session_id = ss.id
                WHERE ss.is_resolved = 0 AND ca.used_hyper_ball = 1
                GROUP BY ca.user_id
            ) sub
            WHERE u.user_id = sub.user_id
        """)
        logger.info(f"Refunded {len(refunded)} balls from {len(refunds)} unresolved attempts")

    await pool.execute(
        """UPDATE spawn_sessions
           SET is_resolved = 1
           WHERE is_resolved = 0"""
    )
    return refunded


# ============================================================
# Catch Attempts
# ============================================================

async def record_catch_attempt(session_id: int, user_id: int, used_master_ball: bool = False, used_hyper_ball: bool = False, used_priority_ball: bool = False):
    if used_priority_ball:
        import logging
        logging.getLogger(__name__).info(
            f"🎯 record_catch_attempt CALLED: session={session_id} user={user_id} "
            f"master={used_master_ball} hyper={used_hyper_ball} priority={used_priority_ball} "
            f"→ DB vals: $3={1 if used_master_ball else 0} $4={1 if used_hyper_ball else 0} $5={1 if used_priority_ball else 0}"
        )
    async def _do():
        pool = await get_db()
        await pool.execute(
            "INSERT INTO catch_attempts (session_id, user_id, used_master_ball, used_hyper_ball, used_priority_ball) "
            "VALUES ($1, $2, $3, $4, $5)",
            session_id, user_id, 1 if used_master_ball else 0, 1 if used_hyper_ball else 0, 1 if used_priority_ball else 0,
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
    """Reset catch attempts and bonus catches to 0 (shop pokeball reset)."""
    pool = await get_db()
    await pool.execute(
        "UPDATE catch_limits SET attempt_count = 0, bonus_catches = 0 WHERE user_id = $1 AND date = $2",
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


async def reset_daily_spawn_counts():
    """Reset daily spawn counts for all chat rooms."""
    pool = await get_db()
    await pool.execute("UPDATE chat_rooms SET daily_spawn_count = 0")


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
    participants: int, is_shiny: bool = False, personality: str | None = None,
):
    pool = await get_db()
    await pool.execute(
        """INSERT INTO spawn_log
           (chat_id, pokemon_id, pokemon_name, pokemon_emoji, rarity,
            caught_by_user_id, caught_by_name, participants, is_shiny, personality)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
        chat_id, pokemon_id, name, emoji, rarity,
        caught_by_id, caught_by_name, participants, 1 if is_shiny else 0, personality,
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


async def get_recent_catch_user_count(chat_id: int, minutes: int = 10) -> int:
    """최근 N분간 포획에 참여한 고유 유저 수 (포켓볼을 던진 유저)."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT COUNT(DISTINCT ca.user_id) as cnt
           FROM catch_attempts ca
           JOIN spawn_sessions ss ON ss.id = ca.session_id
           WHERE ss.chat_id = $1
             AND ca.attempted_at > NOW() - make_interval(mins => $2)""",
        chat_id, minutes,
    )
    return row["cnt"] if row else 0


async def get_recent_spawn_catch_rate(chat_id: int, limit: int = 10) -> tuple[int, int]:
    """최근 N회 스폰 중 포획된 수 반환. (caught, total)"""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT caught_by_user_id FROM spawn_sessions
           WHERE chat_id = $1 AND is_resolved = 1
           ORDER BY spawned_at DESC LIMIT $2""",
        chat_id, limit,
    )
    total = len(rows)
    caught = sum(1 for r in rows if r["caught_by_user_id"] is not None)
    return caught, total


async def cleanup_old_activity(days: int = 7):
    """Remove activity records older than N days."""
    pool = await get_db()
    cutoff = (_cfg.get_kst_now() - timedelta(days=days)).strftime("%Y-%m-%d-00")
    await pool.execute(
        "DELETE FROM chat_activity WHERE hour_bucket < $1", cutoff
    )


async def record_spawn_in_chat(chat_id: int):
    pool = await get_db()
    await pool.execute(
        """UPDATE chat_rooms
           SET last_spawn_at = NOW(), daily_spawn_count = daily_spawn_count + 1
           WHERE chat_id = $1""",
        chat_id,
    )
