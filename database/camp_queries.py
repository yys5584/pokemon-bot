"""Camp system v2 database queries."""

import logging
from datetime import date

from database.connection import get_db

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
# Camp CRUD
# ═══════════════════════════════════════════════════════

async def create_camp(chat_id: int, created_by: int):
    """Create a new camp for a chat."""
    pool = await get_db()
    await pool.execute(
        """INSERT INTO camps (chat_id, level, xp, created_by)
           VALUES ($1, 1, 0, $2)
           ON CONFLICT (chat_id) DO NOTHING""",
        chat_id, created_by,
    )


async def get_camp(chat_id: int) -> dict | None:
    """Get camp info. Returns None if not created."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT chat_id, level, xp, created_by FROM camps WHERE chat_id = $1",
        chat_id,
    )
    return dict(row) if row else None


async def update_camp_xp(chat_id: int, xp_delta: int) -> int:
    """Add XP to camp. Returns new XP value."""
    pool = await get_db()
    row = await pool.fetchrow(
        """UPDATE camps SET xp = xp + $2
           WHERE chat_id = $1
           RETURNING xp""",
        chat_id, xp_delta,
    )
    return row["xp"] if row else 0


async def update_camp_level(chat_id: int, new_level: int):
    """Update camp level."""
    pool = await get_db()
    await pool.execute(
        "UPDATE camps SET level = $2 WHERE chat_id = $1",
        chat_id, new_level,
    )


# ═══════════════════════════════════════════════════════
# Fields
# ═══════════════════════════════════════════════════════

async def add_field(chat_id: int, field_type: str, unlock_order: int) -> int:
    """Add a field to a camp. Returns field id."""
    pool = await get_db()
    row = await pool.fetchrow(
        """INSERT INTO camp_fields (chat_id, field_type, unlock_order)
           VALUES ($1, $2, $3)
           RETURNING id""",
        chat_id, field_type, unlock_order,
    )
    return row["id"]


async def get_fields(chat_id: int) -> list[dict]:
    """Get all fields for a camp, ordered by unlock_order."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT id, chat_id, field_type, unlock_order
           FROM camp_fields
           WHERE chat_id = $1
           ORDER BY unlock_order""",
        chat_id,
    )
    return [dict(r) for r in rows]


async def change_field_type(field_id: int, new_type: str):
    """Change a field's type."""
    pool = await get_db()
    await pool.execute(
        "UPDATE camp_fields SET field_type = $2 WHERE id = $1",
        field_id, new_type,
    )


