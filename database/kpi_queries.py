"""KPI report database queries."""

import asyncio
import logging
from datetime import timedelta
from database.connection import get_db
from database.stats_queries import get_economy_health, get_active_chat_rooms_top, get_dau_history
import config as _cfg

logger = logging.getLogger(__name__)


# ============================================================
# KPI Report Queries (일일/주간 리포트용)
# ============================================================

async def kpi_daily_snapshot(target_date=None) -> dict:
    """일일 KPI 스냅샷 — midnight_reset 직전에 호출. target_date로 특정 날짜 조회 가능."""
    pool = await get_db()
    now = _cfg.get_kst_now()
    if target_date:
        today = target_date
    else:
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    one_hour_ago = now - timedelta(hours=1)

    (
        dau_row, new_row, active_1h_row, total_users_row,
        spawn_row, shiny_row, mb_used_row,
        battle_row, ranked_row, bp_row,
        market_new_row, market_sold_row,
        sub_active_row, sub_revenue_row,
        economy,
        gacha_bp_row, gacha_dist_rows,
    ) = await asyncio.gather(
        # 유저
        pool.fetchrow("SELECT COUNT(DISTINCT user_id) as cnt FROM catch_attempts WHERE attempted_at >= $1", today),
        pool.fetchrow("SELECT COUNT(*) as cnt FROM users WHERE registered_at >= $1", today),
        pool.fetchrow("SELECT COUNT(*) as cnt FROM users WHERE last_active_at >= $1", one_hour_ago),
        pool.fetchrow("SELECT COUNT(*) as cnt FROM users"),
        # 스폰/포획
        pool.fetchrow(
            """SELECT COUNT(*) as spawns,
                      COUNT(caught_by_user_id) as catches,
                      COUNT(*) FILTER (WHERE is_shiny = 1) as shiny_spawns
               FROM spawn_log WHERE spawned_at >= $1""", today),
        pool.fetchrow(
            """SELECT COUNT(*) as cnt FROM spawn_log
               WHERE spawned_at >= $1 AND is_shiny = 1 AND caught_by_user_id IS NOT NULL""", today),
        pool.fetchrow(
            "SELECT COUNT(*) as cnt FROM catch_attempts WHERE used_master_ball = 1 AND attempted_at >= $1", today),
        # 배틀
        pool.fetchrow("SELECT COUNT(*) as cnt FROM battle_records WHERE created_at >= $1", today),
        pool.fetchrow(
            """SELECT COUNT(*) as cnt FROM battle_records
               WHERE created_at >= $1 AND bp_earned > 0
                 AND EXISTS (SELECT 1 FROM season_records)""", today),
        pool.fetchrow(
            "SELECT COALESCE(SUM(amount), 0) as total FROM bp_log WHERE amount > 0 AND created_at >= $1", today),
        # 거래소
        pool.fetchrow(
            "SELECT COUNT(*) as cnt FROM market_listings WHERE created_at >= $1", today),
        pool.fetchrow(
            "SELECT COUNT(*) as cnt FROM market_listings WHERE sold_at >= $1 AND status = 'sold'", today),
        # 구독
        pool.fetchrow(
            "SELECT COUNT(*) as cnt FROM subscriptions WHERE is_active = 1"),
        pool.fetchrow(
            """SELECT COALESCE(SUM(amount_usd), 0) as total
               FROM subscription_payments WHERE status = 'confirmed' AND confirmed_at >= $1""", today),
        # 경제
        get_economy_health(),
        # BP 뽑기 소비
        pool.fetchrow(
            "SELECT COALESCE(SUM(bp_spent), 0) as total, COUNT(*) as pulls FROM gacha_log WHERE created_at >= $1",
            today),
        # 뽑기 결과 분포
        pool.fetch(
            """SELECT result_key, COUNT(*) as cnt
               FROM gacha_log WHERE created_at >= $1
               GROUP BY result_key ORDER BY cnt DESC""", today),
    )

    spawns = spawn_row["spawns"] if spawn_row else 0
    catches = spawn_row["catches"] if spawn_row else 0
    catch_rate = round(catches / spawns * 100, 1) if spawns > 0 else 0

    # Top 채널
    top_chats = await get_active_chat_rooms_top(3)

    # 시간대별 활성 유저
    hourly_rows = await pool.fetch(
        """SELECT EXTRACT(HOUR FROM attempted_at AT TIME ZONE 'Asia/Seoul')::int as hr,
                  COUNT(DISTINCT user_id) as users
           FROM catch_attempts
           WHERE attempted_at >= $1 AND attempted_at < $1 + INTERVAL '1 day'
           GROUP BY hr ORDER BY hr""",
        today,
    )
    hourly = {r["hr"]: r["users"] for r in hourly_rows}

    # BP 소스별 분포
    try:
        bp_source_rows = await pool.fetch(
            """SELECT source,
                      COALESCE(SUM(amount) FILTER (WHERE amount > 0), 0) as earned,
                      COALESCE(SUM(ABS(amount)) FILTER (WHERE amount < 0), 0) as spent
               FROM bp_log WHERE created_at >= $1
               GROUP BY source ORDER BY earned DESC""",
            today,
        )
        bp_sources = {r["source"]: {"earned": int(r["earned"]), "spent": int(r["spent"])} for r in bp_source_rows}
    except Exception:
        bp_sources = {}

    # BP 총 소각 (shop + gacha 등 음수 합)
    try:
        bp_spent_row = await pool.fetchrow(
            "SELECT COALESCE(SUM(ABS(amount)), 0) as total FROM bp_log WHERE amount < 0 AND created_at >= $1",
            today,
        )
        bp_total_spent = int(bp_spent_row["total"]) if bp_spent_row else 0
    except Exception:
        bp_total_spent = 0

    return {
        "date": today.strftime("%Y-%m-%d"),
        "weekday": ["월", "화", "수", "목", "금", "토", "일"][today.weekday()],
        # 유저
        "dau": dau_row["cnt"] if dau_row else 0,
        "new_users": new_row["cnt"] if new_row else 0,
        "active_1h": active_1h_row["cnt"] if active_1h_row else 0,
        "total_users": total_users_row["cnt"] if total_users_row else 0,
        # 스폰/포획
        "spawns": spawns,
        "catches": catches,
        "catch_rate": catch_rate,
        "shiny_caught": shiny_row["cnt"] if shiny_row else 0,
        "mb_used": mb_used_row["cnt"] if mb_used_row else 0,
        # 배틀
        "battles": battle_row["cnt"] if battle_row else 0,
        "ranked_battles": ranked_row["cnt"] if ranked_row else 0,
        "bp_earned": int(bp_row["total"]) if bp_row else 0,
        # 거래소
        "market_new": market_new_row["cnt"] if market_new_row else 0,
        "market_sold": market_sold_row["cnt"] if market_sold_row else 0,
        # 구독
        "sub_active": sub_active_row["cnt"] if sub_active_row else 0,
        "sub_revenue_today": float(sub_revenue_row["total"]) if sub_revenue_row else 0,
        # 경제
        "economy": economy,
        # 채널
        "top_chats": top_chats,
        # 시간대별
        "hourly": hourly,
        # 뽑기 BP 소비
        "gacha_bp_spent": int(gacha_bp_row["total"]) if gacha_bp_row else 0,
        "gacha_pulls": int(gacha_bp_row["pulls"]) if gacha_bp_row else 0,
        "gacha_distribution": {r["result_key"]: r["cnt"] for r in gacha_dist_rows} if gacha_dist_rows else {},
        # BP 소스별
        "bp_sources": bp_sources,
        "bp_total_spent": bp_total_spent,
    }


