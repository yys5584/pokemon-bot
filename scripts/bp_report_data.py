"""BP 리포트 데이터 추출 스크립트."""
import asyncio
import json
import os
from dotenv import load_dotenv
load_dotenv()

async def main():
    from database.connection import get_db
    pool = await get_db()

    battle_bp = await pool.fetch(
        "SELECT DATE(created_at AT TIME ZONE 'Asia/Seoul') as d, "
        "COALESCE(SUM(bp_earned), 0)::int as bp "
        "FROM battle_records WHERE bp_earned > 0 GROUP BY d ORDER BY d"
    )

    gacha_bp = await pool.fetch(
        "SELECT DATE(created_at AT TIME ZONE 'Asia/Seoul') as d, "
        "COALESCE(SUM(bp_spent), 0)::int as bp, COUNT(*)::int as pulls "
        "FROM gacha_log GROUP BY d ORDER BY d"
    )

    shop_bp = await pool.fetch(
        "SELECT DATE(purchased_at AT TIME ZONE 'Asia/Seoul') as d, "
        "item, SUM(amount)::int as cnt "
        "FROM bp_purchase_log GROUP BY d, item ORDER BY d"
    )

    market_bp = await pool.fetch(
        "SELECT DATE(sold_at AT TIME ZONE 'Asia/Seoul') as d, "
        "COALESCE(SUM(price_bp), 0)::int as bp, COUNT(*)::int as trades "
        "FROM market_listings WHERE sold_at IS NOT NULL GROUP BY d ORDER BY d"
    )

    tourn_bp = await pool.fetch(
        "SELECT DATE(created_at AT TIME ZONE 'Asia/Seoul') as d, "
        "COALESCE(SUM(bp_earned), 0)::int as bp "
        "FROM battle_records WHERE battle_type = 'tournament' AND bp_earned > 0 "
        "GROUP BY d ORDER BY d"
    )

    ranked_bp = await pool.fetch(
        "SELECT DATE(created_at AT TIME ZONE 'Asia/Seoul') as d, "
        "COALESCE(SUM(bp_earned), 0)::int as bp "
        "FROM battle_records WHERE battle_type = 'ranked' AND bp_earned > 0 "
        "GROUP BY d ORDER BY d"
    )

    yacha_bp = await pool.fetch(
        "SELECT DATE(created_at AT TIME ZONE 'Asia/Seoul') as d, "
        "COALESCE(SUM(bp_earned), 0)::int as bp "
        "FROM battle_records WHERE battle_type = 'bet' AND bp_earned > 0 "
        "GROUP BY d ORDER BY d"
    )

    signups = await pool.fetch(
        "SELECT DATE(registered_at AT TIME ZONE 'Asia/Seoul') as d, "
        "COUNT(*)::int as cnt FROM users WHERE registered_at IS NOT NULL GROUP BY d ORDER BY d"
    )

    total_bp = await pool.fetchval(
        "SELECT COALESCE(SUM(battle_points), 0)::int FROM users WHERE battle_points > 0"
    )
    user_count = await pool.fetchval(
        "SELECT COUNT(*)::int FROM users WHERE battle_points > 0"
    )
    total_users = await pool.fetchval("SELECT COUNT(*)::int FROM users")

    bp_dist = await pool.fetch(
        "SELECT CASE "
        "WHEN battle_points = 0 THEN '0' "
        "WHEN battle_points BETWEEN 1 AND 499 THEN '1-499' "
        "WHEN battle_points BETWEEN 500 AND 999 THEN '500-999' "
        "WHEN battle_points BETWEEN 1000 AND 2999 THEN '1000-2999' "
        "WHEN battle_points BETWEEN 3000 AND 4999 THEN '3000-4999' "
        "WHEN battle_points >= 5000 THEN '5000+' "
        "END as range, COUNT(*)::int as cnt, "
        "COALESCE(SUM(battle_points), 0)::int as total_bp "
        "FROM users GROUP BY range ORDER BY MIN(battle_points)"
    )

    # Top BP holders
    top_bp = await pool.fetch(
        "SELECT user_id, username, battle_points FROM users "
        "ORDER BY battle_points DESC LIMIT 10"
    )

    def ser(rows):
        return [
            {k: (v.isoformat() if hasattr(v, "isoformat") else v)
             for k, v in dict(r).items()}
            for r in rows
        ]

    data = {
        "battle_bp": ser(battle_bp),
        "gacha_bp": ser(gacha_bp),
        "shop_bp": ser(shop_bp),
        "market_bp": ser(market_bp),
        "tourn_bp": ser(tourn_bp),
        "ranked_bp": ser(ranked_bp),
        "yacha_bp": ser(yacha_bp),
        "signups": ser(signups),
        "bp_dist": ser(bp_dist),
        "top_bp": ser(top_bp),
        "total_bp": total_bp,
        "user_count": user_count,
        "total_users": total_users,
    }
    print(json.dumps(data, ensure_ascii=False, default=str))

asyncio.run(main())
