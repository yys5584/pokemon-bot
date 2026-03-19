"""Daily mission database queries."""

import logging
from database.connection import get_db

logger = logging.getLogger(__name__)


# ============================================================
# Daily Missions
# ============================================================

async def get_daily_missions(user_id: int, date: str) -> list[dict]:
    """Get today's missions for a user. Returns empty list if none."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT mission_key, target, progress, completed,
                  reward_claimed, all_clear_claimed
           FROM daily_missions
           WHERE user_id = $1 AND mission_date = $2
           ORDER BY id""",
        user_id, date,
    )
    return [dict(r) for r in rows]


async def create_daily_missions(user_id: int, date: str, missions: list[dict]):
    """Batch insert daily missions. missions = [{"key": ..., "target": ...}]."""
    pool = await get_db()
    for m in missions:
        await pool.execute(
            """INSERT INTO daily_missions (user_id, mission_date, mission_key, target)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (user_id, mission_date, mission_key) DO NOTHING""",
            user_id, date, m["key"], m["target"],
        )


async def increment_mission_progress(
    user_id: int, date: str, mission_key: str,
) -> dict | None:
    """Increment progress by 1. Returns status dict or None if mission not found."""
    pool = await get_db()
    row = await pool.fetchrow(
        """UPDATE daily_missions
           SET progress = LEAST(progress + 1, target)
           WHERE user_id = $1 AND mission_date = $2 AND mission_key = $3
             AND completed = FALSE
           RETURNING progress, target""",
        user_id, date, mission_key,
    )
    if not row:
        return None  # 미션이 없거나 이미 완료됨

    completed_now = row["progress"] >= row["target"]
    if completed_now:
        await pool.execute(
            """UPDATE daily_missions SET completed = TRUE
               WHERE user_id = $1 AND mission_date = $2 AND mission_key = $3""",
            user_id, date, mission_key,
        )

    # 전체 완료 체크
    remaining = await pool.fetchval(
        """SELECT COUNT(*) FROM daily_missions
           WHERE user_id = $1 AND mission_date = $2 AND completed = FALSE""",
        user_id, date,
    )
    return {
        "completed_now": completed_now,
        "progress": row["progress"],
        "target": row["target"],
        "all_done": remaining == 0,
    }


async def claim_mission_reward(user_id: int, date: str, mission_key: str) -> bool:
    """Mark individual mission reward as claimed."""
    pool = await get_db()
    result = await pool.execute(
        """UPDATE daily_missions SET reward_claimed = TRUE
           WHERE user_id = $1 AND mission_date = $2 AND mission_key = $3
             AND reward_claimed = FALSE""",
        user_id, date, mission_key,
    )
    return "UPDATE 1" in result


async def claim_allclear_reward(user_id: int, date: str) -> bool:
    """Mark all-clear reward as claimed (on first row only)."""
    pool = await get_db()
    # 이미 수령했는지 체크
    already = await pool.fetchval(
        """SELECT COUNT(*) FROM daily_missions
           WHERE user_id = $1 AND mission_date = $2 AND all_clear_claimed = TRUE""",
        user_id, date,
    )
    if already > 0:
        return False
    # 첫 행에 표시
    await pool.execute(
        """UPDATE daily_missions SET all_clear_claimed = TRUE
           WHERE id = (
               SELECT id FROM daily_missions
               WHERE user_id = $1 AND mission_date = $2
               ORDER BY id LIMIT 1
           )""",
        user_id, date,
    )
    return True


async def cleanup_old_missions(days: int = 7):
    """Delete missions older than N days."""
    import datetime as _dt
    import zoneinfo as _zi
    pool = await get_db()
    cutoff = (
        _dt.datetime.now(_zi.ZoneInfo("Asia/Seoul")) - _dt.timedelta(days=days)
    ).strftime("%Y-%m-%d")
    await pool.execute(
        "DELETE FROM daily_missions WHERE mission_date < $1", cutoff,
    )
