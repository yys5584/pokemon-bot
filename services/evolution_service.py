"""Evolution service: friendship and trade evolution logic."""

import random
import logging

import config
from database import queries
from utils.helpers import update_title, type_badge

logger = logging.getLogger(__name__)


async def try_evolve(user_id: int, instance_id: int) -> tuple[bool, str]:
    """Attempt to evolve a Pokemon. Returns (success, message)."""
    pokemon = await queries.get_user_pokemon_by_id(instance_id)
    if not pokemon:
        return False, "해당 포켓몬을 찾을 수 없습니다."

    if pokemon["user_id"] != user_id:
        return False, "해당 포켓몬을 찾을 수 없습니다."

    # 배틀팀에 있는 포켓몬은 진화 불가 (진화 시 코스트 변동 방지)
    protected = await queries.get_protected_pokemon_ids(user_id)
    if instance_id in protected:
        return False, (
            "⚔️ 배틀팀/파트너/거래소에 등록된 포켓몬은 진화할 수 없습니다!\n"
            "팀에서 빼거나 등록을 해제한 후 다시 시도하세요."
        )

    pokemon_id = pokemon["pokemon_id"]
    master = await queries.get_pokemon(pokemon_id)

    if not master:
        return False, "포켓몬 데이터를 찾을 수 없습니다."

    # Check if can evolve
    if not master["evolves_to"] and pokemon_id != config.EEVEE_ID and pokemon_id not in config.BRANCH_EVOLUTIONS:
        return False, f"{master['name_ko']}은(는) 더 이상 진화할 수 없습니다."

    # Trade evolution check
    if master["evolution_method"] == "trade":
        return False, f"{master['name_ko']}은(는) 교환을 통해서만 진화합니다! /교환 을 이용하세요."

    # Friendship check
    if pokemon["friendship"] < config.MAX_FRIENDSHIP:
        return False, (
            f"친밀도가 부족합니다! ({pokemon['friendship']}/{config.MAX_FRIENDSHIP})\n"
            f"/밥 과 /놀기 로 친밀도를 올려주세요."
        )

    # Determine evolution target
    if pokemon_id == config.EEVEE_ID:
        target_id = random.choice(config.EEVEE_EVOLUTIONS)
    elif pokemon_id in config.BRANCH_EVOLUTIONS:
        target_id = random.choice(config.BRANCH_EVOLUTIONS[pokemon_id])
    else:
        target_id = master["evolves_to"]

    target = await queries.get_pokemon(target_id)
    if not target:
        return False, "진화 대상을 찾을 수 없습니다."

    # Perform evolution
    await queries.evolve_pokemon(instance_id, target_id)
    await queries.register_pokedex(user_id, target_id, "evolve")
    await update_title(user_id)

    return True, (
        f"✨ 축하합니다!\n\n"
        f"{type_badge(master['id'])} {master['name_ko']}이(가)\n"
        f"{type_badge(target['id'])} {target['name_ko']}(으)로 진화했습니다!\n\n"
        f"도감에 등록되었습니다!"
    )


def build_trade_evo_info(pokemon_id: int, instance_id: int) -> dict | None:
    """Check if pokemon is eligible for trade evolution. Returns info dict or None.
    Synchronous — no DB calls."""
    if pokemon_id not in config.TRADE_EVOLUTION_MAP:
        return None
    return {
        "instance_id": instance_id,
        "source_id": pokemon_id,
        "target_id": config.TRADE_EVOLUTION_MAP[pokemon_id],
    }


async def try_trade_evolve(user_id: int, instance_id: int, pokemon_id: int) -> str | None:
    """Check and perform trade evolution after a trade.
    Returns evolution message or None."""
    if pokemon_id not in config.TRADE_EVOLUTION_MAP:
        return None

    target_id = config.TRADE_EVOLUTION_MAP[pokemon_id]
    target = await queries.get_pokemon(target_id)
    if not target:
        return None

    source = await queries.get_pokemon(pokemon_id)
    if not source:
        return None

    # Evolve the pokemon
    await queries.evolve_pokemon(instance_id, target_id)
    await queries.register_pokedex(user_id, target_id, "trade")
    await update_title(user_id)

    return (
        f"\n\n✨ 교환 진화!\n"
        f"{type_badge(source['id'])} {source['name_ko']} → "
        f"{type_badge(target['id'])} {target['name_ko']}"
    )