# ─── 리포트 v2: 상세 데이터 수집 ──────────────────

async def report_new_users_detail(today) -> list[dict]:
    """오늘 가입한 유저 상세 (닉네임, 포획수, 배틀수)."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT u.user_id, u.display_name, u.username,
                  COALESCE(c.catches, 0) as catches,
                  COALESCE(b.battles, 0) as battles
           FROM users u
           LEFT JOIN (
               SELECT user_id, COUNT(*) as catches
               FROM catch_attempts WHERE attempted_at >= $1
               GROUP BY user_id
           ) c ON u.user_id = c.user_id
           LEFT JOIN (
               SELECT uid as user_id, COUNT(*) as battles
               FROM (
                   SELECT winner_id as uid FROM battle_records WHERE created_at >= $1
                   UNION ALL
                   SELECT loser_id as uid FROM battle_records WHERE created_at >= $1
               ) _bp
               GROUP BY uid
           ) b ON u.user_id = b.user_id
           WHERE u.registered_at >= $1
           ORDER BY c.catches DESC NULLS LAST
           LIMIT 20""",
        today,
    )
    return [dict(r) for r in rows]


async def report_churned_users(today) -> list[dict]:
    """최근 7일 활성이었으나 오늘 미접속 유저 (이탈 징후)."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT u.user_id, u.display_name, u.username,
                  u.last_active_at,
                  COALESCE(s.total_catches, 0) as week_catches
           FROM users u
           LEFT JOIN (
               SELECT user_id, COUNT(*) as total_catches
               FROM catch_attempts
               WHERE attempted_at >= $1 - INTERVAL '7 days'
               GROUP BY user_id
           ) s ON u.user_id = s.user_id
           WHERE u.last_active_at >= $1 - INTERVAL '7 days'
             AND u.last_active_at < $1
             AND NOT EXISTS (
                 SELECT 1 FROM catch_attempts ca
                 WHERE ca.user_id = u.user_id AND ca.attempted_at >= $1
             )
           ORDER BY s.total_catches DESC NULLS LAST
           LIMIT 10""",
        today,
    )
    return [dict(r) for r in rows]


