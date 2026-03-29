"""수동 지급: S01 + S01.5 랭크전 미지급 보상 (이로치 + IV스톤) + 토너먼트 IV+3.

이미 지급된 마볼/BP는 건드리지 않음.
"""
import asyncio
import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from models.pokemon_data import ALL_POKEMON
from utils.battle_calc import generate_ivs


def random_shiny(rarity: str) -> tuple[int, str]:
    candidates = [(p[0], p[1]) for p in ALL_POKEMON if p[4] == rarity]
    return random.choice(candidates)


# === S01 보상 대상 ===
S01 = {
    "shiny_ultra_legendary": [7609021791],  # Turri
    "shiny_legendary": [7050637391, 1668479932],  # peterchat7, lastmoney64
    "shiny_epic": [5237146711],  # Mcu112
    "iv_stone_3_x2": [7285104306, 5151475366, 5672156380, 8176389709, 8383046826, 867186752],
    "iv_stone_3_x1": [6795306901, 5340105241, 499754576, 345868056, 8008546708, 1832746512,
                       871534626, 994493300, 336224560, 1658538640, 8047499352, 1386472342,
                       1794073008, 1597578165],
}

# === S01.5 보상 대상 ===
S015 = {
    "shiny_ultra_legendary": [345868056],  # occtru2
    "shiny_legendary": [7050637391, 7609021791],  # peterchat7, Turri
    "shiny_epic": [336224560, 6007036282, 7285104306, 1668479932],  # mc7979, holysouling, JJeerrry, lastmoney64
    "iv_stone_3_x2": [5672156380, 994493300, 5151475366, 1943690435, 6795306901, 8616523632],
    "iv_stone_3_x1": [8176389709, 2104756708, 1658538640, 867186752, 1787023873, 8047499352,
                       8383046826, 5237146711, 7538057108, 7044819211],
}


async def main():
    from database.connection import get_db
    from database.queries import give_pokemon_to_user
    from database.item_queries import add_user_item

    pool = await get_db()
    log_entries = []

    for season_label, data in [("S01", S01), ("S01.5", S015)]:
        print(f"\n=== {season_label} 보상 지급 ===")

        for rarity_key, rarity in [
            ("shiny_ultra_legendary", "ultra_legendary"),
            ("shiny_legendary", "legendary"),
            ("shiny_epic", "epic"),
        ]:
            for uid in data.get(rarity_key, []):
                pid, pname = random_shiny(rarity)
                instance_id, ivs = await give_pokemon_to_user(uid, pid, 0, is_shiny=True)
                msg = f"[이로치 {rarity}] uid={uid} → ✨{pname}(#{pid}) inst={instance_id}"
                print(f"  {msg}")
                log_entries.append(f"{season_label}: {msg}")

        for key, cnt in [("iv_stone_3_x2", 2), ("iv_stone_3_x1", 1)]:
            for uid in data.get(key, []):
                await add_user_item(uid, "iv_stone_3", cnt)
                msg = f"[IV+3 ×{cnt}] uid={uid}"
                print(f"  {msg}")
                log_entries.append(f"{season_label}: {msg}")

    # 토너먼트 IV+3 미지급
    print("\n=== 토너먼트 IV+3 미지급 보상 ===")
    for uid, label in [(7050637391, "우승 러스트"), (336224560, "준우승 Yohan")]:
        await add_user_item(uid, "iv_stone_3", 1)
        msg = f"[토너먼트 IV+3] {label} uid={uid}"
        print(f"  {msg}")
        log_entries.append(msg)

    # 로그 DB 저장
    for entry in log_entries:
        try:
            await pool.execute(
                "INSERT INTO admin_logs (action, detail, created_at) VALUES ('ranked_reward_manual', $1, NOW())",
                entry,
            )
        except Exception:
            pass  # admin_logs 테이블 없으면 스킵

    print(f"\n✅ 완료! 총 {len(log_entries)}건 지급")


if __name__ == "__main__":
    asyncio.run(main())
