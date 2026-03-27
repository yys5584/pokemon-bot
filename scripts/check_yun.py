"""Check Yun's abuse data."""
import asyncio
from database.connection import get_db, close_db


async def check():
    pool = await get_db()
    rows = await pool.fetch(
        "SELECT u.user_id, u.display_name, u.username, a.bot_score, "
        "a.total_challenges, a.challenge_passes, a.challenge_fails "
        "FROM abuse_scores a JOIN users u ON a.user_id = u.user_id "
        "WHERE u.display_name ILIKE '%Yun%' OR u.username ILIKE '%yun%'"
    )
    for r in rows:
        uid = r["user_id"]
        print(f"uid={uid} name={r['display_name']} @{r['username']} "
              f"score={float(r['bot_score']):.3f} ch={r['total_challenges']} "
              f"pass={r['challenge_passes']} fail={r['challenge_fails']}")

        catches = await pool.fetchval(
            "SELECT COUNT(*) FROM catch_attempts WHERE user_id = $1 "
            "AND attempted_at > NOW() - interval '1 hour'", uid
        )
        catches_24h = await pool.fetchval(
            "SELECT COUNT(*) FROM catch_attempts WHERE user_id = $1 "
            "AND attempted_at > NOW() - interval '24 hours'", uid
        )
        print(f"  catches/1h: {catches}, catches/24h: {catches_24h}")

    await close_db()


asyncio.run(check())
