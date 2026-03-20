"""Trade / Group Trade related database queries."""

import logging
from database.connection import get_db

logger = logging.getLogger(__name__)


# ============================================================
# Trades
# ============================================================

async def create_trade(
    from_user_id: int, to_user_id: int,
    offer_instance_id: int, request_name: str | None = None
) -> int:
    pool = await get_db()
    row = await pool.fetchrow(
        """INSERT INTO trades
           (from_user_id, to_user_id, offer_pokemon_instance_id, request_pokemon_name)
           VALUES ($1, $2, $3, $4) RETURNING id""",
        from_user_id, to_user_id, offer_instance_id, request_name,
    )
    return row["id"]


async def get_pending_trades_for_user(user_id: int) -> list[dict]:
    """Get all pending trade offers received by a user."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT t.*, u.display_name as from_name,
                  pm.name_ko as offer_name, pm.emoji as offer_emoji,
                  up.is_shiny as offer_is_shiny,
                  up.pokemon_id as offer_pokemon_id
           FROM trades t
           JOIN users u ON t.from_user_id = u.user_id
           JOIN user_pokemon up ON t.offer_pokemon_instance_id = up.id
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE t.to_user_id = $1 AND t.status = 'pending'
           ORDER BY t.created_at DESC""",
        user_id,
    )
    return [dict(r) for r in rows]


async def get_trade(trade_id: int) -> dict | None:
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT t.*, up.pokemon_id as offer_pokemon_id,
                  pm.name_ko as offer_name, pm.emoji as offer_emoji,
                  pm.evolution_method, pm.evolves_to,
                  up.is_shiny as offer_is_shiny
           FROM trades t
           JOIN user_pokemon up ON t.offer_pokemon_instance_id = up.id
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE t.id = $1""",
        trade_id,
    )
    return dict(row) if row else None


async def update_trade_status(trade_id: int, status: str, *, require_pending: bool = False):
    pool = await get_db()
    if require_pending:
        row = await pool.fetchrow(
            "UPDATE trades SET status = $1, resolved_at = NOW() WHERE id = $2 AND status = 'pending' RETURNING id",
            status, trade_id,
        )
        return row is not None
    await pool.execute(
        "UPDATE trades SET status = $1, resolved_at = NOW() WHERE id = $2",
        status, trade_id,
    )


async def get_pending_trade_for_pokemon(instance_id: int) -> dict | None:
    """Check if a Pokemon instance is already in a pending trade."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT * FROM trades
           WHERE offer_pokemon_instance_id = $1 AND status = 'pending'
           LIMIT 1""",
        instance_id,
    )
    return dict(row) if row else None


async def get_pending_trade_between(from_user: int, to_user: int) -> dict | None:
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT * FROM trades
           WHERE from_user_id = $1 AND to_user_id = $2 AND status = 'pending'
           LIMIT 1""",
        from_user, to_user,
    )
    return dict(row) if row else None


# ============================================================
# Group Trades
# ============================================================

async def create_group_trade(
    from_user_id: int, to_user_id: int,
    offer_instance_id: int, chat_id: int, message_id: int | None = None,
) -> int:
    """Create a group trade offer. Returns trade id."""
    pool = await get_db()
    row = await pool.fetchrow(
        """INSERT INTO trades
           (from_user_id, to_user_id, offer_pokemon_instance_id,
            trade_type, chat_id, message_id)
           VALUES ($1, $2, $3, 'group', $4, $5) RETURNING id""",
        from_user_id, to_user_id, offer_instance_id, chat_id, message_id,
    )
    return row["id"]


async def get_group_trade(trade_id: int) -> dict | None:
    """Get a group trade with full Pokemon details."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT t.*, up.pokemon_id AS offer_pokemon_id,
                  pm.name_ko AS offer_name, pm.emoji AS offer_emoji,
                  pm.rarity AS offer_rarity,
                  pm.evolution_method, pm.evolves_to,
                  up.is_shiny AS offer_is_shiny,
                  up.iv_hp, up.iv_atk, up.iv_def,
                  up.iv_spa, up.iv_spdef, up.iv_spd,
                  up.friendship,
                  u_from.display_name AS from_name,
                  u_to.display_name AS to_name
           FROM trades t
           JOIN user_pokemon up ON t.offer_pokemon_instance_id = up.id
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           JOIN users u_from ON t.from_user_id = u_from.user_id
           JOIN users u_to ON t.to_user_id = u_to.user_id
           WHERE t.id = $1""",
        trade_id,
    )
    return dict(row) if row else None


async def update_group_trade_message_id(trade_id: int, message_id: int):
    pool = await get_db()
    await pool.execute(
        "UPDATE trades SET message_id = $1 WHERE id = $2",
        message_id, trade_id,
    )


# ============================================================
# Trade daily limits & expiry
# ============================================================

async def get_daily_trade_count(user_id: int, role: str = "sender") -> int:
    """오늘 교환 횟수 (role='sender': 보낸 횟수, 'receiver': 받은 횟수)."""
    pool = await get_db()
    col = "from_user_id" if role == "sender" else "to_user_id"
    return await pool.fetchval(
        f"SELECT COUNT(*) FROM trades WHERE {col} = $1 AND created_at >= date_trunc('day', NOW() AT TIME ZONE 'Asia/Seoul') AT TIME ZONE 'Asia/Seoul'",
        user_id,
    ) or 0


async def expire_old_pending_trades(expire_minutes: int = 5) -> list[int]:
    """만료된 pending 교환을 cancelled로 변경하고 BP 환불. 환불된 user_id 리스트 반환."""
    import config
    pool = await get_db()
    expired = await pool.fetch(
        """UPDATE trades SET status = 'cancelled'
           WHERE status = 'pending'
             AND created_at < NOW() - make_interval(mins => $1)
           RETURNING id, from_user_id, trade_type""",
        expire_minutes,
    )
    refunded_users = []
    for r in expired:
        cost = config.GROUP_TRADE_BP_COST if r["trade_type"] == "group" else config.TRADE_BP_COST
        await pool.execute(
            "UPDATE users SET battle_points = battle_points + $1 WHERE user_id = $2",
            cost, r["from_user_id"],
        )
        refunded_users.append(r["from_user_id"])
    return refunded_users
