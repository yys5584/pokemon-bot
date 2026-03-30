"""All database query functions — PostgreSQL / asyncpg version."""

import asyncio
import logging
from datetime import datetime, timedelta
from database.connection import get_db, _retry
import config as _cfg

logger = logging.getLogger(__name__)


# ============================================================
# Users
# ============================================================

async def is_user_banned(user_id: int) -> bool:
    """Check if user is banned (banned_until > NOW())."""
    pool = await get_db()
    row = await pool.fetchval(
        "SELECT banned_until > NOW() FROM users WHERE user_id = $1",
        user_id,
    )
    return bool(row)


async def ensure_user(user_id: int, display_name: str, username: str | None = None):
    """Register or update a user. New users get welcome bonus (500 BP + 10 AI tokens). No master balls (earned via journey)."""
    async def _do():
        pool = await get_db()
        await pool.execute(
            """INSERT INTO users (user_id, username, display_name, master_balls, battle_points, llm_bonus_quota)
               VALUES ($1, $2, $3, 0, 500, 10)
               ON CONFLICT(user_id) DO UPDATE SET
                   username = EXCLUDED.username,
                   display_name = EXCLUDED.display_name,
                   last_active_at = NOW()""",
            user_id, username, display_name,
        )
    await _retry(_do)


async def get_user(user_id: int) -> dict | None:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT * FROM users WHERE user_id = $1", user_id
    )
    return dict(row) if row else None


async def get_last_catch_time(user_id: int):
    """유저의 가장 최근 포획 시간 (현재 포획 제외, 2번째 최근)."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT caught_at FROM user_pokemon
           WHERE user_id = $1
           ORDER BY caught_at DESC
           OFFSET 1 LIMIT 1""",
        user_id,
    )
    return row["caught_at"] if row else None


async def get_all_user_ids() -> list[int]:
    """Get all registered user IDs."""
    pool = await get_db()
    rows = await pool.fetch("SELECT user_id FROM users")
    return [r["user_id"] for r in rows]


async def get_recently_active_user_ids(minutes: int = 10) -> list[int]:
    """Get user IDs active within the last N minutes."""
    pool = await get_db()
    rows = await pool.fetch(
        "SELECT user_id FROM users WHERE last_active_at >= NOW() - $1 * INTERVAL '1 minute'",
        minutes,
    )
    return [r["user_id"] for r in rows]


async def update_user_title(user_id: int, title: str, title_emoji: str):
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET title = $1, title_emoji = $2 WHERE user_id = $3",
        title, title_emoji, user_id,
    )


# ============================================================
# Master Balls
# ============================================================

# ============================================================
# Tutorial
# ============================================================

async def get_tutorial_step(user_id: int) -> int:
    """Get user's tutorial progress. 0=not started, 1-7=in progress, 98=skipped, 99=done."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT tutorial_step FROM users WHERE user_id = $1", user_id
    )
    return row["tutorial_step"] if row else 0


async def get_tutorial_restarted(user_id: int) -> bool:
    """Check if user has already restarted the tutorial once."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT tutorial_restarted FROM users WHERE user_id = $1", user_id
    )
    return row["tutorial_restarted"] if row else False


async def update_tutorial_step(user_id: int, step: int):
    """Update user's tutorial progress."""
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET tutorial_step = $1 WHERE user_id = $2",
        step, user_id,
    )


async def restart_tutorial(user_id: int):
    """Restart tutorial (one-time only). Sets step=1 and marks as restarted."""
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET tutorial_step = 1, tutorial_restarted = TRUE, tutorial_legendary_id = NULL WHERE user_id = $1",
        user_id,
    )


async def get_tutorial_legendary(user_id: int) -> int | None:
    """Get the legendary pokemon ID assigned to this user's tutorial."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT tutorial_legendary_id FROM users WHERE user_id = $1", user_id
    )
    return row["tutorial_legendary_id"] if row else None


async def set_tutorial_legendary(user_id: int, pokemon_id: int):
    """Set the legendary pokemon ID for this user's tutorial."""
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET tutorial_legendary_id = $1 WHERE user_id = $2",
        pokemon_id, user_id,
    )


async def get_master_balls(user_id: int) -> int:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT master_balls FROM users WHERE user_id = $1", user_id
    )
    return row["master_balls"] if row else 0


async def add_master_ball(user_id: int, count: int = 1):
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET master_balls = master_balls + $1 WHERE user_id = $2",
        count, user_id,
    )


