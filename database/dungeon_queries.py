"""Dungeon system database queries."""

import json
import logging
from database.connection import get_db

logger = logging.getLogger(__name__)


# ── 입장권 ──────────────────────────────────────────────

async def get_dungeon_tickets(user_id: int) -> int:
    pool = await get_db()
    val = await pool.fetchval(
        "SELECT dungeon_tickets FROM users WHERE user_id = $1", user_id
    )
    return val or 0


async def deduct_dungeon_ticket(user_id: int) -> bool:
    """Atomic ticket deduction. Returns False if 0 tickets."""
    pool = await get_db()
    row = await pool.fetchrow(
        "UPDATE users SET dungeon_tickets = dungeon_tickets - 1 "
        "WHERE user_id = $1 AND dungeon_tickets > 0 "
        "RETURNING dungeon_tickets",
        user_id,
    )
    return row is not None


async def add_dungeon_tickets(user_id: int, count: int):
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET dungeon_tickets = dungeon_tickets + $1 WHERE user_id = $2",
        count, user_id,
    )


async def get_bought_today(user_id: int) -> int:
    pool = await get_db()
    val = await pool.fetchval(
        "SELECT dungeon_tickets_bought_today FROM users WHERE user_id = $1", user_id
    )
    return val or 0


async def buy_ticket_with_bp(user_id: int, bp_cost: int) -> bool:
    """Atomic: deduct BP + increment bought_today + add ticket."""
    pool = await get_db()
    row = await pool.fetchrow(
        "UPDATE users SET battle_points = battle_points - $1, "
        "dungeon_tickets = dungeon_tickets + 1, "
        "dungeon_tickets_bought_today = dungeon_tickets_bought_today + 1 "
        "WHERE user_id = $2 AND battle_points >= $1 "
        "RETURNING battle_points",
        bp_cost, user_id,
    )
    return row is not None


# ── 런 관리 ──────────────────────────────────────────────

async def create_dungeon_run(
    user_id: int,
    pokemon_instance_id: int,
    pokemon_id: int,
    pokemon_name: str,
    is_shiny: bool,
    iv_grade: str,
    rarity: str,
    theme: str,
    current_hp: int,
    max_hp: int,
) -> int:
    """Create a new dungeon run. Returns run ID."""
    pool = await get_db()
    run_id = await pool.fetchval(
        "INSERT INTO dungeon_runs "
        "(user_id, pokemon_instance_id, pokemon_id, pokemon_name, is_shiny, "
        "iv_grade, rarity, floor_reached, theme, current_hp, max_hp, status, season_key) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,0,$8,$9,$10,'active',$11) RETURNING id",
        user_id, pokemon_instance_id, pokemon_id, pokemon_name, is_shiny,
        iv_grade, rarity, theme, current_hp, max_hp,
        _current_season_key(),
    )
    # 시즌 런 카운트 증가
    await pool.execute(
        "UPDATE users SET dungeon_season_runs = dungeon_season_runs + 1 WHERE user_id = $1",
        user_id,
    )
    return run_id


async def get_active_run(user_id: int) -> dict | None:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT * FROM dungeon_runs WHERE user_id = $1 AND status = 'active' "
        "ORDER BY started_at DESC LIMIT 1",
        user_id,
    )
    if not row:
        return None
    d = dict(row)
    if isinstance(d.get("buffs_json"), str):
        d["buffs_json"] = json.loads(d["buffs_json"])
    return d


async def update_run_progress(
    run_id: int, floor: int, current_hp: int, buffs_json: list
):
    pool = await get_db()
    await pool.execute(
        "UPDATE dungeon_runs SET floor_reached = $1, current_hp = $2, "
        "buffs_json = $3::jsonb WHERE id = $4",
        floor, current_hp, json.dumps(buffs_json, ensure_ascii=False), run_id,
    )


async def update_run_skips(run_id: int, skips_used: int):
    pool = await get_db()
    await pool.execute(
        "UPDATE dungeon_runs SET skips_used = $1 WHERE id = $2",
        skips_used, run_id,
    )


async def end_run(run_id: int, floor_reached: int, bp_earned: int, fragments_earned: int,
                  death_enemy: str = None, death_enemy_rarity: str = None, death_floor: int = None):
    pool = await get_db()
    await pool.execute(
        "UPDATE dungeon_runs SET status = 'completed', floor_reached = $1, "
        "bp_earned = $2, fragments_earned = $3, ended_at = NOW(), "
        "death_enemy = $5, death_enemy_rarity = $6, death_floor = $7 WHERE id = $4",
        floor_reached, bp_earned, fragments_earned, run_id,
        death_enemy, death_enemy_rarity, death_floor,
    )


async def abandon_run(run_id: int):
    pool = await get_db()
    await pool.execute(
        "UPDATE dungeon_runs SET status = 'abandoned', ended_at = NOW() WHERE id = $1",
        run_id,
    )


# ── 기록/랭킹 ──────────────────────────────────────────

