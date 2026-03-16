"""Manually bump abuse score for a user."""
import asyncio
import sys
from database.connection import get_db, close_db


async def bump(user_id: int, new_score: float):
    pool = await get_db()
    old = await pool.fetchval("SELECT bot_score FROM abuse_scores WHERE user_id = $1", user_id)
    await pool.execute(
        """INSERT INTO abuse_scores (user_id, bot_score, last_flagged_at, updated_at)
           VALUES ($1, $2, NOW(), NOW())
           ON CONFLICT (user_id) DO UPDATE
           SET bot_score = $2, last_flagged_at = NOW(), updated_at = NOW()""",
        user_id, new_score,
    )
    print(f"uid={user_id}: {float(old or 0):.3f} → {new_score:.3f}")
    await close_db()


if __name__ == "__main__":
    uid = int(sys.argv[1]) if len(sys.argv) > 1 else 1668479932
    score = float(sys.argv[2]) if len(sys.argv) > 2 else 0.95
    asyncio.run(bump(uid, score))
