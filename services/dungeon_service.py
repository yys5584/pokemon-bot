"""Dungeon roguelike system — battle engine, enemy gen, buffs, rewards."""

import datetime as _dt
import logging
import random

import config
from utils.battle_calc import (
    calc_battle_stats, calc_power, get_normalized_base_stats, EVO_STAGE_MAP,
)

logger = logging.getLogger(__name__)

KST = _dt.timezone(_dt.timedelta(hours=9))


# ══════════════════════════════════════════════════════════
# 테마 시스템
# ══════════════════════════════════════════════════════════

def get_today_theme() -> dict:
    """KST 요일 기반 오늘의 던전 테마 반환."""
    now = _dt.datetime.now(KST)
    weekday = now.weekday()  # 0=Mon
    return config.DUNGEON_THEMES[weekday % len(config.DUNGEON_THEMES)]


# ══════════════════════════════════════════════════════════
# 난이도 스케일링
# ══════════════════════════════════════════════════════════

def enemy_scaling(floor: int) -> float:
    """층별 적 스탯 배율."""
    if floor <= 10:
        return 1.0 + floor * 0.06
    elif floor <= 20:
        return 1.60 + (floor - 10) * 0.10
    elif floor <= 30:
        return 2.60 + (floor - 10) * 0.15
    else:
        return 4.10 + (floor - 30) * 0.20


# ══════════════════════════════════════════════════════════
# 적 포켓몬 생성
# ══════════════════════════════════════════════════════════

def _get_all_pokemon_by_type() -> dict[str, list[dict]]:
    """타입별 포켓몬 목록 빌드."""
    from models.pokemon_base_stats import POKEMON_BASE_STATS
    from models.pokemon_data import ALL_POKEMON

    poke_map = {}
    for p in ALL_POKEMON:
        poke_map[p[0]] = {"id": p[0], "name_ko": p[1], "rarity": p[4], "type": p[5]}

    type_pool: dict[str, list[dict]] = {}
    for pid, entry in POKEMON_BASE_STATS.items():
        if pid not in poke_map:
            continue
        info = poke_map[pid]
        types = entry[6] if len(entry) > 6 else [info["type"]]
        for t in types:
            type_pool.setdefault(t, []).append({
                "id": pid,
                "name_ko": info["name_ko"],
                "rarity": info["rarity"],
                "types": types,
            })
    return type_pool


_TYPE_POOL: dict[str, list[dict]] | None = None


def _get_type_pool() -> dict[str, list[dict]]:
    global _TYPE_POOL
    if _TYPE_POOL is None:
        _TYPE_POOL = _get_all_pokemon_by_type()
    return _TYPE_POOL


def _pick_enemy_rarity(floor: int) -> str:
    """층수에 따른 적 희귀도."""
    if floor <= 5:
        return random.choice(["common"] * 8 + ["rare"] * 2)
    elif floor <= 10:
        return random.choice(["common"] * 4 + ["rare"] * 5 + ["epic"])
    elif floor <= 20:
        return random.choice(["rare"] * 5 + ["epic"] * 4 + ["legendary"])
    elif floor <= 30:
        return random.choice(["rare"] * 2 + ["epic"] * 5 + ["legendary"] * 3)
    else:
        return random.choice(["epic"] * 4 + ["legendary"] * 4 + ["ultra_legendary"] * 2)


