"""Backfill NULL personality for active pokemon."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
    import asyncpg
    from utils.battle_calc import generate_personality, personality_to_str

    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres.ycaxgpnxfyumejlriymk:p2ULvy4fwyjFNaRN@aws-1-ap-northeast-1.pooler.supabase.com:6543/postgres",
    )
    pool = await asyncpg.create_pool(db_url, statement_cache_size=0)

    rows = await pool.fetch(
        "SELECT id, is_shiny FROM user_pokemon WHERE personality IS NULL AND is_active = 1"
    )
    print(f"Found {len(rows)} NULL personality pokemon to fix")

    for r in rows:
        is_shiny = bool(r["is_shiny"])
        pers = generate_personality(is_shiny=is_shiny)
        pers_str = personality_to_str(pers)
        await pool.execute(
            "UPDATE user_pokemon SET personality = $1 WHERE id = $2",
            pers_str, r["id"],
        )

    remaining = await pool.fetchval(
        "SELECT COUNT(*) FROM user_pokemon WHERE personality IS NULL AND is_active = 1"
    )
    print(f"Done! Remaining NULL: {remaining}")
    await pool.close()

if __name__ == "__main__":
    asyncio.run(main())