async def report_top_active_users(today, limit: int = 10) -> list[dict]:
    """오늘 활동량 Top 유저 (포획 + 배틀)."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT u.user_id, u.display_name, u.username,
                  COALESCE(c.catches, 0) as catches,
                  COALESCE(b.battles, 0) as battles,
                  COALESCE(b.wins, 0) as wins,
                  COALESCE(c.catches, 0) + COALESCE(b.battles, 0) as total_actions
           FROM users u
           LEFT JOIN (
               SELECT user_id, COUNT(*) as catches
               FROM catch_attempts WHERE attempted_at >= $1
               GROUP BY user_id
           ) c ON u.user_id = c.user_id
           LEFT JOIN (
               SELECT uid as user_id, COUNT(*) as battles,
                      COUNT(*) FILTER (WHERE is_win) as wins
               FROM (
                   SELECT winner_id as uid, true as is_win FROM battle_records WHERE created_at >= $1
                   UNION ALL
                   SELECT loser_id as uid, false as is_win FROM battle_records WHERE created_at >= $1
               ) bp
               GROUP BY uid
           ) b ON u.user_id = b.user_id
           WHERE COALESCE(c.catches, 0) + COALESCE(b.battles, 0) > 0
           ORDER BY total_actions DESC
           LIMIT $2""",
        today, limit,
    )
    return [dict(r) for r in rows]


async def report_shiny_catches(today) -> list[dict]:
    """이로치 포획 요약 — Top 포획자 + 총 수."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT sl.caught_by_user_id as user_id,
                  u.display_name,
                  COUNT(*) as cnt
           FROM spawn_log sl
           LEFT JOIN users u ON sl.caught_by_user_id = u.user_id
           WHERE sl.spawned_at >= $1
             AND sl.is_shiny = 1
             AND sl.caught_by_user_id IS NOT NULL
           GROUP BY sl.caught_by_user_id, u.display_name
           ORDER BY cnt DESC
           LIMIT 10""",
        today,
    )
    return [dict(r) for r in rows]


