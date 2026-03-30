"""Marketplace (거래소) database query functions."""

import logging
from database.connection import get_db
import config as _cfg

logger = logging.getLogger(__name__)


# ============================================================
# Marketplace
# ============================================================

async def create_market_listing(
    seller_id: int, pokemon_instance_id: int,
    pokemon_id: int, pokemon_name: str,
    is_shiny: int, price_bp: int,
) -> int:
    """Create a marketplace listing. Returns listing id."""
    pool = await get_db()
    row = await pool.fetchrow(
        """INSERT INTO market_listings
           (seller_id, pokemon_instance_id, pokemon_id, pokemon_name, is_shiny, price_bp)
           VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
        seller_id, pokemon_instance_id, pokemon_id, pokemon_name, is_shiny, price_bp,
    )
    return row["id"]


async def get_active_listings(
    page: int = 0, page_size: int = 5,
    rarity: str | None = None, iv_grade: str | None = None,
) -> tuple[list[dict], int]:
    """Get paginated active listings (newest first). Returns (listings, total_count).

    Filters:
      rarity: 'common','rare','epic','legendary','ultra_legendary'
      iv_grade: 'S'/'A'/'B'/'C' — uses config.IV_GRADE_THRESHOLDS
    """
    pool = await get_db()

    # Build WHERE clauses and params dynamically
    where = ["ml.status = 'active'", "ml.created_at > NOW() - INTERVAL '7 days'"]
    params = []
    idx = 1

    if rarity:
        params.append(rarity)
        where.append(f"pm.rarity = ${idx}")
        idx += 1

    # IV grade filter: "X이상" — show X grade and above (using config thresholds)
    iv_thresholds = {g: t for g, t, _ in _cfg.IV_GRADE_THRESHOLDS if g != "D"}
    if iv_grade and iv_grade in iv_thresholds:
        min_iv = iv_thresholds[iv_grade]
        where.append(f"(COALESCE(up.iv_hp,0)+COALESCE(up.iv_atk,0)+COALESCE(up.iv_def,0)+COALESCE(up.iv_spa,0)+COALESCE(up.iv_spdef,0)+COALESCE(up.iv_spd,0)) >= ${idx}")
        params.append(min_iv)
        idx += 1

    where_sql = " AND ".join(where)

    count_row = await pool.fetchrow(
        f"""SELECT COUNT(*) AS cnt FROM market_listings ml
           JOIN pokemon_master pm ON ml.pokemon_id = pm.id
           JOIN user_pokemon up ON ml.pokemon_instance_id = up.id
           WHERE {where_sql}""",
        *params,
    )
    total = count_row["cnt"]

    params.append(page_size)
    params.append(page * page_size)
    rows = await pool.fetch(
        f"""SELECT ml.*, u.display_name AS seller_name,
                  pm.name_ko, pm.name_en, pm.emoji, pm.rarity,
                  up.iv_hp, up.iv_atk, up.iv_def,
                  up.iv_spa, up.iv_spdef, up.iv_spd,
                  up.friendship
           FROM market_listings ml
           JOIN users u ON ml.seller_id = u.user_id
           JOIN pokemon_master pm ON ml.pokemon_id = pm.id
           JOIN user_pokemon up ON ml.pokemon_instance_id = up.id
           WHERE {where_sql}
           ORDER BY ml.created_at DESC
           LIMIT ${idx} OFFSET ${idx + 1}""",
        *params,
    )
    return [dict(r) for r in rows], total


async def get_active_listings_web(
    page: int = 0, page_size: int = 20,
    rarity: str | None = None,
    iv_grade: str | None = None,
    shiny_only: bool = False,
    search: str | None = None,
    price_min: int | None = None,
    price_max: int | None = None,
    sort: str = "newest",
) -> tuple[list[dict], int]:
    """Get paginated active listings for web dashboard.

    Extended version of get_active_listings() with more filters and sort options.
    Returns (listings, total_count).
    """
    pool = await get_db()

    where = ["ml.status = 'active'", "ml.created_at > NOW() - INTERVAL '7 days'"]
    params: list = []
    idx = 1

    if rarity:
        params.append(rarity)
        where.append(f"pm.rarity = ${idx}")
        idx += 1

    # IV grade filter
    iv_thresholds = {g: t for t, g, _ in _cfg.IV_GRADE_THRESHOLDS if g != "D"}
    if iv_grade and iv_grade in iv_thresholds:
        min_iv = iv_thresholds[iv_grade]
        where.append(
            f"(COALESCE(up.iv_hp,0)+COALESCE(up.iv_atk,0)+COALESCE(up.iv_def,0)"
            f"+COALESCE(up.iv_spa,0)+COALESCE(up.iv_spdef,0)+COALESCE(up.iv_spd,0)) >= ${idx}"
        )
        params.append(min_iv)
        idx += 1

    if shiny_only:
        where.append("up.is_shiny = 1")

    if search:
        params.append(f"%{search}%")
        where.append(f"ml.pokemon_name ILIKE ${idx}")
        idx += 1

    if price_min is not None:
        params.append(price_min)
        where.append(f"ml.price_bp >= ${idx}")
        idx += 1

    if price_max is not None:
        params.append(price_max)
        where.append(f"ml.price_bp <= ${idx}")
        idx += 1

    where_sql = " AND ".join(where)

    # Sort
    sort_map = {
        "newest": "ml.created_at DESC",
        "price_asc": "ml.price_bp ASC",
        "price_desc": "ml.price_bp DESC",
        "rarity": """CASE pm.rarity
            WHEN 'ultra_legendary' THEN 1 WHEN 'legendary' THEN 2
            WHEN 'epic' THEN 3 WHEN 'rare' THEN 4 ELSE 5 END, ml.created_at DESC""",
    }
    order_sql = sort_map.get(sort, "ml.created_at DESC")

    count_row = await pool.fetchrow(
        f"""SELECT COUNT(*) AS cnt FROM market_listings ml
           JOIN pokemon_master pm ON ml.pokemon_id = pm.id
           JOIN user_pokemon up ON ml.pokemon_instance_id = up.id
           WHERE {where_sql}""",
        *params,
    )
    total = count_row["cnt"]

    params.append(page_size)
    params.append(page * page_size)
    rows = await pool.fetch(
        f"""SELECT ml.id, ml.seller_id, ml.pokemon_id, ml.pokemon_name,
                  ml.price_bp, ml.created_at, ml.is_shiny,
                  u.display_name AS seller_name,
                  pm.emoji, pm.rarity, pm.pokemon_type,
                  up.iv_hp, up.iv_atk, up.iv_def,
                  up.iv_spa, up.iv_spdef, up.iv_spd,
                  up.friendship
           FROM market_listings ml
           JOIN users u ON ml.seller_id = u.user_id
           JOIN pokemon_master pm ON ml.pokemon_id = pm.id
           JOIN user_pokemon up ON ml.pokemon_instance_id = up.id
           WHERE {where_sql}
           ORDER BY {order_sql}
           LIMIT ${idx} OFFSET ${idx + 1}""",
        *params,
    )
    return [dict(r) for r in rows], total


async def get_listing_by_id(listing_id: int) -> dict | None:
    """Get a specific listing with full details."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT ml.*, u.display_name AS seller_name,
                  pm.name_ko, pm.name_en, pm.emoji, pm.rarity,
                  pm.evolution_method, pm.evolves_to,
                  up.iv_hp, up.iv_atk, up.iv_def,
                  up.iv_spa, up.iv_spdef, up.iv_spd,
                  up.friendship, up.user_id AS current_owner_id,
                  up.personality
           FROM market_listings ml
           JOIN users u ON ml.seller_id = u.user_id
           JOIN pokemon_master pm ON ml.pokemon_id = pm.id
           JOIN user_pokemon up ON ml.pokemon_instance_id = up.id
           WHERE ml.id = $1""",
        listing_id,
    )
    return dict(row) if row else None


async def get_user_active_listings(user_id: int) -> list[dict]:
    """Get all active listings by a specific user."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT ml.*, pm.name_ko, pm.name_en, pm.emoji, pm.rarity
           FROM market_listings ml
           JOIN pokemon_master pm ON ml.pokemon_id = pm.id
           WHERE ml.seller_id = $1 AND ml.status = 'active'
           ORDER BY ml.created_at DESC""",
        user_id,
    )
    return [dict(r) for r in rows]


async def get_active_listing_count(user_id: int) -> int:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT COUNT(*) AS cnt FROM market_listings WHERE seller_id = $1 AND status = 'active'",
        user_id,
    )
    return row["cnt"]


async def cancel_listing(listing_id: int):
    pool = await get_db()
    await pool.execute(
        "UPDATE market_listings SET status = 'cancelled' WHERE id = $1",
        listing_id,
    )


async def search_listings(pokemon_name: str, page: int = 0, page_size: int = 5) -> tuple[list[dict], int]:
    """Search active listings by Pokemon name."""
    pool = await get_db()
    pattern = f"%{pokemon_name}%"
    count_row = await pool.fetchrow(
        """SELECT COUNT(*) AS cnt FROM market_listings ml
           JOIN pokemon_master pm ON ml.pokemon_id = pm.id
           WHERE ml.status = 'active'
             AND (ml.pokemon_name LIKE $1 OR pm.name_en ILIKE $1)
             AND ml.created_at > NOW() - INTERVAL '7 days'""",
        pattern,
    )
    total = count_row["cnt"]
    rows = await pool.fetch(
        """SELECT ml.*, u.display_name AS seller_name,
                  pm.name_ko, pm.name_en, pm.emoji, pm.rarity,
                  up.iv_hp, up.iv_atk, up.iv_def,
                  up.iv_spa, up.iv_spdef, up.iv_spd,
                  up.friendship
           FROM market_listings ml
           JOIN users u ON ml.seller_id = u.user_id
           JOIN pokemon_master pm ON ml.pokemon_id = pm.id
           JOIN user_pokemon up ON ml.pokemon_instance_id = up.id
           WHERE ml.status = 'active'
             AND (ml.pokemon_name LIKE $1 OR pm.name_en ILIKE $1)
             AND ml.created_at > NOW() - INTERVAL '7 days'
           ORDER BY ml.created_at DESC
           LIMIT $2 OFFSET $3""",
        pattern, page_size, page * page_size,
    )
    return [dict(r) for r in rows], total


async def get_pending_listing_for_pokemon(instance_id: int) -> dict | None:
    """Check if a Pokemon instance is currently listed on the market."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT * FROM market_listings
           WHERE pokemon_instance_id = $1 AND status = 'active'
           LIMIT 1""",
        instance_id,
    )
    return dict(row) if row else None


async def is_pokemon_locked(instance_id: int) -> tuple[bool, str]:
    """Check if a Pokemon is locked (in trade, market, or camp).
    Returns (is_locked, reason_message)."""
    # 지연 import로 순환 참조 방지
    from database.trade_queries import get_pending_trade_for_pokemon

    pending_trade = await get_pending_trade_for_pokemon(instance_id)
    if pending_trade:
        return True, "이 포켓몬은 교환 대기 중입니다."
    pending_listing = await get_pending_listing_for_pokemon(instance_id)
    if pending_listing:
        return True, "이 포켓몬은 거래소에 등록되어 있습니다."
    # 캠프 배치 체크
    pool = await get_db()
    camp_row = await pool.fetchval(
        "SELECT 1 FROM camp_placements WHERE instance_id = $1 LIMIT 1",
        instance_id,
    )
    if camp_row:
        return True, "🏕 이 포켓몬은 캠프에 배치되어 있습니다. 배치 해제 후 시도하세요."
    # 이로치 전환 대기 체크
    shiny_row = await pool.fetchval(
        "SELECT 1 FROM camp_shiny_pending WHERE instance_id = $1 AND NOT completed LIMIT 1",
        instance_id,
    )
    if shiny_row:
        return True, "✨ 이 포켓몬은 이로치 전환 대기 중입니다."
    return False, ""


async def get_pair_trade_count_this_week(user_a: int, user_b: int) -> int:
    """동일 유저 쌍의 이번 주(KST 월요일 기준) 거래 수."""
    pool = await get_db()
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM market_listings "
        "WHERE status = 'sold' "
        "AND sold_at >= date_trunc('week', NOW() AT TIME ZONE 'Asia/Seoul') AT TIME ZONE 'Asia/Seoul' "
        "AND ((seller_id = $1 AND buyer_id = $2) OR (seller_id = $2 AND buyer_id = $1))",
        user_a, user_b,
    )
    return count or 0


async def complete_market_purchase(
    listing_id: int, buyer_id: int,
    seller_id: int, price_bp: int, fee_bp: int,
    pokemon_instance_id: int, pokemon_id: int,
    is_shiny: bool, ivs: dict, personality: str | None = None,
) -> int:
    """Execute a market purchase in a single transaction. Returns new_instance_id."""
    pool = await get_db()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # 1. Lock listing row & verify still active
            listing = await conn.fetchrow(
                "SELECT * FROM market_listings WHERE id = $1 AND status = 'active' FOR UPDATE",
                listing_id,
            )
            if not listing:
                raise ValueError("이 매물은 이미 판매되었거나 취소되었습니다.")

            # 2. Verify buyer has enough BP
            buyer = await conn.fetchrow(
                "SELECT battle_points FROM users WHERE user_id = $1 FOR UPDATE",
                buyer_id,
            )
            if not buyer or buyer["battle_points"] < price_bp:
                raise ValueError("BP가 부족합니다.")

            # 3. Verify pokemon still active & owned by seller
            pokemon = await conn.fetchrow(
                "SELECT * FROM user_pokemon WHERE id = $1 AND is_active = 1 AND user_id = $2",
                pokemon_instance_id, seller_id,
            )
            if not pokemon:
                raise ValueError("이 포켓몬은 이미 거래되었습니다.")

            # 4. Deduct BP from buyer
            await conn.execute(
                "UPDATE users SET battle_points = battle_points - $1 WHERE user_id = $2",
                price_bp, buyer_id,
            )

            # 5. Add BP to seller (minus fee)
            seller_gets = price_bp - fee_bp
            await conn.execute(
                "UPDATE users SET battle_points = battle_points + $1 WHERE user_id = $2",
                seller_gets, seller_id,
            )

            # 6. Deactivate pokemon from seller + camp placement removal
            await conn.execute(
                "UPDATE user_pokemon SET is_active = 0 WHERE id = $1",
                pokemon_instance_id,
            )
            await conn.execute(
                "DELETE FROM camp_placements WHERE instance_id = $1",
                pokemon_instance_id,
            )

            # 7. Give pokemon to buyer (preserve IVs + shiny + personality)
            new_row = await conn.fetchrow(
                """INSERT INTO user_pokemon
                       (user_id, pokemon_id, is_shiny,
                        iv_hp, iv_atk, iv_def, iv_spa, iv_spdef, iv_spd, personality)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) RETURNING id""",
                buyer_id, pokemon_id, 1 if is_shiny else 0,
                ivs.get("iv_hp"), ivs.get("iv_atk"), ivs.get("iv_def"),
                ivs.get("iv_spa"), ivs.get("iv_spdef"), ivs.get("iv_spd"),
                personality,
            )

            # 8. Register in buyer's pokedex
            await conn.execute(
                """INSERT INTO pokedex (user_id, pokemon_id, method)
                   VALUES ($1, $2, 'trade')
                   ON CONFLICT (user_id, pokemon_id) DO NOTHING""",
                buyer_id, pokemon_id,
            )

            # 9. Update listing
            await conn.execute(
                """UPDATE market_listings
                   SET status = 'sold', buyer_id = $1, sold_at = NOW()
                   WHERE id = $2""",
                buyer_id, listing_id,
            )

            return new_row["id"]


async def cleanup_expired_listings():
    """Mark old active listings as expired."""
    pool = await get_db()
    await pool.execute(
        """UPDATE market_listings
           SET status = 'expired'
           WHERE status = 'active'
           AND created_at < NOW() - INTERVAL '7 days'"""
    )
