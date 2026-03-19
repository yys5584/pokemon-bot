"""Title system database queries."""

import logging
from datetime import timedelta
from database.connection import get_db
import config as _cfg

logger = logging.getLogger(__name__)


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
