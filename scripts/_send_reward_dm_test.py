"""시즌 보상 개인 DM 테스트 (관리자에게만)."""
import asyncio
import os
import sys
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
E_CROWN = '<tg-emoji emoji-id="6143325296675266325">👑</tg-emoji>'


def build_reward_dm(display_name, seasons_rewards):
    """개인 보상 DM 텍스트 생성.
    seasons_rewards: [{"season": "S01", "rank": 1, "tier": "platinum", "reward": "IV+3 ×1"}, ...]
    """
    lines = [
        f"{E_BATTLE} <b>{display_name}님, 시즌 보상 도착!</b>",
        "",
    ]
    for sr in seasons_rewards:
        season = sr["season"]
        rank = sr["rank"]
        tier = sr["tier_name"]
        reward = sr["reward"]

        if rank <= 3:
            medal = ["🥇", "🥈", "🥉"][rank - 1]
            rank_text = f"{medal} {rank}위"
        else:
            rank_text = f"{tier}"

        lines.append(f"{E_CHECK} <b>{season}</b> — {rank_text}")
        lines.append(f"  ㄴ 보상: {reward}")
        lines.append("")

    lines.append("보상은 자동 지급되었습니다.")
    lines.append(f"다음 시즌도 파이팅! {E_BATTLE}")
    return "\n".join(lines)


async def main():
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)

    # 관리자의 시즌 기록 + 전체 순위 조회
    rows = await conn.fetch("""
        SELECT sub.season_id, sub.peak_rp, sub.tier, sub.ranking
        FROM (
            SELECT sr.user_id, sr.season_id, sr.peak_rp, sr.tier,
                   RANK() OVER (PARTITION BY sr.season_id ORDER BY sr.peak_rp DESC) as ranking
            FROM season_records sr
            WHERE sr.season_id IN ('2026-S01', '2026-S01.5')
        ) sub
        WHERE sub.user_id = $1
        ORDER BY sub.season_id
    """, ADMIN_ID)

    tier_names = {
        "bronze": "브론즈", "silver": "실버", "gold": "골드",
        "platinum": "플래티넘", "diamond": "다이아",
        "master": "마스터", "challenger": "챌린저",
    }

    def get_reward(rank, tier):
        if rank == 1:
            return f"{E_CRYSTAL}이로치 초전설 (랜덤)"
        elif rank <= 3:
            return f"{E_CRYSTAL}이로치 전설 (랜덤)"
        elif tier in ("master", "challenger"):
            return f"{E_CRYSTAL}이로치 에픽 (랜덤)"
        elif tier == "diamond":
            return "💎 IV+3 스톤 ×2"
        elif tier == "platinum":
            return "💎 IV+3 스톤 ×1"
        else:
            return None

    seasons_rewards = []
    for r in rows:
        rank = r["ranking"]
        reward = get_reward(rank, r["tier"])
        if reward:
            season_label = "시즌 1" if r["season_id"] == "2026-S01" else "시즌 1.5"
            seasons_rewards.append({
                "season": season_label,
                "rank": rank,
                "tier_name": tier_names.get(r["tier"], r["tier"]),
                "reward": reward,
            })

    if seasons_rewards:
        text = build_reward_dm("문유", seasons_rewards)
        print(text)
        print()

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json={
                "chat_id": ADMIN_ID,
                "text": text,
                "parse_mode": "HTML",
            })
            print(f"Sent: {resp.status_code}")
    else:
        print("보상 대상 아님")

    await conn.close()

asyncio.run(main())
