"""Weekly Boss DB queries."""

import logging
from database.connection import get_db

logger = logging.getLogger(__name__)


async def create_boss(week_key: str, pokemon_id: int, pokemon_name: str,
                      boss_types: list[str], max_hp: int) -> dict | None:
    pool = await get_db()
    row = await pool.fetchrow(
        """INSERT INTO weekly_boss (week_key, pokemon_id, pokemon_name, boss_types, max_hp, current_hp)
           VALUES ($1, $2, $3, $4, $5, $5)
           ON CONFLICT (week_key) DO NOTHING
           RETURNING *""",
        week_key, pokemon_id, pokemon_name, boss_types, max_hp,
    )
    return dict(row) if row else None


async def get_boss(week_key: str) -> dict | None:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT * FROM weekly_boss WHERE week_key = $1", week_key,
    )
    return dict(row) if row else None


async def get_current_boss() -> dict | None:
    """Get the most recent (active) boss."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT * FROM weekly_boss ORDER BY created_at DESC LIMIT 1",
    )
    return dict(row) if row else None


async def deal_damage(week_key: str, amount: int) -> dict | None:
    """Atomic HP deduction. Returns updated boss row."""
    pool = await get_db()
    row = await pool.fetchrow(
        """UPDATE weekly_boss
           SET current_hp = GREATEST(0, current_hp - $2),
               defeated = CASE WHEN current_hp - $2 <= 0 THEN TRUE ELSE defeated END,
               defeated_at = CASE WHEN current_hp - $2 <= 0 AND defeated_at IS NULL THEN NOW() ELSE defeated_at END
           WHERE week_key = $1
           RETURNING *""",
        week_key, amount,
    )
    return dict(row) if row else None


async def record_attack(week_key: str, user_id: int, damage: int, attack_date: str) -> bool:
    """Record daily attack. Returns False if already attacked today."""
    pool = await get_db()
    try:
        await pool.execute(
            """INSERT INTO boss_attacks (week_key, user_id, damage_dealt, attack_date)
               VALUES ($1, $2, $3, $4::date)""",
            week_key, user_id, damage, attack_date,
        )
    except Exception:
        # unique constraint violation = already attacked today
        return False

    # Update weekly aggregate
    await pool.execute(
        """INSERT INTO boss_weekly_damage (week_key, user_id, total_damage, attack_count)
           VALUES ($1, $2, $3, 1)
           ON CONFLICT (week_key, user_id) DO UPDATE
           SET total_damage = boss_weekly_damage.total_damage + $3,
               attack_count = boss_weekly_damage.attack_count + 1""",
        week_key, user_id, damage,
    )
    return True


async def has_attacked_today(week_key: str, user_id: int, attack_date: str) -> bool:
    pool = await get_db()
    row = await pool.fetchval(
        "SELECT 1 FROM boss_attacks WHERE week_key=$1 AND user_id=$2 AND attack_date=$3::date",
        week_key, user_id, attack_date,
    )
    return row is not None


async def get_today_damage(week_key: str, user_id: int, attack_date: str) -> int:
    pool = await get_db()
    return await pool.fetchval(
        "SELECT damage_dealt FROM boss_attacks WHERE week_key=$1 AND user_id=$2 AND attack_date=$3::date",
        week_key, user_id, attack_date,
    ) or 0


async def get_weekly_damage(week_key: str, user_id: int) -> dict:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT total_damage, attack_count FROM boss_weekly_damage WHERE week_key=$1 AND user_id=$2",
        week_key, user_id,
    )
    if row:
        return {"total_damage": row["total_damage"], "attack_count": row["attack_count"]}
    return {"total_damage": 0, "attack_count": 0}


async def get_weekly_ranking(week_key: str, limit: int = 30) -> list[dict]:
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT bwd.user_id, bwd.total_damage, bwd.attack_count,
                  u.display_name
           FROM boss_weekly_damage bwd
           JOIN users u ON u.user_id = bwd.user_id
           WHERE bwd.week_key = $1
           ORDER BY bwd.total_damage DESC
           LIMIT $2""",
        week_key, limit,
    )
    return [dict(r) for r in rows]


async def get_user_rank(week_key: str, user_id: int) -> int | None:
    pool = await get_db()
    return await pool.fetchval(
        """SELECT rank FROM (
               SELECT user_id, RANK() OVER (ORDER BY total_damage DESC) as rank
               FROM boss_weekly_damage WHERE week_key = $1
           ) sub WHERE user_id = $2""",
        week_key, user_id,
    )


async def get_participant_ids(week_key: str) -> list[int]:
    pool = await get_db()
    rows = await pool.fetch(
        "SELECT user_id FROM boss_weekly_damage WHERE week_key = $1",
        week_key,
    )
    return [r["user_id"] for r in rows]


async def get_participant_count(week_key: str) -> int:
    pool = await get_db()
    return await pool.fetchval(
        "SELECT COUNT(*) FROM boss_weekly_damage WHERE week_key = $1",
        week_key,
    ) or 0
