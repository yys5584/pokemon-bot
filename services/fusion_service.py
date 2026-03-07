"""Fusion service: merge two same-species Pokemon into one with random IVs."""

import logging
from database import queries
import config

logger = logging.getLogger(__name__)


async def get_fusable_species(user_id: int) -> list[dict]:
    """Return species where user owns 2+ fusable copies.

    Returns list of dicts: {pokemon_id, name_ko, emoji, rarity, count}
    sorted by pokemon_id.
    """
    all_pokemon = await queries.get_user_pokemon_list(user_id)
    protected = await queries.get_protected_pokemon_ids(user_id)

    # Count fusable copies per species
    species: dict[int, dict] = {}
    for p in all_pokemon:
        if p["id"] in protected:
            continue
        if p.get("is_favorite"):
            continue
        pid = p["pokemon_id"]
        if pid not in species:
            species[pid] = {
                "pokemon_id": pid,
                "name_ko": p.get("name_ko", "???"),
                "emoji": p.get("emoji", ""),
                "rarity": p.get("rarity", "common"),
                "count": 0,
            }
        species[pid]["count"] += 1

    # Only species with 2+ fusable copies
    result = [s for s in species.values() if s["count"] >= 2]
    result.sort(key=lambda s: s["pokemon_id"])
    return result


async def get_fusable_copies(user_id: int, pokemon_id: int) -> list[dict]:
    """Return fusable individual copies of a specific species."""
    all_pokemon = await queries.get_user_pokemon_list(user_id)
    protected = await queries.get_protected_pokemon_ids(user_id)

    copies = []
    for p in all_pokemon:
        if p["pokemon_id"] != pokemon_id:
            continue
        if p["id"] in protected:
            continue
        if p.get("is_favorite"):
            continue
        # Add IV total for display
        total = sum(p.get(f"iv_{s}", 0) or 0 for s in ("hp", "atk", "def", "spa", "spdef", "spd"))
        grade, _ = config.get_iv_grade(total)
        p_copy = dict(p)
        p_copy["iv_total"] = total
        p_copy["iv_grade"] = grade
        copies.append(p_copy)

    return copies


async def execute_fusion(
    user_id: int, instance_id_a: int, instance_id_b: int,
) -> tuple[bool, str, dict | None]:
    """Execute fusion of two Pokemon.

    Returns (success, message, result_pokemon_dict_or_None).
    """
    if instance_id_a == instance_id_b:
        return False, "같은 개체를 선택할 수 없습니다.", None

    # Fetch both
    pa = await queries.get_user_pokemon_by_id(instance_id_a)
    pb = await queries.get_user_pokemon_by_id(instance_id_b)

    if not pa or not pb:
        return False, "포켓몬을 찾을 수 없습니다.", None

    # Ownership check
    if pa["user_id"] != user_id or pb["user_id"] != user_id:
        return False, "본인의 포켓몬만 합성할 수 있습니다.", None

    # Same species check
    if pa["pokemon_id"] != pb["pokemon_id"]:
        return False, "같은 종류의 포켓몬만 합성할 수 있습니다.", None

    # Protection check
    protected = await queries.get_protected_pokemon_ids(user_id)
    if instance_id_a in protected or instance_id_b in protected:
        return False, "보호 중인 포켓몬은 합성할 수 없습니다. (팀/파트너/거래소)", None

    # Favorite check
    if pa.get("is_favorite") or pb.get("is_favorite"):
        return False, "즐겨찾기 포켓몬은 합성할 수 없습니다.", None

    # Lock check (trade/market)
    locked_a, reason_a = await queries.is_pokemon_locked(instance_id_a)
    if locked_a:
        return False, reason_a, None
    locked_b, reason_b = await queries.is_pokemon_locked(instance_id_b)
    if locked_b:
        return False, reason_b, None

    # Shiny: if either is shiny, result is shiny
    is_shiny = bool(pa.get("is_shiny")) or bool(pb.get("is_shiny"))

    # Deactivate both source Pokemon
    await queries.deactivate_pokemon(instance_id_a)
    await queries.deactivate_pokemon(instance_id_b)

    # Create new Pokemon with random IVs
    pokemon_id = pa["pokemon_id"]
    new_id, new_ivs = await queries.give_pokemon_to_user(
        user_id, pokemon_id, chat_id=None, is_shiny=is_shiny,
    )

    # Fetch the new Pokemon for display
    result = await queries.get_user_pokemon_by_id(new_id)

    logger.info(
        "Fusion: user=%s species=%s (%s+%s)->%s shiny=%s",
        user_id, pokemon_id, instance_id_a, instance_id_b, new_id, is_shiny,
    )

    return True, "합성 성공!", result