def generate_enemy(floor: int, theme: dict) -> dict:
    """테마 기반 적 포켓몬 생성."""
    pool = _get_type_pool()
    is_boss = floor % 5 == 0
    is_elite = not is_boss and random.random() < 0.20

    # 테마 타입 60%, 기타 40%
    if random.random() < 0.60:
        chosen_type = random.choice(theme["types"])
    else:
        all_types = list(config.TYPE_ADVANTAGE.keys())
        chosen_type = random.choice(all_types)

    candidates = pool.get(chosen_type, [])
    target_rarity = _pick_enemy_rarity(floor)

    # 희귀도 필터
    filtered = [c for c in candidates if c["rarity"] == target_rarity]
    if not filtered:
        filtered = candidates
    if not filtered:
        # 폴백: 아무 타입에서
        all_poke = []
        for v in pool.values():
            all_poke.extend(v)
        filtered = all_poke

    enemy = random.choice(filtered)
    scaling = enemy_scaling(floor)
    if is_boss:
        scaling *= 1.5
    elif is_elite:
        scaling *= 1.3

    # 적 스탯 계산 (IV=0, 친밀도=0, 최종진화)
    base_kw = get_normalized_base_stats(enemy["id"]) or {}
    raw_stats = calc_battle_stats(
        enemy["rarity"], "balanced", 0, 3,
        0, 0, 0, 0, 0, 0,
        **base_kw,
    )

    # 스케일링 적용
    scaled = {}
    for k, v in raw_stats.items():
        scaled[k] = max(1, int(v * scaling))

    return {
        "id": enemy["id"],
        "name_ko": enemy["name_ko"],
        "rarity": enemy["rarity"],
        "types": enemy.get("types", [chosen_type]),
        "stats": scaled,
        "is_boss": is_boss,
        "is_elite": is_elite,
        "floor": floor,
        "scaling": round(scaling, 2),
    }


# ══════════════════════════════════════════════════════════
# 버프 시스템 (Phase 1: 직접스탯 + 생존만)
# ══════════════════════════════════════════════════════════

BUFF_POOL = [
    # 직접 스탯
    {"id": "atk_15",  "name": "공격 강화",     "grade": "normal",   "category": "stat", "effect": {"stat": "atk",   "mult": 1.15}, "desc": "공격력 +15%"},
    {"id": "atk_25",  "name": "강력한 일격",   "grade": "advanced", "category": "stat", "effect": {"stat": "atk",   "mult": 1.25}, "desc": "공격력 +25%"},
    {"id": "atk_40",  "name": "궁극의 힘",     "grade": "rare",     "category": "stat", "effect": {"stat": "atk",   "mult": 1.40}, "desc": "공격력 +40%"},
    {"id": "spa_15",  "name": "특공 강화",     "grade": "normal",   "category": "stat", "effect": {"stat": "spa",   "mult": 1.15}, "desc": "특수공격 +15%"},
    {"id": "spa_25",  "name": "마력 폭발",     "grade": "advanced", "category": "stat", "effect": {"stat": "spa",   "mult": 1.25}, "desc": "특수공격 +25%"},
    {"id": "hp_15",   "name": "체력 강화",     "grade": "normal",   "category": "stat", "effect": {"stat": "hp",    "mult": 1.15}, "desc": "HP +15%"},
    {"id": "hp_25",   "name": "불굴의 체력",   "grade": "advanced", "category": "stat", "effect": {"stat": "hp",    "mult": 1.25}, "desc": "HP +25%"},
    {"id": "def_15",  "name": "방어 강화",     "grade": "normal",   "category": "stat", "effect": {"stat": "def",   "mult": 1.15}, "desc": "방어력 +15%"},
    {"id": "def_30",  "name": "철벽 방어",     "grade": "advanced", "category": "stat", "effect": {"stat": "def",   "mult": 1.30}, "desc": "방어력 +30%"},
    {"id": "spdef_15","name": "특방 강화",     "grade": "normal",   "category": "stat", "effect": {"stat": "spdef", "mult": 1.15}, "desc": "특수방어 +15%"},
    {"id": "spd_15",  "name": "쾌속",          "grade": "normal",   "category": "stat", "effect": {"stat": "spd",   "mult": 1.15}, "desc": "스피드 +15%"},
    {"id": "spd_25",  "name": "신속의 발",     "grade": "advanced", "category": "stat", "effect": {"stat": "spd",   "mult": 1.25}, "desc": "스피드 +25%"},
    {"id": "all_10",  "name": "전능의 기운",   "grade": "rare",     "category": "stat", "effect": {"stat": "all",   "mult": 1.10}, "desc": "전스탯 +10%"},
    # 생존
    {"id": "lifesteal","name": "생명력 흡수",  "grade": "advanced", "category": "survival", "effect": {"type": "lifesteal", "rate": 0.10}, "desc": "데미지의 10% HP회복"},
    {"id": "revive",   "name": "부활의 깃털",  "grade": "legendary","category": "survival", "effect": {"type": "revive", "hp_pct": 0.30}, "desc": "사망 시 1회 부활 (30%)"},
    {"id": "heal_5",   "name": "자연 치유",    "grade": "normal",   "category": "survival", "effect": {"type": "floor_heal", "rate": 0.05}, "desc": "매 층 HP 5% 회복"},
    {"id": "heal_8",   "name": "응급 처치",    "grade": "advanced", "category": "survival", "effect": {"type": "floor_heal", "rate": 0.08}, "desc": "매 층 HP 8% 회복"},
    {"id": "heal_12",  "name": "생명의 축복",  "grade": "rare",     "category": "survival", "effect": {"type": "floor_heal", "rate": 0.12}, "desc": "매 층 HP 12% 회복"},
]

