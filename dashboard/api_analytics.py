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


async def api_admin_tarot_analytics(request):
    """Admin: tarot reading analytics — 리테일 KPI."""
    from dashboard.api_admin import _admin_check
    if not await _admin_check(request):
        return web.json_response({"error": "Unauthorized"}, status=403)
    pool = await queries.get_db()

    # ── 1. Overall KPI ──
    total_readings = await pool.fetchval("SELECT COUNT(*) FROM tarot_readings") or 0
    total_users = await pool.fetchval("SELECT COUNT(DISTINCT user_id) FROM tarot_readings") or 0
    today_readings = await pool.fetchval(
        "SELECT COUNT(*) FROM tarot_readings WHERE reading_date = (NOW() AT TIME ZONE 'Asia/Seoul')::date"
    ) or 0
    today_users = await pool.fetchval(
        "SELECT COUNT(DISTINCT user_id) FROM tarot_readings WHERE reading_date = (NOW() AT TIME ZONE 'Asia/Seoul')::date"
    ) or 0
    week_readings = await pool.fetchval(
        "SELECT COUNT(*) FROM tarot_readings WHERE reading_date >= (NOW() AT TIME ZONE 'Asia/Seoul')::date - INTERVAL '6 days'"
    ) or 0
    week_users = await pool.fetchval(
        "SELECT COUNT(DISTINCT user_id) FROM tarot_readings WHERE reading_date >= (NOW() AT TIME ZONE 'Asia/Seoul')::date - INTERVAL '6 days'"
    ) or 0

    # ── 2. 일별 추이 (14일) ──
    daily = await pool.fetch("""
        SELECT d::date AS day,
               COALESCE(r.cnt, 0) AS readings,
               COALESCE(r.users, 0) AS users
        FROM generate_series(
            (NOW() AT TIME ZONE 'Asia/Seoul')::date - INTERVAL '13 days',
            (NOW() AT TIME ZONE 'Asia/Seoul')::date, '1 day'
        ) d
        LEFT JOIN (
            SELECT reading_date AS day, COUNT(*) AS cnt, COUNT(DISTINCT user_id) AS users
            FROM tarot_readings
            WHERE reading_date >= (NOW() AT TIME ZONE 'Asia/Seoul')::date - INTERVAL '13 days'
            GROUP BY reading_date
        ) r ON r.day = d::date
        ORDER BY d
    """)

    # ── 3. 신규 vs 기존 유저 ──
    # 신규: 가입 7일 이내에 타로를 쓴 유저
    new_vs_existing = await pool.fetch("""
        SELECT
            CASE WHEN tr.reading_date - u.registered_at::date <= 7 THEN '신규' ELSE '기존' END AS user_type,
            COUNT(DISTINCT tr.user_id) AS users,
            COUNT(*) AS readings
        FROM tarot_readings tr
        JOIN users u ON tr.user_id = u.user_id
        GROUP BY user_type
    """)

    # 신규 유저 타로 전환율: 최근 30일 가입자 중 타로 사용자 비율
    recent_signups = await pool.fetchval(
        "SELECT COUNT(*) FROM users WHERE created_at >= NOW() - INTERVAL '30 days'"
    ) or 0
    recent_signups_tarot = await pool.fetchval("""
        SELECT COUNT(DISTINCT tr.user_id)
        FROM tarot_readings tr
        JOIN users u ON tr.user_id = u.user_id
        WHERE u.registered_at >= NOW() - INTERVAL '30 days'
    """) or 0

    # ── 4. 성별 분포 ──
    by_gender = await pool.fetch("""
        SELECT COALESCE(tr.gender, u.gender, '미등록') AS gender,
               COUNT(DISTINCT tr.user_id) AS users,
               COUNT(*) AS readings
        FROM tarot_readings tr
        LEFT JOIN users u ON tr.user_id = u.user_id
        GROUP BY gender
        ORDER BY readings DESC
    """)

    # ── 5. 연령별 분포 (birth_date 기반) ──
    by_age = await pool.fetch("""
        SELECT
            CASE
                WHEN u.birth_date IS NULL THEN '미등록'
                WHEN EXTRACT(YEAR FROM AGE(u.birth_date)) < 20 THEN '10대'
                WHEN EXTRACT(YEAR FROM AGE(u.birth_date)) < 30 THEN '20대'
                WHEN EXTRACT(YEAR FROM AGE(u.birth_date)) < 40 THEN '30대'
                WHEN EXTRACT(YEAR FROM AGE(u.birth_date)) < 50 THEN '40대'
                ELSE '50대+'
            END AS age_group,
            COUNT(DISTINCT tr.user_id) AS users,
            COUNT(*) AS readings
        FROM tarot_readings tr
        LEFT JOIN users u ON tr.user_id = u.user_id
        GROUP BY age_group
        ORDER BY age_group
    """)

    # ── 6. 주제별 인기도 ──
    by_topic = await pool.fetch("""
        SELECT topic, COUNT(*) AS readings, COUNT(DISTINCT user_id) AS users
        FROM tarot_readings
        GROUP BY topic
        ORDER BY readings DESC
    """)

    # ── 7. 상황별 인기도 (situation) ──
    by_situation = await pool.fetch("""
        SELECT topic, situation, COUNT(*) AS readings
        FROM tarot_readings
        WHERE situation IS NOT NULL AND situation != ''
        GROUP BY topic, situation
        ORDER BY readings DESC
        LIMIT 20
    """)

    # ── 8. 연령×성별 크로스 ──
    age_gender_cross = await pool.fetch("""
        SELECT
            CASE
                WHEN u.birth_date IS NULL THEN '미등록'
                WHEN EXTRACT(YEAR FROM AGE(u.birth_date)) < 20 THEN '10대'
                WHEN EXTRACT(YEAR FROM AGE(u.birth_date)) < 30 THEN '20대'
                WHEN EXTRACT(YEAR FROM AGE(u.birth_date)) < 40 THEN '30대'
                WHEN EXTRACT(YEAR FROM AGE(u.birth_date)) < 50 THEN '40대'
                ELSE '50대+'
            END AS age_group,
            COALESCE(u.gender, '미등록') AS gender,
            COUNT(DISTINCT tr.user_id) AS users,
            COUNT(*) AS readings
        FROM tarot_readings tr
        LEFT JOIN users u ON tr.user_id = u.user_id
        GROUP BY age_group, gender
        ORDER BY age_group, gender
    """)

    # ── 9. 유저 타입 분석: 타로만 vs 게임도 ──
    # 타로 유저의 게임 활동 (배틀, 포획, 거래 등)
    user_engagement = await pool.fetch("""
        WITH tarot_users AS (
            SELECT DISTINCT user_id FROM tarot_readings
        )
        SELECT
            tu.user_id,
            u.username,
            COALESCE(u.gender, '?') AS gender,
            CASE
                WHEN u.birth_date IS NULL THEN '?'
                WHEN EXTRACT(YEAR FROM AGE(u.birth_date)) < 20 THEN '10대'
                WHEN EXTRACT(YEAR FROM AGE(u.birth_date)) < 30 THEN '20대'
                WHEN EXTRACT(YEAR FROM AGE(u.birth_date)) < 40 THEN '30대'
                WHEN EXTRACT(YEAR FROM AGE(u.birth_date)) < 50 THEN '40대'
                ELSE '50대+'
            END AS age_group,
            (SELECT COUNT(*) FROM tarot_readings tr2 WHERE tr2.user_id = tu.user_id) AS tarot_count,
            COALESCE(u.total_catches, 0) AS catches,
            COALESCE(u.battle_count, 0) AS battles,
            COALESCE(u.trade_count, 0) AS trades,
            u.registered_at::date AS joined
        FROM tarot_users tu
        JOIN users u ON tu.user_id = u.user_id
        ORDER BY tarot_count DESC
        LIMIT 50
    """)

    # ── 10. 유저 유형 분류 집계 ──
    user_types = await pool.fetch("""
        WITH tarot_users AS (
            SELECT DISTINCT user_id FROM tarot_readings
        ),
        classified AS (
            SELECT
                tu.user_id,
                CASE
                    WHEN COALESCE(u.battle_count, 0) = 0 AND COALESCE(u.total_catches, 0) <= 5 THEN '타로 전용'
                    WHEN COALESCE(u.battle_count, 0) >= 50 OR COALESCE(u.total_catches, 0) >= 100 THEN '허슬러'
                    ELSE '라이트 게이머'
                END AS user_type
            FROM tarot_users tu
            JOIN users u ON tu.user_id = u.user_id
        )
        SELECT user_type, COUNT(*) AS users
        FROM classified
        GROUP BY user_type
        ORDER BY users DESC
    """)

    # ── 11. 시간대별 (KST) ──
    by_hour = await pool.fetch("""
        SELECT EXTRACT(HOUR FROM created_at AT TIME ZONE 'Asia/Seoul')::int AS hour,
               COUNT(*) AS readings
        FROM tarot_readings
        GROUP BY hour
        ORDER BY hour
    """)

    # ── 12. 리텐션: 1회 vs 재방문 ──
    retention = await pool.fetch("""
        SELECT
            CASE
                WHEN cnt = 1 THEN '1회'
                WHEN cnt BETWEEN 2 AND 3 THEN '2~3회'
                WHEN cnt BETWEEN 4 AND 7 THEN '4~7회'
                ELSE '8회+'
            END AS freq,
            COUNT(*) AS users
        FROM (
            SELECT user_id, COUNT(*) AS cnt
            FROM tarot_readings
            GROUP BY user_id
        ) sub
        GROUP BY freq
        ORDER BY MIN(cnt)
    """)

    return web.json_response({
        "today": {
            "readings": today_readings, "users": today_users,
            "week_readings": week_readings, "week_users": week_users,
            "total_readings": total_readings, "total_users": total_users,
        },
        "daily": [{"date": str(r["day"]), "readings": r["readings"], "users": r["users"]} for r in daily],
        "new_vs_existing": [{"type": r["user_type"], "users": r["users"], "readings": r["readings"]} for r in new_vs_existing],
        "conversion": {"recent_signups": recent_signups, "tarot_users": recent_signups_tarot},
        "by_gender": [{"gender": {"M": "남성", "F": "여성"}.get(r["gender"], r["gender"]), "users": r["users"], "readings": r["readings"]} for r in by_gender],
        "by_age": [{"age": r["age_group"], "users": r["users"], "readings": r["readings"]} for r in by_age],
        "by_topic": [{"topic": r["topic"], "readings": r["readings"], "users": r["users"]} for r in by_topic],
        "by_situation": [{"topic": r["topic"], "situation": r["situation"], "readings": r["readings"]} for r in by_situation],
        "age_gender": [{"age": r["age_group"], "gender": {"M": "남성", "F": "여성"}.get(r["gender"], r["gender"]), "users": r["users"], "readings": r["readings"]} for r in age_gender_cross],
        "user_engagement": [
            {"user_id": r["user_id"], "username": r["username"], "gender": r["gender"],
             "age": r["age_group"], "tarot": r["tarot_count"], "catches": r["catches"],
             "battles": r["battles"], "trades": r["trades"], "joined": str(r["joined"])}
            for r in user_engagement
        ],
        "user_types": [{"type": r["user_type"], "users": r["users"]} for r in user_types],
        "by_hour": [{"hour": r["hour"], "readings": r["readings"]} for r in by_hour],
        "retention": [{"freq": r["freq"], "users": r["users"]} for r in retention],
    })


