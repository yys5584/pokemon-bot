import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()

async def main():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"), statement_cache_size=0)

    rows = await conn.fetch("""
        SELECT id, pokemon_id, is_shiny, iv_atk, iv_def, iv_spd,
               iv_atk + iv_def + iv_spd as total_iv
        FROM user_pokemon
        WHERE user_id = 7437353379 AND pokemon_id = 484
        ORDER BY id DESC
    """)
    for r in rows:
        grade = "S" if r["total_iv"] >= 27 else "A" if r["total_iv"] >= 21 else "B" if r["total_iv"] >= 15 else "C"
        print(f"id={r['id']} iv={r['total_iv']} ({r['iv_atk']}/{r['iv_def']}/{r['iv_spd']}) grade={grade} shiny={r['is_shiny']}")

    await conn.close()

asyncio.run(main())
