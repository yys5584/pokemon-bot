import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()

async def main():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"), statement_cache_size=0)

    rows = await conn.fetch("SELECT id, user_id, instance_id, pokemon_id, rarity FROM camp_shiny_pending WHERE NOT completed")
    print(f"pending: {len(rows)}")
    for r in rows:
        print(f"  id={r['id']} user={r['user_id']} inst={r['instance_id']} pokemon={r['pokemon_id']} rarity={r['rarity']}")

    for r in rows:
        await conn.execute("UPDATE camp_shiny_pending SET completed = TRUE WHERE id = $1", r["id"])
        await conn.execute("UPDATE user_pokemon SET is_shiny = 1 WHERE id = $1", r["instance_id"])
        print(f"  -> done id={r['id']}")

    remaining = await conn.fetchval("SELECT count(*) FROM camp_shiny_pending WHERE NOT completed")
    print(f"remaining: {remaining}")

    await conn.close()

asyncio.run(main())
