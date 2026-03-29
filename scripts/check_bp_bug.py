import asyncio
import asyncpg
import sys
sys.stdout.reconfigure(encoding='utf-8')

async def main():
    dsn = None
    with open(".env") as f:
        for line in f:
            if line.startswith("DATABASE_URL="):
                dsn = line.strip().split("=", 1)[1]
                break
    conn = await asyncpg.connect(dsn, statement_cache_size=0)

    # Check last 3 days
    for days_ago in range(4):
        rows = await conn.fetch(f"""
            SELECT caught_by_user_id, caught_by_name, COUNT(*) as catches
            FROM spawn_log
            WHERE caught_by_user_id IS NOT NULL
            AND spawned_at >= ((NOW() AT TIME ZONE 'Asia/Seoul')::date - {days_ago}) AT TIME ZONE 'Asia/Seoul'
            AND spawned_at < ((NOW() AT TIME ZONE 'Asia/Seoul')::date - {days_ago} + 1) AT TIME ZONE 'Asia/Seoul'
            GROUP BY caught_by_user_id, caught_by_name
            HAVING COUNT(*) >= 80
            ORDER BY catches DESC LIMIT 10
        """)
        if rows:
            print(f"\n=== {days_ago} days ago (80+ catches) ===")
            for r in rows:
                uid = r['caught_by_user_id']
                bp_count = await conn.fetchval(f"""
                    SELECT COUNT(*) FROM bp_log WHERE user_id = {uid} AND source = 'catch'
                    AND created_at >= ((NOW() AT TIME ZONE 'Asia/Seoul')::date - {days_ago}) AT TIME ZONE 'Asia/Seoul'
                    AND created_at < ((NOW() AT TIME ZONE 'Asia/Seoul')::date - {days_ago} + 1) AT TIME ZONE 'Asia/Seoul'
                """)
                flag = " *** OVER LIMIT" if r['catches'] > 100 and bp_count > 100 else ""
                print(f"  {r['caught_by_name']}: catches={r['catches']}, bp_rewards={bp_count}{flag}")

    await conn.close()

asyncio.run(main())
