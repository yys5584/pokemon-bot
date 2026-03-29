"""Check lastmoney64 abuse data."""
import asyncio
from database.connection import get_db, close_db


async def check():
    pool = await get_db()

    user = await pool.fetchrow(
        "SELECT user_id, display_name, username FROM users WHERE username ILIKE '%lastmoney%'"
    )
    if not user:
        print("User not found")
        await close_db()
        return

    uid = user["user_id"]
    print(f"User: {user['display_name']} (@{user['username']}) id={uid}")

    score = await pool.fetchrow("SELECT * FROM abuse_scores WHERE user_id = $1", uid)
    if score:
        print(f"bot_score={float(score['bot_score']):.3f}, total_challenges={score['total_challenges']}, passes={score['challenge_passes']}, fails={score['challenge_fails']}")
        print(f"last_challenge_at={score['last_challenge_at']}, last_flagged_at={score['last_flagged_at']}")
    else:
        print("No abuse_scores record")

    catches = await pool.fetch(
        "SELECT count(*) as cnt FROM catch_attempts WHERE user_id = $1 AND attempted_at > NOW() - interval '24 hours'",
        uid,
    )
    print(f"Catches (24h): {catches[0]['cnt']}")

    fast = await pool.fetch(
        "SELECT reaction_ms FROM catch_attempts WHERE user_id = $1 AND reaction_ms IS NOT NULL "
        "AND attempted_at > NOW() - interval '24 hours' ORDER BY attempted_at DESC LIMIT 20",
        uid,
    )
    if fast:
        times = [r["reaction_ms"] for r in fast]
        print(f"Recent reaction_ms: {times}")

    # Check pokeball count
    balls = await pool.fetchrow(
        "SELECT pokeballs, hyper_balls, master_balls FROM users WHERE user_id = $1", uid
    )
    if balls:
        print(f"Pokeballs={balls['pokeballs']}, Hyper={balls['hyper_balls']}, Master={balls['master_balls']}")

    # Count total pokemon
    poke_count = await pool.fetchval(
        "SELECT COUNT(*) FROM user_pokemon WHERE user_id = $1 AND is_active = 1", uid
    )
    print(f"Pokemon owned: {poke_count}")

    await close_db()


asyncio.run(check())
