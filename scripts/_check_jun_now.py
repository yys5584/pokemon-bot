import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()

async def main():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"), statement_cache_size=0)
    uid = 7437353379

    # Jun's palkia status
    rows = await conn.fetch("""
        SELECT id, pokemon_id, is_shiny, iv_atk + iv_def + iv_spd as total_iv
        FROM user_pokemon WHERE user_id = $1 AND pokemon_id = 484 ORDER BY id DESC
    """, uid)
    print("Jun palkia:")
    for r in rows:
        print(f"  id={r['id']} shiny={r['is_shiny']} iv={r['total_iv']}")

    # Jun's pending
    pend = await conn.fetch("SELECT * FROM camp_shiny_pending WHERE user_id = $1 ORDER BY id DESC", uid)
    print(f"\nJun pending: {len(pend)}")
    for p in pend:
        print(f"  {dict(p)}")

    await conn.close()

asyncio.run(main())
