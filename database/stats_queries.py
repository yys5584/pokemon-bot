"""Statistics / ranking database queries."""

import asyncio
import logging
from datetime import timedelta
from database.connection import get_db
import config as _cfg

logger = logging.getLogger(__name__)


# ============================================================
# Dashboard / Stats Queries
# ============================================================

async def get_total_stats() -> dict:
    """Get overall bot statistics (single query)."""
    pool = await get_db()
    row = await pool.fetchrow("""
        SELECT
            (SELECT COUNT(*) FROM users) AS total_users,
            (SELECT COUNT(*) FROM chat_rooms) AS total_chats,
            (SELECT COUNT(*) FROM spawn_log) AS total_spawns,
            (SELECT COUNT(*) FROM spawn_log WHERE caught_by_user_id IS NOT NULL) AS total_catches,
            (SELECT COUNT(*) FROM trades WHERE status = 'accepted') AS total_trades,
            (SELECT COUNT(*) FROM user_pokemon WHERE is_active = 1 AND is_shiny = 1) AS total_shiny,
            (SELECT COUNT(*) FROM market_listings WHERE status = 'sold') AS market_trades,
            (SELECT COALESCE(SUM(price_bp), 0) FROM market_listings WHERE status = 'sold') AS market_volume_bp
    """)
    return dict(row) if row else {
        "total_users": 0, "total_chats": 0, "total_spawns": 0,
        "total_catches": 0, "total_trades": 0, "total_shiny": 0,
        "market_trades": 0, "market_volume_bp": 0,
    }


async def get_today_stats() -> dict:
    """Get today's spawn/catch counts."""
    pool = await get_db()
    today = _cfg.get_kst_now().replace(hour=0, minute=0, second=0, microsecond=0)
    spawns = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM spawn_log WHERE spawned_at >= $1", today
    )
    catches = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM spawn_log WHERE caught_by_user_id IS NOT NULL AND spawned_at >= $1",
        today,
    )
    return {
        "today_spawns": spawns["cnt"] if spawns else 0,
        "today_catches": catches["cnt"] if catches else 0,
    }


async def get_all_chat_rooms() -> list[dict]:
    """Get all chat rooms (active and inactive)."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT chat_id, chat_title, member_count, is_active,
                  joined_at, last_spawn_at, daily_spawn_count,
                  spawns_today_target, spawn_multiplier
           FROM chat_rooms ORDER BY joined_at DESC"""
    )
    return [dict(r) for r in rows]


async def get_top_pokemon_caught(limit: int = 10) -> list[dict]:
    """Get most caught Pokemon across all users."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT sl.pokemon_id, sl.pokemon_name, sl.pokemon_emoji, sl.rarity,
                  COUNT(*) as catch_count
           FROM spawn_log sl
           WHERE sl.caught_by_user_id IS NOT NULL
           GROUP BY sl.pokemon_id, sl.pokemon_name, sl.pokemon_emoji, sl.rarity
           ORDER BY catch_count DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_recent_spawns_global(limit: int = 50) -> list[dict]:
    """Get recent spawn logs across all chats."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT sl.*, cr.chat_title
           FROM spawn_log sl
           LEFT JOIN chat_rooms cr ON sl.chat_id = cr.chat_id
           ORDER BY sl.id DESC LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_user_rankings(limit: int = 20) -> list[dict]:
    """Get user rankings by pokedex count for dashboard (gen1, gen2, gen3, total)."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT u.user_id, u.display_name, u.username,
                  u.title, u.title_emoji, u.last_active_at,
                  COUNT(p.pokemon_id) FILTER (WHERE p.pokemon_id <= 151) as gen1_count,
                  COUNT(p.pokemon_id) FILTER (WHERE p.pokemon_id >= 152 AND p.pokemon_id <= 251) as gen2_count,
                  COUNT(p.pokemon_id) FILTER (WHERE p.pokemon_id >= 252 AND p.pokemon_id <= 386) as gen3_count,
                  COUNT(p.pokemon_id) FILTER (WHERE p.pokemon_id >= 387 AND p.pokemon_id <= 493) as gen4_count,
                  COUNT(p.pokemon_id) as pokedex_count
           FROM users u
           LEFT JOIN pokedex p ON u.user_id = p.user_id
           GROUP BY u.user_id, u.display_name, u.username, u.title, u.title_emoji, u.last_active_at
           HAVING COUNT(p.pokemon_id) > 0
           ORDER BY pokedex_count DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_rankings(limit: int = 5) -> list[dict]:
    """Get top N users by pokedex count."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT u.user_id, u.display_name, u.username, u.title, u.title_emoji,
                  COUNT(p.pokemon_id) as caught_count
           FROM users u
           LEFT JOIN pokedex p ON u.user_id = p.user_id
           GROUP BY u.user_id, u.display_name, u.username, u.title, u.title_emoji
           HAVING COUNT(p.pokemon_id) > 0
           ORDER BY caught_count DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def count_total_catches(user_id: int) -> int:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM spawn_log WHERE caught_by_user_id = $1",
        user_id,
    )
    return row["cnt"] if row else 0


