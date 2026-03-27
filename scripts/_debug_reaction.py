"""reaction_ms 디버그."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

async def main():
    from database.connection import get_db
    pool = await get_db()

    # spawn_sessions의 spawned_at 확인
    rows = await pool.fetch("SELECT * FROM spawn_sessions ORDER BY spawned_at DESC LIMIT 3")
    for r in rows:
        print(f"session {r['id']}: spawned_at={r['spawned_at']} chat_id={r['chat_id']}")

    # record_reaction이 실제로 UPDATE를 시도했을 때 매칭되는 행이 있는지
    # 최근 catch_attempt 하나 골라서 수동 UPDATE 테스트
    ca = await pool.fetchrow("SELECT session_id, user_id FROM catch_attempts ORDER BY attempted_at DESC LIMIT 1")
    if ca:
        result = await pool.execute(
            "UPDATE catch_attempts SET reaction_ms = 9999 WHERE session_id = $1 AND user_id = $2",
            ca['session_id'], ca['user_id']
        )
        print(f"\nUPDATE 결과: {result} (session_id={ca['session_id']}, user_id={ca['user_id']})")

        # 확인
        check = await pool.fetchval(
            "SELECT reaction_ms FROM catch_attempts WHERE session_id = $1 AND user_id = $2",
            ca['session_id'], ca['user_id']
        )
        print(f"reaction_ms 값: {check}")

        # 원래대로 복구
        await pool.execute(
            "UPDATE catch_attempts SET reaction_ms = NULL WHERE session_id = $1 AND user_id = $2",
            ca['session_id'], ca['user_id']
        )
        print("복구 완료")

asyncio.run(main())
