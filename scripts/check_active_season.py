import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()

async def main():
    pool = await asyncpg.create_pool(os.getenv("DATABASE_URL"), min_size=1, max_size=2, statement_cache_size=0)
    s = await pool.fetchrow("SELECT * FROM seasons WHERE NOW() BETWEEN starts_at AND ends_at ORDER BY id DESC LIMIT 1")
    if s:
        sid = s["season_id"]
        print(f"Active season: {sid}")
        rows = await pool.fetch(
            "SELECT user_id, rp, tier, placement_done, placement_games, ranked_wins, ranked_losses "
            "FROM season_records WHERE season_id = $1 ORDER BY rp DESC", sid)
        for r in rows:
            print(f"  uid={r['user_id']} rp={r['rp']} tier={r['tier']} pd={r['placement_done']} pg={r['placement_games']} w={r['ranked_wins']} l={r['ranked_losses']}")
        print(f"Total: {len(rows)}")
    else:
        print("No active season!")
    await pool.close()

asyncio.run(main())
