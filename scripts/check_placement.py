import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()

async def main():
    pool = await asyncpg.create_pool(os.getenv("DATABASE_URL"), min_size=1, max_size=2, statement_cache_size=0)
    s = await pool.fetchrow("SELECT * FROM seasons ORDER BY created_at DESC LIMIT 1")
    sid = s["season_id"]
    print(f"Season: {sid}")
    rows = await pool.fetch(
        "SELECT user_id, rp, tier, placement_done, placement_games, ranked_wins, ranked_losses "
        "FROM season_records WHERE season_id = $1 ORDER BY rp DESC LIMIT 15", sid)
    for r in rows:
        uid = r["user_id"]
        rp = r["rp"]
        tier = r["tier"]
        pd = r["placement_done"]
        pg = r["placement_games"]
        w = r["ranked_wins"]
        l = r["ranked_losses"]
        print(f"  uid={uid} rp={rp} tier={tier} pd={pd} pg={pg} w={w} l={l}")
    total = await pool.fetchval("SELECT COUNT(*) FROM season_records WHERE season_id = $1", sid)
    placed = await pool.fetchval("SELECT COUNT(*) FROM season_records WHERE season_id = $1 AND placement_done = TRUE", sid)
    unplaced = await pool.fetchval("SELECT COUNT(*) FROM season_records WHERE season_id = $1 AND placement_done = FALSE", sid)
    print(f"Total: {total}, placed: {placed}, unplaced: {unplaced}")
    await pool.close()

asyncio.run(main())