async def get_field_by_id(field_id: int) -> dict | None:
    """Get a single field by id."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT id, chat_id, field_type, unlock_order FROM camp_fields WHERE id = $1",
        field_id,
    )
    return dict(row) if row else None


# ═══════════════════════════════════════════════════════
# Placements
# ═══════════════════════════════════════════════════════

async def place_pokemon(chat_id: int, field_id: int, user_id: int,
                        pokemon_id: int, instance_id: int,
                        slot_type: str, score: int) -> int:
    """Place a pokemon in a field. UPSERT on (chat_id, field_id, user_id).
    Returns placement id."""
    pool = await get_db()
    row = await pool.fetchrow(
        """INSERT INTO camp_placements (chat_id, field_id, user_id, pokemon_id, instance_id, slot_type, score, placed_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
           ON CONFLICT (chat_id, field_id, user_id) DO UPDATE SET
               pokemon_id = EXCLUDED.pokemon_id,
               instance_id = EXCLUDED.instance_id,
               slot_type = EXCLUDED.slot_type,
               score = EXCLUDED.score,
               placed_at = NOW()
           RETURNING id""",
        chat_id, field_id, user_id, pokemon_id, instance_id, slot_type, score,
    )
    return row["id"]


async def remove_placement_by_instance(instance_id: int) -> int:
    """instance_id로 캠프 배치 삭제 (교환/합성/방생 시 호출). Returns deleted count."""
    pool = await get_db()
    result = await pool.execute(
        "DELETE FROM camp_placements WHERE instance_id = $1",
        instance_id,
    )
    return int(result.split()[-1]) if result else 0


async def remove_placement(placement_id: int, user_id: int) -> bool:
    """Remove a placement. Returns True if deleted."""
    pool = await get_db()
    result = await pool.execute(
        "DELETE FROM camp_placements WHERE id = $1 AND user_id = $2",
        placement_id, user_id,
    )
    return result.endswith("1")


async def get_field_placements(field_id: int) -> list[dict]:
    """Get all placements in a field, joined with pokemon info."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT cp.id, cp.chat_id, cp.field_id, cp.user_id, cp.pokemon_id,
                  cp.instance_id, cp.slot_type, cp.score, cp.placed_at,
                  up.is_shiny,
                  up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd,
                  pm.name_ko, pm.rarity,
                  u.display_name
           FROM camp_placements cp
           JOIN user_pokemon up ON up.id = cp.instance_id
           JOIN pokemon_master pm ON pm.id = cp.pokemon_id
           JOIN users u ON u.user_id = cp.user_id
           WHERE cp.field_id = $1
           ORDER BY cp.score DESC, cp.placed_at""",
        field_id,
    )
    return [dict(r) for r in rows]


async def get_user_placements(user_id: int) -> list[dict]:
    """Get all placements for a user across all camps."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT cp.id, cp.chat_id, cp.field_id, cp.pokemon_id,
                  cp.instance_id, cp.slot_type, cp.score, cp.placed_at,
                  cf.field_type, cf.unlock_order,
                  c.level AS camp_level,
                  up.is_shiny,
                  pm.name_ko, pm.rarity
           FROM camp_placements cp
           JOIN camp_fields cf ON cf.id = cp.field_id
           JOIN camps c ON c.chat_id = cp.chat_id
           JOIN user_pokemon up ON up.id = cp.instance_id
           JOIN pokemon_master pm ON pm.id = cp.pokemon_id
           WHERE cp.user_id = $1
           ORDER BY cp.placed_at""",
        user_id,
    )
    return [dict(r) for r in rows]


async def get_user_placed_instance_ids(user_id: int) -> set[int]:
    """캠프에 배치된 포켓몬 instance_id 세트 (배틀 보너스 체크용)."""
    pool = await get_db()
    rows = await pool.fetch(
        "SELECT instance_id FROM camp_placements WHERE user_id = $1",
        user_id,
    )
    return {r["instance_id"] for r in rows}


async def get_user_placements_in_chat(chat_id: int, user_id: int) -> list[dict]:
    """Get placements for a user in a specific chat."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT cp.id, cp.field_id, cp.pokemon_id,
                  cp.instance_id, cp.slot_type, cp.score, cp.placed_at,
                  cf.field_type, cf.unlock_order,
                  up.is_shiny,
                  up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd,
                  pm.name_ko, pm.rarity
           FROM camp_placements cp
           JOIN camp_fields cf ON cf.id = cp.field_id
           JOIN user_pokemon up ON up.id = cp.instance_id
           JOIN pokemon_master pm ON pm.id = cp.pokemon_id
           WHERE cp.chat_id = $1 AND cp.user_id = $2
           ORDER BY cf.unlock_order, cp.placed_at""",
        chat_id, user_id,
    )
    return [dict(r) for r in rows]


async def count_field_placements(field_id: int) -> int:
    """Count placements in a field."""
    pool = await get_db()
    val = await pool.fetchval(
        "SELECT COUNT(*) FROM camp_placements WHERE field_id = $1",
        field_id,
    )
    return val or 0


async def remove_user_pokemon_placements(user_id: int, instance_id: int):
    """Remove all placements of a specific pokemon instance (e.g. on trade/release)."""
    pool = await get_db()
    await pool.execute(
        "DELETE FROM camp_placements WHERE user_id = $1 AND instance_id = $2",
        user_id, instance_id,
    )


# ═══════════════════════════════════════════════════════
# Round Bonus
# ═══════════════════════════════════════════════════════

async def set_round_bonus(chat_id: int, field_id: int, pokemon_id: int,
                          stat_type: str, stat_value: int, round_time):
    """Set round bonus requirement. UPSERT on (chat_id, field_id, round_time)."""
    pool = await get_db()
    await pool.execute(
        """INSERT INTO camp_round_bonus (chat_id, field_id, pokemon_id, stat_type, stat_value, round_time)
           VALUES ($1, $2, $3, $4, $5, $6)
           ON CONFLICT (chat_id, field_id, round_time)
           DO UPDATE SET
               pokemon_id = EXCLUDED.pokemon_id,
               stat_type = EXCLUDED.stat_type,
               stat_value = EXCLUDED.stat_value""",
        chat_id, field_id, pokemon_id, stat_type, stat_value, round_time,
    )


async def get_round_bonus(chat_id: int, round_time) -> list[dict]:
    """Get all bonus entries for a specific round."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT id, chat_id, field_id, pokemon_id, stat_type, stat_value, round_time
           FROM camp_round_bonus
           WHERE chat_id = $1 AND round_time = $2
           ORDER BY field_id""",
        chat_id, round_time,
    )
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════
# Fragments
# ═══════════════════════════════════════════════════════

async def add_fragments(user_id: int, field_type: str, amount: int):
    """Add fragments to a user. Upsert."""
    pool = await get_db()
    await pool.execute(
        """INSERT INTO camp_fragments (user_id, field_type, amount)
           VALUES ($1, $2, $3)
           ON CONFLICT (user_id, field_type)
           DO UPDATE SET amount = camp_fragments.amount + $3""",
        user_id, field_type, amount,
    )


async def get_user_fragments(user_id: int) -> dict[str, int]:
    """Get all fragment counts for a user. Returns {field_type: amount}."""
    pool = await get_db()
    rows = await pool.fetch(
        "SELECT field_type, amount FROM camp_fragments WHERE user_id = $1",
        user_id,
    )
    return {r["field_type"]: r["amount"] for r in rows}


async def consume_fragments(user_id: int, field_type: str, amount: int) -> bool:
    """Atomically deduct fragments. Returns False if insufficient."""
    pool = await get_db()
    row = await pool.fetchrow(
        """UPDATE camp_fragments
           SET amount = amount - $3
           WHERE user_id = $1 AND field_type = $2 AND amount >= $3
           RETURNING amount""",
        user_id, field_type, amount,
    )
    return row is not None


async def log_fragment(user_id: int, chat_id: int, field_type: str, amount: int, source: str):
    """Log fragment acquisition/consumption."""
    pool = await get_db()
    await pool.execute(
        """INSERT INTO camp_fragment_log (user_id, chat_id, field_type, amount, source)
           VALUES ($1, $2, $3, $4, $5)""",
        user_id, chat_id, field_type, amount, source,
    )


# ═══════════════════════════════════════════════════════
# Weekly MVP (주간 기여도 랭킹)
# ═══════════════════════════════════════════════════════

async def get_weekly_top_contributors(chat_id: int, days: int = 7, limit: int = 10) -> list[dict]:
    """최근 N일간 조각 획득 기준 상위 기여자 목록."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT fl.user_id, SUM(fl.amount) AS total,
                  u.first_name, u.username
           FROM camp_fragment_log fl
           LEFT JOIN users u ON u.user_id = fl.user_id
           WHERE fl.chat_id = $1
             AND fl.source = 'round'
             AND fl.amount > 0
             AND fl.created_at >= NOW() - ($2 || ' days')::INTERVAL
           GROUP BY fl.user_id, u.first_name, u.username
           ORDER BY total DESC
           LIMIT $3""",
        chat_id, str(days), limit,
    )
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════
# Crystals
# ═══════════════════════════════════════════════════════

async def get_crystals(user_id: int) -> dict:
    """Get crystal and rainbow counts. Returns {crystal: int, rainbow: int}."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT crystal, rainbow FROM camp_crystals WHERE user_id = $1",
        user_id,
    )
    if row:
        return dict(row)
    return {"crystal": 0, "rainbow": 0}


