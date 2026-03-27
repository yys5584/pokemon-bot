"""야차 베팅 어뷰징 조사."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

async def main():
    from database.connection import get_db
    pool = await get_db()

    # 최근 7일 야차 수익 Top
    rows = await pool.fetch("""
        SELECT bl.user_id, u.display_name, u.username,
               SUM(CASE WHEN bl.amount > 0 THEN bl.amount ELSE 0 END) as total_won,
               SUM(CASE WHEN bl.amount < 0 THEN ABS(bl.amount) ELSE 0 END) as total_lost,
               SUM(bl.amount) as net,
               COUNT(*) as games
        FROM bp_log bl
        JOIN users u ON bl.user_id = u.user_id
        WHERE bl.source IN ('bet_win', 'bet_lose', 'bet_refund')
          AND bl.created_at >= NOW() - INTERVAL '7 days'
        GROUP BY bl.user_id, u.display_name, u.username
        ORDER BY net DESC
        LIMIT 20
    """)

    print("=== 야차 베팅 수익 Top 20 (최근 7일) ===")
    for r in rows:
        print(f"{r['display_name'][:15]:15} | 순수익: {r['net']:>+8,} | 승: +{r['total_won']:>7,} | 패: -{r['total_lost']:>7,} | {r['games']}판")

    # 오늘
    rows2 = await pool.fetch("""
        SELECT bl.user_id, u.display_name,
               SUM(CASE WHEN bl.amount > 0 THEN bl.amount ELSE 0 END) as total_won,
               SUM(CASE WHEN bl.amount < 0 THEN ABS(bl.amount) ELSE 0 END) as total_lost,
               SUM(bl.amount) as net,
               COUNT(*) as games
        FROM bp_log bl
        JOIN users u ON bl.user_id = u.user_id
        WHERE bl.source IN ('bet_win', 'bet_lose', 'bet_refund')
          AND bl.created_at >= (NOW() AT TIME ZONE 'Asia/Seoul')::date
        GROUP BY bl.user_id, u.display_name
        ORDER BY net DESC
        LIMIT 15
    """)

    print("\n=== 야차 베팅 수익 Top 15 (오늘) ===")
    for r in rows2:
        print(f"{r['display_name'][:15]:15} | 순수익: {r['net']:>+8,} | 승: +{r['total_won']:>7,} | 패: -{r['total_lost']:>7,} | {r['games']}판")

    # 야차 패턴 분석: 같은 2명이 반복 대전
    print("\n=== 반복 대전 짝 (최근 7일, 5판 이상) ===")
    pairs = await pool.fetch("""
        SELECT br.winner_id, br.loser_id,
               w.display_name as winner_name, l.display_name as loser_name,
               COUNT(*) as cnt,
               SUM(br.bp_earned) as total_bp
        FROM battle_records br
        JOIN users w ON br.winner_id = w.user_id
        JOIN users l ON br.loser_id = l.user_id
        WHERE br.battle_type = 'normal'
          AND br.created_at >= NOW() - INTERVAL '7 days'
          AND br.bp_earned > 0
        GROUP BY br.winner_id, br.loser_id, w.display_name, l.display_name
        HAVING COUNT(*) >= 5
        ORDER BY cnt DESC
        LIMIT 20
    """)
    for r in pairs:
        print(f"{r['winner_name'][:12]:12} > {r['loser_name'][:12]:12} | {r['cnt']}판 | BP +{r['total_bp']:,}")

asyncio.run(main())