async def update_pokemon_record(
    user_id: int, pokemon_instance_id: int, floor: int, theme: str
):
    pool = await get_db()
    await pool.execute(
        "INSERT INTO dungeon_pokemon_records (user_id, pokemon_instance_id, best_floor, best_theme, updated_at) "
        "VALUES ($1, $2, $3, $4, NOW()) "
        "ON CONFLICT (user_id, pokemon_instance_id) DO UPDATE SET "
        "best_floor = GREATEST(dungeon_pokemon_records.best_floor, EXCLUDED.best_floor), "
        "best_theme = CASE WHEN EXCLUDED.best_floor > dungeon_pokemon_records.best_floor "
        "THEN EXCLUDED.best_theme ELSE dungeon_pokemon_records.best_theme END, "
        "updated_at = NOW()",
        user_id, pokemon_instance_id, floor, theme,
    )


async def update_user_best_floor(user_id: int, floor: int) -> bool:
    """Update user's all-time best floor. Returns True if new record."""
    pool = await get_db()
    old = await pool.fetchval(
        "SELECT dungeon_best_floor FROM users WHERE user_id = $1", user_id
    )
    if floor > (old or 0):
        await pool.execute(
            "UPDATE users SET dungeon_best_floor = $1 WHERE user_id = $2",
            floor, user_id,
        )
        return True
    return False


async def get_user_best_floor(user_id: int) -> int:
    pool = await get_db()
    val = await pool.fetchval(
        "SELECT dungeon_best_floor FROM users WHERE user_id = $1", user_id
    )
    return val or 0


async def get_weekly_ranking(limit: int = 30) -> list[dict]:
    """Current week's ranking by highest floor reached (best per user)."""
    pool = await get_db()
    rows = await pool.fetch(
        "SELECT DISTINCT ON (dr.user_id) "
        "dr.user_id, u.display_name, dr.pokemon_name, dr.is_shiny, "
        "dr.iv_grade, dr.floor_reached, dr.theme "
        "FROM dungeon_runs dr "
        "JOIN users u ON dr.user_id = u.user_id "
        "WHERE dr.season_key = $1 AND dr.status = 'completed' "
        "ORDER BY dr.user_id, dr.floor_reached DESC, dr.ended_at ASC",
        _current_season_key(),
    )
    # 층수 내림차순 정렬
    result = [dict(r) for r in rows]
    result.sort(key=lambda x: x["floor_reached"], reverse=True)
    return result[:limit]


async def get_user_rank(user_id: int) -> int | None:
    """Get user's rank in current season."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT rank FROM ("
        "  SELECT user_id, RANK() OVER (ORDER BY floor_reached DESC, ended_at ASC) as rank "
        "  FROM dungeon_runs WHERE season_key = $1 AND status = 'completed'"
        ") sub WHERE user_id = $2",
        _current_season_key(), user_id,
    )
    return int(row["rank"]) if row else None


async def get_pokemon_dungeon_record(user_id: int, instance_id: int) -> int:
    pool = await get_db()
    val = await pool.fetchval(
        "SELECT best_floor FROM dungeon_pokemon_records "
        "WHERE user_id = $1 AND pokemon_instance_id = $2",
        user_id, instance_id,
    )
    return val or 0


# ── 일일 리셋 ──────────────────────────────────────────

async def reset_daily_dungeon(daily_tickets: dict[int, int] | None = None):
    """Reset bought_today counter and grant daily tickets.
    daily_tickets: {user_id: ticket_count} map. If None, grants 1 to all.
    """
    pool = await get_db()
    # 구매 카운트 리셋
    await pool.execute(
        "UPDATE users SET dungeon_tickets_bought_today = 0 WHERE dungeon_tickets_bought_today > 0"
    )
    if daily_tickets:
        # 구독별 차등 지급
        for uid, count in daily_tickets.items():
            await pool.execute(
                "UPDATE users SET dungeon_tickets = dungeon_tickets + $1 WHERE user_id = $2",
                count, uid,
            )
    else:
        # 전체 유저 기본 1장 지급
        await pool.execute(
            "UPDATE users SET dungeon_tickets = dungeon_tickets + 1"
        )


async def grant_daily_tickets_by_tier():
    """Grant daily dungeon tickets based on subscription tier."""
    import config

    pool = await get_db()

    # 구매 카운트 리셋
    await pool.execute(
        "UPDATE users SET dungeon_tickets_bought_today = 0 WHERE dungeon_tickets_bought_today > 0"
    )

    # 전체 유저 기본 1장
    await pool.execute("UPDATE users SET dungeon_tickets = dungeon_tickets + 1")

    # 구독자 추가 지급
    try:
        from database.subscription_queries import get_all_active_subscriptions
        subs = await get_all_active_subscriptions()
        for sub in subs:
            tier = sub.get("tier", "basic")
            extra = config.DUNGEON_DAILY_TICKETS.get(tier, 1) - 1  # 기본 1장은 이미 지급
            if extra > 0:
                await pool.execute(
                    "UPDATE users SET dungeon_tickets = dungeon_tickets + $1 WHERE user_id = $2",
                    extra, sub["user_id"],
                )
    except Exception as e:
        logger.warning(f"grant_daily_tickets_by_tier error: {e}")


# ── 유틸 ──────────────────────────────────────────────

def _current_season_key() -> str:
    """Weekly season key: 'W2026-12' (year-week)."""
    import datetime as _dt
    kst = _dt.timezone(_dt.timedelta(hours=9))
    now = _dt.datetime.now(kst)
    year, week, _ = now.isocalendar()
    return f"W{year}-{week:02d}"