GRADE_EMOJI = {"normal": "⬜", "advanced": "🟦", "rare": "🟪", "legendary": "🟨"}
GRADE_KO = {"normal": "일반", "advanced": "고급", "rare": "희귀", "legendary": "전설"}


def _get_grade_probs(floor: int) -> dict[str, int]:
    """층수에 맞는 버프 등급 확률."""
    for max_floor, probs in sorted(config.DUNGEON_BUFF_GRADE_PROB.items()):
        if floor <= max_floor:
            return probs
    return config.DUNGEON_BUFF_GRADE_PROB[999]


def _pick_grade(floor: int) -> str:
    probs = _get_grade_probs(floor)
    pool = []
    for grade, weight in probs.items():
        pool.extend([grade] * weight)
    return random.choice(pool)


def generate_buff_choices(
    floor: int, current_buffs: list[dict], count: int = 3
) -> list[dict]:
    """버프 선택지 생성 (서로 다른 카테고리에서 count개)."""
    used_categories = set()
    choices = []
    attempts = 0

    while len(choices) < count and attempts < 50:
        attempts += 1
        grade = _pick_grade(floor)
        candidates = [b for b in BUFF_POOL
                       if b["grade"] == grade
                       and b["category"] not in used_categories]
        if not candidates:
            # 카테고리 제한 완화
            candidates = [b for b in BUFF_POOL if b["grade"] == grade]
        if not candidates:
            # 등급 제한도 완화
            candidates = [b for b in BUFF_POOL if b["category"] not in used_categories]
        if not candidates:
            candidates = list(BUFF_POOL)

        pick = random.choice(candidates)
        choices.append(pick)
        used_categories.add(pick["category"])

    return choices[:count]


def should_offer_buff(floor: int, pokemon_cost: int) -> bool:
    """이번 층에서 버프를 줘야 하는지."""
    freq = config.DUNGEON_BUFF_FREQUENCY.get(pokemon_cost, 1)
    return floor % freq == 0


# ══════════════════════════════════════════════════════════
# 버프 적용
# ══════════════════════════════════════════════════════════

def apply_buffs_to_stats(base_stats: dict, buffs: list[dict]) -> dict:
    """스탯 버프를 곱연산으로 적용. 원본 수정하지 않음."""
    result = dict(base_stats)
    for buff in buffs:
        eff = buff.get("effect", {})
        if eff.get("stat") == "all":
            mult = eff.get("mult", 1.0)
            for k in result:
                result[k] = int(result[k] * mult)
        elif eff.get("stat") in result:
            stat = eff["stat"]
            mult = eff.get("mult", 1.0)
            result[stat] = int(result[stat] * mult)
    return result


def get_floor_heal_rate(buffs: list[dict]) -> float:
    """누적 층간 회복률."""
    total = 0.0
    for b in buffs:
        eff = b.get("effect", {})
        if eff.get("type") == "floor_heal":
            total += eff.get("rate", 0)
    return total


def has_revive(buffs: list[dict]) -> bool:
    return any(b.get("effect", {}).get("type") == "revive" for b in buffs)


def get_lifesteal_rate(buffs: list[dict]) -> float:
    total = 0.0
    for b in buffs:
        eff = b.get("effect", {})
        if eff.get("type") == "lifesteal":
            total += eff.get("rate", 0)
    return total


# ══════════════════════════════════════════════════════════
# 던전 전용 1v1 배틀 엔진
# ══════════════════════════════════════════════════════════

