import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()

async def main():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"), statement_cache_size=0)

    rows = await conn.fetch("SELECT user_id, display_name, username FROM users WHERE username ILIKE '%yul_pa%' LIMIT 5")
    for r in rows:
        uid = r['user_id']
        print(f"{uid} | {r['display_name']} | @{r['username']}")

        # palkia 484, IV S급 (177/186)
        pokes = await conn.fetch("""
            SELECT id, pokemon_id, is_shiny, iv_atk, iv_def, iv_spd,
                   iv_atk + iv_def + iv_spd as total
            FROM user_pokemon WHERE user_id = $1 AND pokemon_id = 484
            ORDER BY id DESC
        """, uid)
        for p in pokes:
            print(f"  id={p['id']} shiny={p['is_shiny']} iv={p['iv_atk']}/{p['iv_def']}/{p['iv_spd']} total={p['total']}")

        # cooldown
        cd = await conn.fetchrow("SELECT * FROM camp_shiny_cooldown WHERE user_id = $1", uid)
        if cd:
            print(f"  cooldown: {cd['last_convert_at']}")

        # pending
        pend = await conn.fetch("SELECT * FROM camp_shiny_pending WHERE user_id = $1", uid)
        print(f"  pending: {len(pend)}")
        for p in pend:
            print(f"    {dict(p)}")

    await conn.close()

asyncio.run(main())
