import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()

async def main():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"), statement_cache_size=0)

    # 1) find convert/shiny columns
    q1 = "SELECT table_name, column_name FROM information_schema.columns WHERE column_name LIKE '%convert%' OR column_name LIKE '%shiny%'"
    for r in await conn.fetch(q1):
        print(r["table_name"], "|", r["column_name"])

    # 2) camp tables
    q2 = "SELECT table_name FROM information_schema.tables WHERE table_name LIKE '%camp%'"
    print("camp tables:", [r["table_name"] for r in await conn.fetch(q2)])

    # 3) camp_shiny_pending
    try:
        rows = await conn.fetch("SELECT * FROM camp_shiny_pending ORDER BY started_at DESC LIMIT 20")
        print(f"\npending: {len(rows)} rows")
        for r in rows:
            print(dict(r))
    except Exception as e:
        print(f"pending error: {e}")

    # 4) check camp_placements for convert info
    q3 = "SELECT column_name FROM information_schema.columns WHERE table_name='camp_placements' ORDER BY ordinal_position"
    cols = await conn.fetch(q3)
    print("\ncamp_placements columns:", [r["column_name"] for r in cols])

    # 5) recent shiny converts from camp_placements if last_convert_at exists
    try:
        rows = await conn.fetch("""
            SELECT cp.user_id, u.first_name, cp.last_convert_at AT TIME ZONE 'Asia/Seoul' as kst, cp.last_convert_rarity
            FROM camp_placements cp JOIN users u ON cp.user_id = u.user_id
            WHERE cp.last_convert_at IS NOT NULL AND cp.last_convert_at > NOW() - INTERVAL '7 days'
            ORDER BY cp.last_convert_at DESC
        """)
        print(f"\nrecent converts: {len(rows)}")
        for r in rows:
            print(r["first_name"], "|", r["user_id"], "|", r["kst"], "|", r["last_convert_rarity"])
    except Exception as e:
        print(f"placements query error: {e}")

    await conn.close()

asyncio.run(main())