async def add_crystals(user_id: int, crystal_delta: int = 0, rainbow_delta: int = 0):
    """Add crystals/rainbow crystals. Upsert."""
    pool = await get_db()
    await pool.execute(
        """INSERT INTO camp_crystals (user_id, crystal, rainbow)
           VALUES ($1, $2, $3)
           ON CONFLICT (user_id)
           DO UPDATE SET
               crystal = camp_crystals.crystal + $2,
               rainbow = camp_crystals.rainbow + $3""",
        user_id, crystal_delta, rainbow_delta,
    )


async def consume_crystals(user_id: int, crystal_cost: int = 0, rainbow_cost: int = 0) -> bool:
    """Atomically deduct crystals. Returns False if insufficient."""
    pool = await get_db()
    row = await pool.fetchrow(
        """UPDATE camp_crystals
           SET crystal = crystal - $2, rainbow = rainbow - $3
           WHERE user_id = $1 AND crystal >= $2 AND rainbow >= $3
           RETURNING crystal, rainbow""",
        user_id, crystal_cost, rainbow_cost,
    )
    return row is not None


# ═══════════════════════════════════════════════════════
# Shiny Cooldown
# ═══════════════════════════════════════════════════════

async def get_shiny_cooldown(user_id: int):
    """Get last shiny convert timestamp. Returns datetime or None."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT last_convert_at FROM camp_shiny_cooldown WHERE user_id = $1",
        user_id,
    )
    return row["last_convert_at"] if row else None


async def set_shiny_cooldown(user_id: int):
    """Set shiny cooldown to NOW()."""
    pool = await get_db()
    await pool.execute(
        """INSERT INTO camp_shiny_cooldown (user_id, last_convert_at)
           VALUES ($1, NOW())
           ON CONFLICT (user_id)
           DO UPDATE SET last_convert_at = NOW()""",
        user_id,
    )


# ═══════════════════════════════════════════════════════
# User Settings
# ═══════════════════════════════════════════════════════

async def get_user_camp_settings(user_id: int) -> dict | None:
    """Get user's camp settings (home camp, etc.)."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT home_chat_id, home_changed_date, home_camp_set_at,
                  COALESCE(camp_notify, TRUE) AS camp_notify
           FROM camp_user_settings WHERE user_id = $1""",
        user_id,
    )
    return dict(row) if row else None


async def set_home_camp(user_id: int, chat_id: int):
    """Set user's home camp. Records timestamp for 7-day change cooldown."""
    pool = await get_db()
    await pool.execute(
        """INSERT INTO camp_user_settings (user_id, home_chat_id, home_changed_date, home_camp_set_at)
           VALUES ($1, $2, CURRENT_DATE, NOW())
           ON CONFLICT (user_id)
           DO UPDATE SET
               home_chat_id = $2,
               home_changed_date = CURRENT_DATE,
               home_camp_set_at = NOW()""",
        user_id, chat_id,
    )


