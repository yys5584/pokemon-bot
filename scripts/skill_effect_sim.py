#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
"""
스킬 효과 시뮬레이션 스크립트
==============================
현재 시스템(자폭만 활성) vs 신규 시스템(전체 효과 + 밸런스 조정) 비교.

사용법:
    python scripts/skill_effect_sim.py

팀 구성: 6마리, 코스트 <= 18 (랭크전 기준)
시뮬레이션: 매치업당 1000전, 라운드 로빈
"""

import sys
import os
import random
import copy
from collections import defaultdict

# ── 프로젝트 루트를 sys.path에 추가 ──
PROJECT_ROOT = r"C:\Users\Administrator\Desktop\pokemon-bot"
sys.path.insert(0, PROJECT_ROOT)

import config
from models.pokemon_base_stats import POKEMON_BASE_STATS
from models.pokemon_skills import POKEMON_SKILLS
from models.pokemon_battle_data import POKEMON_BATTLE_DATA
from utils.battle_calc import (
    get_normalized_base_stats,
    get_type_multiplier,
    calc_battle_stats,
    EVO_STAGE_MAP,
)


# ====================================================================
# 스킬 효과 정의
# ====================================================================

# 현재 시스템: 자폭/대폭발만 활성
SKILL_EFFECTS_OLD = {
    "자폭":         {"type": "self_destruct", "damage_bonus": 3.0},
    "대폭발":       {"type": "self_destruct", "damage_bonus": 3.5},
}

# 신규 시스템: 전체 효과 + 밸런스 조정값
SKILL_EFFECTS_NEW = {
    # --- 자폭계: 기존 동일 ---
    "자폭":         {"type": "self_destruct", "damage_bonus": 3.0},
    "대폭발":       {"type": "self_destruct", "damage_bonus": 3.5},

    # --- 반동계: 고위력 + 자기 피해 (본가 120~130위력 반영) ---
    "역린":         {"type": "recoil", "damage_bonus": 2.0, "pct": 0.25},
    "브레이브버드":  {"type": "recoil", "damage_bonus": 1.8, "pct": 0.25},
    "인파이트":     {"type": "recoil", "damage_bonus": 1.8, "pct": 0.15},
    "하이점프킥":   {"type": "recoil", "damage_bonus": 1.7, "pct": 0.15},

    # --- 흡수계: 데미지의 N% 회복 ---
    "흡수":         {"type": "drain", "pct": 0.25},
    "메가드레인":   {"type": "drain", "pct": 0.35},
    "기가드레인":   {"type": "drain", "pct": 0.50},

    # --- 선제기: 스킬 발동 시에만 선공 ---
    "신속":         {"type": "priority"},
    "전광석화":     {"type": "priority"},
    "불릿펀치":     {"type": "priority"},
    "마하펀치":     {"type": "priority"},

    # --- 특수계 ---
    "튀어오르기":   {"type": "splash"},
    "손가락흔들기": {"type": "random_power", "min": 0.5, "max": 2.5},
    "반격":         {"type": "counter", "mult": 1.5},
    "잠자기":       {"type": "rest", "heal_pct": 0.35},
}


# ====================================================================
# 팀 구성 데이터
# ====================================================================

# 포켓몬 레어리티 매핑 (실제 게임 데이터 기반)
POKEMON_RARITY = {
    # Gen 1-2
    35: "common", 59: "epic", 62: "epic", 129: "common", 143: "epic",
    149: "epic", 189: "rare", 202: "rare", 212: "epic", 214: "epic",
    236: "common", 248: "epic",
    # Gen 3
    257: "epic", 277: "rare", 286: "rare", 308: "rare", 315: "rare",
}

POKEMON_NAMES = {
    35: "삐삐", 59: "윈디", 62: "강챙이", 129: "잉어킹", 143: "잠만보",
    149: "망나뇽", 189: "솜솜코", 202: "마자용", 212: "핫삼",
    214: "헤라크로스", 236: "배루키", 248: "마기라스",
    257: "번치코", 277: "스왈로", 286: "버섯모", 308: "요가램",
    315: "로젤리아",
}


def get_rarity(pid: int) -> str:
    """포켓몬 ID로 레어리티 반환."""
    if pid in POKEMON_RARITY:
        return POKEMON_RARITY[pid]
    # 실제 데이터에서 조회
    from models.pokemon_data import ALL_POKEMON
    for p in ALL_POKEMON:
        if p[0] == pid:
            return p[4]
    try:
        from models.pokemon_data_gen3 import ALL_POKEMON_GEN3
        for p in ALL_POKEMON_GEN3:
            if p[0] == pid:
                return p[4]
    except ImportError:
        pass
    return "common"


