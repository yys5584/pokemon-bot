"""시즌 보상 대상자 핸들 조회 + 관리자 DM 발송."""
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


async def main():
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)

    # S01 rankings by peak_rp
    s01 = await conn.fetch("""
        SELECT sr.user_id, u.display_name, u.username, sr.peak_rp, sr.tier
        FROM season_records sr JOIN users u ON sr.user_id = u.user_id
        WHERE sr.season_id = '2026-S01'
        ORDER BY sr.peak_rp DESC
    """)

    # S01.5 rankings by peak_rp
    s15 = await conn.fetch("""
        SELECT sr.user_id, u.display_name, u.username, sr.peak_rp, sr.tier
        FROM season_records sr JOIN users u ON sr.user_id = u.user_id
        WHERE sr.season_id = '2026-S01.5'
        ORDER BY sr.peak_rp DESC
    """)

    def handle(r):
        return f"@{r['username']}" if r['username'] else r['display_name']

    def tier_rank(rows):
        """1~3위 + 마스터/챌린저 + 다이아 + 플래티넘 분류."""
        result = {"1st": None, "2nd": None, "3rd": None, "master": [], "diamond": [], "platinum": []}
        for i, r in enumerate(rows):
            if i == 0:
                result["1st"] = r
            elif i == 1:
                result["2nd"] = r
            elif i == 2:
                result["3rd"] = r
            elif r["tier"] in ("master", "challenger"):
                result["master"].append(r)
            elif r["tier"] == "diamond":
                result["diamond"].append(r)
            elif r["tier"] == "platinum":
                result["platinum"].append(r)
        return result

    s01_r = tier_rank(s01)
    s15_r = tier_rank(s15)

    lines = ["<b>S01 보상 대상</b>"]
    lines.append(f"🥇 이로치 초전설: {handle(s01_r['1st'])}")
    lines.append(f"🥈 이로치 전설: {handle(s01_r['2nd'])}")
    lines.append(f"🥉 이로치 전설: {handle(s01_r['3rd'])}")
    if s01_r["master"]:
        lines.append(f"👑 이로치 에픽: {', '.join(handle(r) for r in s01_r['master'])}")
    if s01_r["diamond"]:
        lines.append(f"💠 IV+3 ×2: {', '.join(handle(r) for r in s01_r['diamond'])}")
    if s01_r["platinum"]:
        lines.append(f"💎 IV+3 ×1: {', '.join(handle(r) for r in s01_r['platinum'])}")

    lines.append("")
    lines.append("<b>S01.5 보상 대상</b>")
    lines.append(f"🥇 이로치 초전설: {handle(s15_r['1st'])}")
    lines.append(f"🥈 이로치 전설: {handle(s15_r['2nd'])}")
    lines.append(f"🥉 이로치 전설: {handle(s15_r['3rd'])}")
    if s15_r["master"]:
        lines.append(f"👑 이로치 에픽: {', '.join(handle(r) for r in s15_r['master'])}")
    if s15_r["diamond"]:
        lines.append(f"💠 IV+3 ×2: {', '.join(handle(r) for r in s15_r['diamond'])}")
    if s15_r["platinum"]:
        lines.append(f"💎 IV+3 ×1: {', '.join(handle(r) for r in s15_r['platinum'])}")

    text = "\n".join(lines)
    print(text)

    # Send to admin
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json={
            "chat_id": ADMIN_ID,
            "text": text,
            "parse_mode": "HTML",
        })
        print(f"\nSent: {resp.status_code}")

    await conn.close()

asyncio.run(main())