async def toggle_camp_notify(user_id: int) -> bool:
    """Toggle camp notification. Returns new state."""
    pool = await get_db()
    row = await pool.fetchrow(
        """INSERT INTO camp_user_settings (user_id, camp_notify)
           VALUES ($1, FALSE)
           ON CONFLICT (user_id)
           DO UPDATE SET camp_notify = NOT COALESCE(camp_user_settings.camp_notify, TRUE)
           RETURNING camp_notify""",
        user_id,
    )
    return row["camp_notify"] if row else True


async def get_home_camp_users(chat_id: int) -> list[int]:
    """Get all user IDs who have this chat as home camp and notify enabled."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT user_id FROM camp_user_settings
           WHERE home_chat_id = $1 AND COALESCE(camp_notify, TRUE) = TRUE""",
        chat_id,
    )
    return [r["user_id"] for r in rows]


# ═══════════════════════════════════════════════════════
# Chat Settings (owner/admin)
# ═══════════════════════════════════════════════════════

async def get_chat_camp_settings(chat_id: int) -> dict | None:
    """Get chat's camp settings (approval mode, slots, etc.)."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT approval_mode, approval_slots, last_mode_change, last_field_change
           FROM camp_chat_settings
           WHERE chat_id = $1""",
        chat_id,
    )
    return dict(row) if row else None


async def update_chat_camp_settings(chat_id: int, **kwargs):
    """Update specific chat camp settings.
    Supported keys: approval_mode, approval_slots, last_mode_change, last_field_change.
    """
    if not kwargs:
        return
    pool = await get_db()
    # Build SET clause dynamically
    set_parts = []
    values = [chat_id]
    idx = 2
    for key, val in kwargs.items():
        set_parts.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1
    set_clause = ", ".join(set_parts)

    # Upsert: create row if not exists
    columns = ", ".join(kwargs.keys())
    placeholders = ", ".join(f"${i}" for i in range(2, idx))
    await pool.execute(
        f"""INSERT INTO camp_chat_settings (chat_id, {columns})
            VALUES ($1, {placeholders})
            ON CONFLICT (chat_id)
            DO UPDATE SET {set_clause}""",
        *values,
    )


# ═══════════════════════════════════════════════════════
# Daily Placements
# ═══════════════════════════════════════════════════════

async def get_daily_placement_count(user_id: int) -> int:
    """Get user's placement count for today (KST)."""
    pool = await get_db()
    val = await pool.fetchval(
        "SELECT count FROM camp_daily_placements WHERE user_id = $1 AND date = (NOW() AT TIME ZONE 'Asia/Seoul')::date",
        user_id,
    )
    return val or 0


async def increment_daily_placement(user_id: int):
    """Increment user's daily placement count (KST). Upsert."""
    pool = await get_db()
    await pool.execute(
        """INSERT INTO camp_daily_placements (user_id, date, count)
           VALUES ($1, (NOW() AT TIME ZONE 'Asia/Seoul')::date, 1)
           ON CONFLICT (user_id, date)
           DO UPDATE SET count = camp_daily_placements.count + 1""",
        user_id,
    )


