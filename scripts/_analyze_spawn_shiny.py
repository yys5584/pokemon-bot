"""스폰 이로치만 분석 — spawn_log 기준."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

async def main():
    from database.connection import get_db
    pool = await get_db()

    print("=" * 60)
    print("✨ 스폰 이로치 분석 (spawn_log 기준만)")
    print("=" * 60)

    # 1. 유저별 일간 스폰 이로치 Top
    rows = await pool.fetch("""
        SELECT sl.caught_by_user_id as user_id, u.display_name,
               (sl.spawned_at AT TIME ZONE 'Asia/Seoul')::date as day,
               COUNT(*) as shiny_cnt
        FROM spawn_log sl
        JOIN users u ON sl.caught_by_user_id = u.user_id
        WHERE sl.is_shiny = 1 AND sl.caught_by_user_id IS NOT NULL
          AND sl.spawned_at >= NOW() - INTERVAL '14 days'
        GROUP BY sl.caught_by_user_id, u.display_name, day
        ORDER BY shiny_cnt DESC LIMIT 30
    """)
    print("\n🏆 일간 스폰 이로치 Top 30:")
    for r in rows:
        print(f"  {r['day']} | {r['display_name'][:15]:15} | {r['shiny_cnt']}마리")

    # 2. 일간 분포 (몇 마리가 정상인가)
    dist = await pool.fetch("""
        WITH daily AS (
            SELECT caught_by_user_id, (spawned_at AT TIME ZONE 'Asia/Seoul')::date as day,
                   COUNT(*) as cnt
            FROM spawn_log
            WHERE is_shiny = 1 AND caught_by_user_id IS NOT NULL
              AND spawned_at >= NOW() - INTERVAL '14 days'
            GROUP BY caught_by_user_id, day
        )
        SELECT cnt, COUNT(*) as user_days FROM daily GROUP BY cnt ORDER BY cnt
    """)
    print("\n📊 일간 스폰이로치 분포 (유저-일 단위):")
    for r in dist:
        bar = "█" * r['user_days']
        print(f"  {r['cnt']:>3}마리/일: {r['user_days']:>3}건 {bar}")

    # 3. 스폰 이로치 vs 총 포획시도 비율 (스폰만)
    print("\n📊 스폰이로치 / 포획시도 비율 (최근 7일, 스폰이로치 3+):")
    ratio = await pool.fetch("""
        WITH daily_shiny AS (
            SELECT caught_by_user_id as user_id,
                   (spawned_at AT TIME ZONE 'Asia/Seoul')::date as day,
                   COUNT(*) as shiny_cnt
            FROM spawn_log
            WHERE is_shiny = 1 AND caught_by_user_id IS NOT NULL
              AND spawned_at >= NOW() - INTERVAL '7 days'
            GROUP BY caught_by_user_id, day
            HAVING COUNT(*) >= 3
        ),
        daily_catches AS (
            SELECT user_id, (attempted_at AT TIME ZONE 'Asia/Seoul')::date as day,
                   COUNT(*) as catch_cnt
            FROM catch_attempts
            WHERE attempted_at >= NOW() - INTERVAL '7 days'
            GROUP BY user_id, day
        )
        SELECT u.display_name, ds.day, ds.shiny_cnt,
               COALESCE(dc.catch_cnt, 0) as catch_cnt,
               ROUND(100.0 * ds.shiny_cnt / GREATEST(dc.catch_cnt, 1), 2) as pct
        FROM daily_shiny ds
        JOIN users u ON ds.user_id = u.user_id
        LEFT JOIN daily_catches dc ON ds.user_id = dc.user_id AND ds.day = dc.day
        ORDER BY ds.shiny_cnt DESC
    """)
    for r in ratio:
        flag = " 🚨" if float(r['pct']) > 5 else ""
        print(f"  {r['day']} | {r['display_name'][:15]:15} | 이로치 {r['shiny_cnt']} / 포획 {r['catch_cnt']} = {r['pct']}%{flag}")

    # 4. 스폰 이로치 포획 간격 (연속 잡기 패턴)
    print("\n⏱️ 스폰이로치 간격 (최근 7일, 하루 5마리+ 유저):")
    heavy = await pool.fetch("""
        SELECT caught_by_user_id as user_id, u.display_name,
               (spawned_at AT TIME ZONE 'Asia/Seoul')::date as day,
               COUNT(*) as cnt
        FROM spawn_log sl
        JOIN users u ON sl.caught_by_user_id = u.user_id
        WHERE sl.is_shiny = 1 AND sl.caught_by_user_id IS NOT NULL
          AND sl.spawned_at >= NOW() - INTERVAL '7 days'
        GROUP BY sl.caught_by_user_id, u.display_name, day
        HAVING COUNT(*) >= 5
        ORDER BY cnt DESC LIMIT 10
    """)
    for hu in heavy:
        catches = await pool.fetch("""
            SELECT sl.spawned_at AT TIME ZONE 'Asia/Seoul' as t,
                   sl.pokemon_name, sl.chat_id, cr.chat_title
            FROM spawn_log sl
            LEFT JOIN chat_rooms cr ON sl.chat_id = cr.chat_id
            WHERE sl.caught_by_user_id = $1 AND sl.is_shiny = 1
              AND (sl.spawned_at AT TIME ZONE 'Asia/Seoul')::date = $2
            ORDER BY sl.spawned_at
        """, hu['user_id'], hu['day'])
        intervals = []
        for i in range(1, len(catches)):
            gap = (catches[i]['t'] - catches[i-1]['t']).total_seconds() / 60
            intervals.append(gap)
        avg_gap = sum(intervals) / len(intervals) if intervals else 0
        min_gap = min(intervals) if intervals else 0
        print(f"\n  {hu['display_name'][:12]:12} | {hu['day']} | {hu['cnt']}마리 | 평균 {avg_gap:.0f}분 | 최소 {min_gap:.0f}분")
        for i, c in enumerate(catches):
            gap_str = f"(+{intervals[i-1]:.0f}분)" if i > 0 else ""
            chat = (c['chat_title'] or '?')[:12]
            print(f"    [{c['t'].strftime('%H:%M')}] ✨{c['pokemon_name']:8} @ {chat} {gap_str}")

    # 5. 시간대별 스폰 이로치
    print("\n🕐 시간대별 스폰 이로치 (최근 7일):")
    hourly = await pool.fetch("""
        SELECT EXTRACT(HOUR FROM spawned_at AT TIME ZONE 'Asia/Seoul')::int as hr,
               COUNT(*) as cnt
        FROM spawn_log
        WHERE is_shiny = 1 AND caught_by_user_id IS NOT NULL
          AND spawned_at >= NOW() - INTERVAL '7 days'
        GROUP BY hr ORDER BY hr
    """)
    for r in hourly:
        bar = "█" * (r['cnt'] // 2)
        print(f"  {r['hr']:2}시 | {r['cnt']:3}마리 {bar}")

    # 6. 강스 vs 자연 이로치 구분 (spawn_sessions.is_forced 없으면 chat_id로 추정)
    print("\n🏠 채널별 스폰 이로치:")
    ch = await pool.fetch("""
        SELECT cr.chat_title, COUNT(*) as cnt,
               COUNT(DISTINCT sl.caught_by_user_id) as users
        FROM spawn_log sl
        LEFT JOIN chat_rooms cr ON sl.chat_id = cr.chat_id
        WHERE sl.is_shiny = 1 AND sl.caught_by_user_id IS NOT NULL
          AND sl.spawned_at >= NOW() - INTERVAL '7 days'
        GROUP BY cr.chat_title ORDER BY cnt DESC LIMIT 15
    """)
    for r in ch:
        title = (r['chat_title'] or '?')[:25]
        print(f"  {title:25} | {r['cnt']}마리 | {r['users']}명")

asyncio.run(main())