async def count_common_catches(user_id: int) -> int:
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT COUNT(*) as cnt FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.user_id = $1 AND pm.rarity = 'common' AND up.is_active = 1""",
        user_id,
    )
    return row["cnt"] if row else 0


async def count_shiny_pokemon(user_id: int) -> int:
    """Count user's shiny pokemon."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM user_pokemon WHERE user_id = $1 AND is_shiny = 1 AND is_active = 1",
        user_id,
    )
    return row["cnt"] if row else 0


async def count_shiny_legendary(user_id: int) -> int:
    """Count user's shiny legendary pokemon."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT COUNT(*) as cnt FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.user_id = $1 AND up.is_shiny = 1 AND pm.rarity IN ('legendary', 'ultra_legendary') AND up.is_active = 1""",
        user_id,
    )
    return row["cnt"] if row else 0


async def count_rare_epic_legendary(user_id: int) -> int:
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT COUNT(*) as cnt FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.user_id = $1 AND pm.rarity IN ('epic', 'legendary', 'ultra_legendary') AND up.is_active = 1""",
        user_id,
    )
    return row["cnt"] if row else 0


async def count_completed_trades(user_id: int) -> int:
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT COUNT(*) as cnt FROM trades
           WHERE (from_user_id = $1 OR to_user_id = $1) AND status = 'accepted'""",
        user_id,
    )
    return row["cnt"] if row else 0


# ============================================================
# Fun KPI Queries (Dashboard)
# ============================================================

async def get_rare_pokemon_holders(limit: int = 20) -> list[dict]:
    """에픽+전설 보유자 랭킹 — 보유 수 기준."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT u.display_name, u.title, u.title_emoji,
                  SUM(CASE WHEN pm.rarity = 'epic' THEN 1 ELSE 0 END) as epic_count,
                  SUM(CASE WHEN pm.rarity = 'legendary' THEN 1 ELSE 0 END) as legendary_count,
                  SUM(CASE WHEN pm.rarity = 'ultra_legendary' THEN 1 ELSE 0 END) as ultra_legendary_count,
                  COUNT(*) as total
           FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           JOIN users u ON up.user_id = u.user_id
           WHERE pm.rarity IN ('epic', 'legendary', 'ultra_legendary') AND up.is_active = 1
           GROUP BY up.user_id, u.display_name, u.title, u.title_emoji
           ORDER BY ultra_legendary_count DESC, legendary_count DESC, epic_count DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_shiny_holders(limit: int = 20) -> list[dict]:
    """이로치 보유자 랭킹."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT u.display_name, COUNT(*) as shiny_count
           FROM user_pokemon up
           JOIN users u ON up.user_id = u.user_id
           WHERE up.is_shiny = 1 AND up.is_active = 1
           GROUP BY up.user_id, u.display_name
           HAVING COUNT(*) > 0
           ORDER BY shiny_count DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_global_catch_rate() -> float:
    """전체 포획률 (%)."""
    pool = await get_db()
    total = await pool.fetchrow("SELECT COUNT(*) as cnt FROM spawn_log")
    caught = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM spawn_log WHERE caught_by_user_id IS NOT NULL"
    )
    t = total["cnt"] if total else 0
    c = caught["cnt"] if caught else 0
    return round(c / t * 100, 1) if t > 0 else 0.0


