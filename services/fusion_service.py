"""Fusion service: merge two same-species Pokemon into one with random IVs."""

import asyncio
import logging
from database import queries, market_queries
import config

logger = logging.getLogger(__name__)


async def get_fusable_species(user_id: int) -> list[dict]:
    """Return species where user owns 2+ fusable copies."""
    # Parallel: get pokemon list + protected ids
    all_pokemon, protected = await asyncio.gather(
        queries.get_user_pokemon_list(user_id),
        queries.get_protected_pokemon_ids(user_id),
    )

    species: dict[int, dict] = {}
    for p in all_pokemon:
        if p["id"] in protected:
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

    result = [s for s in species.values() if s["count"] >= 2]
    result.sort(key=lambda s: s["pokemon_id"])
    return result


async def get_fusable_copies(user_id: int, pokemon_id: int) -> list[dict]:
    """Return fusable individual copies of a specific species."""
    # Parallel: get pokemon list + protected ids
    all_pokemon, protected = await asyncio.gather(
        queries.get_user_pokemon_list(user_id),
        queries.get_protected_pokemon_ids(user_id),
    )

    copies = []
    for p in all_pokemon:
        if p["pokemon_id"] != pokemon_id:
            continue
        if p["id"] in protected:
            continue
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
    """Execute fusion of two Pokemon."""
    if instance_id_a == instance_id_b:
        return False, "같은 개체를 선택할 수 없습니다.", None

    # Phase 1: fetch both pokemon in parallel
    pa, pb = await asyncio.gather(
        queries.get_user_pokemon_by_id(instance_id_a),
        queries.get_user_pokemon_by_id(instance_id_b),
    )

    if not pa or not pb:
        return False, "포켓몬을 찾을 수 없습니다.", None
    if pa["user_id"] != user_id or pb["user_id"] != user_id:
        return False, "본인의 포켓몬만 합성할 수 있습니다.", None
    if pa["pokemon_id"] != pb["pokemon_id"]:
        return False, "같은 종류의 포켓몬만 합성할 수 있습니다.", None

    # 이로치 판정: 하나라도 이로치면 결과도 이로치
    a_shiny = bool(pa.get("is_shiny"))
    b_shiny = bool(pb.get("is_shiny"))
    both_shiny = a_shiny and b_shiny
    any_shiny = a_shiny or b_shiny

    # Phase 2: protection + lock checks in parallel
    protected, (locked_a, reason_a), (locked_b, reason_b) = await asyncio.gather(
        queries.get_protected_pokemon_ids(user_id),
        market_queries.is_pokemon_locked(instance_id_a),
        market_queries.is_pokemon_locked(instance_id_b),
    )
    if instance_id_a in protected or instance_id_b in protected:
        return False, "보호 중인 포켓몬은 합성할 수 없습니다. (팀/파트너/거래소)", None
    if locked_a:
        return False, reason_a, None
    if locked_b:
        return False, reason_b, None

    is_shiny = any_shiny  # 하나라도 이로치면 결과도 이로치

    # Phase 3: deactivate both in parallel
    await asyncio.gather(
        queries.deactivate_pokemon(instance_id_a),
        queries.deactivate_pokemon(instance_id_b),
    )

    # Create new Pokemon with random IVs
    pokemon_id = pa["pokemon_id"]

    # 합성 결과 최소 등급 보장: 두 재료 중 낮은 등급 이상
    from utils.battle_calc import generate_ivs
    iv_total_a = sum(pa.get(f"iv_{s}", 0) or 0 for s in ("hp", "atk", "def", "spa", "spdef", "spd"))
    iv_total_b = sum(pb.get(f"iv_{s}", 0) or 0 for s in ("hp", "atk", "def", "spa", "spdef", "spd"))
    min_iv_total = min(iv_total_a, iv_total_b)

    # 최소 보장 기준: 재료 중 낮은 쪽 등급보다 한 단계 아래
    grade_min, _ = config.get_iv_grade(min_iv_total)
    GRADE_BELOW = {"S": 120, "A": 93, "B": 62, "C": 0, "D": 0}  # S→A, A→B, B→C, C→D, D→D
    MIN_IV_TOTAL = GRADE_BELOW.get(grade_min, 0)

    # 이로치+이로치는 최소 A등급(120+)
    if both_shiny:
        MIN_IV_TOTAL = max(MIN_IV_TOTAL, 120)

    forced_ivs = None
    for _ in range(200):
        candidate = generate_ivs(is_shiny=is_shiny)
        total = sum(candidate.values())
        if total >= MIN_IV_TOTAL:
            forced_ivs = candidate
            break
    if forced_ivs is None:
        forced_ivs = generate_ivs(is_shiny=is_shiny)
        while sum(forced_ivs.values()) < MIN_IV_TOTAL:
            lowest_key = min(forced_ivs, key=forced_ivs.get)
            forced_ivs[lowest_key] = min(31, forced_ivs[lowest_key] + 1)

    new_id, new_ivs = await queries.give_pokemon_to_user(
        user_id, pokemon_id, chat_id=None, is_shiny=is_shiny,
        ivs=forced_ivs,
    )

    result = await queries.get_user_pokemon_by_id(new_id)

    fusion_type = "shiny+shiny" if both_shiny else ("shiny+normal" if any_shiny else "normal")
    logger.info(
        "Fusion: user=%s species=%s (%s+%s)->%s shiny=%s type=%s iv_total=%s",
        user_id, pokemon_id, instance_id_a, instance_id_b, new_id, is_shiny,
        fusion_type, sum(new_ivs.values()),
    )

    return True, "합성 성공!", result
