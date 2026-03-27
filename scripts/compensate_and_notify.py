"""Compensate bug-affected users + give shiny Chansey + send DM notifications."""
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from database.connection import get_db
from database.queries import give_pokemon_to_user, register_pokedex

# Already compensated pokemon (from previous script run) — per user
ALREADY_GIVEN = {
    7437353379: [  # @Keepgoingthat
        "플라이곤", "팬텀", "아라리", "파비코리", "로젤리아",
        "메탕", "셀러", "크로뱃", "강철톤", "세레비", "라티아스",
    ],
    6795306901: ["도나리", "헤라크로스"],       # @Y_THEBEST
    8176389709: ["헤라크로스", "주뱃"],         # @artechowl
    8383046826: ["레지락"],                     # @Cu_ling
    5672156380: ["레지락"],                     # @NoGongju
}

# Shiny Chansey compensation (bot restart killed the session)
SHINY_CHANSEY_USERS = [
    (506304557, "coinhanna"),       # @coinhanna
    (7437353379, "Keepgoingthat"),   # @Keepgoingthat
]

CHANSEY_ID = 113


async def main():
    pool = await get_db()

    # 1) Give shiny Chansey
    for uid, uname in SHINY_CHANSEY_USERS:
        instance_id, ivs = await give_pokemon_to_user(uid, CHANSEY_ID, is_shiny=True)
        try:
            await register_pokedex(uid, CHANSEY_ID, "catch")
        except Exception:
            pass
        print(f"[SHINY] @{uname} <- shiny Chansey instance={instance_id}")

        # Add to notification list
        if uid not in ALREADY_GIVEN:
            ALREADY_GIVEN[uid] = []
        ALREADY_GIVEN[uid].append("★이로치 럭키")

    # 2) Send DM to all compensated users
    import aiohttp
    token = os.environ["BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    # Get display names
    usernames = {}
    for uid in ALREADY_GIVEN:
        row = await pool.fetchrow("SELECT display_name, username FROM users WHERE user_id = $1", uid)
        if row:
            usernames[uid] = row["username"] or row["display_name"]

    async with aiohttp.ClientSession() as session:
        for uid, pokemon_list in ALREADY_GIVEN.items():
            poke_lines = "\n".join(f"  - {name}" for name in pokemon_list)
            text = (
                f"📦 서버 점검 보상 안내\n\n"
                f"점검 중 포획에 실패한 포켓몬을 지급해드렸습니다.\n\n"
                f"🎁 지급 목록:\n{poke_lines}\n\n"
                f"DM에서 '내포켓몬'으로 확인해주세요!"
            )
            try:
                async with session.post(url, json={
                    "chat_id": uid,
                    "text": text,
                }) as resp:
                    status = resp.status
                    if status == 200:
                        print(f"[DM OK] @{usernames.get(uid, uid)} ({len(pokemon_list)} pokemon)")
                    else:
                        body = await resp.text()
                        print(f"[DM FAIL] @{usernames.get(uid, uid)} status={status} {body}")
            except Exception as e:
                print(f"[DM ERR] @{usernames.get(uid, uid)} {e}")
            await asyncio.sleep(0.1)

    print("\nAll done!")


if __name__ == "__main__":
    asyncio.run(main())
