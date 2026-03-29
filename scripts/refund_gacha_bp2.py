"""2차 가챠 환불 — battle_stats 버그 영향 유저 BP 환불 + DM."""
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

    # 버그 배포(10:03 UTC) ~ 수정 배포(10:12 UTC) 사이 가챠 기록
    rows = await pool.fetch(
        "SELECT user_id, COUNT(*) as cnt, SUM(bp_spent) as total_bp "
        "FROM gacha_log "
        "WHERE created_at >= timestamp '2026-03-14 10:03:00+00' "
        "  AND created_at < timestamp '2026-03-14 10:12:00+00' "
        "GROUP BY user_id"
    )

    total = sum(dict(r)["total_bp"] for r in rows)
    print(f"Affected: {len(rows)} users, Total BP: {total}")

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
                    f"🔔 뽑기 시스템 오류 보상 안내\n\n"
                    f"뽑기 BP 환급/잭팟 보상 오류로 불편을 드려 죄송합니다.\n"
                    f"사용하신 {bp} BP를 환불해드렸습니다.\n"
                    f"(아이템 보상은 정상 지급되어 있습니다!)"
                ),
            )
            print(f"OK uid={uid} pulls={r['cnt']} refund={bp}BP DM_sent")
        except Exception as e:
            print(f"OK uid={uid} pulls={r['cnt']} refund={bp}BP DM_fail={e}")


asyncio.run(main())
