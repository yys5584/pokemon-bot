"""던전 통계 분석 스크립트."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
from database.connection import get_db

async def main():
    pool = await get_db()

    # 기본 통계
    row = await pool.fetchrow(
        "SELECT COUNT(*) as total, AVG(floor_reached)::numeric(5,1) as avg_floor, "
        "MAX(floor_reached) as max_floor FROM dungeon_runs WHERE status = 'completed'"
    )
    print(f"=== 던전 통계 ===")
    print(f"총 런: {row['total']}, 평균: {row['avg_floor']}F, 최고: {row['max_floor']}F\n")

    # 층별 사망 분포
    rows = await pool.fetch(
        "SELECT floor_reached, COUNT(*) as cnt FROM dungeon_runs "
        "WHERE status = 'completed' GROUP BY floor_reached ORDER BY floor_reached"
    )
    print("층별 분포:")
    for r in rows:
        bar = "#" * min(r['cnt'], 40)
        print(f"  {r['floor_reached']:>3}F: {r['cnt']:>3} {bar}")

    # 희귀도별
    rows2 = await pool.fetch(
        "SELECT rarity, COUNT(*) as cnt, AVG(floor_reached)::numeric(5,1) as avg "
        "FROM dungeon_runs WHERE status = 'completed' AND rarity IS NOT NULL "
        "GROUP BY rarity ORDER BY avg DESC"
    )
    print("\n희귀도별:")
    for r in rows2:
        print(f"  {r['rarity']:<18} {r['cnt']:>3}회 평균 {r['avg']}F")

    # 사망 원인 Top 10
    rows3 = await pool.fetch(
        "SELECT death_enemy, death_enemy_rarity, COUNT(*) as cnt "
        "FROM dungeon_runs WHERE status = 'completed' AND death_enemy IS NOT NULL "
        "GROUP BY death_enemy, death_enemy_rarity ORDER BY cnt DESC LIMIT 10"
    )
    print("\n사망 원인 Top10:")
    for r in rows3:
        print(f"  {r['death_enemy']} ({r['death_enemy_rarity']}): {r['cnt']}회")

asyncio.run(main())
