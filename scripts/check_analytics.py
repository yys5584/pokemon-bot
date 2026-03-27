"""Check web_analytics table status."""
import asyncio, asyncpg, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

async def check():
    pool = await asyncpg.create_pool(os.getenv("DATABASE_URL"), statement_cache_size=0)

    exists = await pool.fetchval(
        "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='web_analytics')"
    )
    print(f"Table exists: {exists}")

    if exists:
        count = await pool.fetchval("SELECT COUNT(*) FROM web_analytics")
        print(f"Total rows: {count}")

        pv_count = await pool.fetchval(
            "SELECT COUNT(*) FROM web_analytics WHERE event_type='pageview'"
        )
        sess_count = await pool.fetchval(
            "SELECT COUNT(*) FROM web_analytics WHERE event_type='session'"
        )
        print(f"  pageviews: {pv_count}, sessions: {sess_count}")

        recent = await pool.fetch(
            "SELECT event_type, page, user_id, duration_sec, created_at "
            "FROM web_analytics ORDER BY id DESC LIMIT 10"
        )
        if recent:
            print("\nRecent 10 rows:")
            for r in recent:
                print(f"  {r['event_type']:10} | page={r['page'] or '-':12} | user={r['user_id'] or 'anon':>12} | dur={r['duration_sec'] or 0:>4}s | {r['created_at']}")
        else:
            print("\nNo data found!")
    else:
        print("Table does not exist!")

    await pool.close()

asyncio.run(check())