async def report_new_user_sources(today) -> list[dict]:
    """신규 유저의 첫 포획 채널별 분류 (유입 소스 분석)."""
    pool = await get_db()
    rows = await pool.fetch(
        """WITH new_users AS (
               SELECT user_id FROM users WHERE registered_at >= $1
           ),
           first_catch AS (
               SELECT DISTINCT ON (ca.user_id)
                      ca.user_id, ss.chat_id
               FROM catch_attempts ca
               JOIN spawn_sessions ss ON ca.session_id = ss.id
               WHERE ca.user_id IN (SELECT user_id FROM new_users)
                 AND ca.attempted_at >= $1
               ORDER BY ca.user_id, ca.attempted_at ASC
           )
           SELECT cr.chat_id, cr.chat_title, COUNT(*) as cnt
           FROM first_catch fc
           JOIN chat_rooms cr ON fc.chat_id = cr.chat_id
           GROUP BY cr.chat_id, cr.chat_title
           ORDER BY cnt DESC
           LIMIT 10""",
        today,
    )
    return [dict(r) for r in rows]


async def report_market_trends(today) -> list[dict]:
    """오늘 거래소 거래 완료 건 (인기 매물, 가격)."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT ml.pokemon_name as name_ko, ml.pokemon_id,
                  ml.price_bp as price, ml.is_shiny,
                  seller.display_name as seller_name,
                  buyer.display_name as buyer_name
           FROM market_listings ml
           LEFT JOIN users seller ON ml.seller_id = seller.user_id
           LEFT JOIN users buyer ON ml.buyer_id = buyer.user_id
           WHERE ml.sold_at >= $1 AND ml.status = 'sold'
           ORDER BY ml.price_bp DESC
           LIMIT 15""",
        today,
    )
    return [dict(r) for r in rows]


async def report_battle_meta(today) -> list[dict]:
    """오늘 배틀에서 많이 사용된 포켓몬 (승자팀 기준)."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT pm.name_ko, pm.id as pokemon_id,
                  COUNT(*) as uses, 0.0 as win_rate
           FROM battle_records br
           JOIN battle_teams bt ON br.winner_id = bt.user_id AND bt.team_number = 1
           JOIN user_pokemon up ON bt.pokemon_instance_id = up.id
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE br.created_at >= $1
           GROUP BY pm.name_ko, pm.id
           ORDER BY uses DESC
           LIMIT 10""",
        today,
    )
    return [dict(r) for r in rows]


async def report_subscription_changes(today) -> dict:
    """오늘 구독 변동 (신규, 해지, 갱신)."""
    pool = await get_db()
    new_subs = await pool.fetch(
        """SELECT s.user_id, u.display_name, s.tier
           FROM subscriptions s
           JOIN users u ON s.user_id = u.user_id
           WHERE s.started_at >= $1 AND s.is_active = 1""",
        today,
    )
    expired = await pool.fetch(
        """SELECT s.user_id, u.display_name, s.tier
           FROM subscriptions s
           JOIN users u ON s.user_id = u.user_id
           WHERE s.expires_at >= $1 AND s.expires_at < $1 + INTERVAL '1 day'
             AND s.is_active = 0""",
        today,
    )
    return {
        "new": [dict(r) for r in new_subs],
        "expired": [dict(r) for r in expired],
    }


async def report_chat_health(today) -> list[dict]:
    """채팅방 활성도 (오늘 vs 어제 스폰 비교)."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT cr.chat_id, cr.chat_title, cr.member_count,
                  COALESCE(t.today_spawns, 0) as today_spawns,
                  COALESCE(y.yesterday_spawns, 0) as yesterday_spawns
           FROM chat_rooms cr
           LEFT JOIN (
               SELECT chat_id, COUNT(*) as today_spawns
               FROM spawn_log WHERE spawned_at >= $1
               GROUP BY chat_id
           ) t ON cr.chat_id = t.chat_id
           LEFT JOIN (
               SELECT chat_id, COUNT(*) as yesterday_spawns
               FROM spawn_log WHERE spawned_at >= $1 - INTERVAL '1 day'
                 AND spawned_at < $1
               GROUP BY chat_id
           ) y ON cr.chat_id = y.chat_id
           WHERE COALESCE(t.today_spawns, 0) + COALESCE(y.yesterday_spawns, 0) > 0
           ORDER BY t.today_spawns DESC
           LIMIT 15""",
        today,
    )
    return [dict(r) for r in rows]


async def report_checkin_stats(today) -> dict:
    """!돈 출석 체크 통계."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT COUNT(*) as checkins
           FROM bp_log
           WHERE source = 'daily_checkin'
             AND created_at >= $1""",
        today,
    )
    return {"checkins": row["checkins"] if row else 0}


