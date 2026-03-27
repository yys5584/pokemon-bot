"""러스트 유저 보상 확인 스크립트."""
import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
from database.connection import get_db

async def check():
    pool = await get_db()
    uid = 7050637391

    # 유저 현재 상태
    u = await pool.fetchrow(
        "SELECT master_balls, hyper_balls, battle_points, shiny_spawn_tickets FROM users WHERE user_id = $1", uid)
    print(f"현재: 마볼={u['master_balls']}, 하볼={u['hyper_balls']}, BP={u['battle_points']}, 강스권={u['shiny_spawn_tickets']}")

    # user_items
    items = await pool.fetch("SELECT * FROM user_items WHERE user_id = $1", uid)
    print(f"아이템: {[dict(i) for i in items]}")

    # 이로치알
    eggs = await pool.fetch("SELECT * FROM shiny_eggs WHERE user_id = $1 ORDER BY created_at DESC LIMIT 5", uid)
    for e in eggs:
        print(f"알: {dict(e)}")

    # bp_log 최근
    bp = await pool.fetch(
        "SELECT amount, source, created_at FROM bp_log WHERE user_id = $1 AND created_at >= NOW() - INTERVAL '5 hours' ORDER BY created_at DESC", uid)
    for b in bp:
        print(f"  BP: {b['amount']:+d} ({b['source']}) @ {b['created_at']}")

    # 뽑기 시점의 마볼/BP 변화 추적 (gacha 5연차 시점 08:10 UTC)
    print("\n--- 뽑기 시간대 전후 체크 ---")
    # gacha_log에서 BP가 차감됐는지 (500BP = 5*100)
    gacha_sum = await pool.fetchval(
        "SELECT COALESCE(SUM(bp_spent), 0) FROM gacha_log WHERE user_id = $1 AND created_at BETWEEN '2026-03-16 08:10:00+00' AND '2026-03-16 08:11:00+00'", uid)
    print(f"뽑기 BP 차감 기록: {gacha_sum}BP")

asyncio.run(check())
