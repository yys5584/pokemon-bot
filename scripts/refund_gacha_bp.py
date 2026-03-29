"""패치 중 뽑기 오류로 BP 환불 + DM 발송."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from database.connection import get_db
from telegram import Bot


async def main():
    pool = await get_db()
    bot = Bot(token=os.getenv("BOT_TOKEN"))

    rows = await pool.fetch(
        "SELECT user_id, COUNT(*) as cnt, SUM(bp_spent) as total_bp "
        "FROM gacha_log "
        "WHERE created_at >= timestamp '2026-03-14 09:49:00+00' "
        "GROUP BY user_id"
    )

    for r in rows:
        uid = r["user_id"]
        bp = r["total_bp"]
        await pool.execute(
            "UPDATE users SET battle_points = battle_points + $1 WHERE user_id = $2",
            bp, uid,
        )
        try:
            await bot.send_message(
                chat_id=uid,
                text=(
                    f"🔔 뽑기 시스템 점검 보상 안내\n\n"
                    f"패치 중 뽑기 오류로 불편을 드려 죄송합니다.\n"
                    f"사용하신 {bp} BP를 환불해드렸습니다.\n"
                    f"(보상은 정상 지급되어 있으니 아이템도 확인해주세요!)"
                ),
            )
            print(f"OK uid={uid} refund={bp}BP DM_sent")
        except Exception as e:
            print(f"OK uid={uid} refund={bp}BP DM_fail={e}")


asyncio.run(main())