def get_name(pid: int) -> str:
    """포켓몬 ID로 한글 이름 반환."""
    if pid in POKEMON_NAMES:
        return POKEMON_NAMES[pid]
    from models.pokemon_data import ALL_POKEMON
    for p in ALL_POKEMON:
        if p[0] == pid:
            return p[1]
    try:
        from models.pokemon_data_gen3 import ALL_POKEMON_GEN3
        for p in ALL_POKEMON_GEN3:
            if p[0] == pid:
                return p[1]
    except ImportError:
        pass
    return f"포켓몬#{pid}"


# 팀 정의: (pokemon_id, ...) 리스트
# 코스트: common=1, rare=2, epic=4, legendary=5, ultra_legendary=6

TEAMS = {
    "공격형 (반동+선제)": {
        # 마기라스(4) + 망나뇽(4) + 핫삼(4) + 스왈로(2) + 버섯모(2) + 요가램(2) = 18
        "members": [248, 149, 212, 277, 286, 308],
        "description": "마기라스/망나뇽/핫삼 + 스왈로(브버)/버섯모(마하)/요가램(하점킥)",
        "effects": "역린, 브레이브버드, 불릿펀치, 마하펀치, 하이점프킥",
    },
    "생존형 (흡수+잠자기)": {
        # 잠만보(4) + 강챙이(4) + 윈디(4) + 솜솜코(2) + 로젤리아(2) + 스왈로(2) = 18
        "members": [143, 62, 59, 189, 315, 277],
        "description": "잠만보(잠자기)/강챙이(인파)/윈디(신속) + 솜솜코/로젤리아(기가드레인)",
        "effects": "잠자기, 인파이트, 신속, 기가드레인",
    },
    "올라운드 (혼합)": {
        # 헤라크로스(4) + 번치코(4) + 마기라스(4) + 마자용(2) + 삐삐(1) + 버섯모(2) = 17
        # 1 남으니 배루키(1) 추가 → 7마리 → 6마리로 맞추기
        # 헤라크로스(4) + 번치코(4) + 마기라스(4) + 마자용(2) + 삐삐(1) + 배루키(1) = 16
        # → 마자용 → 로젤리아(2): 4+4+4+2+1+2 = 17. 버섯모로: 4+4+4+2+2+1 = 17
        # 좀 더 효과적으로: 헤라크로스(4)+번치코(4)+마자용(2)+삐삐(1)+버섯모(2)+로젤리아(2) = 15
        # 아니, epic 2 + rare 4 조합: 4+4+2+2+2+2 = 16, 혹은 4+4+4+2+2+2 = 18
        # 헤라크로스(4) + 번치코(4) + 마자용(2) + 삐삐(1) + 로젤리아(2) + 버섯모(2) = 15... 아니
        # 다시: 헤라크로스(4) + 번치코(4) + 스왈로(2) + 마자용(2) + 삐삐(1) + 버섯모(2) = 15
        # 남은 3: 배루키(1) 추가하면 7마리. 6마리로 맞춰야 한다.
        # 헤라크로스(4) + 번치코(4) + 강챙이(4) + 마자용(2) + 삐삐(1) + 배루키(1) = 16
        # OK, 16 cost, 다양한 효과 포함
        "members": [214, 257, 62, 202, 35, 236],
        "description": "헤라크로스/번치코(인파)/강챙이(인파) + 마자용(반격)/삐삐(손가락흔들기)/배루키(마하펀치)",
        "effects": "인파이트, 반격, 손가락흔들기, 마하펀치",
    },
    "스탯형 (효과 없음)": {
        # 마기라스(4) + 잠만보(4) + 핫삼(4) + 윈디(4) + 삐삐(1) + 잉어킹(1) = 18
        # 핫삼/윈디는 선제기가 있지만, OLD 시스템에서는 항상 선공(100% 패시브)
        # 잉어킹은 튀어오르기(splash) → 효과 대비용
        "members": [248, 143, 212, 59, 35, 129],
        "description": "마기라스/잠만보/핫삼/윈디 에픽 4마리 + 삐삐/잉어킹",
        "effects": "신속, 불릿펀치, 손가락흔들기, 튀어오르기 (잉어킹은 splash)",
    },
}


# ====================================================================
# 시뮬레이션 엔진
# ====================================================================

