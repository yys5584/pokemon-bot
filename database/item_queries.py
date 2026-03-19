"""Item / gacha / egg / IV stone database queries."""

import logging
from database.connection import get_db

logger = logging.getLogger(__name__)


# ─── Gacha / Item System ─────────────────────────────────

async def get_user_item(user_id: int, item_type: str) -> int:
    """유저의 특정 아이템 보유 수량."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT quantity FROM user_items WHERE user_id = $1 AND item_type = $2",
        user_id, item_type)
    return row["quantity"] if row else 0


async def add_user_item(user_id: int, item_type: str, amount: int = 1):
    """아이템 추가 (upsert)."""
    pool = await get_db()
    await pool.execute(
        """INSERT INTO user_items (user_id, item_type, quantity)
           VALUES ($1, $2, $3)
           ON CONFLICT (user_id, item_type) DO UPDATE SET quantity = user_items.quantity + $3""",
        user_id, item_type, amount)


async def use_user_item(user_id: int, item_type: str, amount: int = 1) -> bool:
    """아이템 사용 (수량 차감). 부족하면 False."""
    pool = await get_db()
    row = await pool.fetchrow(
        "UPDATE user_items SET quantity = quantity - $3 WHERE user_id = $1 AND item_type = $2 AND quantity >= $3 RETURNING quantity",
        user_id, item_type, amount)
    return row is not None


async def get_all_user_items(user_id: int) -> list:
    """유저의 모든 아이템 목록."""
    pool = await get_db()
    return await pool.fetch(
        "SELECT item_type, quantity FROM user_items WHERE user_id = $1 AND quantity > 0 ORDER BY item_type",
        user_id)


async def log_gacha(user_id: int, result_key: str, bp_spent: int):
    """가챠 로그 기록."""
    pool = await get_db()
    await pool.execute(
        "INSERT INTO gacha_log (user_id, result_key, bp_spent) VALUES ($1, $2, $3)",
        user_id, result_key, bp_spent)


async def get_recent_gacha_by_user(minutes: int = 2) -> dict[int, list[str]]:
    """최근 N분 내 가챠 기록을 유저별로 그룹핑."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT user_id, result_key
           FROM gacha_log
           WHERE created_at >= NOW() - ($1 || ' minutes')::INTERVAL
           ORDER BY created_at""",
        str(minutes),
    )
    result: dict[int, list[str]] = {}
    for r in rows:
        result.setdefault(r["user_id"], []).append(r["result_key"])
    return result


async def create_shiny_egg(user_id: int, pokemon_id: int, rarity: str, hatches_at) -> int:
    """이로치 알 생성."""
    pool = await get_db()
    row = await pool.fetchrow(
        """INSERT INTO shiny_eggs (user_id, pokemon_id, rarity, hatches_at)
           VALUES ($1, $2, $3, $4) RETURNING id""",
        user_id, pokemon_id, rarity, hatches_at)
    return row["id"]


async def get_user_eggs(user_id: int) -> list:
    """유저의 부화 대기 중인 알 목록."""
    pool = await get_db()
    return await pool.fetch(
        """SELECT se.*, pm.name_ko FROM shiny_eggs se
           JOIN pokemon_master pm ON se.pokemon_id = pm.id
           WHERE se.user_id = $1 AND se.hatched = FALSE
           ORDER BY se.hatches_at""",
        user_id)


async def get_ready_eggs():
    """부화 시간이 된 알 목록."""
    pool = await get_db()
    return await pool.fetch(
        """SELECT se.*, pm.name_ko FROM shiny_eggs se
           JOIN pokemon_master pm ON se.pokemon_id = pm.id
           WHERE se.hatched = FALSE AND se.hatches_at <= NOW()""")


async def mark_egg_hatched(egg_id: int):
    """알 부화 완료 마킹."""
    pool = await get_db()
    await pool.execute("UPDATE shiny_eggs SET hatched = TRUE WHERE id = $1", egg_id)


async def update_pokemon_iv(instance_id: int, iv_key: str, value: int):
    """포켓몬 특정 IV 스탯 업데이트."""
    allowed = {"iv_hp", "iv_atk", "iv_def", "iv_spa", "iv_spdef", "iv_spd"}
    if iv_key not in allowed:
        raise ValueError(f"Invalid IV key: {iv_key}")
    pool = await get_db()
    await pool.execute(
        f"UPDATE user_pokemon SET {iv_key} = $1 WHERE id = $2",
        value, instance_id)


async def update_pokemon_all_ivs(instance_id: int, ivs: dict):
    """포켓몬 6종 IV 전체 업데이트."""
    pool = await get_db()
    await pool.execute(
        """UPDATE user_pokemon SET iv_hp=$1, iv_atk=$2, iv_def=$3,
           iv_spa=$4, iv_spdef=$5, iv_spd=$6 WHERE id=$7""",
        ivs["iv_hp"], ivs["iv_atk"], ivs["iv_def"],
        ivs["iv_spa"], ivs["iv_spdef"], ivs["iv_spd"],
        instance_id)


async def get_shiny_spawn_tickets(user_id: int) -> int:
    """이로치 강스권 보유 수."""
    pool = await get_db()
    return await pool.fetchval(
        "SELECT shiny_spawn_tickets FROM users WHERE user_id = $1",
        user_id) or 0


async def add_shiny_spawn_ticket(user_id: int, amount: int = 1):
    """이로치 강스권 추가."""
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET shiny_spawn_tickets = shiny_spawn_tickets + $2 WHERE user_id = $1",
        user_id, amount)


async def use_shiny_spawn_ticket(user_id: int) -> bool:
    """이로치 강스권 사용 (1개 차감). 부족하면 False."""
    pool = await get_db()
    row = await pool.fetchrow(
        "UPDATE users SET shiny_spawn_tickets = shiny_spawn_tickets - 1 WHERE user_id = $1 AND shiny_spawn_tickets > 0 RETURNING shiny_spawn_tickets",
        user_id)
    return row is not None


# ─── IV 스톤 & 만능 조각 ─────────────────────────────────

async def get_iv_stones(user_id: int) -> int:
    pool = await get_db()
    return await pool.fetchval(
        "SELECT iv_stones FROM users WHERE user_id = $1",
        user_id) or 0


async def add_iv_stones(user_id: int, amount: int = 1):
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET iv_stones = iv_stones + $2 WHERE user_id = $1",
        user_id, amount)


async def use_iv_stone(user_id: int) -> bool:
    """IV 스톤 1개 차감. 부족하면 False."""
    pool = await get_db()
    row = await pool.fetchrow(
        "UPDATE users SET iv_stones = iv_stones - 1 WHERE user_id = $1 AND iv_stones > 0 RETURNING iv_stones",
        user_id)
    return row is not None


async def get_universal_fragments(user_id: int) -> int:
    pool = await get_db()
    return await pool.fetchval(
        "SELECT universal_fragments FROM users WHERE user_id = $1",
        user_id) or 0


async def add_universal_fragments(user_id: int, amount: int = 1):
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET universal_fragments = universal_fragments + $2 WHERE user_id = $1",
        user_id, amount)


async def use_universal_fragments(user_id: int, amount: int) -> bool:
    """만능 조각 차감. 부족하면 False."""
    pool = await get_db()
    row = await pool.fetchrow(
        "UPDATE users SET universal_fragments = universal_fragments - $2 WHERE user_id = $1 AND universal_fragments >= $2 RETURNING universal_fragments",
        user_id, amount)
    return row is not None


async def apply_iv_stone(user_id: int, instance_id: int, stat: str) -> dict | None:
    """IV 스톤 적용: 해당 스탯 +3 (최대 31). 성공 시 업데이트된 row 반환."""
    pool = await get_db()
    valid_stats = {"iv_hp", "iv_atk", "iv_def", "iv_spa", "iv_spdef", "iv_spd"}
    if stat not in valid_stats:
        return None
    async with pool.acquire() as conn:
        async with conn.transaction():
            # IV 스톤 차감
            used = await conn.fetchrow(
                "UPDATE users SET iv_stones = iv_stones - 1 WHERE user_id = $1 AND iv_stones > 0 RETURNING iv_stones",
                user_id)
            if not used:
                return None
            # IV 적용
            row = await conn.fetchrow(
                f"UPDATE user_pokemon SET {stat} = LEAST(COALESCE({stat}, 15) + 3, 31) "
                f"WHERE id = $1 AND user_id = $2 "
                f"RETURNING id, pokemon_id, iv_hp, iv_atk, iv_def, iv_spa, iv_spdef, iv_spd",
                instance_id, user_id)
            return dict(row) if row else None