def _type_multiplier(atk_types: list[str], def_types: list[str], is_dungeon: bool = True) -> tuple[float, int]:
    """상성 배율 계산. Returns (multiplier, best_atk_type_index)."""
    best_mult = 0.0
    best_idx = 0

    for i, at in enumerate(atk_types):
        mult = 1.0
        for dt in def_types:
            # 면역 체크
            if dt in config.TYPE_IMMUNITY.get(at, []):
                if is_dungeon:
                    mult *= config.DUNGEON_IMMUNITY_MULT
                else:
                    mult *= 0.0
            # 효과좋음
            elif dt in config.TYPE_ADVANTAGE.get(at, []):
                mult *= 1.5
            # 효과별로
            elif dt in config.TYPE_RESISTANCE.get(at, []):
                mult *= 0.67
        if mult > best_mult:
            best_mult = mult
            best_idx = i

    return max(best_mult, 0.01), best_idx


def resolve_dungeon_battle(
    player_stats: dict,
    player_types: list[str],
    player_rarity: str,
    enemy: dict,
    buffs: list[dict],
) -> dict:
    """던전 1v1 배틀 해결.

    Returns:
        {won, remaining_hp, max_hp, turns, total_damage_dealt, total_damage_taken, log}
    """
    # 버프 적용된 플레이어 스탯
    p_stats = apply_buffs_to_stats(player_stats, buffs)
    e_stats = dict(enemy["stats"])

    p_hp = p_stats["hp"]
    p_max_hp = p_stats["hp"]
    e_hp = e_stats["hp"]

    lifesteal = get_lifesteal_rate(buffs)
    revive_available = has_revive(buffs)

    log_lines = []
    total_dmg_dealt = 0
    total_dmg_taken = 0

    # 상성 계산
    type_mult_p, _ = _type_multiplier(player_types, enemy["types"])
    type_mult_e, _ = _type_multiplier(enemy["types"], player_types)

    type_display = ""
    if type_mult_p > 1.0:
        type_display = f"유리! (×{type_mult_p:.1f})"
    elif type_mult_p < 1.0:
        type_display = f"불리 (×{type_mult_p:.2f})"
    else:
        type_display = "보통 (×1.0)"

    for turn in range(1, config.DUNGEON_MAX_ROUNDS + 1):
        if p_hp <= 0 or e_hp <= 0:
            break

        # 속도순 결정
        p_first = p_stats["spd"] >= e_stats["spd"]
        if p_stats["spd"] == e_stats["spd"]:
            p_first = random.random() < 0.5

        fighters = [("player", p_stats, player_types, player_rarity, type_mult_p),
                     ("enemy", e_stats, enemy["types"], enemy["rarity"], type_mult_e)]
        if not p_first:
            fighters.reverse()

        for tag, atk_s, atk_types, rarity, t_mult in fighters:
            if p_hp <= 0 or e_hp <= 0:
                break

            # 물리 vs 특수
            if atk_s["atk"] >= atk_s["spa"]:
                atk_val = atk_s["atk"]
                def_val = e_stats["def"] if tag == "player" else p_stats["def"]
            else:
                atk_val = atk_s["spa"]
                def_val = e_stats["spdef"] if tag == "player" else p_stats["spdef"]

            # 기본 데미지
            base = max(1, atk_val - int(def_val * 0.4))

            # 크리티컬
            is_crit = random.random() < config.DUNGEON_CRIT_RATE
            crit_mult = config.DUNGEON_CRIT_MULT if is_crit else 1.0

            # 스킬
            skill_activated = random.random() < config.DUNGEON_SKILL_RATE
            skill_mult = config.DUNGEON_SKILL_MULT.get(rarity, 1.2) if skill_activated else 1.0

            # 편차
            variance = random.uniform(0.9, 1.1)

            damage = max(1, int(base * t_mult * crit_mult * skill_mult * variance))

            if tag == "player":
                e_hp -= damage
                total_dmg_dealt += damage
                # 흡혈
                if lifesteal > 0:
                    heal = int(damage * lifesteal)
                    p_hp = min(p_max_hp, p_hp + heal)
            else:
                p_hp -= damage
                total_dmg_taken += damage

        # 턴 종료 후 부활 체크
        if p_hp <= 0 and revive_available:
            p_hp = int(p_max_hp * 0.30)
            revive_available = False
            log_lines.append("💫 부활의 깃털 발동! HP 30% 회복")

    won = p_hp > 0 and e_hp <= 0

    # 50턴 초과: 남은 HP 비율로 판정
    if p_hp > 0 and e_hp > 0:
        won = (p_hp / p_max_hp) > (e_hp / e_stats["hp"])

    return {
        "won": won,
        "remaining_hp": max(0, p_hp),
        "max_hp": p_max_hp,
        "turns": min(turn, config.DUNGEON_MAX_ROUNDS),
        "total_damage_dealt": total_dmg_dealt,
        "total_damage_taken": total_dmg_taken,
        "type_display": type_display,
        "type_mult_player": type_mult_p,
        "log": log_lines,
    }