async def kpi_weekly_snapshot() -> dict:
    """주간 KPI 스냅샷 — 월요일 리셋 시점에 호출."""
    pool = await get_db()
    now = _cfg.get_kst_now()
    week_start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)

    (
        wau_row, new_row,
        spawn_row, shiny_row, mb_row,
        battle_row, bp_row,
        market_row, sub_row,
    ) = await asyncio.gather(
        pool.fetchrow(
            "SELECT COUNT(DISTINCT user_id) as cnt FROM catch_attempts WHERE attempted_at >= $1", week_start),
        pool.fetchrow(
            "SELECT COUNT(*) as cnt FROM users WHERE registered_at >= $1", week_start),
        pool.fetchrow(
            """SELECT COUNT(*) as spawns, COUNT(caught_by_user_id) as catches
               FROM spawn_log WHERE spawned_at >= $1""", week_start),
        pool.fetchrow(
            """SELECT COUNT(*) as cnt FROM spawn_log
               WHERE spawned_at >= $1 AND is_shiny = 1 AND caught_by_user_id IS NOT NULL""", week_start),
        pool.fetchrow(
            "SELECT COUNT(*) as cnt FROM catch_attempts WHERE used_master_ball = 1 AND attempted_at >= $1",
            week_start),
        pool.fetchrow(
            "SELECT COUNT(*) as cnt FROM battle_records WHERE created_at >= $1", week_start),
        pool.fetchrow(
            "SELECT COALESCE(SUM(bp_earned), 0) as total FROM battle_records WHERE created_at >= $1", week_start),
        pool.fetchrow(
            "SELECT COUNT(*) as cnt FROM market_listings WHERE sold_at >= $1 AND status = 'sold'", week_start),
        pool.fetchrow(
            """SELECT COALESCE(SUM(amount_usd), 0) as total
               FROM subscription_payments WHERE status = 'confirmed' AND confirmed_at >= $1""", week_start),
    )

    dau_hist = await get_dau_history(7)

    # 일별 BP 뽑기 소비 (주간 그래프용)
    bp_daily_rows = await pool.fetch(
        """SELECT (created_at AT TIME ZONE 'Asia/Seoul')::date as d,
                  COALESCE(SUM(bp_spent), 0) as spent,
                  COUNT(*) as pulls
           FROM gacha_log
           WHERE created_at >= $1
           GROUP BY d ORDER BY d""",
        week_start,
    )
    bp_daily = [{"date": str(r["d"]), "spent": int(r["spent"]), "pulls": int(r["pulls"])} for r in bp_daily_rows]

    # 주간 총 뽑기 BP 소비
    gacha_week_row = await pool.fetchrow(
        "SELECT COALESCE(SUM(bp_spent), 0) as total, COUNT(*) as pulls FROM gacha_log WHERE created_at >= $1",
        week_start)

    spawns = spawn_row["spawns"] if spawn_row else 0
    catches = spawn_row["catches"] if spawn_row else 0

    return {
        "period": f"{week_start.strftime('%m/%d')} ~ {now.strftime('%m/%d')}",
        "dau_history": dau_hist,
        "wau": wau_row["cnt"] if wau_row else 0,
        "new_users": new_row["cnt"] if new_row else 0,
        "spawns": spawns,
        "catches": catches,
        "catch_rate": round(catches / spawns * 100, 1) if spawns > 0 else 0,
        "shiny_caught": shiny_row["cnt"] if shiny_row else 0,
        "mb_used": mb_row["cnt"] if mb_row else 0,
        "battles": battle_row["cnt"] if battle_row else 0,
        "bp_earned": int(bp_row["total"]) if bp_row else 0,
        "market_sold": market_row["cnt"] if market_row else 0,
        "sub_revenue": float(sub_row["total"]) if sub_row else 0,
        # 뽑기 BP 소비
        "gacha_bp_spent": int(gacha_week_row["total"]) if gacha_week_row else 0,
        "gacha_pulls": int(gacha_week_row["pulls"]) if gacha_week_row else 0,
        "bp_daily": bp_daily,
    }


