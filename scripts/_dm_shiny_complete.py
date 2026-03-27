import asyncio, os
from dotenv import load_dotenv
load_dotenv()

from telegram import Bot

BOT_TOKEN = os.getenv("BOT_TOKEN")

USERS = {
    5151475366: ["터검니", "야미라미"],
    7437353379: ["번치코", "꾸꾸리", "이브이"],
    6007036282: ["아르세우스"],
}

async def main():
    bot = Bot(token=BOT_TOKEN)
    for uid, names in USERS.items():
        poke_list = ", ".join(names)
        text = (
            f"🎉 이로치 전환 완료 안내\n\n"
            f"시스템 개선 패치로 인해 대기 중이던 이로치 전환이 즉시 완료 처리되었습니다.\n\n"
            f"✨ 전환 완료: {poke_list}\n\n"
            f"내포켓몬에서 확인해보세요!"
        )
        try:
            await bot.send_message(chat_id=uid, text=text)
            print(f"sent to {uid}")
        except Exception as e:
            print(f"failed {uid}: {e}")

asyncio.run(main())
