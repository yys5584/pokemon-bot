"""Check shiny Phantom spawn and master ball usage."""
import asyncio, asyncpg, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

async def check():
    pool = await asyncpg.create_pool(os.getenv("DATABASE_URL"), statement_cache_size=0)

    # Find shiny Phantom spawns
    rows = await pool.fetch(
        "SELECT ss.id, ss.chat_id, ss.is_resolved, ss.is_shiny, ss.caught_by_user_id, ss.spawned_at, pm.name_ko "
        "FROM spawn_sessions ss JOIN pokemon_master pm ON ss.pokemon_id = pm.id "
        "WHERE pm.name_ko = '팬텀' AND ss.is_shiny = 1 ORDER BY ss.spawned_at DESC LIMIT 5"
    )
    print(f"Found {len(rows)} shiny Phantom spawns\n")
    for r in rows:
        print(f"Session {r['id']}: resolved={r['is_resolved']} caught_by={r['caught_by_user_id']} time={r['spawned_at']}")
        attempts = await pool.fetch(
            "SELECT user_id, display_name, used_master_ball, attempted_at FROM catch_attempts WHERE session_id = $1", r['id']
        )
        if attempts:
            for a in attempts:
                print(f"  -> {a['display_name']} (id={a['user_id']}) master={a['used_master_ball']} at {a['attempted_at']}")
        else:
            print("  -> No attempts")
        print()

    await pool.close()

asyncio.run(check())
