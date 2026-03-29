"""Compensate users who used hyper/master balls during failed_ids bug.
Give the pokemon they tried to catch to the first special-ball user in each session.
"""
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from database.connection import get_db
from database.queries import give_pokemon_to_user, register_pokedex

# Sessions where hyper/master ball was used (from analysis)
# Format: (session_id, pokemon_id, name_ko, user_id, username, ball_type)
COMPENSATIONS = [
    (103871, 330, "Keepgoingthat", 7437353379, "HYPER"),   # 플라이곤 epic
    (103875, 94, "Keepgoingthat", 7437353379, "HYPER"),    # 팬텀 epic
    (103876, 298, "Keepgoingthat", 7437353379, "HYPER"),   # 아라리 - keepgoing used hyper
    (103877, 334, "Keepgoingthat", 7437353379, "HYPER"),   # 파비코리 rare
    (103878, 315, "Keepgoingthat", 7437353379, "HYPER"),   # 로젤리아 rare
    (103881, 269, "Y_THEBEST", 6795306901, "HYPER"),       # 도나리 rare
    (103885, 374, "Keepgoingthat", 7437353379, "HYPER"),   # 메탕 common
    (103887, 90, "Keepgoingthat", 7437353379, "HYPER"),    # 셀러 common
    (103889, 169, "Keepgoingthat", 7437353379, "HYPER"),   # 크로뱃 epic
    (103891, 214, "Y_THEBEST", 6795306901, "HYPER"),       # 헤라크로스 epic (holysouling=poke, Y=hyper first)
    (103891, 214, "artechowl", 8176389709, "HYPER"),       # 헤라크로스 epic (artechowl also hyper)
    (103894, 208, "Keepgoingthat", 7437353379, "HYPER"),   # 강철톤 epic
    (103895, 251, "Keepgoingthat", 7437353379, "HYPER"),   # 세레비 legendary
    (103896, 380, "Keepgoingthat", 7437353379, "HYPER"),   # 라티아스 legendary
    (103901, 377, "Cu_ling", 8383046826, "HYPER"),         # 레지락 legendary
    (103901, 377, "NoGongju", 5672156380, "HYPER"),        # 레지락 legendary (both hyper)
    (103903, 41, "artechowl", 8176389709, "HYPER"),        # 주뱃 common
]


async def main():
    pool = await get_db()

    # Verify pokemon IDs from DB
    for sid, pid, uname, uid, ball in COMPENSATIONS:
        session = await pool.fetchrow(
            "SELECT pokemon_id, pm.name_ko FROM spawn_sessions ss "
            "JOIN pokemon_master pm ON pm.id = ss.pokemon_id WHERE ss.id = $1", sid
        )
        if not session:
            print(f"[SKIP] Session {sid} not found")
            continue

        actual_pid = session["pokemon_id"]
        name = session["name_ko"]

        instance_id, ivs = await give_pokemon_to_user(uid, actual_pid, is_shiny=False)
        try:
            await register_pokedex(uid, actual_pid, "catch")
        except Exception:
            pass  # already registered

        print(f"[OK] @{uname} (id={uid}) <- {name} (pid={actual_pid}) instance={instance_id} [{ball}]")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
