"""Check 오쿠 user catches."""
import asyncio
from database.connection import get_db, close_db


async def check():
    pool = await get_db()
    rows = await pool.fetch(
        "SELECT user_id, display_name, username FROM users "
        "WHERE display_name ILIKE '%오쿠%'"
    )
    for r in rows:
        uid = r["user_id"]
        cnt = await pool.fetchval(
            "SELECT COUNT(*) FROM catch_attempts WHERE user_id = $1 "
            "AND attempted_at > NOW() - interval '1 hour'", uid
        )
        cnt24 = await pool.fetchval(
            "SELECT COUNT(*) FROM catch_attempts WHERE user_id = $1 "
            "AND attempted_at > NOW() - interval '24 hours'", uid
        )
        # check abuse_scores
        score = await pool.fetchrow(
            "SELECT bot_score, total_challenges, challenge_passes, challenge_fails "
            "FROM abuse_scores WHERE user_id = $1", uid
        )
        print(f"{r['display_name']} (@{r['username']}) uid={uid}")
        print(f"  catches: 1h={cnt}, 24h={cnt24}")
        if score:
            print(f"  abuse: score={float(score['bot_score']):.3f} ch={score['total_challenges']} P={score['challenge_passes']} F={score['challenge_fails']}")
    await close_db()

asyncio.run(check())
