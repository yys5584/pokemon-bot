"""Check evo chain data for branch evolution Pokemon."""
import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
from database.connection import get_db

async def check():
    pool = await get_db()
    for pid in [281, 282, 475, 361, 362, 478]:
        r = await pool.fetchrow("SELECT id, name_ko, evolves_from, evolves_to FROM pokemon_master WHERE id = $1", pid)
        if r:
            print(f"#{r['id']} {r['name_ko']} from={r['evolves_from']} to={r['evolves_to']}")

asyncio.run(check())
