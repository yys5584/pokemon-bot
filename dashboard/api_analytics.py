"""Dashboard API — Analytics, KPI, Cloudflare, battle analytics."""

import logging
import os
import time

import config
from aiohttp import web
from database import queries

logger = logging.getLogger(__name__)

# --- Cloudflare Analytics ---
_CF_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
_CF_ZONE = os.getenv("CLOUDFLARE_ZONE_ID", "")
_cf_cache: dict = {"data": None, "ts": 0}


async def api_analytics_pageview(request):
    """Record a pageview event (public, rate limited)."""
    from dashboard.server import _get_session
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False}, status=400)
    page = str(body.get("page", ""))[:50]
    if not page:
        return web.json_response({"ok": False}, status=400)
    sess = await _get_session(request)
    uid = sess["user_id"] if sess else None
    pool = await queries.get_db()
    await pool.execute(
        "INSERT INTO web_analytics (event_type, user_id, page) VALUES ('pageview', $1, $2)",
        uid, page,
    )
    return web.json_response({"ok": True})


async def api_analytics_session(request):
    """Record session end with duration (public, via sendBeacon)."""
    from dashboard.server import _get_session
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False}, status=400)
    duration = min(int(body.get("duration_sec", 0)), 86400)
    pages = min(int(body.get("pages_viewed", 0)), 1000)
    if duration <= 0:
        return web.json_response({"ok": False})
    sess = await _get_session(request)
    uid = sess["user_id"] if sess else None
    pool = await queries.get_db()
    await pool.execute(
        "INSERT INTO web_analytics (event_type, user_id, duration_sec, pages_viewed) VALUES ('session', $1, $2, $3)",
        uid, duration, pages,
    )
    return web.json_response({"ok": True})


async def _fetch_cloudflare_analytics(days: int = 7) -> list[dict]:
    """Fetch visitor analytics from Cloudflare GraphQL API (5-min cache)."""
    now = time.time()
    if _cf_cache["data"] is not None and now - _cf_cache["ts"] < 300:
        return _cf_cache["data"]

    if not _CF_TOKEN or not _CF_ZONE:
        return []

    from datetime import timedelta
    today = config.get_kst_now().date()
    date_start = str(today - timedelta(days=days - 1))
    date_end = str(today)

    query = """{
      viewer {
        zones(filter: {zoneTag: "%s"}) {
          httpRequests1dGroups(limit: %d, filter: {date_geq: "%s", date_leq: "%s"}, orderBy: [date_ASC]) {
            dimensions { date }
            sum { requests pageViews }
            uniq { uniques }
          }
        }
      }
    }""" % (_CF_ZONE, days, date_start, date_end)

    try:
        import aiohttp as _aio
        async with _aio.ClientSession() as sess:
            async with sess.post(
                "https://api.cloudflare.com/client/v4/graphql",
                headers={"Authorization": f"Bearer {_CF_TOKEN}", "Content-Type": "application/json"},
                json={"query": query},
                timeout=_aio.ClientTimeout(total=10),
            ) as resp:
                body = await resp.json()
        zones = body.get("data", {}).get("viewer", {}).get("zones", [])
        if not zones:
            return []
        result = []
        for row in zones[0].get("httpRequests1dGroups", []):
            result.append({
                "date": row["dimensions"]["date"],
                "requests": row["sum"]["requests"],
                "pageviews": row["sum"]["pageViews"],
                "visitors": row["uniq"]["uniques"],
            })
        _cf_cache["data"] = result
        _cf_cache["ts"] = now
        return result
    except Exception as e:
        logger.warning(f"Cloudflare analytics fetch failed: {e}")
        return _cf_cache.get("data") or []


