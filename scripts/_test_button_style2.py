"""api_kwargs로 style 전달 테스트."""
import asyncio, os
from dotenv import load_dotenv
load_dotenv()
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

ADMIN_ID = 1832746512

async def main():
    bot = Bot(token=os.getenv("BOT_TOKEN"))

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚔️ 다음 층", callback_data="test1", api_kwargs={"style": "primary"}),
            InlineKeyboardButton("🏳️ 포기", callback_data="test2", api_kwargs={"style": "danger"}),
        ],
        [
            InlineKeyboardButton("💚 부활권 사용", callback_data="test3", api_kwargs={"style": "success"}),
            InlineKeyboardButton("➡️ 지나가기", callback_data="test4"),
        ],
    ])

    await bot.send_message(
        chat_id=ADMIN_ID,
        text="🏰 던전 버튼 스타일 테스트\n\napi_kwargs로 style 전달",
        reply_markup=keyboard,
    )
    print("sent!")

asyncio.run(main())