async def get_escape_masters(limit: int = 5) -> list[dict]:
    """도망 장인 TOP N — 잡기 실패 많은 유저."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT u.display_name, ts.catch_fail_count
           FROM user_title_stats ts
           JOIN users u ON ts.user_id = u.user_id
           WHERE ts.catch_fail_count > 0
           ORDER BY ts.catch_fail_count DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_night_owls(limit: int = 5) -> list[dict]:
    """올빼미족 TOP N — 심야 포획 많은 유저."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT u.display_name, ts.midnight_catch_count
           FROM user_title_stats ts
           JOIN users u ON ts.user_id = u.user_id
           WHERE ts.midnight_catch_count > 0
           ORDER BY ts.midnight_catch_count DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_masterball_rich(limit: int = 5) -> list[dict]:
    """마볼 부자 TOP N."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT display_name, master_balls
           FROM users
           WHERE master_balls > 0
           ORDER BY master_balls DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_pokeball_addicts(limit: int = 5) -> list[dict]:
    """포볼 중독자 TOP N — 오늘 보너스 캐치 많은 유저."""
    pool = await get_db()
    today = _cfg.get_kst_today()
    rows = await pool.fetch(
        """SELECT u.display_name, cl.bonus_catches
           FROM catch_limits cl
           JOIN users u ON cl.user_id = u.user_id
           WHERE cl.date = $1 AND cl.bonus_catches > 0
           ORDER BY cl.bonus_catches DESC
           LIMIT $2""",
        today, limit,
    )
    return [dict(r) for r in rows]


async def get_user_catch_rates(limit: int = 10) -> list[dict]:
    """개인 포획률 — 시도 대비 성공률 (최소 5회 이상 시도)."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT u.display_name,
                  COUNT(*) as attempts,
                  SUM(CASE WHEN ss.caught_by_user_id = ca.user_id THEN 1 ELSE 0 END) as catches,
                  ROUND(
                      (CAST(SUM(CASE WHEN ss.caught_by_user_id = ca.user_id THEN 1 ELSE 0 END) AS NUMERIC)
                      / COUNT(*) * 100)::NUMERIC, 1
                  ) as catch_rate
           FROM catch_attempts ca
           JOIN spawn_sessions ss ON ca.session_id = ss.id
           JOIN users u ON ca.user_id = u.user_id
           GROUP BY ca.user_id, u.display_name
           HAVING COUNT(*) >= 5
           ORDER BY catch_rate DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_trade_kings(limit: int = 5) -> list[dict]:
    """교환왕 TOP N."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT u.display_name, COUNT(*) as trade_count
           FROM (
               SELECT from_user_id as uid FROM trades WHERE status = 'accepted'
               UNION ALL
               SELECT to_user_id as uid FROM trades WHERE status = 'accepted'
           ) t
           JOIN users u ON t.uid = u.user_id
           GROUP BY t.uid, u.display_name
           ORDER BY trade_count DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_most_escaped_pokemon(limit: int = 5) -> list[dict]:
    """도망 많은 포켓몬 TOP N."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT pokemon_name, pokemon_emoji, rarity,
                  COUNT(*) as escape_count
           FROM spawn_log
           WHERE caught_by_user_id IS NULL
           GROUP BY pokemon_id, pokemon_name, pokemon_emoji, rarity
           ORDER BY escape_count DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_love_leaders(limit: int = 5) -> list[dict]:
    """사랑꾼 TOP N — love_count 높은 유저."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT u.display_name, ts.love_count
           FROM user_title_stats ts
           JOIN users u ON ts.user_id = u.user_id
           WHERE ts.love_count > 0
           ORDER BY ts.love_count DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_total_master_balls_used() -> int:
    """총 마스터볼 사용량."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM catch_attempts WHERE used_master_ball = 1"
    )
    return row["cnt"] if row else 0


async def get_longest_streak_user() -> dict | None:
    """최장 연속출석 유저."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT u.display_name, ts.login_streak
           FROM user_title_stats ts
           JOIN users u ON ts.user_id = u.user_id
           WHERE ts.login_streak > 0
           ORDER BY ts.login_streak DESC
           LIMIT 1"""
    )
    return dict(row) if row else None


# ─── Dashboard: DAU / Retention / Economy ───

async def get_dau() -> int:
    """오늘 활동한 유저 수 (포획 시도 기준)."""
    pool = await get_db()
    today = _cfg.get_kst_now().replace(hour=0, minute=0, second=0, microsecond=0)
    row = await pool.fetchrow(
        "SELECT COUNT(DISTINCT user_id) as cnt FROM catch_attempts WHERE attempted_at >= $1",
        today,
    )
    return row["cnt"] if row else 0


async def get_dau_history(days: int = 7) -> list[dict]:
    """최근 N일 DAU 추이."""
    pool = await get_db()
    since = _cfg.get_kst_now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)
    rows = await pool.fetch(
        """SELECT attempted_at::date as day, COUNT(DISTINCT user_id) as dau
           FROM catch_attempts
           WHERE attempted_at >= $1
           GROUP BY day ORDER BY day""",
        since,
    )
    return [{"day": str(r["day"]), "dau": r["dau"]} for r in rows]


