"""이로치 리자드 마스터볼 사용자 조회."""
import asyncio, os
from dotenv import load_dotenv
load_dotenv()

async def main():
    from database.connection import get_db
    pool = await get_db()
    rows = await pool.fetch("""
        SELECT ca.user_id, u.username, ca.used_master_ball, ca.used_hyper_ball, ca.attempted_at
        FROM catch_attempts ca
        JOIN spawn_sessions ss ON ca.session_id = ss.id
        JOIN users u ON u.user_id = ca.user_id
        WHERE ss.pokemon_id = 5 AND ss.is_shiny = 1
        AND ss.spawned_at > NOW() - INTERVAL '30 minutes'
        ORDER BY ca.attempted_at ASC
    """)
    for r in rows:
        print(f"uid={r['user_id']} @{r['username']} master={r['used_master_ball']} hyper={r['used_hyper_ball']} at={r['attempted_at']}")

asyncio.run(main())