async def save_kpi_snapshot(data: dict):
    """일일 KPI 스냅샷을 DB에 저장하고, D+1/D+7 리텐션을 계산."""
    pool = await get_db()
    today = _cfg.get_kst_now().date()

    # 오늘 활성 유저 ID 목록
    active_rows = await pool.fetch(
        """SELECT DISTINCT user_id FROM catch_attempts
           WHERE (attempted_at AT TIME ZONE 'Asia/Seoul')::date = $1""",
        today,
    )
    active_ids = [r["user_id"] for r in active_rows]

    # D+1 리텐션: 어제 활성 유저 중 오늘도 활성인 비율
    d1_retention = None
    yesterday_snap = await pool.fetchrow(
        "SELECT active_user_ids FROM kpi_daily_snapshots WHERE date = $1",
        today - timedelta(days=1),
    )
    if yesterday_snap and yesterday_snap["active_user_ids"]:
        y_set = set(yesterday_snap["active_user_ids"])
        if y_set:
            returned = len(y_set & set(active_ids))
            d1_retention = round(returned / len(y_set) * 100, 1)

    # D+7 리텐션: 7일 전 활성 유저 중 오늘도 활성인 비율
    d7_retention = None
    week_ago_snap = await pool.fetchrow(
        "SELECT active_user_ids FROM kpi_daily_snapshots WHERE date = $1",
        today - timedelta(days=7),
    )
    if week_ago_snap and week_ago_snap["active_user_ids"]:
        w_set = set(week_ago_snap["active_user_ids"])
        if w_set:
            returned = len(w_set & set(active_ids))
            d7_retention = round(returned / len(w_set) * 100, 1)

    bp_circ = data.get("economy", {}).get("bp_circulation", 0)
    bp_spent = data.get("bp_total_spent", 0)

    await pool.execute("""
        INSERT INTO kpi_daily_snapshots
            (date, dau, new_users, spawns, catches, shiny_caught,
             battles, ranked_battles, bp_earned, active_user_ids,
             d1_retention, d7_retention, bp_circulation, bp_total_spent)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
        ON CONFLICT (date) DO UPDATE SET
            dau = EXCLUDED.dau, new_users = EXCLUDED.new_users,
            spawns = EXCLUDED.spawns, catches = EXCLUDED.catches,
            shiny_caught = EXCLUDED.shiny_caught, battles = EXCLUDED.battles,
            ranked_battles = EXCLUDED.ranked_battles, bp_earned = EXCLUDED.bp_earned,
            active_user_ids = EXCLUDED.active_user_ids,
            d1_retention = EXCLUDED.d1_retention, d7_retention = EXCLUDED.d7_retention,
            bp_circulation = EXCLUDED.bp_circulation, bp_total_spent = EXCLUDED.bp_total_spent
    """,
        today, data.get("dau", 0), data.get("new_users", 0),
        data.get("spawns", 0), data.get("catches", 0), data.get("shiny_caught", 0),
        data.get("battles", 0), data.get("ranked_battles", 0), data.get("bp_earned", 0),
        active_ids, d1_retention, d7_retention, bp_circ, bp_spent,
    )

    return {"d1_retention": d1_retention, "d7_retention": d7_retention}


async def get_previous_snapshot() -> dict | None:
    """전일 KPI 스냅샷 조회."""
    pool = await get_db()
    yesterday = (_cfg.get_kst_now().date() - timedelta(days=1))
    row = await pool.fetchrow(
        "SELECT * FROM kpi_daily_snapshots WHERE date = $1", yesterday,
    )
    return dict(row) if row else None


async def get_retention_history(days: int = 14) -> list[dict]:
    """최근 N일간 리텐션 히스토리 조회."""
    pool = await get_db()
    rows = await pool.fetch("""
        SELECT date, dau, d1_retention, d7_retention
        FROM kpi_daily_snapshots
        WHERE date >= (NOW() AT TIME ZONE 'Asia/Seoul')::date - $1
        ORDER BY date
    """, days)
    return [dict(r) for r in rows]