async def use_master_ball(user_id: int) -> int | None:
    """Use one master ball. Returns remaining count, or None if not available."""
    pool = await get_db()
    row = await pool.fetchrow(
        "UPDATE users SET master_balls = master_balls - 1 "
        "WHERE user_id = $1 AND master_balls >= 1 "
        "RETURNING master_balls",
        user_id,
    )
    return row["master_balls"] if row else None


async def get_hyper_balls(user_id: int) -> int:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT hyper_balls FROM users WHERE user_id = $1", user_id
    )
    return row["hyper_balls"] if row else 0


async def add_hyper_ball(user_id: int, count: int = 1):
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET hyper_balls = hyper_balls + $1 WHERE user_id = $2",
        count, user_id,
    )


async def use_hyper_ball(user_id: int) -> bool:
    """Use one hyper ball. Returns True if successful (atomic operation)."""
    pool = await get_db()
    row = await pool.fetchrow(
        "UPDATE users SET hyper_balls = hyper_balls - 1 "
        "WHERE user_id = $1 AND hyper_balls >= 1 "
        "RETURNING hyper_balls",
        user_id,
    )
    return row is not None


# ============================================================
# Force Spawn Tickets
# ============================================================

async def get_force_spawn_tickets(user_id: int) -> int:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT force_spawn_tickets FROM users WHERE user_id = $1", user_id
    )
    return row["force_spawn_tickets"] if row and row["force_spawn_tickets"] else 0


async def add_force_spawn_ticket(user_id: int, count: int = 1):
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET force_spawn_tickets = force_spawn_tickets + $1 WHERE user_id = $2",
        count, user_id,
    )


async def use_force_spawn_ticket(user_id: int) -> bool:
    """Use one force spawn ticket. Returns True if successful (atomic)."""
    pool = await get_db()
    row = await pool.fetchrow(
        "UPDATE users SET force_spawn_tickets = force_spawn_tickets - 1 "
        "WHERE user_id = $1 AND force_spawn_tickets >= 1 "
        "RETURNING force_spawn_tickets",
        user_id,
    )
    return row is not None


# ============================================================
# Arcade Pass
# ============================================================

async def get_arcade_tickets(user_id: int) -> int:
    """Get user's arcade ticket count."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT arcade_tickets FROM users WHERE user_id = $1", user_id
    )
    return row["arcade_tickets"] if row and row["arcade_tickets"] else 0


async def add_arcade_ticket(user_id: int, count: int = 1):
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET arcade_tickets = arcade_tickets + $1 WHERE user_id = $2",
        count, user_id,
    )


async def use_arcade_ticket(user_id: int) -> bool:
    """Use one arcade ticket. Returns True if successful (atomic)."""
    pool = await get_db()
    row = await pool.fetchrow(
        "UPDATE users SET arcade_tickets = arcade_tickets - 1 "
        "WHERE user_id = $1 AND arcade_tickets >= 1 "
        "RETURNING arcade_tickets",
        user_id,
    )
    return row is not None


async def get_active_arcade_pass(chat_id: int) -> dict | None:
    """Get active arcade pass for a chat (temporary 1hr registration)."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT * FROM arcade_passes WHERE chat_id = $1 AND is_active = 1 AND expires_at > NOW() ORDER BY expires_at DESC LIMIT 1",
        chat_id,
    )
    return dict(row) if row else None


async def create_arcade_pass(chat_id: int, user_id: int, duration_seconds: int) -> dict:
    """Activate arcade mode for a chat. Returns the pass record."""
    pool = await get_db()
    row = await pool.fetchrow(
        """INSERT INTO arcade_passes (chat_id, activated_by, expires_at)
           VALUES ($1, $2, NOW() + make_interval(secs => $3))
           RETURNING *""",
        chat_id, user_id, float(duration_seconds),
    )
    return dict(row)


async def expire_arcade_passes():
    """Mark expired arcade passes as inactive. Returns list of expired chat_ids."""
    pool = await get_db()
    rows = await pool.fetch(
        "UPDATE arcade_passes SET is_active = 0 WHERE is_active = 1 AND expires_at <= NOW() RETURNING chat_id"
    )
    return [r["chat_id"] for r in rows]


async def extend_arcade_pass(chat_id: int, extend_minutes: int):
    """Extend active arcade pass expiry time in DB."""
    pool = await get_db()
    row = await pool.fetchrow(
        "UPDATE arcade_passes SET expires_at = expires_at + make_interval(mins => $2) "
        "WHERE chat_id = $1 AND is_active = 1 AND expires_at > NOW() RETURNING expires_at",
        chat_id, float(extend_minutes),
    )
    return dict(row) if row else None


