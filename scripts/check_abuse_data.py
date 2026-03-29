"""Check abuse detection system data."""
import asyncio
from database.connection import get_db, close_db


async def check():
    pool = await get_db()

    scores = await pool.fetch("SELECT count(*) as cnt FROM abuse_scores")
    print(f"abuse_scores count: {scores[0]['cnt']}")

    flagged = await pool.fetch(
        "SELECT user_id, bot_score FROM abuse_scores "
        "WHERE bot_score >= 0.3 ORDER BY bot_score DESC LIMIT 10"
    )
    for r in flagged:
        print(f"  flagged: uid={r['user_id']} score={float(r['bot_score']):.3f}")

    reactions = await pool.fetch(
        "SELECT count(*) as total FROM catch_attempts "
        "WHERE reaction_ms IS NOT NULL AND attempted_at > NOW() - interval '1 day'"
    )
    print(f"reactions with ms (24h): {reactions[0]['total']}")

    no_ms = await pool.fetch(
        "SELECT count(*) as total FROM catch_attempts "
        "WHERE reaction_ms IS NULL AND attempted_at > NOW() - interval '1 day'"
    )
    print(f"reactions WITHOUT ms (24h): {no_ms[0]['total']}")

    fast = await pool.fetch(
        "SELECT user_id, count(*) as cnt FROM catch_attempts "
        "WHERE reaction_ms < 2000 AND reaction_ms IS NOT NULL "
        "AND attempted_at > NOW() - interval '7 days' "
        "GROUP BY user_id ORDER BY cnt DESC LIMIT 15"
    )
    print(f"\nFast catchers (<2s, 7 days):")
    for r in fast:
        print(f"  uid={r['user_id']} count={r['cnt']}")

    vfast = await pool.fetch(
        "SELECT user_id, count(*) as cnt FROM catch_attempts "
        "WHERE reaction_ms < 1000 AND reaction_ms IS NOT NULL "
        "AND attempted_at > NOW() - interval '7 days' "
        "GROUP BY user_id ORDER BY cnt DESC LIMIT 15"
    )
    print(f"\nVery fast catchers (<1s, 7 days):")
    for r in vfast:
        print(f"  uid={r['user_id']} count={r['cnt']}")

    ch = await pool.fetch("SELECT count(*) as cnt FROM catch_challenges")
    print(f"\nchallenges total: {ch[0]['cnt']}")

    # Check spawned_at availability
    spawn_check = await pool.fetch(
        "SELECT count(*) as total, "
        "count(CASE WHEN spawned_at IS NOT NULL THEN 1 END) as with_spawned "
        "FROM spawn_sessions WHERE created_at > NOW() - interval '1 day'"
    )
    print(f"\nspawn_sessions (24h): total={spawn_check[0]['total']}, with_spawned_at={spawn_check[0]['with_spawned']}")

    await close_db()


asyncio.run(check())
