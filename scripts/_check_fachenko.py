import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()

async def main():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"), statement_cache_size=0)

    rows = await conn.fetch("SELECT user_id, display_name, username FROM users WHERE display_name ILIKE '%fachenko%' OR username ILIKE '%fachenko%' LIMIT 5")
    print("fachenko users:")
    for r in rows:
        uid = r['user_id']
        print(f"  {uid} | {r['display_name']} | @{r['username']}")

        # 버섯모 = pokemon_id 285 (shroomish) or 286 (breloom)
        pokes = await conn.fetch("SELECT id, pokemon_id, is_shiny FROM user_pokemon WHERE user_id = $1 AND pokemon_id IN (285, 286) ORDER BY id DESC", uid)
        print(f"  shroomish/breloom:")
        for p in pokes:
            print(f"    id={p['id']} pokemon={p['pokemon_id']} shiny={p['is_shiny']}")

        cd = await conn.fetchrow("SELECT * FROM camp_shiny_cooldown WHERE user_id = $1", uid)
        if cd:
            print(f"  cooldown: {cd['last_convert_at']}")

    await conn.close()

asyncio.run(main())
