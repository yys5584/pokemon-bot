"""Trade service: trade creation, acceptance, and trade evolution."""

import logging
from database import queries
from services.evolution_service import try_trade_evolve
from utils.helpers import update_title

logger = logging.getLogger(__name__)


async def create_trade_offer(
    from_user_id: int, to_user_id: int,
    pokemon_name: str
) -> tuple[bool, str, int | None]:
    """Create a trade offer. Returns (success, message, trade_id)."""

    # Find the Pokemon in the user's collection
    pokemon = await queries.find_user_pokemon_by_name(from_user_id, pokemon_name)
    if not pokemon:
        return False, f"'{pokemon_name}'을(를) 보유하고 있지 않습니다.", None

    # Check target user exists
    target = await queries.get_user(to_user_id)
    if not target:
        return False, "상대 트레이너를 찾을 수 없습니다.\n상대방이 먼저 /start 를 해야 합니다.", None

    # Check existing pending trade
    existing = await queries.get_pending_trade_between(from_user_id, to_user_id)
    if existing:
        return False, "이미 해당 트레이너에게 보낸 교환 요청이 있습니다.", None

    # Check if this Pokemon is already in another pending trade
    existing_for_pokemon = await queries.get_pending_trade_for_pokemon(pokemon["id"])
    if existing_for_pokemon:
        return False, "이 포켓몬은 이미 다른 교환 요청에 등록되어 있습니다.", None

    # Create trade
    trade_id = await queries.create_trade(
        from_user_id, to_user_id, pokemon["id"]
    )

    return True, (
        f"📤 교환 요청을 보냈습니다!\n\n"
        f"제안: {pokemon['emoji']} {pokemon['name_ko']}\n"
        f"상대: {target['display_name']}\n\n"
        f"상대방에게 DM으로 알림이 갑니다."
    ), trade_id


async def accept_trade(user_id: int, trade_id: int) -> tuple[bool, str, dict | None]:
    """Accept a trade. Returns (success, message, trade_info for notifications)."""
    trade = await queries.get_trade(trade_id)
    if not trade:
        return False, "해당 교환 요청을 찾을 수 없습니다.", None

    if trade["to_user_id"] != user_id:
        return False, "해당 교환 요청을 찾을 수 없습니다.", None

    if trade["status"] != "pending":
        return False, "이미 처리된 교환입니다.", None

    offer_instance_id = trade["offer_pokemon_instance_id"]
    offer_pokemon_id = trade["offer_pokemon_id"]
    from_user_id = trade["from_user_id"]

    # Verify the Pokemon is still active (not already traded away)
    offer_pokemon = await queries.get_user_pokemon_by_id(offer_instance_id)
    if not offer_pokemon or offer_pokemon["user_id"] != from_user_id:
        await queries.update_trade_status(trade_id, "cancelled")
        return False, "이 포켓몬은 이미 교환되었거나 존재하지 않습니다.", None

    # Deactivate from sender's collection
    await queries.deactivate_pokemon(offer_instance_id)

    # Give to receiver
    new_instance_id = await queries.give_pokemon_to_user(user_id, offer_pokemon_id)

    # Register in receiver's pokedex
    await queries.register_pokedex(user_id, offer_pokemon_id, "trade")

    # Check for trade evolution
    evo_msg = await try_trade_evolve(user_id, new_instance_id, offer_pokemon_id)

    # Update trade status
    await queries.update_trade_status(trade_id, "accepted")

    # Update titles
    await update_title(user_id)
    await update_title(from_user_id)

    msg = (
        f"✅ 교환 성사!\n\n"
        f"{trade['offer_emoji']} {trade['offer_name']}을(를) 받았습니다!"
    )
    if evo_msg:
        msg += evo_msg

    return True, msg, trade