def prepare_combatant(pokemon_id: int, friendship: int = 3) -> dict:
    """배틀용 전투원 데이터 생성 (IV 중간값 15 고정, 친밀도 3)."""
    rarity = get_rarity(pokemon_id)
    battle_data = POKEMON_BATTLE_DATA.get(pokemon_id, ("normal", "balanced"))
    pokemon_type, stat_type = battle_data

    base = get_normalized_base_stats(pokemon_id)
    evo_stage = 3 if base else EVO_STAGE_MAP.get(pokemon_id, 3)

    # IV = 15 (중간값) 고정
    iv_val = 15
    stats = calc_battle_stats(
        rarity, stat_type, friendship,
        evo_stage=evo_stage,
        iv_hp=iv_val, iv_atk=iv_val, iv_def=iv_val,
        iv_spa=iv_val, iv_spdef=iv_val, iv_spd=iv_val,
        **(base or {}),
    )

    # 스킬 데이터
    raw_skill = POKEMON_SKILLS.get(pokemon_id, ("몸통박치기", 1.2))
    skills = raw_skill if isinstance(raw_skill, list) else [raw_skill]

    # 타입 (듀얼 타입 지원)
    bs = POKEMON_BASE_STATS.get(pokemon_id)
    dual_types = bs[-1] if bs else [pokemon_type]

    return {
        "pokemon_id": pokemon_id,
        "name": get_name(pokemon_id),
        "rarity": rarity,
        "type": dual_types,
        "stat_type": stat_type,
        "stats": stats,
        "current_hp": stats["hp"],
        "skills": skills,
    }


def get_skill_effect_for_system(skill_name: str, effects_table: dict) -> dict | None:
    """주어진 효과 테이블에서 스킬 효과 조회."""
    return effects_table.get(skill_name)


def has_priority_skill(mon: dict, effects_table: dict) -> bool:
    """선제기 보유 여부 (효과 테이블 기준)."""
    for skill_name, _ in mon.get("skills", []):
        eff = get_skill_effect_for_system(skill_name, effects_table)
        if eff and eff["type"] == "priority":
            return True
    return False