async def get_all_active_arcade_passes() -> list[dict]:
    """Get all currently active arcade passes (for startup recovery)."""
    pool = await get_db()
    rows = await pool.fetch(
        "SELECT * FROM arcade_passes WHERE is_active = 1 AND expires_at > NOW()"
    )
    return [dict(r) for r in rows]


# ============================================================
# Pokemon Master (with in-memory cache — 251 rows, never changes)
# ============================================================

_pokemon_cache: dict[int, dict] = {}       # id -> pokemon dict
_pokemon_by_name: dict[str, dict] = {}     # name_ko -> pokemon dict
_pokemon_by_rarity: dict[str, list] = {}   # rarity -> [pokemon dicts]


async def _load_pokemon_cache():
    """Load all pokemon_master into memory. Called once at startup."""
    global _pokemon_cache, _pokemon_by_name, _pokemon_by_rarity
    if _pokemon_cache:
        return
    pool = await get_db()
    rows = await pool.fetch("SELECT * FROM pokemon_master ORDER BY id")
    _pokemon_cache = {}
    _pokemon_by_name = {}
    _pokemon_by_rarity = {}
    for r in rows:
        d = dict(r)
        _pokemon_cache[d["id"]] = d
        _pokemon_by_name[d["name_ko"]] = d
        _pokemon_by_rarity.setdefault(d["rarity"], []).append(d)
    logger.info(f"Pokemon cache loaded: {len(_pokemon_cache)} species")


async def get_pokemon(pokemon_id: int) -> dict | None:
    await _load_pokemon_cache()
    return _pokemon_cache.get(pokemon_id)


async def search_pokemon_by_name(name: str) -> dict | None:
    """Search pokemon_master by name (Korean or English, exact or partial, min 2 chars)."""
    await _load_pokemon_cache()
    # Exact match (Korean)
    if name in _pokemon_by_name:
        return _pokemon_by_name[name]
    # Exact match (English, case-insensitive)
    name_lower = name.lower()
    for pid, p in _pokemon_cache.items():
        if p.get("name_en", "").lower() == name_lower:
            return p
    # Partial match (require at least 2 characters)
    if len(name) >= 2:
        # Korean partial
        for k, v in _pokemon_by_name.items():
            if name in k:
                return v
        # English partial (case-insensitive)
        for pid, p in _pokemon_cache.items():
            if name_lower in p.get("name_en", "").lower():
                return p
    return None


async def get_pokemon_by_rarity(rarity: str) -> list[dict]:
    await _load_pokemon_cache()
    return _pokemon_by_rarity.get(rarity, [])


async def get_all_pokemon() -> list[dict]:
    await _load_pokemon_cache()
    return list(_pokemon_cache.values())


# ============================================================
# User Pokemon (owned collection)
# ============================================================

async def give_pokemon_to_user(
    user_id: int, pokemon_id: int, chat_id: int | None = None,
    is_shiny: bool = False, ivs: dict | None = None,
    nurture_locked: bool = False, personality: str | None = None,
) -> tuple[int, dict]:
    """Add a Pokemon to user's collection with IVs.

    If ivs dict provided, uses those IVs (for trades). Otherwise generates random IVs.
    nurture_locked: True면 친밀도 강화 불가 (진화 후 교환된 포켓몬)
    personality: 성격 문자열 "T3:atk:사나움" (없으면 새로 생성)
    Returns (instance_id, iv_dict).
    iv_dict keys: iv_hp, iv_atk, iv_def, iv_spa, iv_spdef, iv_spd
    """
    if ivs is None:
        from utils.battle_calc import generate_ivs
        ivs = generate_ivs(is_shiny=is_shiny)
    if not personality:
        # 성격 없으면 자동 생성
        from utils.battle_calc import generate_personality, personality_to_str
        _pers = generate_personality(is_shiny=is_shiny)
        personality = personality_to_str(_pers)

    pool = await get_db()
    row = await pool.fetchrow(
        """INSERT INTO user_pokemon
               (user_id, pokemon_id, caught_in_chat_id, is_shiny,
                iv_hp, iv_atk, iv_def, iv_spa, iv_spdef, iv_spd,
                nurture_locked, personality)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12) RETURNING id""",
        user_id, pokemon_id, chat_id, 1 if is_shiny else 0,
        ivs["iv_hp"], ivs["iv_atk"], ivs["iv_def"],
        ivs["iv_spa"], ivs["iv_spdef"], ivs["iv_spd"],
        nurture_locked, personality,
    )
    return row["id"], ivs


