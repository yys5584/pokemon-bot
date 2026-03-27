import asyncio, os
from dotenv import load_dotenv
load_dotenv()
from telegram import Bot

async def main():
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    await bot.send_message(
        chat_id=2104756708,
        text=(
            "🎉 이로치 전환 완료 안내\n\n"
            "이전 시스템 버그로 조각은 소모되었으나 전환이 되지 않았던 버섯모가 이로치로 전환 처리되었습니다.\n\n"
            "✨ 전환 완료: 버섯모\n\n"
            "내포켓몬에서 확인해보세요!"
        )
    )
    print("sent")

asyncio.run(main())
