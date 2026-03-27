import asyncio, asyncpg, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

async def main():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"), statement_cache_size=0)
    row = await conn.fetchrow("SELECT season_id, weekly_rule FROM seasons ORDER BY starts_at DESC LIMIT 1")
    if row:
        print(f"현재: {row['season_id']} rule={row['weekly_rule']}")
        await conn.execute("UPDATE seasons SET weekly_rule = $1 WHERE season_id = $2", "cost_12", row["season_id"])
        verify = await conn.fetchrow("SELECT season_id, weekly_rule FROM seasons WHERE season_id = $1", row["season_id"])
        print(f"변경 후: {verify['season_id']} rule={verify['weekly_rule']}")
    await conn.close()

asyncio.run(main())