def calc_damage(
    attacker: dict,
    defender: dict,
    effects_table: dict,
    received_dmg: int = 0,
    is_new_system: bool = False,
) -> tuple[int, dict | None, str, bool]:
    """데미지 계산.

    Returns: (damage, effect_info, description, skill_activated)
    """
    # 물/특 선택
    atk_phys = attacker["stats"]["atk"]
    atk_spec = attacker["stats"]["spa"]
    if atk_spec > atk_phys:
        attack = atk_spec
        defense = defender["stats"]["spdef"]
    else:
        attack = atk_phys
        defense = defender["stats"]["def"]

    # 기본 데미지
    base = max(1, int((22 * config.BATTLE_BASE_POWER * attack / defense) / 50 + 2))

    # 타입 상성
    type_mult, best_type_idx = get_type_multiplier(attacker["type"], defender["type"])

    # 스킬 선택 (유리한 타입)
    skills = attacker.get("skills", [])
    if skills and best_type_idx < len(skills):
        chosen_skill = skills[best_type_idx]
    elif skills:
        chosen_skill = skills[0]
    else:
        chosen_skill = ("몸통박치기", 1.2)
    skill_name, skill_power = chosen_skill

    # 효과 조회
    effect = get_skill_effect_for_system(skill_name, effects_table)
    effect_info = None

    # 크리티컬
    crit = 1.5 if random.random() < config.BATTLE_CRIT_RATE else 1.0

    # 스킬 발동 (30%)
    skill_activated = random.random() < config.BATTLE_SKILL_RATE

    # 레어리티 보정
    rarity_mult = config.RARITY_BATTLE_MULT.get(attacker["rarity"], 1.0)

    desc_parts = []

    if skill_activated and effect:
        etype = effect["type"]

        if etype == "splash":
            damage = 0
            effect_info = {"type": "splash"}
            desc_parts.append(f"[{skill_name}] 아무 일도 일어나지 않았다!")

        elif etype == "rest":
            max_hp = attacker["stats"]["hp"]
            heal_pct = effect["heal_pct"]
            heal = int(max_hp * heal_pct)
            damage = 0
            effect_info = {"type": "rest", "heal": heal}
            desc_parts.append(f"[{skill_name}] HP {heal} 회복! (최대HP의 {heal_pct:.0%})")

        elif etype == "self_destruct":
            skill_mult = effect["damage_bonus"]
            variance = random.uniform(0.9, 1.1)
            damage = max(1, int(base * type_mult * crit * skill_mult * variance))
            effect_info = {"type": "self_destruct"}
            desc_parts.append(f"[{skill_name}] 자폭! x{skill_mult:.1f} = {damage}dmg")

        elif etype == "random_power":
            rand_mult = random.uniform(effect["min"], effect["max"])
            variance = random.uniform(0.9, 1.1)
            damage = max(1, int(base * type_mult * crit * rand_mult * variance))
            effect_info = {"type": "random_power", "mult": rand_mult}
            desc_parts.append(f"[{skill_name}] 랜덤 x{rand_mult:.2f} = {damage}dmg")

        elif etype == "counter":
            if received_dmg > 0:
                damage = int(received_dmg * effect["mult"])
                effect_info = {"type": "counter", "reflected": damage}
                desc_parts.append(f"[{skill_name}] 반사! {received_dmg}x{effect['mult']:.1f} = {damage}dmg")
            else:
                # 선공 시 일반 공격
                skill_mult = skill_power
                variance = random.uniform(0.9, 1.1)
                damage = max(1, int(base * type_mult * crit * skill_mult * variance))
                desc_parts.append(f"[{skill_name}] (선공이라 일반공격) {damage}dmg")

        elif etype == "recoil":
            if is_new_system:
                # 신규: damage_bonus를 스킬 배율로 사용
                skill_mult = effect["damage_bonus"]
            else:
                # 구: 일반 스킬 파워 사용 (실제로 OLD에는 recoil 없음)
                skill_mult = skill_power
            variance = random.uniform(0.9, 1.1)
            damage = max(1, int(base * type_mult * crit * skill_mult * variance))
            recoil_dmg = max(1, int(damage * effect["pct"]))
            effect_info = {"type": "recoil", "pct": effect["pct"], "recoil_dmg": recoil_dmg}
            desc_parts.append(
                f"[{skill_name}] 반동! x{skill_mult:.1f} = {damage}dmg, "
                f"자기피해 {recoil_dmg} ({effect['pct']:.0%})"
            )

        elif etype == "drain":
            skill_mult = skill_power
            variance = random.uniform(0.9, 1.1)
            damage = max(1, int(base * type_mult * crit * skill_mult * variance))
            drain_heal = max(1, int(damage * effect["pct"]))
            effect_info = {"type": "drain", "pct": effect["pct"], "drain_heal": drain_heal}
            desc_parts.append(
                f"[{skill_name}] 흡수! {damage}dmg, "
                f"회복 {drain_heal} ({effect['pct']:.0%})"
            )

        elif etype == "priority":
            # 선제기 발동 시에도 데미지는 스킬 파워 적용
            skill_mult = skill_power
            variance = random.uniform(0.9, 1.1)
            damage = max(1, int(base * type_mult * crit * skill_mult * variance))
            effect_info = {"type": "priority"}
            desc_parts.append(f"[{skill_name}] 선제기 발동! {damage}dmg")

        else:
            # 알 수 없는 효과 → 일반 데미지
            skill_mult = skill_power
            variance = random.uniform(0.9, 1.1)
            damage = max(1, int(base * type_mult * crit * skill_mult * variance))

    else:
        # 스킬 미발동 또는 효과 없는 스킬
        skill_mult = skill_power if skill_activated else 1.0
        variance = random.uniform(0.9, 1.1)
        damage = max(1, int(base * type_mult * crit * skill_mult * variance))
        if skill_activated:
            desc_parts.append(f"[{skill_name}] x{skill_mult:.1f} = {damage}dmg")
        else:
            desc_parts.append(f"일반공격 {damage}dmg")

    if crit > 1.0:
        desc_parts.append("크리!")
    if type_mult > 1.0:
        desc_parts.append(f"효과적! x{type_mult:.1f}")
    elif type_mult < 1.0 and type_mult > 0:
        desc_parts.append(f"반감 x{type_mult:.1f}")
    elif type_mult == 0:
        desc_parts.append("무효!")
        damage = 0

    desc = " ".join(desc_parts)
    return damage, effect_info, desc, skill_activated