async def get_retention_d1() -> dict:
    """D+1 리텐션: 출시일(3/1) 이후 가입자 중 다음날도 활동한 비율.
    오늘 가입자는 아직 D+1이 안 왔으므로 어제까지만 대상."""
    pool = await get_db()
    from datetime import date as dt_date
    launch = dt_date(2026, 3, 1)
    yesterday = _cfg.get_kst_now().date() - timedelta(days=1)
    row = await pool.fetchrow(
        """WITH new_users AS (
               SELECT user_id, registered_at::date as reg_date
               FROM users
               WHERE registered_at::date >= $1
                 AND registered_at::date <= $2
           ),
           next_day_active AS (
               SELECT DISTINCT nu.user_id
               FROM new_users nu
               JOIN catch_attempts ca ON nu.user_id = ca.user_id
                   AND ca.attempted_at::date = nu.reg_date + INTERVAL '1 day'
           )
           SELECT
               (SELECT COUNT(*) FROM new_users) as total_new,
               (SELECT COUNT(*) FROM next_day_active) as retained
        """,
        launch, yesterday,
    )
    total = row["total_new"] if row else 0
    retained = row["retained"] if row else 0
    rate = round(retained / total * 100, 1) if total > 0 else 0
    return {"total_new": total, "retained": retained, "rate": rate}


async def get_economy_health() -> dict:
    """경제 건강도: 마볼/하볼/BP 유통량 및 소비량."""
    pool = await get_db()
    mb, hb, bp, mb_used, hb_used, bp_spent = await asyncio.gather(
        pool.fetchrow("SELECT COALESCE(SUM(master_balls),0) as total, COALESCE(AVG(master_balls),0) as avg FROM users WHERE master_balls > 0"),
        pool.fetchrow("SELECT COALESCE(SUM(hyper_balls),0) as total, COALESCE(AVG(hyper_balls),0) as avg FROM users WHERE hyper_balls > 0"),
        pool.fetchrow("SELECT COALESCE(SUM(battle_points),0) as total, COALESCE(AVG(battle_points),0) as avg FROM users WHERE battle_points > 0"),
        pool.fetchrow("SELECT COUNT(*) as cnt FROM catch_attempts WHERE used_master_ball = 1"),
        pool.fetchrow("SELECT COUNT(*) as cnt FROM catch_attempts WHERE used_hyper_ball = 1"),
        pool.fetchrow("SELECT COALESCE(SUM(bp_earned),0) as total FROM battle_records"),
    )
    return {
        "master_balls_circulation": int(mb["total"]),
        "master_balls_avg": round(float(mb["avg"]), 1),
        "master_balls_used_total": mb_used["cnt"] if mb_used else 0,
        "hyper_balls_circulation": int(hb["total"]),
        "hyper_balls_avg": round(float(hb["avg"]), 1),
        "hyper_balls_used_total": hb_used["cnt"] if hb_used else 0,
        "bp_circulation": int(bp["total"]),
        "bp_avg": round(float(bp["avg"]), 1),
        "bp_spent_total": int(bp_spent["total"]),
    }


async def get_active_chat_rooms_top(limit: int = 5) -> list[dict]:
    """오늘 포획이 가장 많은 활성 채팅방 TOP N (평균 참여자 포함)."""
    pool = await get_db()
    today = _cfg.get_kst_now().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = await pool.fetch(
        """SELECT cr.chat_id, cr.chat_title, cr.member_count, cr.invite_link,
                  COUNT(sl.id) as today_spawns,
                  COUNT(sl.caught_by_user_id) as today_catches,
                  ROUND(AVG(sl.participants)::numeric, 1) as avg_participants
           FROM chat_rooms cr
           LEFT JOIN spawn_log sl ON cr.chat_id = sl.chat_id AND sl.spawned_at >= $1
           WHERE cr.is_active = 1 AND cr.chat_title IS NOT NULL
           GROUP BY cr.chat_id, cr.chat_title, cr.member_count, cr.invite_link
           HAVING COUNT(sl.caught_by_user_id) > 0
           ORDER BY today_catches DESC
           LIMIT $2""",
        today, limit,
    )
    return [dict(r) for r in rows]


# ============================================================
# Bulk / Transaction Helpers (optimization)
# ============================================================

async def count_total_catches_bulk(user_ids: list[int]) -> dict[int, int]:
    """Batch count total catches for multiple users at once."""
    if not user_ids:
        return {}
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT caught_by_user_id AS user_id, COUNT(*) AS cnt
           FROM spawn_log
           WHERE caught_by_user_id = ANY($1::bigint[])
           GROUP BY caught_by_user_id""",
        user_ids,
    )
    return {r["user_id"]: r["cnt"] for r in rows}


async def count_pokedex_bulk(user_ids: list[int]) -> dict[int, int]:
    """유저별 도감 보유 종 수 (뉴비 스폰 티어 판별용)."""
    if not user_ids:
        return {}
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT user_id, COUNT(DISTINCT pokemon_id) AS cnt
           FROM user_pokemon
           WHERE user_id = ANY($1::bigint[])
           GROUP BY user_id""",
        user_ids,
    )
    return {r["user_id"]: r["cnt"] for r in rows}
