"""KPI 리포트 데이터 감사 스크립트."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

async def main():
    from database.connection import get_db
    pool = await get_db()
    from datetime import date, timedelta
    d = date(2026, 3, 21)
    d2 = date(2026, 3, 22)

    # user_pokemon 컬럼
    up_cols = await pool.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'user_pokemon' ORDER BY ordinal_position")
    print('user_pokemon cols:', [r['column_name'] for r in up_cols])

    # 배틀만 한 유저
    battle_only = await pool.fetchval(
        "SELECT COUNT(DISTINCT uid) FROM ("
        "SELECT winner_id as uid FROM battle_records WHERE created_at >= $1 AND created_at < $2 "
        "UNION SELECT loser_id as uid FROM battle_records WHERE created_at >= $1 AND created_at < $2"
        ") w WHERE uid NOT IN (SELECT DISTINCT user_id FROM catch_attempts WHERE attempted_at >= $1 AND attempted_at < $2)",
        d, d2)
    print(f'배틀만한 유저(포획없음): {battle_only}')

    # 포획 시도 총수
    total_attempts = await pool.fetchval(
        "SELECT COUNT(*) FROM catch_attempts WHERE attempted_at >= $1 AND attempted_at < $2", d, d2)
    print(f'포획 시도(catch_attempts): {total_attempts}')

    # 이로치 - user_pokemon 전체 vs spawn_log
    shiny_up_total = await pool.fetchval(
        "SELECT COUNT(*) FROM user_pokemon WHERE is_shiny = 1 AND caught_at >= $1 AND caught_at < $2", d, d2)
    shiny_sl_total = await pool.fetchval(
        "SELECT COUNT(*) FROM spawn_log WHERE is_shiny = 1 AND caught_by_user_id IS NOT NULL AND spawned_at >= $1 AND spawned_at < $2", d, d2)
    print(f'이로치 user_pokemon: {shiny_up_total}, spawn_log: {shiny_sl_total}')

asyncio.run(main())