async def count_user_pokemon_species(user_id: int, pokemon_id: int) -> int:
    """Count how many of a specific pokemon species a user owns (active only)."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM user_pokemon WHERE user_id = $1 AND pokemon_id = $2 AND is_active = 1",
        user_id, pokemon_id,
    )
    return row["cnt"] if row else 0


async def get_user_pokemon_list(user_id: int) -> list[dict]:
    """Get all active Pokemon owned by a user, with battle team info."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT up.*, pm.name_ko, pm.name_en, pm.emoji, pm.rarity,
                  pm.evolves_to, pm.evolution_method,
                  pm.pokemon_type, pm.stat_type,
                  bt.slot AS team_slot, bt.team_number AS team_num
           FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           LEFT JOIN battle_teams bt ON bt.pokemon_instance_id = up.id
           WHERE up.user_id = $1 AND up.is_active = 1
           ORDER BY
               CASE WHEN bt.slot IS NOT NULL THEN 0 ELSE 1 END,
               bt.team_number NULLS LAST, bt.slot NULLS LAST,
               CASE pm.rarity
                   WHEN 'ultra_legendary' THEN 0
                   WHEN 'legendary' THEN 1
                   WHEN 'epic' THEN 2
                   WHEN 'rare' THEN 3
                   WHEN 'common' THEN 4
               END, pm.name_ko, up.is_shiny DESC, up.id ASC""",
        user_id,
    )
    return [dict(r) for r in rows]


async def toggle_favorite(instance_id: int) -> bool:
    """Toggle is_favorite on a user_pokemon row. Returns new state."""
    pool = await get_db()
    row = await pool.fetchrow(
        "UPDATE user_pokemon SET is_favorite = 1 - is_favorite WHERE id = $1 RETURNING is_favorite",
        instance_id,
    )
    return bool(row["is_favorite"]) if row else False


async def get_user_pokemon_by_index(user_id: int, index: int) -> dict | None:
    """Get user's Nth active Pokemon (1-indexed)."""
    pokemon_list = await get_user_pokemon_list(user_id)
    if 1 <= index <= len(pokemon_list):
        return pokemon_list[index - 1]
    return None


async def get_user_pokemon_by_name(user_id: int, name: str) -> dict | None:
    """Get user's Pokemon by name (Korean or English). Returns first match."""
    pokemon_list = await get_user_pokemon_list(user_id)
    name_lower = name.strip().lower()
    # Exact match (ko or en)
    for p in pokemon_list:
        if p["name_ko"].lower() == name_lower or p.get("name_en", "").lower() == name_lower:
            return p
    # Partial match fallback
    for p in pokemon_list:
        if name_lower in p["name_ko"].lower() or name_lower in p.get("name_en", "").lower():
            return p
    return None


async def get_user_pokemon_by_id(instance_id: int) -> dict | None:
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT up.*, pm.name_ko, pm.name_en, pm.emoji, pm.rarity,
                  pm.evolves_to, pm.evolution_method, pm.evolves_from
           FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.id = $1 AND up.is_active = 1""",
        instance_id,
    )
    return dict(row) if row else None


async def update_pokemon_friendship(instance_id: int, friendship: int):
    pool = await get_db()
    await pool.execute(
        "UPDATE user_pokemon SET friendship = $1 WHERE id = $2",
        friendship, instance_id,
    )


async def atomic_feed(instance_id: int, gain: int, max_friendship: int, feed_limit: int = 5) -> int | None:
    """Atomically increment friendship + fed_today only if under limit.
    Returns new friendship, or None if limit already reached (race-safe)."""
    pool = await get_db()
    row = await pool.fetchrow(
        """UPDATE user_pokemon
           SET friendship = LEAST(friendship + $2, $3),
               fed_today = fed_today + 1
           WHERE id = $1 AND fed_today < $4
           RETURNING friendship""",
        instance_id, gain, max_friendship, feed_limit,
    )
    return row["friendship"] if row else None


async def atomic_play(instance_id: int, gain: int, max_friendship: int, play_limit: int = 5) -> int | None:
    """Atomically increment friendship + played_today only if under limit.
    Returns new friendship, or None if limit already reached (race-safe)."""
    pool = await get_db()
    row = await pool.fetchrow(
        """UPDATE user_pokemon
           SET friendship = LEAST(friendship + $2, $3),
               played_today = played_today + 1
           WHERE id = $1 AND played_today < $4
           RETURNING friendship""",
        instance_id, gain, max_friendship, play_limit,
    )
    return row["friendship"] if row else None


async def increment_feed(instance_id: int):
    pool = await get_db()
    await pool.execute(
        "UPDATE user_pokemon SET fed_today = fed_today + 1 WHERE id = $1",
        instance_id,
    )


async def increment_play(instance_id: int):
    pool = await get_db()
    await pool.execute(
        "UPDATE user_pokemon SET played_today = played_today + 1 WHERE id = $1",
        instance_id,
    )


async def evolve_pokemon(instance_id: int, new_pokemon_id: int):
    """Change a Pokemon's species (evolution). Reset friendship."""
    pool = await get_db()
    await pool.execute(
        """UPDATE user_pokemon
           SET pokemon_id = $1, friendship = 0
           WHERE id = $2""",
        new_pokemon_id, instance_id,
    )


