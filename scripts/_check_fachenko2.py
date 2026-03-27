import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()

async def main():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"), statement_cache_size=0)
    uid = 2104756708

    rows = await conn.fetch("""
        SELECT id, pokemon_id, is_shiny, iv_atk, iv_def, iv_spd,
               iv_atk + iv_def + iv_spd as total_iv
        FROM user_pokemon WHERE user_id = $1 AND pokemon_id IN (285, 286)
        ORDER BY id DESC
    """, uid)
    for r in rows:
        print(f"id={r['id']} pokemon={r['pokemon_id']} shiny={r['is_shiny']} iv={r['iv_atk']}/{r['iv_def']}/{r['iv_spd']} total={r['total_iv']}")

    await conn.close()

asyncio.run(main())
