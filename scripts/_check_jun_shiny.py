import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()

async def main():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"), statement_cache_size=0)

    # Jun's user_id = 7437353379 (from pending data)
    uid = 7437353379

    # check all shiny conversions for Jun - completed pendings
    pendings = await conn.fetch(
        "SELECT * FROM camp_shiny_pending WHERE user_id = $1 ORDER BY id", uid
    )
    print(f"Jun pendings: {len(pendings)}")
    for p in pendings:
        print(dict(p))

    # check Jun's pokemon for palkia (484)
    palkia = await conn.fetch(
        "SELECT id, pokemon_id, is_shiny, nickname FROM user_pokemon WHERE user_id = $1 AND pokemon_id = 484", uid
    )
    print(f"\nJun palkia: {len(palkia)}")
    for p in palkia:
        print(dict(p))

    # check old cooldown log - maybe Jun converted palkia before the new system
    cooldown = await conn.fetch(
        "SELECT * FROM camp_shiny_cooldown WHERE user_id = $1", uid
    )
    print(f"\nJun cooldown: {len(cooldown)}")
    for c in cooldown:
        print(dict(c))

    await conn.close()

asyncio.run(main())
