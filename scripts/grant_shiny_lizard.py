"""이로치 리자드 보상 지급 + DM 전송."""
import asyncio, os
from dotenv import load_dotenv
load_dotenv()

TARGET_USER = 8008546708
POKEMON_ID = 5  # 리자드

async def main():
    from database.connection import get_db
    from database import queries
    import random

    pool = await get_db()

    # 포켓몬 지급 (IV 자동 생성)
    instance_id, ivs = await queries.give_pokemon_to_user(
        user_id=TARGET_USER,
        pokemon_id=POKEMON_ID,
        is_shiny=True,
    )
    print(f"Granted shiny 리자드 to {TARGET_USER}, instance_id={instance_id}")

    # 마스터볼 환불 (재시작으로 소모됨)
    await pool.execute(
        "UPDATE users SET master_balls = master_balls + 1 WHERE user_id = $1",
        TARGET_USER,
    )
    print(f"Refunded 1 masterball to {TARGET_USER}")

    # 나머지 3명 마스터볼 환불
    others = [8176389709, 7050637391, 1658538640]
    for uid in others:
        await pool.execute(
            "UPDATE users SET master_balls = master_balls + 1 WHERE user_id = $1",
            uid,
        )
        print(f"Refunded 1 masterball to {uid}")

    # DM 전송
    from telegram import Bot
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    async with bot:
        # 당첨자 DM
        await bot.send_message(
            chat_id=TARGET_USER,
            text="🎁 서버 점검 중 유실된 ✨이로치 리자드가 보상 지급되었습니다!\n마스터볼도 1개 환불되었습니다. 불편을 드려 죄송합니다 🙏",
        )
        print(f"DM sent to {TARGET_USER}")

        # 나머지 마볼 환불 DM
        for uid in others:
            try:
                await bot.send_message(
                    chat_id=uid,
                    text="🎁 서버 점검으로 인해 마스터볼이 1개 환불되었습니다. 불편을 드려 죄송합니다 🙏",
                )
                print(f"DM sent to {uid}")
            except Exception as e:
                print(f"DM failed for {uid}: {e}")

asyncio.run(main())
