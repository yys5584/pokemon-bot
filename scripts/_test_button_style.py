"""Telegram 버튼 스타일 테스트 — style + icon_custom_emoji_id."""
import asyncio, os, json
from dotenv import load_dotenv
load_dotenv()

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

ADMIN_ID = 1832746512

async def main():
    bot = Bot(token=os.getenv("BOT_TOKEN"))

    # 1) 색상 버튼 테스트 (Bot API 9.4+)
    # python-telegram-bot이 style 파라미터를 지원하는지 확인
    try:
        # 직접 API 호출로 테스트
        import httpx
        token = os.getenv("BOT_TOKEN")
        url = f"https://api.telegram.org/bot{token}/sendMessage"

        payload = {
            "chat_id": ADMIN_ID,
            "text": "🎨 버튼 스타일 테스트\n\n빨강(danger), 파랑(primary), 초록(success)",
            "reply_markup": json.dumps({
                "inline_keyboard": [
                    [
                        {"text": "🔴 위험 (danger)", "callback_data": "test_danger", "style": "danger"},
                        {"text": "🔵 기본 (primary)", "callback_data": "test_primary", "style": "primary"},
                    ],
                    [
                        {"text": "🟢 성공 (success)", "callback_data": "test_success", "style": "success"},
                        {"text": "⬜ 기본 (없음)", "callback_data": "test_default"},
                    ],
                ]
            })
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            if data.get("ok"):
                print("sent! check telegram")
            else:
                print(f"error: {data}")

    except Exception as e:
        print(f"error: {e}")

asyncio.run(main())
