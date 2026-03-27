import asyncio, os
from dotenv import load_dotenv
load_dotenv()
from telegram import Bot

async def main():
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    await bot.send_message(
        chat_id=994493300,
        text=(
            "🎉 이로치 전환 완료 안내\n\n"
            "시스템 개선 패치로 대기 중이던 펄기아가 즉시 이로치로 전환 처리되었습니다.\n\n"
            "✨ 전환 완료: 펄기아 (S급, IV 177)\n\n"
            "내포켓몬에서 확인해보세요!"
        )
    )
    print("sent")

asyncio.run(main())
