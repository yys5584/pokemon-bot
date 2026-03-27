"""10일간 운영 데이터 수집 — 분석 리포트용."""
import asyncio, json, datetime, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from database import connection

class Enc(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, (datetime.date, datetime.datetime)):
            return o.isoformat()
        if isinstance(o, float):
            return round(o, 2)
        return super().default(o)

def ser(rows):
    return [dict(r) for r in rows]

async def main():
    pool = await connection.get_db()

    dau = await pool.fetch("""
        SELECT (attempted_at AT TIME ZONE 'Asia/Seoul')::date as d,
               COUNT(DISTINCT user_id) as dau
        FROM catch_attempts
        WHERE attempted_at >= NOW() - INTERVAL '10 days'
        GROUP BY d ORDER BY d
    """)

    signups = await pool.fetch("""
        SELECT (registered_at AT TIME ZONE 'Asia/Seoul')::date as d,
               COUNT(*) as cnt
        FROM users
        WHERE registered_at >= NOW() - INTERVAL '10 days'
        GROUP BY d ORDER BY d
    """)

    spawns = await pool.fetch("""
        SELECT (spawned_at AT TIME ZONE 'Asia/Seoul')::date as d,
               COUNT(*) as spawns,
               COUNT(*) FILTER(WHERE caught_by_user_id IS NOT NULL) as catches,
               COUNT(*) FILTER(WHERE is_shiny = 1 AND caught_by_user_id IS NOT NULL) as shiny
        FROM spawn_log
        WHERE spawned_at >= NOW() - INTERVAL '10 days'
        GROUP BY d ORDER BY d
    """)

    battles = await pool.fetch("""
        SELECT (created_at AT TIME ZONE 'Asia/Seoul')::date as d,
               COUNT(*) as total,
               COALESCE(SUM(bp_earned), 0) as bp
        FROM battle_records
        WHERE created_at >= NOW() - INTERVAL '10 days'
        GROUP BY d ORDER BY d
    """)

    ranked = await pool.fetch("""
        SELECT (created_at AT TIME ZONE 'Asia/Seoul')::date as d,
               COUNT(*) as ranked
        FROM ranked_battle_log
        WHERE created_at >= NOW() - INTERVAL '10 days'
        GROUP BY d ORDER BY d
    """)

    market = await pool.fetch("""
        SELECT (created_at AT TIME ZONE 'Asia/Seoul')::date as d,
               COUNT(*) as listed,
               COUNT(*) FILTER(WHERE sold_at IS NOT NULL) as sold
        FROM market_listings
        WHERE created_at >= NOW() - INTERVAL '10 days'
        GROUP BY d ORDER BY d
    """)

    totals = await pool.fetchrow("""
        SELECT
            (SELECT COUNT(*) FROM users) as total_users,
            (SELECT COUNT(*) FROM user_pokemon) as total_pokemon,
            (SELECT COUNT(*) FROM user_pokemon WHERE is_shiny = 1) as total_shiny,
            (SELECT COUNT(DISTINCT user_id) FROM catch_attempts
             WHERE attempted_at >= NOW() - INTERVAL '7 days') as wau
    """)

    chats = await pool.fetch("""
        SELECT cr.chat_title, cr.member_count,
               COUNT(sl.id) as week_spawns
        FROM chat_rooms cr
        LEFT JOIN spawn_log sl ON sl.chat_id = cr.chat_id
            AND sl.spawned_at >= NOW() - INTERVAL '7 days'
        GROUP BY cr.chat_id, cr.chat_title, cr.member_count
        ORDER BY week_spawns DESC LIMIT 10
    """)

    subs = await pool.fetch("""
        SELECT tier, COUNT(*) as cnt
        FROM subscriptions WHERE is_active = 1
        GROUP BY tier
    """)
    sub_rev = await pool.fetchval("""
        SELECT COALESCE(SUM(amount_usd), 0)
        FROM subscription_payments
        WHERE confirmed_at >= NOW() - INTERVAL '10 days' AND status = 'confirmed'
    """) or 0

    hourly = await pool.fetch("""
        SELECT EXTRACT(HOUR FROM attempted_at AT TIME ZONE 'Asia/Seoul')::int as hr,
               COUNT(DISTINCT user_id) as users
        FROM catch_attempts
        WHERE attempted_at >= NOW() - INTERVAL '7 days'
        GROUP BY hr ORDER BY hr
    """)

    popular = await pool.fetch("""
        SELECT pm.name_ko as pokemon_name, COUNT(*) as cnt
        FROM user_pokemon up
        JOIN pokemon_master pm ON pm.id = up.pokemon_id
        WHERE up.caught_at >= NOW() - INTERVAL '10 days'
        GROUP BY pm.name_ko ORDER BY cnt DESC LIMIT 10
    """)

    retention = await pool.fetch("""
        WITH daily_users AS (
            SELECT DISTINCT user_id,
                   (attempted_at AT TIME ZONE 'Asia/Seoul')::date as d
            FROM catch_attempts
            WHERE attempted_at >= NOW() - INTERVAL '11 days'
        )
        SELECT a.d,
               COUNT(DISTINCT a.user_id) as day_users,
               COUNT(DISTINCT b.user_id) as returned
        FROM daily_users a
        LEFT JOIN daily_users b ON a.user_id = b.user_id AND b.d = a.d + 1
        WHERE a.d >= (NOW() - INTERVAL '10 days')::date
          AND a.d < (NOW() AT TIME ZONE 'Asia/Seoul')::date
        GROUP BY a.d ORDER BY a.d
    """)

    # 토너먼트 — tournament_registrations만 존재
    tournaments = []

    result = {
        "dau": ser(dau), "signups": ser(signups), "spawns": ser(spawns),
        "battles": ser(battles), "ranked": ser(ranked), "market": ser(market),
        "totals": dict(totals), "chats": ser(chats), "subs": ser(subs),
        "sub_revenue_10d": float(sub_rev), "hourly": ser(hourly),
        "popular": ser(popular), "retention": ser(retention),
        "tournaments": ser(tournaments),
    }
    print(json.dumps(result, cls=Enc, ensure_ascii=False))

asyncio.run(main())
