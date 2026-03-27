"""1위~마스터 추가 IV+3 ×2 지급 + DM."""
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

E_BATTLE = '<tg-emoji emoji-id="6143344370625026850">⚔️</tg-emoji>'
E_CHECK = '<tg-emoji emoji-id="6143254176311811828">✅</tg-emoji>'


async def main():
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    client = httpx.AsyncClient()
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    results = []

    for season_id, season_label in [("2026-S01", "시즌 1"), ("2026-S01.5", "시즌 1.5")]:
        print(f"\n=== {season_label} 추가 IV+3 ×2 ===")

        rows = await conn.fetch("""
            SELECT sr.user_id, u.display_name, u.username, sr.peak_rp, sr.tier,
                   RANK() OVER (ORDER BY sr.peak_rp DESC) as ranking
            FROM season_records sr
            JOIN users u ON sr.user_id = u.user_id
            WHERE sr.season_id = $1
            ORDER BY sr.peak_rp DESC
        """, season_id)

        for r in rows:
            rank = r["ranking"]
            tier = r["tier"]
            # 1~3위 + 마스터/챌린저만
            if rank <= 3 or tier in ("master", "challenger"):
                user_id = r["user_id"]
                handle = f"@{r['username']}" if r['username'] else r['display_name']

                await conn.execute("""
                    INSERT INTO user_items (user_id, item_type, quantity)
                    VALUES ($1, 'iv_stone_3', 2)
                    ON CONFLICT (user_id, item_type)
                    DO UPDATE SET quantity = user_items.quantity + 2
                """, user_id)

                print(f"  {rank}위 {handle} ({tier}) → IV+3 ×2 추가")
                results.append(f"{season_label} {rank}위 {handle} → IV+3 ×2 추가")

                # DM
                text = (
                    f"{E_BATTLE} <b>추가 보상 도착!</b>\n\n"
                    f"{E_CHECK} <b>{season_label}</b> 상위권 추가 보상\n"
                    f"  ㄴ 💎 IV+3 스톤 ×2 추가 지급!\n\n"
                    f"축하합니다! {E_BATTLE}"
                )
                try:
                    resp = await client.post(url, json={
                        "chat_id": user_id, "text": text, "parse_mode": "HTML",
                    })
                    status = "OK" if resp.status_code == 200 else f"ERR:{resp.status_code}"
                    print(f"    DM: {status}")
                except Exception as e:
                    print(f"    DM: FAIL ({e})")
                await asyncio.sleep(0.3)
            else:
                break  # 순위 내림차순이므로 마스터 이하면 중단

    await client.aclose()

    # 관리자 로그
    log = "<b>추가 IV+3 ×2 지급 완료</b>\n\n" + "\n".join(results)
    async with httpx.AsyncClient() as c:
        await c.post(url, json={"chat_id": ADMIN_ID, "text": log, "parse_mode": "HTML"})

    await conn.close()
    print(f"\n=== 완료: {len(results)}건 ===")

asyncio.run(main())
