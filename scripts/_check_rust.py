import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()

async def main():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"), statement_cache_size=0)

    rows = await conn.fetch("SELECT user_id, display_name, username FROM users WHERE display_name ILIKE '%러스트%' OR display_name ILIKE '%rust%' OR username ILIKE '%rust%' LIMIT 5")
    print("rust users:")
    for r in rows:
        uid = r['user_id']
        print(f"  {uid} | {r['display_name']} | @{r['username']}")

        cd = await conn.fetchrow("SELECT * FROM camp_shiny_cooldown WHERE user_id = $1", uid)
        if cd:
            print(f"    cooldown: {cd['last_convert_at']}")

        pend = await conn.fetch("SELECT * FROM camp_shiny_pending WHERE user_id = $1", uid)
        print(f"    pending: {len(pend)}")
        for p in pend:
            print(f"      {dict(p)}")

        # recently converted shiny pokemon
        shinies = await conn.fetch("SELECT id, pokemon_id, is_shiny FROM user_pokemon WHERE user_id = $1 AND is_shiny = 1 ORDER BY id DESC LIMIT 5", uid)
        print(f"    recent shinies: {len(shinies)}")
        for s in shinies:
            print(f"      id={s['id']} pokemon={s['pokemon_id']}")

    await conn.close()

asyncio.run(main())
