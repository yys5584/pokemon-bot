"""활성 런 유저 던전 횟수 초기화."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

async def main():
    from database.connection import get_db
    pool = await get_db()

    uids = [8176389709, 1667292909, 345868056]
    for uid in uids:
        # 오늘 시작된 런을 어제로 이동 → 일일 횟수 초기화
        r = await pool.execute(
            "UPDATE dungeon_runs SET started_at = started_at - INTERVAL '1 day' "
            "WHERE user_id = $1 "
            "AND started_at >= date_trunc('day', NOW() AT TIME ZONE 'Asia/Seoul') "
            "AT TIME ZONE 'Asia/Seoul'",
            uid
        )
        print(f"  user {uid}: {r}")
    print("Done!")

asyncio.run(main())
