"""이로치 매크로 모니터링 — 이로치 파밍 집중 감시."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

async def main():
    from database.connection import get_db
    pool = await get_db()

    # KST 시간 확인
    now_row = await pool.fetchrow("SELECT NOW() AT TIME ZONE 'Asia/Seoul' as kst")
    kst_now = now_row['kst']
    print(f"🕐 KST {kst_now.strftime('%Y-%m-%d %H:%M')}")
    if kst_now.hour >= 4 and kst_now.hour < 12:
        print("모니터링 시간 종료 (새벽 4시)")
        return

    print("=" * 55)
    print("✨ 이로치 매크로 모니터링")
    print("=" * 55)

    # 1. 오늘 스폰 이로치 포획 Top 유저 (spawn_log 기준 — 합성/뽑기 제외)
    rows = await pool.fetch("""
        SELECT sl.caught_by_user_id as user_id, u.display_name, COUNT(*) as cnt,
               MIN(sl.spawned_at AT TIME ZONE 'Asia/Seoul') as first_at,
               MAX(sl.spawned_at AT TIME ZONE 'Asia/Seoul') as last_at
        FROM spawn_log sl
        JOIN users u ON sl.caught_by_user_id = u.user_id
        WHERE sl.is_shiny = 1 AND sl.caught_by_user_id IS NOT NULL
          AND sl.spawned_at >= (NOW() AT TIME ZONE 'Asia/Seoul')::date AT TIME ZONE 'Asia/Seoul'
        GROUP BY sl.caught_by_user_id, u.display_name
        ORDER BY cnt DESC LIMIT 15
    """)
    print("\n✨ 오늘 이로치 Top 15:")
    for r in rows:
        mins = (r['last_at'] - r['first_at']).total_seconds() / 60 if r['cnt'] > 1 else 0
        rate = f"{r['cnt']/max(mins,1)*60:.1f}마리/h" if mins > 10 else ""
        flag = " 🚨" if r['cnt'] >= 15 else " ⚠️" if r['cnt'] >= 10 else ""
        print(f"  {r['display_name'][:15]:15} | {r['cnt']:>3}마리 | {rate:>10}{flag}")

    # 2. 최근 1시간 스폰 이로치 (spawn_log 기준)
    rows2 = await pool.fetch("""
        SELECT sl.caught_by_user_id as user_id, u.display_name, COUNT(*) as cnt
        FROM spawn_log sl
        JOIN users u ON sl.caught_by_user_id = u.user_id
        WHERE sl.is_shiny = 1 AND sl.caught_by_user_id IS NOT NULL
          AND sl.spawned_at >= NOW() - INTERVAL '1 hour'
        GROUP BY sl.caught_by_user_id, u.display_name
        HAVING COUNT(*) >= 2
        ORDER BY cnt DESC
    """)
    print("\n✨ 최근 1시간 이로치 2마리+ :")
    if rows2:
        for r in rows2:
            flag = " 🚨" if r['cnt'] >= 5 else ""
            print(f"  {r['display_name'][:15]:15} | {r['cnt']}마리{flag}")
    else:
        print("  (없음)")

    # 3. 최근 3시간 스폰 이로치 로그 (spawn_log 기준)
    rows3 = await pool.fetch("""
        SELECT sl.caught_by_user_id as user_id, u.display_name,
               sl.pokemon_name as name_ko,
               sl.spawned_at AT TIME ZONE 'Asia/Seoul' as caught_kst,
               sl.chat_id
        FROM spawn_log sl
        JOIN users u ON sl.caught_by_user_id = u.user_id
        WHERE sl.is_shiny = 1 AND sl.caught_by_user_id IS NOT NULL
          AND sl.spawned_at >= NOW() - INTERVAL '3 hours'
        ORDER BY sl.spawned_at DESC LIMIT 30
    """)
    print("\n✨ 최근 3시간 이로치 로그:")
    for r in rows3:
        t = r['caught_kst'].strftime('%H:%M')
        print(f"  [{t}] {r['display_name'][:12]:12} — ✨{r['name_ko']}")

    # 4. 이로치 비율 이상치 (spawn_log 기준)
    rows4 = await pool.fetch("""
        WITH shiny AS (
            SELECT caught_by_user_id as user_id, COUNT(*) as shiny_cnt
            FROM spawn_log
            WHERE is_shiny = 1 AND caught_by_user_id IS NOT NULL
              AND spawned_at >= (NOW() AT TIME ZONE 'Asia/Seoul')::date AT TIME ZONE 'Asia/Seoul'
            GROUP BY caught_by_user_id
        ),
        catches AS (
            SELECT user_id, COUNT(*) as catch_cnt
            FROM catch_attempts
            WHERE attempted_at >= (NOW() AT TIME ZONE 'Asia/Seoul')::date AT TIME ZONE 'Asia/Seoul'
            GROUP BY user_id
        )
        SELECT u.display_name, s.shiny_cnt, COALESCE(c.catch_cnt, 0) as catch_cnt,
               ROUND(100.0 * s.shiny_cnt / GREATEST(c.catch_cnt, 1), 1) as shiny_pct
        FROM shiny s
        JOIN users u ON s.user_id = u.user_id
        LEFT JOIN catches c ON s.user_id = c.user_id
        WHERE s.shiny_cnt >= 3
        ORDER BY shiny_pct DESC LIMIT 10
    """)
    if rows4:
        print("\n📊 이로치 비율 이상치 (3마리+):")
        for r in rows4:
            flag = " 🚨" if float(r['shiny_pct']) > 20 else ""
            print(f"  {r['display_name'][:15]:15} | 이로치 {r['shiny_cnt']} / 포획 {r['catch_cnt']} = {r['shiny_pct']}%{flag}")

asyncio.run(main())
