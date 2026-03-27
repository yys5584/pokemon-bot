import asyncio
from telegram import Bot

BOT_TOKEN = "8616848852:AAEEboGyiQ9vUq_8NpzPxlzZEWF0jhNr7iU"
ADMIN_ID = 1832746512

async def main():
    bot = Bot(BOT_TOKEN)
    with open("scripts/slot_test.mp4", "rb") as f:
        await bot.send_animation(
            chat_id=ADMIN_ID,
            animation=f,
            caption="<b>JACKPOT test</b> (Playwright v2)\n\nBlack Han Sans + Orbitron + light rays + particles",
            parse_mode="HTML",
            width=500, height=400,
        )
    print("Sent!")

asyncio.run(main())