def resolve_battle(
    team_a: list[dict],
    team_b: list[dict],
    effects_table: dict,
    is_new_system: bool = False,
    verbose: bool = False,
) -> tuple[str, list[str]]:
    """배틀 실행.

    Args:
        team_a, team_b: prepare_combatant() 결과 딥카피 필요
        effects_table: SKILL_EFFECTS_OLD 또는 SKILL_EFFECTS_NEW
        is_new_system: 신규 시스템 여부 (priority/recoil 동작 변경)
        verbose: 상세 로그 출력

    Returns:
        ("A" or "B", log_lines)
    """
    a = [copy.deepcopy(m) for m in team_a]
    b = [copy.deepcopy(m) for m in team_b]

    a_idx = 0
    b_idx = 0
    round_num = 0
    log = []

    a_mon = a[a_idx]
    b_mon = b[b_idx]

    if verbose:
        log.append(f"=== {a_mon['name']} vs {b_mon['name']} ===")

    while a_idx < len(a) and b_idx < len(b):
        round_num += 1
        if round_num > config.BATTLE_MAX_ROUNDS:
            if verbose:
                log.append(f"  [{round_num}] 시간 초과!")
            break

        # ── 선공 결정 ──
        if is_new_system:
            # 신규: 선제기는 스킬 발동(30%) 시에만 작동
            # 미리 선제기 발동 여부 체크 (실제 데미지 계산 시에도 동일 시드 사용 불가하므로
            # 여기서는 별도로 선제기 보유 + 30% 롤로 판정)
            a_prio_roll = has_priority_skill(a_mon, effects_table) and random.random() < config.BATTLE_SKILL_RATE
            b_prio_roll = has_priority_skill(b_mon, effects_table) and random.random() < config.BATTLE_SKILL_RATE

            if a_prio_roll and not b_prio_roll:
                first, second = a_mon, b_mon
                first_is_a = True
            elif b_prio_roll and not a_prio_roll:
                first, second = b_mon, a_mon
                first_is_a = False
            elif a_mon["stats"]["spd"] >= b_mon["stats"]["spd"]:
                first, second = a_mon, b_mon
                first_is_a = True
            else:
                first, second = b_mon, a_mon
                first_is_a = False
        else:
            # 구시스템: 선제기 100% 패시브 선공
            a_prio = has_priority_skill(a_mon, effects_table)
            b_prio = has_priority_skill(b_mon, effects_table)
            if a_prio and not b_prio:
                first, second = a_mon, b_mon
                first_is_a = True
            elif b_prio and not a_prio:
                first, second = b_mon, a_mon
                first_is_a = False
            elif a_mon["stats"]["spd"] >= b_mon["stats"]["spd"]:
                first, second = a_mon, b_mon
                first_is_a = True
            else:
                first, second = b_mon, a_mon
                first_is_a = False

        # ── 선공 공격 ──
        dmg1, fx1, desc1, sk1 = calc_damage(first, second, effects_table, 0, is_new_system)

        if fx1 and fx1["type"] == "rest":
            max_hp = first["stats"]["hp"]
            first["current_hp"] = min(max_hp, first["current_hp"] + fx1["heal"])
            if verbose:
                tag = "A" if first_is_a else "B"
                log.append(f"  [{round_num}] {tag}:{first['name']} {desc1}")
        else:
            second["current_hp"] -= dmg1
            if verbose:
                tag = "A" if first_is_a else "B"
                log.append(f"  [{round_num}] {tag}:{first['name']} -> {second['name']}: {desc1}")

        # ── 후공 공격 (생존 시) ──
        dmg2, fx2, desc2, sk2 = 0, None, "", False
        if second["current_hp"] > 0:
            received = dmg1 if (fx1 is None or fx1["type"] != "rest") else 0
            dmg2, fx2, desc2, sk2 = calc_damage(second, first, effects_table, received, is_new_system)

            if fx2 and fx2["type"] == "rest":
                max_hp = second["stats"]["hp"]
                second["current_hp"] = min(max_hp, second["current_hp"] + fx2["heal"])
                if verbose:
                    tag = "B" if first_is_a else "A"
                    log.append(f"         {tag}:{second['name']} {desc2}")
            else:
                first["current_hp"] -= dmg2
                if verbose:
                    tag = "B" if first_is_a else "A"
                    log.append(f"         {tag}:{second['name']} -> {first['name']}: {desc2}")

        # ── 스킬 효과 적용 (반동, 흡수, 자폭) ──
        if fx1:
            if fx1["type"] == "self_destruct":
                first["current_hp"] = 0
                if verbose:
                    log.append(f"         {first['name']} 자폭으로 쓰러짐!")
            elif fx1["type"] == "recoil" and dmg1 > 0:
                recoil = fx1.get("recoil_dmg", max(1, int(dmg1 * fx1["pct"])))
                first["current_hp"] -= recoil
                if verbose:
                    log.append(f"         {first['name']} 반동 피해 -{recoil} (잔여HP: {max(0,first['current_hp'])})")
            elif fx1["type"] == "drain" and dmg1 > 0:
                heal = fx1.get("drain_heal", max(1, int(dmg1 * fx1["pct"])))
                max_hp = first["stats"]["hp"]
                first["current_hp"] = min(max_hp, first["current_hp"] + heal)
                if verbose:
                    log.append(f"         {first['name']} 흡수 회복 +{heal} (현재HP: {first['current_hp']})")

        if fx2:
            if fx2["type"] == "self_destruct":
                second["current_hp"] = 0
                if verbose:
                    log.append(f"         {second['name']} 자폭으로 쓰러짐!")
            elif fx2["type"] == "recoil" and dmg2 > 0:
                recoil = fx2.get("recoil_dmg", max(1, int(dmg2 * fx2["pct"])))
                second["current_hp"] -= recoil
                if verbose:
                    log.append(f"         {second['name']} 반동 피해 -{recoil} (잔여HP: {max(0,second['current_hp'])})")
            elif fx2["type"] == "drain" and dmg2 > 0:
                heal = fx2.get("drain_heal", max(1, int(dmg2 * fx2["pct"])))
                max_hp = second["stats"]["hp"]
                second["current_hp"] = min(max_hp, second["current_hp"] + heal)
                if verbose:
                    log.append(f"         {second['name']} 흡수 회복 +{heal} (현재HP: {second['current_hp']})")

        # ── HP 바 표시 (verbose) ──
        if verbose:
            a_hp = a_mon["current_hp"] if a_mon["current_hp"] > 0 else 0
            b_hp = b_mon["current_hp"] if b_mon["current_hp"] > 0 else 0
            a_max = a_mon["stats"]["hp"]
            b_max = b_mon["stats"]["hp"]
            log.append(
                f"         HP: A:{a_mon['name']} {a_hp}/{a_max} | "
                f"B:{b_mon['name']} {b_hp}/{b_max}"
            )

        # ── KO 체크: A측 ──
        if a_mon["current_hp"] <= 0:
            dead = a_mon["name"]
            a_idx += 1
            if a_idx < len(a):
                a_mon = a[a_idx]
                if verbose:
                    log.append(f"  ** A:{dead} 쓰러짐! -> A:{a_mon['name']} 등장!")
            else:
                if verbose:
                    log.append(f"  ** A:{dead} 쓰러짐! (A팀 전멸)")

        # ── KO 체크: B측 ──
        if b_mon["current_hp"] <= 0:
            dead = b_mon["name"]
            b_idx += 1
            if b_idx < len(b):
                b_mon = b[b_idx]
                if verbose:
                    log.append(f"  ** B:{dead} 쓰러짐! -> B:{b_mon['name']} 등장!")
            else:
                if verbose:
                    log.append(f"  ** B:{dead} 쓰러짐! (B팀 전멸)")

    # ── 승자 결정 ──
    if round_num > config.BATTLE_MAX_ROUNDS:
        a_hp_sum = sum(m["current_hp"] for m in a[a_idx:] if m["current_hp"] > 0)
        b_hp_sum = sum(m["current_hp"] for m in b[b_idx:] if m["current_hp"] > 0)
        winner = "A" if a_hp_sum >= b_hp_sum else "B"
    elif b_idx >= len(b):
        winner = "A"
    else:
        winner = "B"

    a_remaining = len(a) - a_idx
    b_remaining = len(b) - b_idx

    if verbose:
        log.append(f"\n  => 승자: {winner}팀 (A잔여: {max(0,a_remaining)}, B잔여: {max(0,b_remaining)}, {round_num}라운드)")

    return winner, log