async def api_admin_kpi(request):
    """Admin: web analytics KPI dashboard data."""
    from dashboard.api_admin import _admin_check
    if not await _admin_check(request):
        return web.json_response({"error": "Unauthorized"}, status=403)
    pool = await queries.get_db()

    # Today stats
    today_pv = await pool.fetchval(
        "SELECT COUNT(*) FROM web_analytics WHERE event_type='pageview' AND created_at >= CURRENT_DATE"
    ) or 0
    today_visitors = await pool.fetchval(
        "SELECT COUNT(DISTINCT COALESCE(user_id, -1 * id)) FROM web_analytics WHERE event_type='pageview' AND created_at >= CURRENT_DATE"
    ) or 0
    avg_dur = await pool.fetchval(
        "SELECT COALESCE(AVG(duration_sec), 0) FROM web_analytics WHERE event_type='session' AND created_at >= CURRENT_DATE AND duration_sec > 0"
    ) or 0

    # Daily trend (7 days)
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

    # By page (last 7 days)
    by_page = await pool.fetch("""
        SELECT page, COUNT(*) as views
        FROM web_analytics
        WHERE event_type='pageview' AND created_at >= CURRENT_DATE - INTERVAL '6 days'
        GROUP BY page ORDER BY views DESC LIMIT 15
    """)

    # By hour (last 7 days)
    by_hour = await pool.fetch("""
        SELECT EXTRACT(HOUR FROM created_at AT TIME ZONE 'Asia/Seoul')::int as hour, COUNT(*) as views
        FROM web_analytics
        WHERE event_type='pageview' AND created_at >= CURRENT_DATE - INTERVAL '6 days'
        GROUP BY hour ORDER BY hour
    """)

    # Cloudflare analytics (parallel fetch)
    cf_data = await _fetch_cloudflare_analytics(7)

    return web.json_response({
        "today": {"visitors": today_visitors, "pageviews": today_pv, "avg_duration": round(float(avg_dur))},
        "daily": [{"date": str(r["day"]), "visitors": r["visitors"], "pageviews": r["pageviews"]} for r in daily],
        "by_page": [{"page": r["page"], "views": r["views"]} for r in by_page],
        "by_hour": [{"hour": r["hour"], "views": r["views"]} for r in by_hour],
        "cloudflare": cf_data,
    })


