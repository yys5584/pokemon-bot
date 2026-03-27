"""이로치 제련소 비즈니스 로직."""

import asyncio
import logging
import random
from typing import Literal

import config
from database import queries
from database import smelting_queries as sq
from database import item_queries
from database.connection import get_db

logger = logging.getLogger(__name__)

RARITY_ORDER = ["common", "rare", "epic", "legendary", "ultra_legendary"]


# ── 게이지 계산 ──────────────────────────────────────────────

def calculate_gauge(pokemon_list: list[dict], subscription: str = "none") -> float:
    """투입할 포켓몬 목록으로 예상 게이지 기여 계산."""
    total = 0.0
    for p in pokemon_list:
        rarity = p.get("rarity", "common")
        base = config.SMELTING_GAUGE_PER_RARITY.get(rarity, 0.05)
        if p.get("is_shiny"):
            base *= config.SMELTING_SHINY_MULTIPLIER
        total += base
    mult = config.SMELTING_SUB_MULTIPLIER.get(subscription, 1.0)
    return round(total * mult, 2)


def get_highest_rarity(pokemon_list: list[dict]) -> str:
    """투입 포켓몬 중 가장 높은 등급 반환."""
    best = 0
    for p in pokemon_list:
        r = p.get("rarity", "common")
        idx = RARITY_ORDER.index(r) if r in RARITY_ORDER else 0
        best = max(best, idx)
    return RARITY_ORDER[best]


def get_rarity_contributions(pokemon_list: list[dict]) -> dict:
    """투입 포켓몬의 등급별 게이지 기여 비율 (히든 보정용)."""
    contribs: dict[str, float] = {}
    total = 0.0
    for p in pokemon_list:
        rarity = p.get("rarity", "common")
        base = config.SMELTING_GAUGE_PER_RARITY.get(rarity, 0.05)
        if p.get("is_shiny"):
            base *= config.SMELTING_SHINY_MULTIPLIER
        contribs[rarity] = contribs.get(rarity, 0) + base
        total += base
    # 비율로 변환
    if total > 0:
        for k in contribs:
            contribs[k] = round(contribs[k] / total * 100, 1)
    return contribs


# ── 확률 판정 ────────────────────────────────────────────────

def _get_rates(gauge: float) -> tuple[float, float]:
    """현재 게이지에 따른 (대성공%, 메가스톤%) 반환."""
    shiny_rate, mega_rate = 2.0, 0.7
    for threshold, s, m in config.SMELTING_RATES:
        if gauge >= threshold:
            shiny_rate, mega_rate = s, m
    return shiny_rate, mega_rate


def roll_smelting_result(gauge: float) -> Literal["shiny", "mega_ticket", "fail"]:
    """제련 결과 판정."""
    if gauge >= 100:
        return "mega_ticket"

    shiny_rate, mega_rate = _get_rates(gauge)
    roll = random.random() * 100

    if roll < mega_rate:
        return "mega_ticket"
    if roll < mega_rate + shiny_rate:
        return "shiny"
    return "fail"


def roll_shiny_rarity(contributions: dict) -> str:
    """대성공 시 이로치 등급 판정 — 투입 비율 기반 가중치."""
    weights = {}
    for r in RARITY_ORDER:
        weights[r] = contributions.get(r, 0)
    # 최소 가중치 보장 (일반은 항상 나올 수 있음)
    weights["common"] = max(weights.get("common", 0), 10)

    total = sum(weights.values())
    if total <= 0:
        return "common"

    roll = random.random() * total
    cumulative = 0
    for r in RARITY_ORDER:
        cumulative += weights.get(r, 0)
        if roll < cumulative:
            return r
    return "common"


def roll_burn_reward() -> tuple[str, str, int]:
    """소각 보상 등급 + 아이템 결정. Returns (tier_label, item_key, amount)."""
    # 등급 판정
    roll = random.random()
    cumulative = 0
    tier_key = "common"
    tier_label = "⬜ 일반"
    for prob, key, label in config.SMELTING_REWARD_TIERS:
        cumulative += prob
        if roll < cumulative:
            tier_key = key
            tier_label = label
            break

    # 해당 등급 보상풀에서 랜덤
    pool = config.SMELTING_REWARD_POOL.get(tier_key, config.SMELTING_REWARD_POOL["common"])
    item_key, min_qty, max_qty = random.choice(pool)
    amount = random.randint(min_qty, max_qty)

    return tier_label, item_key, amount


def roll_mega_stone_grade(contributions: dict) -> str:
    """메가스톤 제련권 사용 시 등급 판정."""
    base = dict(config.MEGA_STONE_RATES)

    # 히든 보정: 투입된 등급 비율에 따라 소폭 상향
    # 기여 비율 1%당 해당 등급 메가스톤 확률 +0.05%
    for rarity, pct in contributions.items():
        if rarity in base:
            base[rarity] += pct * 0.0005  # 매우 소폭

    total = sum(base.values())
    roll = random.random() * total
    cumulative = 0
    for r in RARITY_ORDER:
        cumulative += base.get(r, 0)
        if roll < cumulative:
            return r
    return "common"


# ── 메인 실행 ────────────────────────────────────────────────

async def get_smeltable_pokemon(user_id: int) -> list[dict]:
    """제련 가능한 포켓몬 목록 (보호/팀 제외)."""
    all_pokemon = await queries.get_user_pokemon_list(user_id)
    protected = await queries.get_protected_pokemon_ids(user_id)

    smeltable = []
    for p in all_pokemon:
        if p["id"] in protected:
            continue
        smeltable.append(p)
    return smeltable