# ══════════════════════════════════════════════════════════
# 보상 계산
# ══════════════════════════════════════════════════════════

def calculate_rewards(floor_reached: int, theme: str, sub_tier: str | None = None) -> dict:
    """런 종료 시 보상 계산."""
    # 기본 BP
    bp = floor_reached * config.DUNGEON_BP_PER_FLOOR
    fragments = 0
    tickets = 0
    milestones = []

    # 마일스톤 보상 합산
    for milestone_floor, rewards in sorted(config.DUNGEON_MILESTONE_REWARDS.items()):
        if floor_reached >= milestone_floor:
            bp += rewards.get("bp", 0)
            fragments += rewards.get("fragments", 0)
            tickets += rewards.get("tickets", 0)
            milestones.append(milestone_floor)

    # 구독 배율
    if sub_tier == "channel_owner":
        bp = int(bp * 1.5)
    elif sub_tier == "basic":
        bp = int(bp * 1.2)

    # 칭호 체크
    new_titles = []
    for t_floor, (title, emoji) in config.DUNGEON_MILESTONE_TITLES.items():
        if floor_reached >= t_floor:
            new_titles.append({"floor": t_floor, "title": title, "emoji": emoji})

    return {
        "bp": bp,
        "fragments": fragments,
        "tickets": tickets,
        "milestones": milestones,
        "new_titles": new_titles,
    }


# ══════════════════════════════════════════════════════════
# 플레이어 포켓몬 스탯 빌드
# ══════════════════════════════════════════════════════════

def build_player_stats(pokemon: dict) -> tuple[dict, list[str]]:
    """유저 포켓몬의 배틀 스탯 + 타입 반환.

    pokemon: DB row dict (pokemon_id, rarity, stat_type, friendship, is_shiny, iv_*)
    Returns: (stats_dict, types_list)
    """
    from models.pokemon_base_stats import POKEMON_BASE_STATS

    pid = pokemon["pokemon_id"]
    rarity = pokemon["rarity"]
    stat_type = pokemon.get("stat_type", "balanced")
    friendship = pokemon.get("friendship", 0)
    is_shiny = pokemon.get("is_shiny", False)
    evo_stage = EVO_STAGE_MAP.get(pid, 3)

    # 어드바이저와 동일: 이로치 7강, 일반 5강 (최대 육성 가정)
    max_friendship = 7 if is_shiny else 5

    base_kw = get_normalized_base_stats(pid) or {}
    stats = calc_battle_stats(
        rarity, stat_type, max_friendship, evo_stage,
        pokemon.get("iv_hp"), pokemon.get("iv_atk"), pokemon.get("iv_def"),
        pokemon.get("iv_spa"), pokemon.get("iv_spdef"), pokemon.get("iv_spd"),
        **base_kw,
    )

    # HP 배율 (배틀과 동일)
    hp_mult = getattr(config, 'BATTLE_HP_MULTIPLIER', 1)
    if hp_mult > 1:
        stats["hp"] = int(stats["hp"] * hp_mult)

    # 타입
    entry = POKEMON_BASE_STATS.get(pid)
    if entry and len(entry) > 6:
        types = list(entry[6])
    else:
        types = [pokemon.get("pokemon_type", "normal")]

    return stats, types
