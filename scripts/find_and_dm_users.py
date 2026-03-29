"""Find registered tournament players by name and send them a DM to re-register."""
import asyncio
import asyncpg
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# Names from screenshots (partial matches)
SEARCH_NAMES = [
    "코인한나", "o_it", "인요리사", "젬하", "oney", "urri", "Moni",
    "이반짝짝", "문유", "크캣", "딸딸기", "ozea", "가운도쿄", "비밥",
    "배즙", "아크", "MGG", "USDT", "kumi", "dms", "우니", "arry", "oo",
]

DM_TEXT = (
    "🏟️ 토너먼트 재등록 안내\n\n"
    "서버 점검으로 등록이 초기화되었습니다.\n"
    "아래 채널에서 ㄷ 을 다시 입력해 주세요!\n\n"
    "👉 https://t.me/tg_poke"
)


async def main():
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)

    # Find user_ids
    found = {}
    for name in SEARCH_NAMES:
        rows = await conn.fetch(
            "SELECT user_id, display_name FROM users WHERE display_name ILIKE $1 LIMIT 3",
            f"%{name}%",
        )
        for r in rows:
            uid = r["user_id"]
            if uid not in found:
                found[uid] = r["display_name"]

    await conn.close()
    print(f"Found {len(found)} users:")
    for uid, dn in found.items():
        print(f"  {uid}: {dn}")

    # Send DMs via Bot API (form-data for reliability)
    sent = 0
    async with aiohttp.ClientSession() as session:
        for uid, dn in found.items():
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            data = aiohttp.FormData()
            data.add_field("chat_id", str(uid))
            data.add_field("text", DM_TEXT)
            try:
                async with session.post(url, data=data) as resp:
                    if resp.status == 200:
                        sent += 1
                        print(f"  DM sent to {dn} ({uid})")
                    else:
                        body = await resp.text()
                        print(f"  FAILED {dn} ({uid}): {resp.status} {body}")
            except Exception as e:
                print(f"  ERROR {dn} ({uid}): {e}")

    print(f"\nDone: {sent}/{len(found)} DMs sent")


asyncio.run(main())
