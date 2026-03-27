import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()

async def main():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"), statement_cache_size=0)

    rows = await conn.fetch("SELECT user_id, display_name, username FROM users WHERE display_name ILIKE '%revuildio%' OR username ILIKE '%revuildio%' LIMIT 5")
    for r in rows:
        uid = r['user_id']
        print(f"{uid} | {r['display_name']} | @{r['username']}")

        # 뿔카노 = 323 (camerupt)
        pokes = await conn.fetch("""
            SELECT id, pokemon_id, is_shiny, iv_atk, iv_def, iv_spd
            FROM user_pokemon WHERE user_id = $1 AND pokemon_id IN (322, 323)
            ORDER BY id DESC
        """, uid)
        print(f"  numel/camerupt: {len(pokes)}")
        for p in pokes:
            print(f"    id={p['id']} pokemon={p['pokemon_id']} shiny={p['is_shiny']} iv={p['iv_atk']}/{p['iv_def']}/{p['iv_spd']}")

    await conn.close()

asyncio.run(main())
