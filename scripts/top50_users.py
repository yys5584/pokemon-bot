"""상위 50명 유저 상세 데이터 추출."""
import asyncio
import json
import os
from dotenv import load_dotenv
load_dotenv()

async def main():
    from database.connection import get_db
    pool = await get_db()

    # 상위 50명 기본 정보
    top50 = await pool.fetch("""
        SELECT user_id, username, battle_points,
               registered_at AT TIME ZONE 'Asia/Seoul' as reg,
               (SELECT COUNT(*) FROM user_pokemon WHERE user_pokemon.user_id = users.user_id) as pokemon_count
        FROM users
        ORDER BY battle_points DESC
        LIMIT 50
    """)

    uids = [u["user_id"] for u in top50]

    # 배틀 통계 (winner + loser)
    battle_stats = await pool.fetch("""
        SELECT uid, COUNT(*) as cnt, COALESCE(SUM(bp), 0)::int as bp FROM (
            SELECT winner_id as uid, bp_earned as bp FROM battle_records WHERE winner_id = ANY($1::bigint[])
            UNION ALL
            SELECT loser_id as uid, 0 as bp FROM battle_records WHERE loser_id = ANY($1::bigint[])
        ) t GROUP BY uid
    """, uids)
    battle_map = {r["uid"]: r for r in battle_stats}

    # 가챠 소비
    gacha_stats = await pool.fetch("""
        SELECT user_id, COALESCE(SUM(bp_spent), 0)::int as spent, COUNT(*)::int as pulls
        FROM gacha_log WHERE user_id = ANY($1::bigint[])
        GROUP BY user_id
    """, uids)
    gacha_map = {r["user_id"]: r for r in gacha_stats}

    # 상점 소비 (item별 개수)
    shop_stats = await pool.fetch("""
        SELECT user_id, item, SUM(amount)::int as cnt
        FROM bp_purchase_log WHERE user_id = ANY($1::bigint[])
        GROUP BY user_id, item
    """, uids)
    shop_map = {}
    for r in shop_stats:
        uid = r["user_id"]
        if uid not in shop_map:
            shop_map[uid] = 0
        shop_map[uid] += r["cnt"]  # count purchases

    # 마켓 판매
    market_sales = await pool.fetch("""
        SELECT seller_id as user_id, COALESCE(SUM(price_bp), 0)::int as bp, COUNT(*)::int as cnt
        FROM market_listings WHERE sold_at IS NOT NULL AND seller_id = ANY($1::bigint[])
        GROUP BY seller_id
    """, uids)
    sale_map = {r["user_id"]: r for r in market_sales}

    # 마켓 구매
    market_buys = await pool.fetch("""
        SELECT buyer_id as user_id, COALESCE(SUM(price_bp), 0)::int as bp, COUNT(*)::int as cnt
        FROM market_listings WHERE sold_at IS NOT NULL AND buyer_id = ANY($1::bigint[]) AND buyer_id IS NOT NULL
        GROUP BY buyer_id
    """, uids)
    buy_map = {r["user_id"]: r for r in market_buys}

    results = []
    for u in top50:
        uid = u["user_id"]
        b = battle_map.get(uid, {})
        g = gacha_map.get(uid, {})
        s_cnt = shop_map.get(uid, 0)
        sale = sale_map.get(uid, {})
        buy = buy_map.get(uid, {})
        results.append({
            "rank": len(results) + 1,
            "username": u["username"] or str(uid),
            "bp": u["battle_points"],
            "pokemon": u["pokemon_count"],
            "battles": b.get("cnt", 0),
            "bp_earned": b.get("bp", 0),
            "gacha_spent": g.get("spent", 0),
            "gacha_pulls": g.get("pulls", 0),
            "shop_purchases": s_cnt,
            "market_sold": sale.get("bp", 0),
            "market_bought": buy.get("bp", 0),
            "reg": str(u["reg"])[:10] if u["reg"] else "N/A",
        })

    print(json.dumps(results, ensure_ascii=False, default=str))

asyncio.run(main())
