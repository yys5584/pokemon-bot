"""Trade service: trade creation, acceptance, and trade evolution."""

import asyncio
import logging
import config
from database import queries
from database import battle_queries as bq
from services.evolution_service import build_trade_evo_info
from utils.helpers import update_title, type_badge, icon_emoji
from models.pokemon_data import ALL_POKEMON

# evolves_from 빠른 조회용 dict: {pokemon_id: evolves_from_id or None}
_EVOLVES_FROM = {p[0]: p[6] for p in ALL_POKEMON}

logger = logging.getLogger(__name__)


async def create_trade_offer(
    from_user_id: int, to_user_id: int,
    pokemon_name: str, instance_id: int | None = None
) -> tuple[bool, str, int | None]:
    """Create a trade offer. Returns (success, message, trade_id)."""

    cost = config.TRADE_BP_COST

    # Phase 1: BP check + pokemon lookup + target user in parallel
    if instance_id:
        bp_task = bq.get_bp(from_user_id)
        poke_task = queries.get_user_pokemon_by_id(instance_id)
        target_task = queries.get_user(to_user_id)
        current_bp, pokemon, target = await asyncio.gather(bp_task, poke_task, target_task)
        if not pokemon or pokemon["user_id"] != from_user_id:
            return False, f"'{pokemon_name}'을(를) 보유하고 있지 않습니다.", None
    else:
        bp_task = bq.get_bp(from_user_id)
        poke_task = queries.find_user_pokemon_by_name(from_user_id, pokemon_name)
        target_task = queries.get_user(to_user_id)
        current_bp, pokemon, target = await asyncio.gather(bp_task, poke_task, target_task)
        if not pokemon:
            return False, f"'{pokemon_name}'을(를) 보유하고 있지 않습니다.", None

    if current_bp < cost:
        return False, f"BP가 부족합니다! (필요: {cost} BP, 보유: {current_bp} BP)", None
    if not target:
        return False, "상대 트레이너를 찾을 수 없습니다.\n상대방이 먼저 /start 를 해야 합니다.", None

    # Phase 2: pending trade check + lock check in parallel
    existing, (locked, lock_reason) = await asyncio.gather(
        queries.get_pending_trade_between(from_user_id, to_user_id),
        queries.is_pokemon_locked(pokemon["id"]),
    )
    if existing:
        return False, "이미 해당 트레이너에게 보낸 교환 요청이 있습니다.", None
    if locked:
        return False, lock_reason, None

    # Deduct BP
    spent = await bq.spend_bp(from_user_id, cost)
    if not spent:
        return False, f"BP 차감에 실패했습니다. (필요: {cost} BP)", None

    # Create trade + get remaining BP in parallel
    trade_id, remaining_bp = await asyncio.gather(
        queries.create_trade(from_user_id, to_user_id, pokemon["id"]),
        bq.get_bp(from_user_id),
    )

    is_shiny = bool(pokemon.get("is_shiny", 0))
    shiny_tag = " ★이로치" if is_shiny else ""
    return True, (
        f"📤 교환 요청을 보냈습니다!\n\n"
        f"제안: {pokemon['emoji']} {pokemon['name_ko']}{shiny_tag}\n"
        f"상대: {target['display_name']}\n"
        f"💰 BP {cost} 차감 (잔여: {remaining_bp} BP)\n\n"
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

    # Atomically claim this trade (prevents race condition / double-accept)
    claimed = await queries.update_trade_status(trade_id, "accepted", require_pending=True)
    if not claimed:
        return False, "이미 처리된 교환입니다.", None

    offer_instance_id = trade["offer_pokemon_instance_id"]
    offer_pokemon_id = trade["offer_pokemon_id"]
    from_user_id = trade["from_user_id"]

    # Verify the Pokemon is still active
    offer_pokemon = await queries.get_user_pokemon_by_id(offer_instance_id)
    if not offer_pokemon or offer_pokemon["user_id"] != from_user_id:
        await queries.update_trade_status(trade_id, "cancelled")
        return False, "이 포켓몬은 이미 교환되었거나 존재하지 않습니다.", None

    # Deactivate from sender's collection
    await queries.deactivate_pokemon(offer_instance_id)

    # Give to receiver (preserve shiny status + IVs, reset friendship)
    is_shiny = bool(offer_pokemon.get("is_shiny", 0))
    original_ivs = {
        "iv_hp": offer_pokemon.get("iv_hp"),
        "iv_atk": offer_pokemon.get("iv_atk"),
        "iv_def": offer_pokemon.get("iv_def"),
        "iv_spa": offer_pokemon.get("iv_spa"),
        "iv_spdef": offer_pokemon.get("iv_spdef"),
        "iv_spd": offer_pokemon.get("iv_spd"),
    }
    # 진화형 포켓몬 교환 시 친밀도 강화 잠금
    is_evolved = _EVOLVES_FROM.get(offer_pokemon_id) is not None
    new_instance_id, _ivs = await queries.give_pokemon_to_user(
        user_id, offer_pokemon_id, is_shiny=is_shiny, ivs=original_ivs,
        nurture_locked=is_evolved,
    )

    # Phase: pokedex + title updates in parallel (trade status already set above)
    reg_task = queries.register_pokedex(user_id, offer_pokemon_id, "trade")
    title1_task = update_title(user_id)
    title2_task = update_title(from_user_id)

    await asyncio.gather(reg_task, title1_task, title2_task)

    # Check trade evolution eligibility (don't auto-evolve)
    pending_evo = build_trade_evo_info(offer_pokemon_id, new_instance_id)

    shiny_tag = " ★이로치" if is_shiny else ""
    tb = type_badge(trade["offer_pokemon_id"]) if trade.get("offer_pokemon_id") else ""
    msg = (
        f"{icon_emoji('check')} 교환 성사!\n\n"
        f"{tb} {trade['offer_name']}{shiny_tag}을(를) 받았습니다!"
    )

    trade["pending_evo"] = pending_evo
    return True, msg, trade
