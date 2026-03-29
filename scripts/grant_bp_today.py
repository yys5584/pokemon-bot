"""오늘 접속한 모든 유저에게 BP 500 지급 + DM."""
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

    # 오늘(KST 3/14 00:00 = UTC 3/13 15:00) 이후 접속한 유저
    rows = await pool.fetch(
        "SELECT user_id FROM users "
        "WHERE last_active_at >= timestamp '2026-03-13 15:00:00+00'"
    )

    print(f"Today active users: {len(rows)}")
    bp = 500
    sent = 0
    fail = 0

    for r in rows:
        uid = r["user_id"]
        await pool.execute(
            "UPDATE users SET battle_points = battle_points + $1 WHERE user_id = $2",
            bp, uid,
        )
        try:
            await bot.send_message(
                chat_id=uid,
                text=(
                    f"🎁 긴급 점검 보상 안내\n\n"
                    f"오늘 뽑기/스폰 시스템 오류로 불편을 드려 죄송합니다.\n"
                    f"보상으로 {bp} BP를 지급해드렸습니다!\n\n"
                    f"앞으로 더 안정적인 서비스를 제공하겠습니다. 감사합니다 🙏"
                ),
            )
            sent += 1
        except Exception:
            fail += 1

    print(f"Done. BP granted: {len(rows)} users, DM sent: {sent}, DM fail: {fail}")


asyncio.run(main())