async def deactivate_pokemon(instance_id: int):
    """Mark a Pokemon as inactive (traded away). Also removes camp placement."""
    pool = await get_db()
    await pool.execute(
        "UPDATE user_pokemon SET is_active = 0 WHERE id = $1",
        instance_id,
    )
    # 캠프 배치 자동 해제
    try:
        from database.camp_queries import remove_placement_by_instance
        await remove_placement_by_instance(instance_id)
    except Exception:
        pass


async def bulk_deactivate_pokemon(instance_ids: list[int]) -> int:
    """Mark multiple Pokemon as inactive (bulk release). Returns count."""
    if not instance_ids:
        return 0
    pool = await get_db()
    result = await pool.execute(
        "UPDATE user_pokemon SET is_active = 0 WHERE id = ANY($1) AND is_active = 1",
        instance_ids,
    )
    # 캠프 배치 자동 해제
    try:
        for iid in instance_ids:
            from database.camp_queries import remove_placement_by_instance
            await remove_placement_by_instance(iid)
    except Exception:
        pass
    # result like "UPDATE 23"
    return int(result.split()[-1]) if result else 0


async def get_protected_pokemon_ids(user_id: int) -> set[int]:
    """Get instance IDs that cannot be released (team, partner, market, trade, camp)."""
    pool = await get_db()
    rows = await pool.fetch(
        """
        SELECT pokemon_instance_id AS pid FROM battle_teams WHERE user_id = $1
        UNION
        SELECT partner_pokemon_id FROM users WHERE user_id = $1 AND partner_pokemon_id IS NOT NULL
        UNION
        SELECT pokemon_instance_id FROM market_listings WHERE seller_id = $1 AND status = 'active'
        UNION
        SELECT offer_pokemon_instance_id FROM trades WHERE from_user_id = $1 AND status = 'pending'
        UNION
        SELECT instance_id FROM camp_placements WHERE user_id = $1
        """,
        user_id,
    )
    return {r["pid"] for r in rows if r["pid"] is not None}


async def reset_daily_nurture():
    """Reset daily feed/play counts for all Pokemon. Called at midnight."""
    pool = await get_db()
    await pool.execute(
        "UPDATE user_pokemon SET fed_today = 0, played_today = 0 WHERE is_active = 1"
    )


# ─── 채팅방 레벨 CXP ─────────────────────────────────

async def add_chat_cxp(chat_id: int, amount: int, action: str, user_id: int = None):
    """CXP 적립 (일일 상한 체크). 레벨업 시 new_level 반환, 아니면 None."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT cxp, chat_level, cxp_today FROM chat_rooms WHERE chat_id = $1",
        chat_id,
    )
    if not row or row["cxp_today"] >= _cfg.CXP_DAILY_CAP:
        return None

    actual = min(amount, _cfg.CXP_DAILY_CAP - row["cxp_today"])
    new_cxp = row["cxp"] + actual

    info = _cfg.get_chat_level_info(new_cxp)
    new_level = info["level"]
    leveled_up = new_level > row["chat_level"]

    await pool.execute(
        """UPDATE chat_rooms
           SET cxp = $1, chat_level = $2, cxp_today = cxp_today + $3
           WHERE chat_id = $4""",
        new_cxp, new_level, actual, chat_id,
    )

    # CXP 로그 (비동기, 실패해도 무시)
    try:
        await pool.execute(
            """INSERT INTO chat_cxp_log (chat_id, action, user_id, amount)
               VALUES ($1, $2, $3, $4)""",
            chat_id, action, user_id, actual,
        )
    except Exception:
        pass

    return new_level if leveled_up else None


async def get_chat_level(chat_id: int) -> dict:
    """채팅방 레벨 정보 조회."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT cxp, chat_level, cxp_today FROM chat_rooms WHERE chat_id = $1",
        chat_id,
    )
    if not row:
        return {"cxp": 0, "chat_level": 1, "cxp_today": 0}
    return dict(row)


