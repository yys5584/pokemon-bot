"""Send dungeon v2.8 patch notice to admin DM only (preview)."""
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from utils.helpers import icon_emoji

CASTLE = icon_emoji("container")
SKILL = icon_emoji("skill")
COIN = icon_emoji("coin")
CRYSTAL = icon_emoji("crystal")
CROWN = icon_emoji("crown")
BOLT = icon_emoji("bolt")
FOOT = icon_emoji("footsteps")

DM_TEXT = (
    f"{CASTLE} <b>신규 컨텐츠: 던전</b>\n"
    f"\n"
    f"포켓몬 <b>1마리</b>로 도전하는 로그라이크\n"
    f"매 층 배틀 {SKILL} 승리 시 버프 선택\n"
    f"같은 버프를 뽑으면 레벨업!\n"
    f"\n"
    f"{COIN} <b>보상:</b> BP · 조각 · 결정 · IV스톤\n"
    f"\n"
    f"DM → <b>「던전」</b>"
)

ADMIN_ID = 1832746512


async def main():
    import aiohttp
    token = os.environ["BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json={
            "chat_id": ADMIN_ID,
            "text": DM_TEXT,
            "parse_mode": "HTML",
        }) as resp:
            result = await resp.json()
            if result.get("ok"):
                print("Sent to admin DM.")
            else:
                print(f"Failed: {result}")


if __name__ == "__main__":
    asyncio.run(main())