async def execute_smelting(
    user_id: int,
    instance_ids: list[int],
    subscription: str = "none",
) -> dict:
    """제련 실행.

    Returns:
        {
            "success": bool,
            "error": str | None,
            "result": "shiny" | "mega_ticket" | "fail",
            "gauge_before": float,
            "gauge_after": float,
            "gauge_gained": float,
            "reward": {...},  # 보상 상세
            "pokemon_consumed": [...],  # 소모된 포켓몬 이름 목록
        }
    """
    # 1. BP 체크
    user = await queries.get_user(user_id)
    if not user or user.get("battle_points", 0) < config.SMELTING_BP_COST:
        return {"success": False, "error": "BP가 부족합니다."}

    # 2. 포켓몬 검증
    protected = await queries.get_protected_pokemon_ids(user_id)
    pokemon_list = []
    for iid in instance_ids:
        p = await queries.get_user_pokemon_by_id(iid)
        if not p or p.get("user_id") != user_id:
            return {"success": False, "error": "포켓몬을 찾을 수 없습니다."}
        if iid in protected:
            return {"success": False, "error": "보호 중인 포켓몬이 포함되어 있습니다."}
        pokemon_list.append(p)

    if len(pokemon_list) != config.SMELTING_REQUIRED_COUNT:
        return {"success": False, "error": f"{config.SMELTING_REQUIRED_COUNT}마리를 선택해야 합니다."}

    # 3. 현재 게이지 조회
    gauge_data = await sq.get_smelting_gauge(user_id)
    gauge_before = gauge_data["gauge"]

    # 4. 게이지 기여 계산
    gauge_gained = calculate_gauge(pokemon_list, subscription)
    new_gauge = round(gauge_before + gauge_gained, 2)

    # 등급 정보 업데이트
    highest = get_highest_rarity(pokemon_list)
    contributions = get_rarity_contributions(pokemon_list)
    # 기존 contributions와 머지
    old_contribs = gauge_data.get("rarity_contributions", {})
    for k, v in contributions.items():
        old_contribs[k] = old_contribs.get(k, 0) + v

    # 5. BP 차감 + 포켓몬 소각 (deactivate)
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET battle_points = battle_points - $1 WHERE user_id = $2",
        config.SMELTING_BP_COST, user_id,
    )
    deactivate_tasks = [queries.deactivate_pokemon(iid) for iid in instance_ids]
    await asyncio.gather(*deactivate_tasks)

    # 6. 결과 판정
    result = roll_smelting_result(new_gauge)
    reward = {}
    result_detail = None

    if result == "shiny":
        # 이로치 등급 판정 + 랜덤 포켓몬 생성
        shiny_rarity = roll_shiny_rarity(old_contribs)
        # 해당 등급에서 랜덤 포켓몬
        from models.pokemon_base_stats import POKEMON_BASE_STATS
        candidates = [
            pid for pid, data in POKEMON_BASE_STATS.items()
            if data.get("rarity") == shiny_rarity
        ]
        if candidates:
            chosen_pid = random.choice(candidates)
            new_id, _ = await queries.give_pokemon_to_user(
                user_id, chosen_pid, chat_id=None, is_shiny=1,
            )
            pdata = POKEMON_BASE_STATS.get(chosen_pid, {})
            result_detail = {
                "pokemon_id": chosen_pid,
                "instance_id": new_id,
                "name": pdata.get("name_ko", "???"),
                "rarity": shiny_rarity,
            }
            reward = {"type": "shiny", "detail": result_detail}

        # 게이지 리셋
        await sq.reset_smelting_gauge(user_id)
        new_gauge = 0

    elif result == "mega_ticket":
        # 메가스톤 제련권 지급
        await item_queries.add_user_item(user_id, "mega_stone_ticket", 1)
        reward = {"type": "mega_ticket"}

        # 게이지 리셋
        await sq.reset_smelting_gauge(user_id)
        new_gauge = 0

    else:
        # 소각 보상
        tier_label, item_key, amount = roll_burn_reward()
        # 보상 지급
        if item_key == "bp":
            await pool.execute(
                "UPDATE users SET battle_points = battle_points + $1 WHERE user_id = $2",
                amount, user_id,
            )
        elif item_key == "fragment":
            await pool.execute(
                "UPDATE users SET universal_fragments = universal_fragments + $1 WHERE user_id = $2",
                amount, user_id,
            )
        elif item_key == "hyperball":
            await pool.execute(
                "UPDATE users SET hyper_balls = hyper_balls + $1 WHERE user_id = $2",
                amount, user_id,
            )
        elif item_key == "masterball":
            await pool.execute(
                "UPDATE users SET master_balls = master_balls + $1 WHERE user_id = $2",
                amount, user_id,
            )
        else:
            await item_queries.add_user_item(user_id, item_key, amount)

        reward = {"type": "burn", "tier": tier_label, "item": item_key, "amount": amount}

        # 게이지 업데이트 (적립)
        await sq.update_smelting_gauge(user_id, new_gauge, highest, old_contribs)

    # 7. 로그
    consumed_names = [p.get("name_ko", "???") for p in pokemon_list]
    materials = {
        "instance_ids": instance_ids,
        "names": consumed_names,
        "rarities": [p.get("rarity", "common") for p in pokemon_list],
        "shinies": [bool(p.get("is_shiny")) for p in pokemon_list],
    }
    await sq.log_smelting(
        user_id, materials, gauge_before, new_gauge,
        result, result_detail, reward,
    )

    logger.info(
        f"Smelting: user={user_id} result={result} gauge={gauge_before:.1f}→{new_gauge:.1f} "
        f"consumed={len(instance_ids)}"
    )

    return {
        "success": True,
        "error": None,
        "result": result,
        "gauge_before": gauge_before,
        "gauge_after": new_gauge,
        "gauge_gained": gauge_gained,
        "reward": reward,
        "pokemon_consumed": consumed_names,
    }