# ====================================================================
# 시뮬레이션 실행
# ====================================================================

def run_matchup(
    team_a_ids: list[int],
    team_b_ids: list[int],
    effects_table: dict,
    is_new_system: bool,
    n_sims: int = 1000,
) -> dict:
    """두 팀 간 N회 시뮬레이션."""
    team_a = [prepare_combatant(pid) for pid in team_a_ids]
    team_b = [prepare_combatant(pid) for pid in team_b_ids]

    wins_a = 0
    wins_b = 0
    total_rounds = 0

    for _ in range(n_sims):
        winner, _ = resolve_battle(team_a, team_b, effects_table, is_new_system)
        if winner == "A":
            wins_a += 1
        else:
            wins_b += 1

    return {
        "wins_a": wins_a,
        "wins_b": wins_b,
        "rate_a": wins_a / n_sims * 100,
        "rate_b": wins_b / n_sims * 100,
    }


def print_team_info(name: str, team_data: dict):
    """팀 정보 출력."""
    members = team_data["members"]
    cost_map = config.RANKED_COST
    total_cost = sum(cost_map.get(get_rarity(pid), 1) for pid in members)

    print(f"  {name} (코스트: {total_cost}/18)")
    print(f"    설명: {team_data['description']}")
    print(f"    효과: {team_data['effects']}")
    print(f"    멤버:")
    for pid in members:
        r = get_rarity(pid)
        n = get_name(pid)
        c = cost_map.get(r, 1)
        raw_skill = POKEMON_SKILLS.get(pid, ("몸통박치기", 1.2))
        if isinstance(raw_skill, list):
            skill_str = " / ".join(f"{s[0]}(x{s[1]})" for s in raw_skill)
        else:
            skill_str = f"{raw_skill[0]}(x{raw_skill[1]})"
        bt = POKEMON_BATTLE_DATA.get(pid, ("?", "?"))
        types = POKEMON_BASE_STATS.get(pid, [None]*7)[-1] if POKEMON_BASE_STATS.get(pid) else [bt[0]]
        type_str = "/".join(types) if isinstance(types, list) else types

        base = get_normalized_base_stats(pid)
        stats = calc_battle_stats(
            r, bt[1], 3, evo_stage=3 if base else EVO_STAGE_MAP.get(pid, 3),
            iv_hp=15, iv_atk=15, iv_def=15, iv_spa=15, iv_spdef=15, iv_spd=15,
            **(base or {}),
        )
        power = sum(stats.values())
        print(f"      {n}(#{pid}) [{type_str}] {r}({c}) 전투력:{power} 스킬: {skill_str}")
    print()