async def reset_daily_cxp():
    """자정에 cxp_today 리셋."""
    pool = await get_db()
    await pool.execute("UPDATE chat_rooms SET cxp_today = 0")


async def get_lv8_plus_chats():
    """Lv.8 이상 활성 채팅방 목록."""
    pool = await get_db()
    rows = await pool.fetch(
        "SELECT chat_id FROM chat_rooms WHERE chat_level >= 8 AND is_active = 1"
    )
    return [r["chat_id"] for r in rows]


async def find_user_pokemon_by_name(user_id: int, name: str) -> dict | None:
    """Find a user's active Pokemon by name (Korean or English)."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT up.*, pm.name_ko, pm.name_en, pm.emoji, pm.rarity,
                  pm.evolves_to, pm.evolution_method
           FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.user_id = $1 AND up.is_active = 1
             AND (pm.name_ko = $2 OR LOWER(pm.name_en) = LOWER($2))
           ORDER BY up.id LIMIT 1""",
        user_id, name,
    )
    return dict(row) if row else None


async def find_all_user_pokemon_by_name(user_id: int, name: str) -> list[dict]:
    """Find ALL active Pokemon of a user by name (Korean or English)."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT up.*, pm.name_ko, pm.name_en, pm.emoji, pm.rarity,
                  pm.evolves_to, pm.evolution_method
           FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.user_id = $1 AND up.is_active = 1
             AND (pm.name_ko = $2 OR LOWER(pm.name_en) = LOWER($2))
           ORDER BY up.id""",
        user_id, name,
    )
    return [dict(r) for r in rows]


# ============================================================
# Pokedex
# ============================================================

async def register_pokedex(user_id: int, pokemon_id: int, method: str = "catch"):
    """Register a Pokemon in the user's Pokedex."""
    pool = await get_db()
    await pool.execute(
        """INSERT INTO pokedex (user_id, pokemon_id, method)
           VALUES ($1, $2, $3)
           ON CONFLICT (user_id, pokemon_id) DO NOTHING""",
        user_id, pokemon_id, method,
    )


async def get_user_pokedex(user_id: int) -> list[dict]:
    """Get all Pokedex entries for a user."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT p.pokemon_id, p.method, p.first_caught_at,
                  pm.name_ko, pm.emoji, pm.rarity
           FROM pokedex p
           JOIN pokemon_master pm ON p.pokemon_id = pm.id
           WHERE p.user_id = $1
           ORDER BY p.pokemon_id""",
        user_id,
    )
    return [dict(r) for r in rows]


async def count_pokedex(user_id: int) -> int:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM pokedex WHERE user_id = $1", user_id
    )
    return row["cnt"] if row else 0


async def count_pokedex_gen1(user_id: int) -> int:
    """Count Gen 1 pokedex entries (pokemon_id 1~151)."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM pokedex WHERE user_id = $1 AND pokemon_id <= 151",
        user_id,
    )
    return row["cnt"] if row else 0


async def count_pokedex_gen2(user_id: int) -> int:
    """Count Gen 2 pokedex entries (pokemon_id 152~251)."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM pokedex WHERE user_id = $1 AND pokemon_id >= 152 AND pokemon_id <= 251",
        user_id,
    )
    return row["cnt"] if row else 0


async def count_pokedex_gen3(user_id: int) -> int:
    """Count Gen 3 pokedex entries (pokemon_id 252~386)."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM pokedex WHERE user_id = $1 AND pokemon_id >= 252 AND pokemon_id <= 386",
        user_id,
    )
    return row["cnt"] if row else 0


async def count_legendary_caught(user_id: int) -> int:
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT COUNT(*) as cnt FROM pokedex p
           JOIN pokemon_master pm ON p.pokemon_id = pm.id
           WHERE p.user_id = $1 AND pm.rarity IN ('legendary', 'ultra_legendary')""",
        user_id,
    )
    return row["cnt"] if row else 0


async def is_first_catch_in_chat(chat_id: int, pokemon_id: int) -> bool:
    """Check if this Pokemon has never been caught in this chat."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT COUNT(*) as cnt FROM spawn_log
           WHERE chat_id = $1 AND pokemon_id = $2 AND caught_by_user_id IS NOT NULL""",
        chat_id, pokemon_id,
    )
    return row["cnt"] == 0 if row else True