async def api_admin_battle_analytics(request):
    """Admin: battle analytics with filters."""
    from dashboard.api_admin import _admin_check
    if not await _admin_check(request):
        return web.json_response({"error": "Unauthorized"}, status=403)
    pool = await queries.get_db()

    # Parse filter params
    days = request.query.get("days", "7")
    battle_type = request.query.get("battle_type", "all")
    rarity = request.query.get("rarity", "all")
    tier = request.query.get("tier", "all")

    # Build WHERE clause dynamically
    conditions = []
    params = []
    idx = 1

    if days != "all":
        try:
            d = int(days)
            conditions.append(f"bps.created_at >= NOW() - INTERVAL '{d} days'")
        except ValueError:
            pass

    if battle_type != "all":
        conditions.append(f"bps.battle_type = ${idx}")
        params.append(battle_type)
        idx += 1

    if rarity != "all":
        conditions.append(f"bps.rarity = ${idx}")
        params.append(rarity)
        idx += 1

    if tier != "all" and battle_type == "ranked":
        conditions.append(f"""bps.battle_record_id IN (
            SELECT rbl.battle_record_id FROM ranked_battle_log rbl
            WHERE rbl.winner_tier_before = ${idx} OR rbl.loser_tier_before = ${idx}
        )""")
        params.append(tier)
        idx += 1

    where = " AND ".join(conditions) if conditions else "TRUE"

    # 1) Summary stats
    summary_q = f"""
        SELECT
            COUNT(DISTINCT bps.battle_record_id) AS total_battles,
            COUNT(*) AS total_pokemon,
            ROUND(AVG(br.total_rounds)::numeric, 1) AS avg_rounds
        FROM battle_pokemon_stats bps
        JOIN battle_records br ON bps.battle_record_id = br.id
        WHERE {where}
    """
    summary_row = await pool.fetchrow(summary_q, *params)

    today_battles = await pool.fetchval(
        "SELECT COUNT(DISTINCT battle_record_id) FROM battle_pokemon_stats WHERE created_at >= CURRENT_DATE"
    ) or 0

    # 2) Pokemon ranking (top 30 by usage)
    pokemon_q = f"""
        SELECT bps.pokemon_id, pm.name_ko, pm.emoji, bps.rarity,
               COUNT(*) AS uses,
               COUNT(DISTINCT bps.user_id) AS unique_users,
               SUM(CASE WHEN bps.won THEN 1 ELSE 0 END) AS wins,
               ROUND(100.0 * SUM(CASE WHEN bps.won THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) AS win_rate,
               ROUND(AVG(bps.damage_dealt)) AS avg_damage,
               ROUND(AVG(bps.kills)::numeric, 1) AS avg_kills,
               ROUND(AVG(bps.deaths)::numeric, 1) AS avg_deaths
        FROM battle_pokemon_stats bps
        JOIN pokemon_master pm ON bps.pokemon_id = pm.id
        WHERE {where}
        GROUP BY bps.pokemon_id, pm.name_ko, pm.emoji, bps.rarity
        HAVING COUNT(*) >= 3
        ORDER BY uses DESC
    """
    pokemon_rows = await pool.fetch(pokemon_q, *params)

    # 3) Rarity stats
    rarity_q = f"""
        SELECT bps.rarity,
               COUNT(*) AS uses,
               SUM(CASE WHEN bps.won THEN 1 ELSE 0 END) AS wins,
               ROUND(100.0 * SUM(CASE WHEN bps.won THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) AS win_rate,
               ROUND(AVG(bps.damage_dealt)) AS avg_damage
        FROM battle_pokemon_stats bps
        WHERE {where}
        GROUP BY bps.rarity
        ORDER BY uses DESC
    """
    rarity_rows = await pool.fetch(rarity_q, *params)

    # 4) Daily battle trend (last N days based on filter)
    trend_days = 7 if days == "all" else min(int(days), 30)
    daily_q = f"""
        SELECT d::date AS day,
               COALESCE(cnt.total, 0) AS total,
               COALESCE(cnt.ranked, 0) AS ranked,
               COALESCE(cnt.normal, 0) AS normal
        FROM generate_series(CURRENT_DATE - INTERVAL '{trend_days - 1} days', CURRENT_DATE, '1 day') d
        LEFT JOIN (
            SELECT bps.created_at::date AS day,
                   COUNT(DISTINCT bps.battle_record_id) AS total,
                   COUNT(DISTINCT CASE WHEN bps.battle_type = 'ranked' THEN bps.battle_record_id END) AS ranked,
                   COUNT(DISTINCT CASE WHEN bps.battle_type = 'normal' THEN bps.battle_record_id END) AS normal
            FROM battle_pokemon_stats bps
            WHERE bps.created_at >= CURRENT_DATE - INTERVAL '{trend_days - 1} days'
            GROUP BY bps.created_at::date
        ) cnt ON cnt.day = d::date
        ORDER BY d
    """
    daily_rows = await pool.fetch(daily_q)

    # 5) Crit/Skill rate verification
    rates_q = f"""
        SELECT
            ROUND(100.0 * SUM(crits_landed) / NULLIF(SUM(turns_alive), 0), 1) AS actual_crit,
            ROUND(100.0 * SUM(skills_activated) / NULLIF(SUM(turns_alive), 0), 1) AS actual_skill,
            SUM(turns_alive) AS total_turns
        FROM battle_pokemon_stats bps
        WHERE {where}
    """
    rates_row = await pool.fetchrow(rates_q, *params)

    return web.json_response({
        "filters": {"days": days, "battle_type": battle_type, "rarity": rarity, "tier": tier},
        "summary": {
            "total_battles": int(summary_row["total_battles"] or 0) if summary_row else 0,
            "today_battles": int(today_battles),
            "avg_rounds": float(summary_row["avg_rounds"] or 0) if summary_row else 0,
            "total_pokemon_used": int(summary_row["total_pokemon"] or 0) if summary_row else 0,
        },
        "pokemon_ranking": [
            {
                "pokemon_id": r["pokemon_id"], "name_ko": r["name_ko"], "emoji": r["emoji"] or "",
                "rarity": r["rarity"], "uses": r["uses"], "unique_users": r["unique_users"],
                "wins": r["wins"], "win_rate": float(r["win_rate"] or 0),
                "avg_damage": int(r["avg_damage"] or 0),
                "avg_kills": float(r["avg_kills"] or 0),
                "avg_deaths": float(r["avg_deaths"] or 0),
            }
            for r in pokemon_rows
        ],
        "rarity_stats": [
            {
                "rarity": r["rarity"], "uses": r["uses"], "wins": r["wins"],
                "win_rate": float(r["win_rate"] or 0),
                "avg_damage": int(r["avg_damage"] or 0),
            }
            for r in rarity_rows
        ],
        "daily_battles": [
            {"date": str(r["day"]), "total": r["total"], "ranked": r["ranked"], "normal": r["normal"]}
            for r in daily_rows
        ],
        "crit_skill_rates": {
            "actual_crit_rate": float(rates_row["actual_crit"] or 0) if rates_row else 0,
            "expected_crit_rate": 10.0,
            "actual_skill_rate": float(rates_row["actual_skill"] or 0) if rates_row else 0,
            "expected_skill_rate": 30.0,
            "total_turns": int(rates_row["total_turns"] or 0) if rates_row else 0,
        },
    })


def setup_routes(app):
    """Register analytics routes."""
    app.router.add_post("/api/analytics/pageview", api_analytics_pageview)
    app.router.add_post("/api/analytics/session", api_analytics_session)
    app.router.add_get("/api/admin/kpi", api_admin_kpi)
    app.router.add_get("/api/admin/battle-analytics", api_admin_battle_analytics)