def run_detailed_battle(
    team_a_name: str,
    team_a_ids: list[int],
    team_b_name: str,
    team_b_ids: list[int],
    effects_table: dict,
    is_new_system: bool,
    label: str,
):
    """상세 배틀 1회 출력."""
    team_a = [prepare_combatant(pid) for pid in team_a_ids]
    team_b = [prepare_combatant(pid) for pid in team_b_ids]

    system_tag = "신규" if is_new_system else "현재"
    print(f"\n{'='*70}")
    print(f"  상세 배틀 로그 [{label}] ({system_tag} 시스템)")
    print(f"  A팀: {team_a_name}")
    print(f"  B팀: {team_b_name}")
    print(f"{'='*70}")

    winner, log_lines = resolve_battle(team_a, team_b, effects_table, is_new_system, verbose=True)
    for line in log_lines:
        print(line)
    print()


def main():
    random.seed(42)  # 재현 가능한 결과

    print("=" * 70)
    print("  스킬 효과 시뮬레이션: 현재 시스템 vs 신규 시스템")
    print("  (매치업당 1,000회 시뮬레이션)")
    print("=" * 70)
    print()

    # ── 팀 정보 출력 ──
    print("[팀 구성]")
    print("-" * 50)
    for name, data in TEAMS.items():
        print_team_info(name, data)

    # ── 효과 차이 요약 ──
    print("[시스템 비교]")
    print("-" * 50)
    print("  현재 시스템:")
    print("    - 자폭/대폭발: 활성 (데미지 x3.0/x3.5 + 자신 즉사)")
    print("    - 선제기: 100% 패시브 선공 (항상 먼저 때림)")
    print("    - 그 외 모든 효과: 비활성 (일반 스킬 데미지만)")
    print()
    print("  신규 시스템:")
    print("    - 자폭/대폭발: 기존 동일")
    print("    - 선제기: 스킬 발동(30%) 시에만 선공")
    print("    - 반동: 발동 시 damage_bonus 배율 + 자기 피해")
    print("    - 흡수: 발동 시 데미지의 25~50% HP 회복")
    print("    - 잠자기: 발동 시 최대HP의 35% 회복 (50% -> 35%)")
    print("    - 손가락흔들기: 랜덤 x0.5~2.5 (x3.0 -> x2.5)")
    print("    - 반격: 받은 데미지 x1.5 반사")
    print("    - 튀어오르기: 데미지 0 (잉어킹 특수)")
    print()

    # ── 라운드 로빈 시뮬레이션 ──
    team_names = list(TEAMS.keys())
    n_teams = len(team_names)
    n_sims = 1000

    print("=" * 70)
    print("  [시뮬레이션 결과] 라운드 로빈 (각 매치업 1,000회)")
    print("=" * 70)
    print()

    # 승률 저장
    results_old = {}
    results_new = {}

    for i in range(n_teams):
        for j in range(i + 1, n_teams):
            name_a = team_names[i]
            name_b = team_names[j]
            ids_a = TEAMS[name_a]["members"]
            ids_b = TEAMS[name_b]["members"]

            # 동일 시드로 비교하기 위해 각 시스템별 시드 리셋
            random.seed(42 + i * 100 + j)
            old = run_matchup(ids_a, ids_b, SKILL_EFFECTS_OLD, is_new_system=False, n_sims=n_sims)

            random.seed(42 + i * 100 + j)
            new = run_matchup(ids_a, ids_b, SKILL_EFFECTS_NEW, is_new_system=True, n_sims=n_sims)

            results_old[(name_a, name_b)] = old
            results_new[(name_a, name_b)] = new

            # 짧은 이름
            short_a = name_a.split("(")[0].strip()
            short_b = name_b.split("(")[0].strip()

            print(f"  [{short_a}] vs [{short_b}]")
            print(f"    현재: {short_a} {old['rate_a']:.1f}% | {short_b} {old['rate_b']:.1f}%")
            print(f"    신규: {short_a} {new['rate_a']:.1f}% | {short_b} {new['rate_b']:.1f}%")
            diff_a = new['rate_a'] - old['rate_a']
            arrow = "+" if diff_a > 0 else ""
            print(f"    변화: {short_a} {arrow}{diff_a:.1f}%p")
            print()

    # ── 팀별 총 승률 ──
    print("=" * 70)
    print("  [팀별 총합 승률]")
    print("=" * 70)
    print()
    print(f"  {'팀':<25} {'현재 승률':>10} {'신규 승률':>10} {'변화':>8}")
    print(f"  {'-'*25} {'-'*10} {'-'*10} {'-'*8}")

    for name in team_names:
        old_wins = 0
        old_total = 0
        new_wins = 0
        new_total = 0
        short = name.split("(")[0].strip()

        for i in range(n_teams):
            for j in range(i + 1, n_teams):
                na = team_names[i]
                nb = team_names[j]
                if na == name:
                    old_wins += results_old[(na, nb)]["wins_a"]
                    old_total += n_sims
                    new_wins += results_new[(na, nb)]["wins_a"]
                    new_total += n_sims
                elif nb == name:
                    old_wins += results_old[(na, nb)]["wins_b"]
                    old_total += n_sims
                    new_wins += results_new[(na, nb)]["wins_b"]
                    new_total += n_sims

        old_rate = old_wins / old_total * 100 if old_total > 0 else 0
        new_rate = new_wins / new_total * 100 if new_total > 0 else 0
        diff = new_rate - old_rate
        arrow = "+" if diff > 0 else ""
        print(f"  {short:<25} {old_rate:>9.1f}% {new_rate:>9.1f}% {arrow}{diff:>6.1f}%p")

    print()

    # ── 상세 배틀 로그 (3회) ──
    print()
    print("=" * 70)
    print("  [상세 배틀 로그] 신규 효과별 예시 3전")
    print("=" * 70)

    # 예시 1: 반동 효과 (공격형 vs 스탯형)
    random.seed(1234)
    run_detailed_battle(
        "공격형 (반동+선제)", TEAMS["공격형 (반동+선제)"]["members"],
        "스탯형 (효과 없음)", TEAMS["스탯형 (효과 없음)"]["members"],
        SKILL_EFFECTS_NEW, is_new_system=True,
        label="반동/선제기 효과 (역린, 브레이브버드, 불릿펀치 등)",
    )

    # 예시 2: 흡수/잠자기 효과 (생존형 vs 올라운드)
    random.seed(5678)
    run_detailed_battle(
        "생존형 (흡수+잠자기)", TEAMS["생존형 (흡수+잠자기)"]["members"],
        "올라운드 (혼합)", TEAMS["올라운드 (혼합)"]["members"],
        SKILL_EFFECTS_NEW, is_new_system=True,
        label="흡수/잠자기 효과 (기가드레인, 잠자기, 인파이트 등)",
    )

    # 예시 3: 혼합 효과 (올라운드 vs 스탯형)
    random.seed(9012)
    run_detailed_battle(
        "올라운드 (혼합)", TEAMS["올라운드 (혼합)"]["members"],
        "스탯형 (효과 없음)", TEAMS["스탯형 (효과 없음)"]["members"],
        SKILL_EFFECTS_NEW, is_new_system=True,
        label="반격/손가락흔들기/마하펀치 (특수 효과 혼합)",
    )

    print()
    print("=" * 70)
    print("  시뮬레이션 완료!")
    print("=" * 70)


if __name__ == "__main__":
    main()
