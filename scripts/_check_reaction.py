"""반응시간 패턴으로 매크로 감지."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

async def main():
    from database.connection import get_db
    pool = await get_db()

    rows = await pool.fetch("""
        SELECT ca.user_id, u.display_name,
               COUNT(*) as cnt,
               AVG(ca.reaction_ms)::int as avg_ms,
               STDDEV(ca.reaction_ms)::int as std_ms,
               MIN(ca.reaction_ms) as min_ms,
               MAX(ca.reaction_ms) as max_ms,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ca.reaction_ms)::int as median_ms
        FROM catch_attempts ca
        JOIN users u ON ca.user_id = u.user_id
        WHERE ca.attempted_at >= NOW() - INTERVAL '3 hours'
          AND ca.reaction_ms IS NOT NULL AND ca.reaction_ms > 0
        GROUP BY ca.user_id, u.display_name
        HAVING COUNT(*) >= 20
        ORDER BY AVG(ca.reaction_ms) ASC LIMIT 20
    """)
    print("반응시간 분석 (최근 3시간, 20회+):")
    print(f"{'유저':15} | {'횟수':>4} | {'평균':>7} | {'중앙':>7} | {'표준편차':>7} | {'최소':>6} | {'최대':>6}")
    print("-" * 85)
    for r in rows:
        avg = r['avg_ms'] or 0
        std = r['std_ms'] or 0
        med = r['median_ms'] or 0
        # 매크로 판별: 평균 빠르고 + 편차 작음
        flag = ' 🤖' if avg < 1000 and std < 500 else ''
        print(f"{r['display_name'][:15]:15} | {r['cnt']:>4} | {avg:>5}ms | {med:>5}ms | {std:>5}ms | {r['min_ms']:>5}ms | {r['max_ms']:>5}ms{flag}")

    # 이로치를 잡은 유저의 반응시간 따로
    print("\n\n이로치 포획자 반응시간 (최근 3시간):")
    shiny_rows = await pool.fetch("""
        SELECT ca.user_id, u.display_name,
               ca.reaction_ms, sl.pokemon_name,
               ca.attempted_at AT TIME ZONE 'Asia/Seoul' as t
        FROM catch_attempts ca
        JOIN users u ON ca.user_id = u.user_id
        JOIN spawn_sessions ss ON ca.session_id = ss.id
        JOIN spawn_log sl ON sl.chat_id = ss.chat_id AND sl.spawned_at = ss.spawned_at
        WHERE ca.attempted_at >= NOW() - INTERVAL '3 hours'
          AND ss.is_shiny = 1 AND ss.caught_by_user_id = ca.user_id
          AND ca.reaction_ms IS NOT NULL
        ORDER BY ca.attempted_at DESC LIMIT 30
    """)
    for r in shiny_rows:
        ms = r['reaction_ms']
        flag = ' 🤖' if ms < 500 else ''
        print(f"  [{r['t'].strftime('%H:%M')}] {r['display_name'][:12]:12} | {ms:>5}ms | {r['pokemon_name']}{flag}")

asyncio.run(main())