async def api_admin_overview(request):
    """Admin: unified overview dashboard — North Star + Tier 1~3."""
    from dashboard.api_admin import _admin_check
    if not await _admin_check(request):
        return web.json_response({"error": "Unauthorized"}, status=403)
    pool = await queries.get_db()

    import asyncio
    from datetime import timedelta
    today_ts = config.get_kst_now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_date = today_ts.date()
    one_hour_ago = config.get_kst_now() - timedelta(hours=1)

    # ── Parallel fetch: 오늘 실시간 + 히스토리 ──
    (
        dau_row, new_row, active_1h_row, total_users_row,
        spawn_row, battle_row, ranked_row,
        trade_row, tarot_row, camp_row,
        sub_active_row, sub_revenue_row,
        web_visitors_row,
        bp_earned_row, bp_spent_row,
        history_rows,
    ) = await asyncio.gather(
        # DAU
        pool.fetchrow("""SELECT COUNT(DISTINCT user_id) as cnt FROM (
            SELECT user_id FROM catch_attempts WHERE attempted_at >= $1
            UNION SELECT user_id FROM bp_log WHERE source = 'daily_checkin' AND created_at >= $1
        ) _""", today_ts),
        # 신규
        pool.fetchrow("SELECT COUNT(*) as cnt FROM users WHERE registered_at >= $1", today_ts),
        # 1시간 활성
        pool.fetchrow("SELECT COUNT(*) as cnt FROM users WHERE last_active_at >= $1", one_hour_ago),
        # 전체 유저
        pool.fetchrow("SELECT COUNT(*) as cnt FROM users"),
        # 포획
        pool.fetchrow("""SELECT COUNT(*) as spawns, COUNT(caught_by_user_id) as catches,
            COUNT(*) FILTER (WHERE is_shiny = 1) as shiny FROM spawn_log WHERE spawned_at >= $1""", today_ts),
        # 배틀
        pool.fetchrow("SELECT COUNT(*) as cnt FROM battle_records WHERE created_at >= $1", today_ts),
        pool.fetchrow("SELECT COUNT(*) as cnt FROM battle_records WHERE created_at >= $1 AND battle_type = 'ranked'", today_ts),
        # 거래
        pool.fetchrow("SELECT COUNT(*) as cnt FROM trades WHERE status = 'accepted' AND resolved_at >= $1", today_ts),
        # 타로
        pool.fetchrow("SELECT COUNT(*) as cnt, COUNT(DISTINCT user_id) as users FROM tarot_readings WHERE reading_date = $1", today_date),
        # 캠프
        pool.fetchrow("SELECT COUNT(DISTINCT user_id) as cnt FROM camp_placements WHERE placed_at >= $1", today_ts),
        # 구독
        pool.fetchrow("SELECT COUNT(*) as cnt FROM subscriptions WHERE is_active = 1"),
        pool.fetchrow("SELECT COALESCE(SUM(amount_usd), 0) as total FROM subscription_payments WHERE status = 'confirmed' AND confirmed_at >= $1", today_ts),
        # 웹 방문자
        pool.fetchrow("SELECT COUNT(DISTINCT COALESCE(user_id, -1*id)) as cnt FROM web_analytics WHERE event_type='pageview' AND created_at >= CURRENT_DATE"),
        # BP 유입/소각
        pool.fetchrow("SELECT COALESCE(SUM(amount), 0) as total FROM bp_log WHERE amount > 0 AND created_at >= $1", today_ts),
        pool.fetchrow("SELECT COALESCE(SUM(ABS(amount)), 0) as total FROM bp_log WHERE amount < 0 AND created_at >= $1", today_ts),
        # 14일 히스토리 (kpi_daily_snapshots)
        pool.fetch("""
            SELECT date, dau, new_users, spawns, catches, battles, ranked_battles,
                   COALESCE(d1_retention, 0) as d1_ret, COALESCE(d7_retention, 0) as d7_ret,
                   bp_earned, COALESCE(bp_total_spent, 0) as bp_spent
            FROM kpi_daily_snapshots
            WHERE date >= $1 ORDER BY date
        """, today_date - timedelta(days=13)),
    )

    dau = dau_row["cnt"] if dau_row else 0
    new_users = new_row["cnt"] if new_row else 0
    spawns = spawn_row["spawns"] if spawn_row else 0
    catches = spawn_row["catches"] if spawn_row else 0
    shiny = spawn_row["shiny"] if spawn_row else 0
    battles = battle_row["cnt"] if battle_row else 0
    ranked = ranked_row["cnt"] if ranked_row else 0
    trades = trade_row["cnt"] if trade_row else 0
    tarot_readings = tarot_row["cnt"] if tarot_row else 0
    tarot_users = tarot_row["users"] if tarot_row else 0
    camp_users = camp_row["cnt"] if camp_row else 0
    sub_active = sub_active_row["cnt"] if sub_active_row else 0
    sub_revenue = float(sub_revenue_row["total"]) if sub_revenue_row else 0
    web_visitors = web_visitors_row["cnt"] if web_visitors_row else 0
    bp_earned = int(bp_earned_row["total"]) if bp_earned_row else 0
    bp_spent = int(bp_spent_row["total"]) if bp_spent_row else 0

    # 리텐션: 어제 스냅샷에서
    yesterday = today_date - timedelta(days=1)
    ret_row = await pool.fetchrow(
        "SELECT COALESCE(d1_retention, 0) as d1, COALESCE(d7_retention, 0) as d7 FROM kpi_daily_snapshots WHERE date = $1",
        yesterday,
    )
    d1_ret = round(float(ret_row["d1"]) * 100, 1) if ret_row and ret_row["d1"] else 0
    d7_ret = round(float(ret_row["d7"]) * 100, 1) if ret_row and ret_row["d7"] else 0

    # 기능별 참여율 (오늘 DAU 대비)
    # 포획 유저, 배틀 유저, 거래 유저, 타로 유저, 캠프 유저
    catch_users = await pool.fetchval(
        "SELECT COUNT(DISTINCT user_id) FROM catch_attempts WHERE attempted_at >= $1", today_ts
    ) or 0
    battle_users = await pool.fetchval("""
        SELECT COUNT(DISTINCT uid) FROM (
            SELECT winner_id as uid FROM battle_records WHERE created_at >= $1
            UNION SELECT loser_id as uid FROM battle_records WHERE created_at >= $1
        ) _""", today_ts) or 0
    trade_users = await pool.fetchval("""
        SELECT COUNT(DISTINCT uid) FROM (
            SELECT from_user_id as uid FROM trades WHERE status='accepted' AND resolved_at >= $1
            UNION SELECT to_user_id as uid FROM trades WHERE status='accepted' AND resolved_at >= $1
        ) _""", today_ts) or 0

    safe_dau = max(dau, 1)
    adoption = [
        {"feature": "포획", "users": catch_users, "pct": round(100 * catch_users / safe_dau, 1)},
        {"feature": "배틀", "users": battle_users, "pct": round(100 * battle_users / safe_dau, 1)},
        {"feature": "거래", "users": trade_users, "pct": round(100 * trade_users / safe_dau, 1)},
        {"feature": "타로", "users": tarot_users, "pct": round(100 * tarot_users / safe_dau, 1)},
        {"feature": "캠프", "users": camp_users, "pct": round(100 * camp_users / safe_dau, 1)},
    ]
    adoption.sort(key=lambda x: x["pct"], reverse=True)

    # 히스토리 포맷
    history = [
        {
            "date": str(r["date"]),
            "dau": r["dau"], "new_users": r["new_users"],
            "spawns": r["spawns"], "catches": r["catches"],
            "battles": r["battles"], "ranked": r["ranked_battles"],
            "d1_ret": round(float(r["d1_ret"]) * 100, 1) if r["d1_ret"] else 0,
            "d7_ret": round(float(r["d7_ret"]) * 100, 1) if r["d7_ret"] else 0,
            "bp_earned": r["bp_earned"] or 0, "bp_spent": r["bp_spent"] or 0,
        }
        for r in history_rows
    ]

    # 어제 대비 변화율
    yesterday_snap = next((h for h in history if h["date"] == str(yesterday)), None)
    def delta(cur, prev_key):
        if not yesterday_snap or not yesterday_snap.get(prev_key):
            return None
        prev = yesterday_snap[prev_key]
        if prev == 0:
            return None
        return round((cur - prev) / prev * 100, 1)

    return web.json_response({
        "today": {
            "dau": dau, "dau_delta": delta(dau, "dau"),
            "new_users": new_users,
            "active_1h": active_1h_row["cnt"] if active_1h_row else 0,
            "total_users": total_users_row["cnt"] if total_users_row else 0,
            "d1_retention": d1_ret, "d7_retention": d7_ret,
            "web_visitors": web_visitors,
            "sub_active": sub_active, "sub_revenue": sub_revenue,
        },
        "engagement": {
            "spawns": spawns, "catches": catches, "shiny": shiny,
            "catch_rate": round(catches / max(spawns, 1) * 100, 1),
            "battles": battles, "ranked": ranked,
            "trades": trades,
            "tarot": tarot_readings, "tarot_users": tarot_users,
            "camp_users": camp_users,
        },
        "economy": {
            "bp_earned": bp_earned, "bp_spent": bp_spent,
            "bp_net": bp_earned - bp_spent,
        },
        "adoption": adoption,
        "history": history,
    })


def setup_routes(app):
    """Register analytics routes."""
    app.router.add_post("/api/analytics/pageview", api_analytics_pageview)
    app.router.add_post("/api/analytics/session", api_analytics_session)
    app.router.add_get("/api/admin/overview", api_admin_overview)
    app.router.add_get("/api/admin/kpi", api_admin_kpi)
    app.router.add_get("/api/admin/battle-analytics", api_admin_battle_analytics)
    app.router.add_get("/api/admin/tarot-analytics", api_admin_tarot_analytics)
