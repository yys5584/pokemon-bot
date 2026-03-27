"""러스트 유저 강스권 사용 여부 추적."""
import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
from database.connection import get_db

async def check():
    pool = await get_db()
    uid = 7050637391

    # 강스(강제스폰) 사용 기록 확인 — spawn_log에서 forced=true
    forced = await pool.fetch(
        "SELECT * FROM spawn_log WHERE forced_by = $1 AND spawned_at >= '2026-03-16' ORDER BY spawned_at DESC LIMIT 10", uid)
    print(f"강제스폰 기록: {len(forced)}건")
    for f in forced:
        print(f"  id={f['id']}, pokemon={f['pokemon_id']}, shiny={f.get('is_shiny')}, at={f['spawned_at']}")

    # 뽑기 전후 마볼 변화 추적 (catch_attempts에서 마볼 사용 기록)
    mb_used = await pool.fetch(
        "SELECT * FROM catch_attempts WHERE user_id = $1 AND used_master_ball = 1 AND attempted_at >= '2026-03-16 08:10:00+00' ORDER BY attempted_at", uid)
    print(f"\n뽑기 이후 마볼 사용: {len(mb_used)}건")
    for m in mb_used:
        print(f"  at={m['attempted_at']}")

    # 이로치 강스 사용 확인 — shiny_spawn_tickets 변경 이력
    # bp_log에 강스 관련 기록?
    forced_bp = await pool.fetch(
        "SELECT * FROM bp_log WHERE user_id = $1 AND source LIKE '%spawn%' AND created_at >= '2026-03-16' ORDER BY created_at DESC LIMIT 5", uid)
    print(f"\n강스 관련 BP 로그: {len(forced_bp)}건")
    for b in forced_bp:
        print(f"  {dict(b)}")

asyncio.run(check())
