"""Test KPI API query directly (bypassing auth)."""
import asyncio, asyncpg, os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

async def check():
    pool = await asyncpg.create_pool(os.getenv("DATABASE_URL"), statement_cache_size=0)

    # Same queries as api_admin_kpi
    today_pv = await pool.fetchval(
        "SELECT COUNT(*) FROM web_analytics WHERE event_type='pageview' AND created_at >= CURRENT_DATE"
    ) or 0

    today_visitors = await pool.fetchval(
        "SELECT COUNT(DISTINCT COALESCE(user_id, -1 * id)) FROM web_analytics WHERE event_type='pageview' AND created_at >= CURRENT_DATE"
    ) or 0

    avg_dur = await pool.fetchval(
        "SELECT COALESCE(AVG(duration_sec), 0) FROM web_analytics WHERE event_type='session' AND created_at >= CURRENT_DATE AND duration_sec > 0"
    ) or 0

    daily = await pool.fetch("""
        SELECT d::date as day,
               COALESCE(pv.cnt, 0) as pageviews,
               COALESCE(vis.cnt, 0) as visitors
        FROM generate_series(CURRENT_DATE - INTERVAL '6 days', CURRENT_DATE, '1 day') d
        LEFT JOIN (
            SELECT created_at::date as day, COUNT(*) as cnt
            FROM web_analytics WHERE event_type='pageview'
            AND created_at >= CURRENT_DATE - INTERVAL '6 days'
            GROUP BY created_at::date
        ) pv ON pv.day = d::date
        LEFT JOIN (
            SELECT created_at::date as day, COUNT(DISTINCT COALESCE(user_id, -1 * id)) as cnt
            FROM web_analytics WHERE event_type='pageview'
            AND created_at >= CURRENT_DATE - INTERVAL '6 days'
            GROUP BY created_at::date
        ) vis ON vis.day = d::date
        ORDER BY d
    """)

    by_page = await pool.fetch("""
        SELECT page, COUNT(*) as views
        FROM web_analytics
        WHERE event_type='pageview' AND created_at >= CURRENT_DATE - INTERVAL '6 days'
        GROUP BY page ORDER BY views DESC LIMIT 15
    """)

    by_hour = await pool.fetch("""
        SELECT EXTRACT(HOUR FROM created_at AT TIME ZONE 'Asia/Seoul')::int as hour, COUNT(*) as views
        FROM web_analytics
        WHERE event_type='pageview' AND created_at >= CURRENT_DATE - INTERVAL '6 days'
        GROUP BY hour ORDER BY hour
    """)

    result = {
        "today": {"visitors": today_visitors, "pageviews": today_pv, "avg_duration": round(float(avg_dur))},
        "daily": [{"date": str(r["day"]), "visitors": r["visitors"], "pageviews": r["pageviews"]} for r in daily],
        "by_page": [{"page": r["page"], "views": r["views"]} for r in by_page],
        "by_hour": [{"hour": r["hour"], "views": r["views"]} for r in by_hour],
    }

    print(json.dumps(result, indent=2, default=str))
    await pool.close()

asyncio.run(check())
