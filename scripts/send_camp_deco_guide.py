"""Send 캠꾸(캠프꾸미기) guide DM to all camp owners."""

import asyncio
import os
import sys
import aiohttp
import asyncpg
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DATABASE_URL = os.getenv("DATABASE_URL")
BOT_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_ID = 1832746512


def ce(eid, fallback=""):
    return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'


# Icons
game = ce("6143111020756868297", "🎮")
check = ce("6143254176311811828", "✅")
pokecenter = ce("6142954550803307680", "🏥")
footsteps = ce("6143075514262233319", "👣")
bookmark = ce("6143229132357509310", "📖")
crystal = ce("6143120589944004477", "💎")

MESSAGE = (
    f"{game} <b>🏕️ 캠프 꾸미기 기능 안내</b>\n"
    f"\n"
    f"안녕하세요, 캠프 소유자님!\n"
    f"캠프를 꾸밀 수 있는 <b>캠꾸</b> 기능이 추가되었습니다.\n"
    f"\n"
    f"{footsteps} <b>환영 메시지 설정</b>\n"
    f"  {check} 다른 유저가 <b>방문</b> 시 표시되는 메시지\n"
    f"  {check} 최대 100자까지 자유롭게 작성\n"
    f"  {check} 캠프의 개성을 보여주세요!\n"
    f"\n"
    f"{crystal} <b>방문 시스템</b>\n"
    f"  {check} 다른 캠프 유저가 '방문'으로 조각 획득\n"
    f"  {check} 캠프 레벨이 높을수록 더 많은 조각!\n"
    f"  {check} 환영 메시지로 방문자를 맞이하세요\n"
    f"\n"
    f"{bookmark} <b>설정 방법</b>\n"
    f"  1. DM에서 <b>내캠프</b> 입력\n"
    f"  2. <b>⚙️ 캠프 관리</b> 버튼 클릭\n"
    f"  3. <b>✏️ 환영 메시지 수정</b>으로 작성\n"
    f"\n"
    f"{pokecenter} <i>문의: @moon_ys_yu</i>"
)


async def send_message(session, bot_token, chat_id, text):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    async with session.post(url, json=payload) as resp:
        return await resp.json()


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "preview"

    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2,
                                     statement_cache_size=0)

    # Get unique camp owners
    rows = await pool.fetch(
        "SELECT DISTINCT created_by FROM camps WHERE created_by IS NOT NULL"
    )
    owner_ids = [r["created_by"] for r in rows]
    print(f"[INFO] 캠프 소유자 {len(owner_ids)}명")

    if mode == "preview":
        print(f"[PREVIEW] Sending to admin {ADMIN_ID}...")
        async with aiohttp.ClientSession() as session:
            result = await send_message(session, BOT_TOKEN, ADMIN_ID, MESSAGE)
            if result.get("ok"):
                print("[OK] Preview sent!")
            else:
                print(f"[FAIL] {result}")
        await pool.close()
        return

    if mode == "send":
        sent, failed = 0, 0
        async with aiohttp.ClientSession() as session:
            for uid in owner_ids:
                try:
                    result = await send_message(session, BOT_TOKEN, uid, MESSAGE)
                    if result.get("ok"):
                        sent += 1
                        print(f"  [OK] {uid}")
                    else:
                        failed += 1
                        desc = result.get("description", "")
                        print(f"  [WARN] {uid}: {desc}")
                except Exception as e:
                    failed += 1
                    print(f"  [ERR] {uid}: {e}")
                await asyncio.sleep(0.05)

        print(f"[DONE] sent={sent}, failed={failed}")
        await pool.close()
        return

    print("Usage: python send_camp_deco_guide.py [preview|send]")
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