# ============================================================
# Chat Rooms
# ============================================================

async def ensure_chat_room(chat_id: int, title: str | None = None,
                           member_count: int = 0, invite_link: str | None = None):
    pool = await get_db()
    await pool.execute(
        """INSERT INTO chat_rooms (chat_id, chat_title, member_count, invite_link)
           VALUES ($1, $2, $3, $4)
           ON CONFLICT(chat_id) DO UPDATE SET
               chat_title = COALESCE(EXCLUDED.chat_title, chat_rooms.chat_title),
               member_count = CASE
                   WHEN EXCLUDED.member_count > 0 THEN EXCLUDED.member_count
                   ELSE chat_rooms.member_count
               END,
               invite_link = COALESCE(EXCLUDED.invite_link, chat_rooms.invite_link)""",
        chat_id, title, member_count, invite_link,
    )


async def get_chat_room(chat_id: int) -> dict | None:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT * FROM chat_rooms WHERE chat_id = $1", chat_id
    )
    return dict(row) if row else None


async def get_all_active_chats() -> list[dict]:
    pool = await get_db()
    rows = await pool.fetch(
        "SELECT * FROM chat_rooms WHERE is_active = 1"
    )
    return [dict(r) for r in rows]


async def update_chat_member_count(chat_id: int, count: int):
    pool = await get_db()
    await pool.execute(
        "UPDATE chat_rooms SET member_count = $1 WHERE chat_id = $2",
        count, chat_id,
    )


async def update_chat_spawn_info(chat_id: int, target: int):
    pool = await get_db()
    await pool.execute(
        """UPDATE chat_rooms
           SET spawns_today_target = $1
           WHERE chat_id = $2""",
        target, chat_id,
    )


# ============================================================
# Chat Spawn Multiplier
# ============================================================

async def set_spawn_multiplier(chat_id: int, multiplier: float):
    pool = await get_db()
    await pool.execute(
        "UPDATE chat_rooms SET spawn_multiplier = $1 WHERE chat_id = $2",
        multiplier, chat_id,
    )


async def get_spawn_multiplier(chat_id: int) -> float:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT spawn_multiplier FROM chat_rooms WHERE chat_id = $1", chat_id
    )
    return row["spawn_multiplier"] if row else 1.0


async def set_arcade(chat_id: int, enabled: bool):
    pool = await get_db()
    await pool.execute(
        "UPDATE chat_rooms SET is_arcade = $1 WHERE chat_id = $2",
        1 if enabled else 0, chat_id,
    )


async def get_arcade_chat_ids() -> set[int]:
    """Get all chat IDs with arcade mode enabled."""
    pool = await get_db()
    rows = await pool.fetch("SELECT chat_id FROM chat_rooms WHERE is_arcade = 1")
    return {r["chat_id"] for r in rows}


async def get_tournament_chat_id() -> int | None:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT value FROM bot_settings WHERE key = 'tournament_chat_id'"
    )
    return int(row["value"]) if row else None


async def set_tournament_chat_id(chat_id: int | None):
    pool = await get_db()
    if chat_id is None:
        await pool.execute(
            "DELETE FROM bot_settings WHERE key = 'tournament_chat_id'"
        )
    else:
        await pool.execute("""
            INSERT INTO bot_settings (key, value)
            VALUES ('tournament_chat_id', $1)
            ON CONFLICT (key) DO UPDATE SET value = $1
        """, str(chat_id))


# ============================================================
# Events
# ============================================================

async def create_event(
    name: str, event_type: str, multiplier: float,
    target: str | None, description: str, end_time,
    created_by: int | None = None,
) -> int:
    pool = await get_db()
    # Ensure end_time is a datetime object for asyncpg
    if isinstance(end_time, str):
        et = datetime.fromisoformat(end_time)
    else:
        et = end_time
    row = await pool.fetchrow(
        """INSERT INTO events (name, event_type, multiplier, target, description, end_time, created_by)
           VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
        name, event_type, multiplier, target, description, et, created_by,
    )
    return row["id"]


async def get_active_events() -> list[dict]:
    """Get all currently active events that haven't expired."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT * FROM events
           WHERE active = 1 AND end_time > NOW()
           ORDER BY start_time"""
    )
    return [dict(r) for r in rows]


async def get_active_events_by_type(event_type: str) -> list[dict]:
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT * FROM events
           WHERE active = 1 AND event_type = $1 AND end_time > NOW()""",
        event_type,
    )
    return [dict(r) for r in rows]


