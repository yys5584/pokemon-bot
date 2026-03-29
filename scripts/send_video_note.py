"""동영상 노트로 슬롯 데모 전송."""
import asyncio
from telegram import Bot

BOT_TOKEN = "8616848852:AAEEboGyiQ9vUq_8NpzPxlzZEWF0jhNr7iU"
ADMIN_ID = 1832746512

async def main():
    bot = Bot(BOT_TOKEN)
    with open("scripts/slot_demo.mp4", "rb") as f:
        await bot.send_video_note(
            chat_id=ADMIN_ID,
            video_note=f,
            length=480,
            duration=8,
        )
    print("Sent!")

asyncio.run(main())
