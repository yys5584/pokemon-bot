"""4시간 이내 접속자에게 포획볼 정책 변경 DM 발송."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.update({
    k: v for k, v in (
        line.strip().split("=", 1)
        for line in open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
        if "=" in line and not line.startswith("#")
    )
})

import asyncpg
from telegram import Bot

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# 커스텀 이모지
MASTERBALL = '<tg-emoji emoji-id="6143130859210807699">🟣</tg-emoji>'
HYPERBALL = '<tg-emoji emoji-id="6142944354550946803">🔵</tg-emoji>'
PRIORITY = "🎯"

MESSAGE = (
    f"⚾ <b>포획볼 정책 변경 안내</b>\n"
    f"\n"
    f"{MASTERBALL} 마스터볼, {HYPERBALL} 하이퍼볼, {PRIORITY} 우선포획볼 모두\n"
    f"<b>던지는 순간 소멸</b>됩니다.\n"
    f"\n"
    f"❌ 포획 실패해도 환불 없음\n"
    f"❌ 다른 사람에게 져도 환불 없음\n"
    f"❌ 뉴비 스폰에서도 환불 없음\n"
    f"\n"
    f"신중하게 던져주세요! {PRIORITY}"
)


async def main():
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    bot = Bot(token=BOT_TOKEN)

    # 4시간 이내 접속자
    rows = await conn.fetch(
        "SELECT user_id, display_name FROM users "
        "WHERE last_active_at >= NOW() - INTERVAL '4 hours'"
    )
    print(f"대상 유저: {len(rows)}명")

    success = 0
    fail = 0
    for r in rows:
        uid = r["user_id"]
        name = r["display_name"]
        try:
            await bot.send_message(chat_id=uid, text=MESSAGE, parse_mode="HTML")
            success += 1
            print(f"  ✅ {name} ({uid})")
        except Exception as e:
            fail += 1
            print(f"  ❌ {name} ({uid}): {e}")
        await asyncio.sleep(0.1)  # rate limit

    print(f"\n완료: 성공 {success}, 실패 {fail}")
    await conn.close()


asyncio.run(main())
