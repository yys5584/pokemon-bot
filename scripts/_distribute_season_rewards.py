"""시즌 1 & 1.5 보상 지급 + 개인 DM 발송."""
import asyncio
import os
import sys
import random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import asyncpg
import httpx

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = 1832746512

# 커스텀 이모지
E_BATTLE = '<tg-emoji emoji-id="6143344370625026850">⚔️</tg-emoji>'
E_CRYSTAL = '<tg-emoji emoji-id="6143120589944004477">💎</tg-emoji>'
E_CHECK = '<tg-emoji emoji-id="6143254176311811828">✅</tg-emoji>'

# 이로치 포켓몬 풀 (pokemon_id)
ULTRA_LEGENDARY_IDS = [150, 249, 250, 384, 483, 484, 487, 491]  # 뮤츠, 루기아, 호오, 레쿠자, 디아루가, 펄기아, 기라티나, 다크라이
LEGENDARY_IDS = [144, 145, 146, 243, 244, 245, 377, 378, 379, 380, 381, 480, 481, 482, 485, 486]  # 삼신조, 삼개, 레지, 라티, 호수삼총사, 히드런, 레지기가스
EPIC_IDS = [3, 6, 9, 59, 65, 68, 76, 94, 103, 112, 115, 127, 128, 130, 131, 134, 135, 136, 143, 149, 154, 157, 160, 169, 181, 196, 197, 212, 214, 217, 230, 232, 237, 241, 242, 248, 254, 257, 260, 275, 282, 289, 295, 306, 310, 319, 321, 323, 330, 332, 334, 344, 346, 348, 350, 354, 357, 359, 362, 365, 373, 376, 389, 392, 395, 398, 405, 407, 409, 411, 416, 423, 428, 430, 435, 437, 445, 448, 452, 454, 460, 461, 462, 463, 464, 465, 466, 467, 468, 469, 470, 471, 472, 473, 474, 475, 476, 477]

TIER_NAMES = {
    "bronze": "브론즈", "silver": "실버", "gold": "골드",
    "platinum": "플래티넘", "diamond": "다이아",
    "master": "마스터", "challenger": "챌린저",
}


def get_reward_info(rank, tier):
    """순위+티어 → (reward_type, reward_text)"""
    if rank == 1:
        pid = random.choice(ULTRA_LEGENDARY_IDS)
        return ("shiny_pokemon", pid, f"{E_CRYSTAL}이로치 초전설")
    elif rank <= 3:
        pid = random.choice(LEGENDARY_IDS)
        return ("shiny_pokemon", pid, f"{E_CRYSTAL}이로치 전설")
    elif tier in ("master", "challenger"):
        pid = random.choice(EPIC_IDS)
        return ("shiny_pokemon", pid, f"{E_CRYSTAL}이로치 에픽")
    elif tier == "diamond":
        return ("iv_stone", 2, "💎 IV+3 스톤 ×2")
    elif tier == "platinum":
        return ("iv_stone", 1, "💎 IV+3 스톤 ×1")
    return None


def build_reward_dm(display_name, seasons_rewards):
    lines = [
        f"{E_BATTLE} <b>{display_name}님, 시즌 보상 도착!</b>",
        "",
    ]
    for sr in seasons_rewards:
        season = sr["season"]
        rank = sr["rank"]
        tier_name = sr["tier_name"]
        reward_text = sr["reward_text"]

        if rank <= 3:
            medal = ["🥇", "🥈", "🥉"][rank - 1]
            rank_text = f"{medal} {rank}위"
        else:
            rank_text = tier_name

        lines.append(f"{E_CHECK} <b>{season}</b> — {rank_text}")
        lines.append(f"  ㄴ 보상: {reward_text}")
        lines.append("")

    lines.append("보상은 자동 지급되었습니다.")
    lines.append(f"다음 시즌도 파이팅! {E_BATTLE}")
    return "\n".join(lines)


async def grant_shiny_pokemon(conn, user_id, pokemon_id):
    """이로치 포켓몬 지급."""
    # 포켓몬 마스터 데이터 조회
    master = await conn.fetchrow("SELECT * FROM pokemon_master WHERE id = $1", pokemon_id)
    if not master:
        print(f"  [ERROR] pokemon_id={pokemon_id} not found in pokemon_master")
        return None

    # IV 랜덤 (이로치 최소 10)
    ivs = {k: random.randint(10, 31) for k in ["iv_hp", "iv_atk", "iv_def", "iv_spa", "iv_spdef", "iv_spd"]}

    row = await conn.fetchrow("""
        INSERT INTO user_pokemon (user_id, pokemon_id, friendship, is_shiny,
            iv_hp, iv_atk, iv_def, iv_spa, iv_spdef, iv_spd)
        VALUES ($1, $2, 0, 1, $3, $4, $5, $6, $7, $8)
        RETURNING id
    """, user_id, pokemon_id,
        ivs["iv_hp"], ivs["iv_atk"], ivs["iv_def"],
        ivs["iv_spa"], ivs["iv_spdef"], ivs["iv_spd"])

    return row["id"] if row else None


