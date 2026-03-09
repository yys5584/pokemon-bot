"""Market service: listing creation, purchase, cancellation, and validation."""

import logging
import math

import config
from database import queries
from database import battle_queries as bq
from services.evolution_service import build_trade_evo_info
from utils.helpers import update_title

logger = logging.getLogger(__name__)


def calc_fee(price_bp: int) -> int:
    """Calculate marketplace fee (5%, rounded up)."""
    return max(1, math.ceil(price_bp * config.MARKET_FEE_RATE))


async def create_listing(
    user_id: int, pokemon_name: str, price_bp: int,
    instance_id: int | None = None,
) -> tuple[bool, str, int | None, list | None]:
    """Create a market listing.

    Returns (success, message, listing_id, duplicates_for_selection).
    If duplicates_for_selection is not None, caller should show selection UI.
    """
    # Validate price
    if price_bp < config.MARKET_MIN_PRICE:
        return False, f"최소 등록가는 {config.MARKET_MIN_PRICE:,} BP입니다.", None, None

    # Check listing count limit
    count = await queries.get_active_listing_count(user_id)
    if count >= config.MARKET_MAX_ACTIVE_LISTINGS:
        return False, f"최대 {config.MARKET_MAX_ACTIVE_LISTINGS}개까지 등록할 수 있습니다.", None, None

    # Find the Pokemon
    if instance_id:
        pokemon = await queries.get_user_pokemon_by_id(instance_id)
        if not pokemon or pokemon["user_id"] != user_id or not pokemon.get("is_active"):
            return False, "해당 포켓몬을 보유하고 있지 않습니다.", None, None
    else:
        # Find all matching pokemon by name
        all_pokemon = await queries.get_user_pokemon_list(user_id)
        name_lower = pokemon_name.strip().lower()
        matches = [p for p in all_pokemon if p["name_ko"].lower() == name_lower]
        if not matches:
            # Partial match
            matches = [p for p in all_pokemon if name_lower in p["name_ko"].lower()]
        if not matches:
            return False, f"'{pokemon_name}'을(를) 보유하고 있지 않습니다.", None, None
        if len(matches) > 1:
            # Return duplicates for selection
            return False, "", None, matches
        pokemon = matches[0]

    # Check pokemon lock (pending trade or market listing)
    locked, reason = await queries.is_pokemon_locked(pokemon["id"])
    if locked:
        return False, reason, None, None

    # Check not on battle team
    if pokemon.get("team_slot") is not None:
        return False, "배틀 팀에 등록된 포켓몬은 거래소에 올릴 수 없습니다.\n팀해제 후 다시 시도하세요.", None, None

    # Check not favorited
    if pokemon.get("is_favorite"):
        return False, "즐겨찾기 포켓몬은 거래소에 올릴 수 없습니다.\n즐겨찾기 해제 후 다시 시도하세요.", None, None

    # Create listing
    listing_id = await queries.create_market_listing(
        seller_id=user_id,
        pokemon_instance_id=pokemon["id"],
        pokemon_id=pokemon["pokemon_id"],
        pokemon_name=pokemon["name_ko"],
        is_shiny=pokemon.get("is_shiny", 0),
        price_bp=price_bp,
    )

    fee = calc_fee(price_bp)
    seller_gets = price_bp - fee
    shiny_tag = " ★이로치" if pokemon.get("is_shiny") else ""
    return True, (
        f"🏪 거래소 등록 완료!\n\n"
        f"{pokemon['emoji']} {pokemon['name_ko']}{shiny_tag}\n"
        f"💰 판매가: {price_bp:,} BP\n"
        f"📋 수수료: {fee:,} BP ({int(config.MARKET_FEE_RATE*100)}%)\n"
        f"💵 수익 예상: {seller_gets:,} BP\n\n"
        f"등록 번호: #{listing_id}"
    ), listing_id, None


async def buy_listing(
    buyer_id: int, listing_id: int,
) -> tuple[bool, str, dict | None]:
    """Purchase a listed Pokemon.

    Returns (success, message, info_for_notification).
    """
    listing = await queries.get_listing_by_id(listing_id)
    if not listing:
        return False, "해당 매물을 찾을 수 없습니다.", None

    if listing["status"] != "active":
        return False, "이미 판매된 매물입니다.", None

    if listing["seller_id"] == buyer_id:
        return False, "자신의 매물은 구매할 수 없습니다.", None

    price = listing["price_bp"]
    fee = calc_fee(price)

    # Check buyer BP
    buyer_bp = await bq.get_bp(buyer_id)
    if buyer_bp < price:
        return False, f"BP가 부족합니다. (필요: {price:,} BP, 보유: {buyer_bp:,} BP)", None

    # Prepare IVs
    ivs = {
        "iv_hp": listing.get("iv_hp"),
        "iv_atk": listing.get("iv_atk"),
        "iv_def": listing.get("iv_def"),
        "iv_spa": listing.get("iv_spa"),
        "iv_spdef": listing.get("iv_spdef"),
        "iv_spd": listing.get("iv_spd"),
    }

    is_shiny = bool(listing.get("is_shiny", 0))

    # Execute purchase in transaction
    try:
        new_instance_id = await queries.complete_market_purchase(
            listing_id=listing_id,
            buyer_id=buyer_id,
            seller_id=listing["seller_id"],
            price_bp=price,
            fee_bp=fee,
            pokemon_instance_id=listing["pokemon_instance_id"],
            pokemon_id=listing["pokemon_id"],
            is_shiny=is_shiny,
            ivs=ivs,
        )
    except ValueError as e:
        return False, str(e), None
    except Exception as e:
        logger.error(f"Market purchase failed: {e}")
        return False, "거래 처리 중 오류가 발생했습니다.", None

    # Check for trade evolution eligibility (don't auto-evolve)
    pending_evo = build_trade_evo_info(listing["pokemon_id"], new_instance_id)

    # Update titles
    await update_title(buyer_id)
    await update_title(listing["seller_id"])

    shiny_tag = " ★이로치" if is_shiny else ""
    seller_gets = price - fee
    msg = (
        f"🎉 구매 완료!\n\n"
        f"{listing['emoji']} {listing['pokemon_name']}{shiny_tag}\n"
        f"💰 {price:,} BP 지불"
    )

    return True, msg, {
        "seller_id": listing["seller_id"],
        "seller_name": listing.get("seller_name", ""),
        "buyer_id": buyer_id,
        "pokemon_name": listing["pokemon_name"],
        "emoji": listing["emoji"],
        "price": price,
        "fee": fee,
        "seller_gets": seller_gets,
        "is_shiny": is_shiny,
        "pending_evo": pending_evo,
    }


async def cancel_listing_for_user(
    user_id: int, listing_id: int,
) -> tuple[bool, str]:
    """Cancel a listing owned by this user."""
    listing = await queries.get_listing_by_id(listing_id)
    if not listing:
        return False, "해당 매물을 찾을 수 없습니다."
    if listing["seller_id"] != user_id:
        return False, "본인의 매물만 취소할 수 있습니다."
    if listing["status"] != "active":
        return False, "이미 처리된 매물입니다."

    await queries.cancel_listing(listing_id)

    shiny_tag = " ★이로치" if listing.get("is_shiny") else ""
    return True, (
        f"✅ 거래소 등록 취소!\n"
        f"{listing['emoji']} {listing['pokemon_name']}{shiny_tag} (#{listing_id})"
    )