async def end_event(event_id: int):
    pool = await get_db()
    await pool.execute(
        "UPDATE events SET active = 0 WHERE id = $1", event_id
    )


async def cleanup_expired_events():
    """Deactivate events past their end_time."""
    pool = await get_db()
    await pool.execute(
        "UPDATE events SET active = 0 WHERE active = 1 AND end_time <= NOW()"
    )


async def add_master_balls_bulk(user_ids: list[int]):
    """Refund 1 master ball to each user in the list (batch UPDATE)."""
    if not user_ids:
        return
    pool = await get_db()
    await pool.execute(
        """UPDATE users SET master_balls = master_balls + 1
           WHERE user_id = ANY($1::bigint[])""",
        user_ids,
    )


async def add_hyper_balls_bulk(user_ids: list[int]):
    """Refund 1 hyper ball to each user in the list (batch UPDATE)."""
    if not user_ids:
        return
    pool = await get_db()
    await pool.execute(
        """UPDATE users SET hyper_balls = hyper_balls + 1
           WHERE user_id = ANY($1::bigint[])""",
        user_ids,
    )


# ============================================================
# Journey System
# ============================================================

async def add_battle_points(user_id: int, amount: int):
    """Add battle points to a user."""
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET battle_points = battle_points + $1 WHERE user_id = $2",
        amount, user_id,
    )


async def update_journey_step(user_id: int, step: int):
    """Update journey step for a user."""
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET journey_step = $1 WHERE user_id = $2",
        step, user_id,
    )


async def update_journey_tip_date(user_id: int, date_str: str):
    """Update journey last tip date (YYYY-MM-DD)."""
    from datetime import date as dt_date
    pool = await get_db()
    d = dt_date.fromisoformat(date_str)
    await pool.execute(
        "UPDATE users SET journey_last_tip_date = $1, journey_step = journey_step + 1 WHERE user_id = $2",
        d, user_id,
    )


async def catch_pokemon_transaction(
    user_id: int,
    pokemon_id: int,
    chat_id: int | None,
    is_shiny: bool,
    session_id: int,
    personality: str | None = None,
) -> tuple[int, dict]:
    """Give pokemon + register pokedex + close session in a single transaction."""
    from utils.battle_calc import generate_ivs
    # 스폰 세션에 미리 생성된 IV가 있으면 사용, 없으면 새로 생성
    ivs = None
    _pers = personality
    try:
        import json as _json
        _pool = await get_db()
        _row = await _pool.fetchrow(
            "SELECT pre_ivs, personality FROM spawn_sessions WHERE id = $1", session_id)
        if _row:
            if _row["pre_ivs"]:
                ivs = _json.loads(_row["pre_ivs"]) if isinstance(_row["pre_ivs"], str) else dict(_row["pre_ivs"])
            if not _pers and _row.get("personality"):
                _pers = _row["personality"]
    except Exception:
        pass
    if not ivs:
        ivs = generate_ivs(is_shiny=is_shiny)
    pool = await get_db()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """INSERT INTO user_pokemon
                       (user_id, pokemon_id, caught_in_chat_id, is_shiny,
                        iv_hp, iv_atk, iv_def, iv_spa, iv_spdef, iv_spd, personality)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) RETURNING id""",
                user_id, pokemon_id, chat_id, 1 if is_shiny else 0,
                ivs["iv_hp"], ivs["iv_atk"], ivs["iv_def"],
                ivs["iv_spa"], ivs["iv_spdef"], ivs["iv_spd"], _pers,
            )
            await conn.execute(
                """INSERT INTO pokedex (user_id, pokemon_id, method)
                   VALUES ($1, $2, 'catch')
                   ON CONFLICT (user_id, pokemon_id) DO NOTHING""",
                user_id, pokemon_id,
            )
            await conn.execute(
                """UPDATE spawn_sessions
                   SET is_resolved = 1, caught_by_user_id = $1
                   WHERE id = $2""",
                user_id, session_id,
            )
    return row["id"], ivs



# ============================================================
# Patch Note Opt-out
# ============================================================

async def toggle_patch_optout(user_id: int) -> bool:
    """Toggle patch_optout for a user. Returns new state (True=opted out)."""
    pool = await get_db()
    row = await pool.fetchrow(
        "UPDATE users SET patch_optout = NOT patch_optout WHERE user_id = $1 RETURNING patch_optout",
        user_id,
    )
    return bool(row["patch_optout"]) if row else False