async def grant_iv_stone(conn, user_id, count):
    """IV+3 스톤 지급."""
    await conn.execute("""
        INSERT INTO user_items (user_id, item_type, quantity)
        VALUES ($1, 'iv_stone_3', $2)
        ON CONFLICT (user_id, item_type)
        DO UPDATE SET quantity = user_items.quantity + $2
    """, user_id, count)


async def main():
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    client = httpx.AsyncClient()
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    results = []  # 로그용

    for season_id, season_label in [("2026-S01", "시즌 1"), ("2026-S01.5", "시즌 1.5")]:
        print(f"\n=== {season_label} 보상 지급 ===")

        # 전체 순위 조회
        rows = await conn.fetch("""
            SELECT sr.user_id, u.display_name, u.username, sr.peak_rp, sr.tier,
                   RANK() OVER (ORDER BY sr.peak_rp DESC) as ranking
            FROM season_records sr
            JOIN users u ON sr.user_id = u.user_id
            WHERE sr.season_id = $1
            ORDER BY sr.peak_rp DESC
        """, season_id)

        # 유저별 보상 계산 + 지급
        user_rewards = {}  # user_id → [{season, rank, tier_name, reward_text}]

        for r in rows:
            rank = r["ranking"]
            tier = r["tier"]
            info = get_reward_info(rank, tier)
            if not info:
                continue

            user_id = r["user_id"]
            display_name = r["display_name"]
            handle = f"@{r['username']}" if r['username'] else display_name

            reward_type = info[0]
            reward_val = info[1]
            reward_text = info[2]

            # 지급
            if reward_type == "shiny_pokemon":
                pokemon_id = reward_val
                master = await conn.fetchrow("SELECT name_ko FROM pokemon_master WHERE id = $1", pokemon_id)
                pname = master["name_ko"] if master else str(pokemon_id)
                new_id = await grant_shiny_pokemon(conn, user_id, pokemon_id)
                reward_text_full = f"{reward_text} ({pname})"
                print(f"  {rank:>2}위 {handle:20s} → 이로치 {pname} (user_pokemon.id={new_id})")
                results.append(f"{season_label} {rank}위 {handle} → 이로치 {pname} (id={new_id})")
            else:
                count = reward_val
                await grant_iv_stone(conn, user_id, count)
                reward_text_full = reward_text
                print(f"  {rank:>2}위 {handle:20s} → IV+3 ×{count}")
                results.append(f"{season_label} {rank}위 {handle} → IV+3 ×{count}")

            if user_id not in user_rewards:
                user_rewards[user_id] = {"display_name": display_name, "rewards": []}
            user_rewards[user_id]["rewards"].append({
                "season": season_label,
                "rank": rank,
                "tier_name": TIER_NAMES.get(tier, tier),
                "reward_text": reward_text_full,
            })

        # 개인 DM 발송
        print(f"\n  --- {season_label} DM 발송 ---")
        for user_id, data in user_rewards.items():
            text = build_reward_dm(data["display_name"], data["rewards"])
            try:
                resp = await client.post(url, json={
                    "chat_id": user_id,
                    "text": text,
                    "parse_mode": "HTML",
                })
                status = "OK" if resp.status_code == 200 else f"ERR:{resp.status_code}"
                print(f"  DM → {data['display_name']}: {status}")
            except Exception as e:
                print(f"  DM → {data['display_name']}: FAIL ({e})")
            await asyncio.sleep(0.3)  # rate limit 방지

    await client.aclose()

    # 결과 로그를 관리자에게 전송
    log_text = "<b>시즌 보상 지급 완료</b>\n\n" + "\n".join(results)
    async with httpx.AsyncClient() as c:
        # 4096자 제한 대응
        for i in range(0, len(log_text), 4000):
            chunk = log_text[i:i+4000]
            await c.post(url, json={"chat_id": ADMIN_ID, "text": chunk, "parse_mode": "HTML"})

    await conn.close()
    print(f"\n=== 완료: {len(results)}건 지급 ===")

asyncio.run(main())
