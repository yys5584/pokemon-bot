"""관리자에게 테스트 캡차 DM 발송."""
import asyncio
import dotenv
dotenv.load_dotenv()

import os
import config
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from services.abuse_service import create_challenge

ADMIN_ID = config.ADMIN_IDS[0]


async def main():
    bot = Bot(token=os.getenv("BOT_TOKEN"))

    # 테스트용 챌린지 생성 (피카츄)
    challenge = create_challenge(ADMIN_ID, session_id=0, pokemon_name="피카츄")
    choices = challenge["choices"]

    buttons = []
    for name in choices:
        buttons.append([InlineKeyboardButton(name, callback_data=f"captcha_{ADMIN_ID}_{name}")])

    text = (
        "⚠️ <b>캡차 테스트</b>\n\n"
        "이 포켓몬의 이름은?\n"
        "🔒 정답: 피카츄\n\n"
        "아래에서 올바른 이름을 선택하세요!"
    )

    await bot.send_message(
        chat_id=ADMIN_ID,
        text=text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
    )
    print(f"Captcha sent to admin {ADMIN_ID}")


asyncio.run(main())
