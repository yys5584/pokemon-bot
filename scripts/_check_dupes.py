import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
from database.connection import get_db

async def main():
    pool = await get_db()
    rows = await pool.fetch(
        "SELECT id, user_id, pokemon_id, is_shiny FROM user_pokemon WHERE id BETWEEN 144921 AND 144931 ORDER BY id"
    )
    for r in rows:
        print(f"inst={r['id']} uid={r['user_id']} pid={r['pokemon_id']} shiny={r['is_shiny']}")
asyncio.run(main())
