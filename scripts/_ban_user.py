import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
import asyncpg

async def main():
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL'], statement_cache_size=0)

    # Find user
    row = await pool.fetchrow("SELECT user_id, username, display_name FROM users WHERE username = 'guestiong'")
    if not row:
        print("User not found!")
        return

    uid = row['user_id']
    print(f"Found: uid={uid} username={row['username']} name={row['display_name']}")

    # Check columns
    cols = await pool.fetch("SELECT column_name FROM information_schema.columns WHERE table_name='users' ORDER BY ordinal_position")
    col_names = [c['column_name'] for c in cols]
    print(f"Users columns: {col_names}")

    await pool.close()

asyncio.run(main())