async def decrement_daily_placement(user_id: int):
    """Decrement user's daily placement count (배치 해제 시 횟수 복구)."""
    pool = await get_db()
    await pool.execute(
        """UPDATE camp_daily_placements
           SET count = GREATEST(count - 1, 0)
           WHERE user_id = $1 AND date = (NOW() AT TIME ZONE 'Asia/Seoul')::date""",
        user_id,
    )


# ═══════════════════════════════════════════════════════
# Approval Queue
# ═══════════════════════════════════════════════════════

async def add_approval_request(chat_id: int, field_id: int, user_id: int,
                               pokemon_id: int, instance_id: int) -> int:
    """Add an approval request. Returns request id."""
    pool = await get_db()
    row = await pool.fetchrow(
        """INSERT INTO camp_approval_queue (chat_id, field_id, user_id, pokemon_id, instance_id, requested_at, status)
           VALUES ($1, $2, $3, $4, $5, NOW(), 'pending')
           RETURNING id""",
        chat_id, field_id, user_id, pokemon_id, instance_id,
    )
    return row["id"]


async def get_pending_approvals(chat_id: int) -> list[dict]:
    """Get all pending approval requests for a chat."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT aq.id, aq.chat_id, aq.field_id, aq.user_id, aq.pokemon_id, aq.instance_id,
                  aq.requested_at, aq.status,
                  cf.field_type,
                  pm.name_ko, pm.rarity,
                  u.display_name
           FROM camp_approval_queue aq
           JOIN camp_fields cf ON cf.id = aq.field_id
           JOIN pokemon_master pm ON pm.id = aq.pokemon_id
           JOIN users u ON u.user_id = aq.user_id
           WHERE aq.chat_id = $1 AND aq.status = 'pending'
           ORDER BY aq.requested_at""",
        chat_id,
    )
    return [dict(r) for r in rows]


async def approve_request(request_id: int) -> dict | None:
    """Approve a request. Returns the request info for processing, or None if not found."""
    pool = await get_db()
    row = await pool.fetchrow(
        """UPDATE camp_approval_queue
           SET status = 'approved'
           WHERE id = $1 AND status = 'pending'
           RETURNING id, chat_id, field_id, user_id, pokemon_id, instance_id""",
        request_id,
    )
    return dict(row) if row else None


async def reject_request(request_id: int) -> bool:
    """Reject a request. Returns True if updated."""
    pool = await get_db()
    result = await pool.execute(
        "UPDATE camp_approval_queue SET status = 'rejected' WHERE id = $1 AND status = 'pending'",
        request_id,
    )
    return result.endswith("1")


async def auto_approve_expired(chat_id: int, timeout_seconds: int) -> list[dict]:
    """Auto-approve pending requests older than timeout. Returns approved requests."""
    pool = await get_db()
    rows = await pool.fetch(
        """UPDATE camp_approval_queue
           SET status = 'approved'
           WHERE chat_id = $1 AND status = 'pending'
             AND requested_at < NOW() - INTERVAL '1 second' * $2
           RETURNING id, chat_id, field_id, user_id, pokemon_id, instance_id""",
        chat_id, timeout_seconds,
    )
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════
# Shiny Conversion
# ═══════════════════════════════════════════════════════

async def make_pokemon_shiny(pokemon_row_id: int) -> bool:
    """Set a user_pokemon to shiny. Returns True on success."""
    pool = await get_db()
    result = await pool.execute(
        "UPDATE user_pokemon SET is_shiny = 1 WHERE id = $1 AND is_shiny = 0",
        pokemon_row_id,
    )
    return result.endswith("1")


# ═══════════════════════════════════════════════════════
# Utility
# ═══════════════════════════════════════════════════════

async def get_camp_enabled_chats() -> list[int]:
    """Get all chat IDs that have a camp."""
    pool = await get_db()
    rows = await pool.fetch("SELECT chat_id FROM camps")
    return [r["chat_id"] for r in rows]


async def get_available_camps() -> list[dict]:
    """Get all active camps with chat info for home camp selection."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT c.chat_id, c.level, cr.chat_title, cr.member_count, cr.invite_link
           FROM camps c
           JOIN chat_rooms cr ON cr.chat_id = c.chat_id
           WHERE cr.is_active = 1
           ORDER BY cr.member_count DESC NULLS LAST
           LIMIT 50""",
    )
    return [dict(r) for r in rows]
