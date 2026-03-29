"""러스트 유저 강스권 추적."""
import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
from database.connection import get_db

async def check():
    pool = await get_db()
    uid = 7050637391

    # spawn_log 컬럼 확인
    cols = await pool.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'spawn_log'")
    print("spawn_log cols:", sorted([c['column_name'] for c in cols]))

    # 강스 기록 확인 - spawn_log에서 user_id가 spawner인 것
    forced = await pool.fetch(
        "SELECT * FROM spawn_log WHERE spawner_user_id = $1 AND spawned_at >= '2026-03-16' ORDER BY spawned_at DESC LIMIT 10", uid)
    print(f"\n강제스폰(spawner) 기록: {len(forced)}건")
    for f in forced:
        print(f"  {dict(f)}")

    # 그 외 방법으로 강스 확인 - 이로치 강스의 결과로 이로치가 나왔는지
    shiny_today = await pool.fetch(
        "SELECT id, pokemon_id, is_shiny, spawned_at FROM spawn_log WHERE is_shiny = 1 AND spawned_at >= '2026-03-16 08:00:00+00' ORDER BY spawned_at DESC LIMIT 10")
    print(f"\n오늘 이로치 스폰: {len(shiny_today)}건")
    for s in shiny_today:
        print(f"  {dict(s)}")

asyncio.run(check())
