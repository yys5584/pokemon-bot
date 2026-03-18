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
        return 2.60 + (floor - 20) * 0.15
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
# 버프 시스템 (뱀서식 레벨업 + 히든 시너지)
# ══════════════════════════════════════════════════════════

# 레벨업 버프 정의: id → {name, category, max_lv, levels: [{효과값들}]}
BUFF_DEFS = {
    # ── 스탯 계열 ──
    "atk":    {"name": "공격 강화",   "category": "stat", "max_lv": 3,
               "levels": [{"mult": 1.15, "desc": "공격력 +15%"}, {"mult": 1.30, "desc": "공격력 +30%"}, {"mult": 1.45, "desc": "공격력 +45%"}]},
    "spa":    {"name": "특공 강화",   "category": "stat", "max_lv": 3,
               "levels": [{"mult": 1.15, "desc": "특수공격 +15%"}, {"mult": 1.30, "desc": "특수공격 +30%"}, {"mult": 1.45, "desc": "특수공격 +45%"}]},
    "hp":     {"name": "체력 강화",   "category": "stat", "max_lv": 3,
               "levels": [{"mult": 1.15, "desc": "HP +15%"}, {"mult": 1.25, "desc": "HP +25%"}, {"mult": 1.40, "desc": "HP +40%"}]},
    "def":    {"name": "방어 강화",   "category": "stat", "max_lv": 3,
               "levels": [{"mult": 1.15, "desc": "방어 +15%"}, {"mult": 1.25, "desc": "방어 +25%"}, {"mult": 1.35, "desc": "방어 +35%"}]},
    "spdef":  {"name": "특방 강화",   "category": "stat", "max_lv": 3,
               "levels": [{"mult": 1.15, "desc": "특방 +15%"}, {"mult": 1.25, "desc": "특방 +25%"}, {"mult": 1.35, "desc": "특방 +35%"}]},
    "spd":    {"name": "스피드",      "category": "stat", "max_lv": 3,
               "levels": [{"mult": 1.15, "desc": "스피드 +15%"}, {"mult": 1.25, "desc": "스피드 +25%"}, {"mult": 1.35, "desc": "스피드 +35%"}]},
    # ── 전투 계열 ──
    "crit":   {"name": "크리 강화",   "category": "combat", "max_lv": 3,
               "levels": [{"rate": 0.10, "desc": "크리 확률 +10%"}, {"rate": 0.18, "desc": "크리 확률 +18%"}, {"rate": 0.25, "desc": "크리 확률 +25%"}]},
    "double": {"name": "이중타격",    "category": "combat", "max_lv": 3,
               "levels": [{"rate": 0.15, "desc": "15% 2회 공격"}, {"rate": 0.22, "desc": "22% 2회 공격"}, {"rate": 0.30, "desc": "30% 2회 공격"}]},
    "dodge":  {"name": "회피 본능",   "category": "combat", "max_lv": 3,
               "levels": [{"rate": 0.10, "desc": "10% 회피"}, {"rate": 0.18, "desc": "18% 회피"}, {"rate": 0.25, "desc": "25% 회피"}]},
    "thorns": {"name": "가시갑옷",    "category": "combat", "max_lv": 3,
               "levels": [{"rate": 0.15, "desc": "피해 15% 반사"}, {"rate": 0.25, "desc": "피해 25% 반사"}, {"rate": 0.35, "desc": "피해 35% 반사"}]},
    # ── 생존 계열 ──
    "lifesteal": {"name": "흡혈",     "category": "survival", "max_lv": 3,
               "levels": [{"rate": 0.08, "desc": "8% 흡혈"}, {"rate": 0.15, "desc": "15% 흡혈"}, {"rate": 0.20, "desc": "20% 흡혈"}]},
    "heal":   {"name": "층간 회복",   "category": "survival", "max_lv": 3,
               "levels": [{"rate": 0.05, "desc": "매층 HP 5%"}, {"rate": 0.10, "desc": "매층 HP 10%"}, {"rate": 0.15, "desc": "매층 HP 15%"}]},
    "shield": {"name": "보호막",      "category": "survival", "max_lv": 3,
               "levels": [{"rate": 0.10, "desc": "매층 10% 실드"}, {"rate": 0.15, "desc": "매층 15% 실드"}, {"rate": 0.20, "desc": "매층 20% 실드"}]},
    # ── 1회성 (레벨 없음) ──
    "revive": {"name": "부활의 깃털", "category": "unique", "max_lv": 1,
               "levels": [{"desc": "사망 시 1회 부활 (30%)"}]},
    "allstat":{"name": "전능의 기운", "category": "unique", "max_lv": 1,
               "levels": [{"mult": 1.15, "desc": "전스탯 +15%"}]},
}

# 히든 시너지: 조건 충족 시 자동 발동
SYNERGIES = {
    "fury":    {"name": "필살연격",   "emoji": "🔥", "req": {"crit": 2, "double": 2},
                "desc": "크리 시 이중타격 확률 2배", "effect": {"type": "crit_double"}},
    "vampire": {"name": "피의 갑옷",  "emoji": "🩸", "req": {"lifesteal": 2, "thorns": 2},
                "desc": "반사 데미지도 흡혈", "effect": {"type": "thorns_lifesteal"}},
    "phantom": {"name": "잔상",       "emoji": "👻", "req": {"dodge": 2, "spd": 2},
                "desc": "회피 시 다음 공격 크리 확정", "effect": {"type": "dodge_crit"}},
    "power":   {"name": "풀파워",     "emoji": "⚡", "req": {"atk": 3, "spa": 3},
                "desc": "전체 데미지 +20%", "effect": {"type": "damage_boost", "mult": 1.20}},
    "iron":    {"name": "철벽요새",   "emoji": "🛡️", "req": {"hp": 2, "def": 2, "spdef": 2},
                "desc": "받는 데미지 -15%", "effect": {"type": "damage_reduce", "mult": 0.85}},
    "reaper":  {"name": "사신의 낫",  "emoji": "💀", "req": {"crit": 3, "atk": 3},
                "desc": "적 HP 15% 이하 즉사", "effect": {"type": "execute", "threshold": 0.15}},
}

# 등급별 이모지/한글 (레벨 기반)
LV_EMOJI = {1: "⬜", 2: "🟦", 3: "🟪"}
LV_KO = {1: "Lv.1", 2: "Lv.2", 3: "Lv.3"}

GRADE_EMOJI = {"normal": "⬜", "advanced": "🟦", "rare": "🟪", "legendary": "🟨"}
GRADE_KO = {"normal": "일반", "advanced": "고급", "rare": "희귀", "legendary": "전설"}


def _get_buff_level(buff_id: str, current_buffs: list[dict]) -> int:
    """현재 버프 리스트에서 해당 버프의 레벨을 반환 (없으면 0)."""
    for b in current_buffs:
        if b.get("id") == buff_id:
            return b.get("lv", 1)
    return 0


def _get_active_synergies(current_buffs: list[dict]) -> list[dict]:
    """현재 버프에서 발동 중인 시너지 목록."""
    buff_levels = {}
    for b in current_buffs:
        buff_levels[b["id"]] = b.get("lv", 1)

    active = []
    for syn_id, syn in SYNERGIES.items():
        if all(buff_levels.get(bid, 0) >= req_lv for bid, req_lv in syn["req"].items()):
            active.append({"id": syn_id, **syn})
    return active


def check_new_synergies(old_buffs: list[dict], new_buffs: list[dict]) -> list[dict]:
    """버프 변경 후 새로 발동된 시너지 반환."""
    old_syn = {s["id"] for s in _get_active_synergies(old_buffs)}
    new_syn = _get_active_synergies(new_buffs)
    return [s for s in new_syn if s["id"] not in old_syn]


def generate_buff_choices(
    floor: int, current_buffs: list[dict], count: int = 3
) -> list[dict]:
    """버프 선택지 생성 — 레벨업 가능한 것 + 새로운 것 혼합."""
    choices = []
    used_ids = set()

    # 현재 보유 버프 중 레벨업 가능한 것들
    upgradable = []
    for b in current_buffs:
        bdef = BUFF_DEFS.get(b["id"])
        if bdef and b.get("lv", 1) < bdef["max_lv"]:
            upgradable.append(b["id"])

    # 아직 없는 버프들
    owned_ids = {b["id"] for b in current_buffs}
    new_available = [bid for bid in BUFF_DEFS if bid not in owned_ids]

    # 선택지 구성: 레벨업 1~2개 + 새 버프 1~2개 (가능한 만큼)
    random.shuffle(upgradable)
    random.shuffle(new_available)

    # 레벨업 선택지 (최대 2개)
    for bid in upgradable:
        if len(choices) >= min(2, count):
            break
        if bid in used_ids:
            continue
        bdef = BUFF_DEFS[bid]
        cur_lv = _get_buff_level(bid, current_buffs)
        next_lv = cur_lv + 1
        lv_data = bdef["levels"][next_lv - 1]
        choices.append({
            "id": bid, "name": bdef["name"], "category": bdef["category"],
            "lv": next_lv, "is_upgrade": True,
            "effect": lv_data, "desc": lv_data["desc"],
        })
        used_ids.add(bid)

    # 새 버프 선택지 (나머지 채움)
    for bid in new_available:
        if len(choices) >= count:
            break
        if bid in used_ids:
            continue
        bdef = BUFF_DEFS[bid]
        lv_data = bdef["levels"][0]
        choices.append({
            "id": bid, "name": bdef["name"], "category": bdef["category"],
            "lv": 1, "is_upgrade": False,
            "effect": lv_data, "desc": lv_data["desc"],
        })
        used_ids.add(bid)

    # 선택지가 부족하면 남은 레벨업으로 채움
    for bid in upgradable:
        if len(choices) >= count:
            break
        if bid in used_ids:
            continue
        bdef = BUFF_DEFS[bid]
        cur_lv = _get_buff_level(bid, current_buffs)
        next_lv = cur_lv + 1
        lv_data = bdef["levels"][next_lv - 1]
        choices.append({
            "id": bid, "name": bdef["name"], "category": bdef["category"],
            "lv": next_lv, "is_upgrade": True,
            "effect": lv_data, "desc": lv_data["desc"],
        })
        used_ids.add(bid)

    random.shuffle(choices)
    return choices[:count]


def apply_buff_choice(current_buffs: list[dict], choice: dict) -> list[dict]:
    """선택된 버프를 적용 (레벨업 또는 새로 추가)."""
    new_buffs = []
    found = False
    for b in current_buffs:
        if b["id"] == choice["id"]:
            # 레벨업
            new_buffs.append({**b, "lv": choice["lv"], "effect": choice["effect"], "desc": choice["desc"]})
            found = True
        else:
            new_buffs.append(b)
    if not found:
        new_buffs.append({
            "id": choice["id"], "name": choice["name"], "category": choice["category"],
            "lv": choice["lv"], "effect": choice["effect"], "desc": choice["desc"],
        })
    return new_buffs


def should_offer_buff(floor: int, pokemon_cost: int) -> bool:
    """이번 층에서 버프를 줘야 하는지."""
    freq = config.DUNGEON_BUFF_FREQUENCY.get(pokemon_cost, 1)
    return floor % freq == 0


# ══════════════════════════════════════════════════════════
# 버프 적용 (배틀 엔진용)
# ══════════════════════════════════════════════════════════

def apply_buffs_to_stats(base_stats: dict, buffs: list[dict]) -> dict:
    """스탯 버프를 적용. 원본 수정하지 않음."""
    result = dict(base_stats)
    for buff in buffs:
        eff = buff.get("effect", {})
        bid = buff.get("id", "")
        # 스탯 계열: mult 적용
        if bid in ("atk", "spa", "hp", "def", "spdef", "spd") and "mult" in eff:
            if bid in result:
                result[bid] = int(result[bid] * eff["mult"])
        # 전스탯
        elif bid == "allstat" and "mult" in eff:
            for k in result:
                result[k] = int(result[k] * eff["mult"])
    return result


def get_floor_heal_rate(buffs: list[dict]) -> float:
    """층간 회복률."""
    for b in buffs:
        if b.get("id") == "heal":
            return b["effect"].get("rate", 0)
    return 0.0


def get_shield_rate(buffs: list[dict]) -> float:
    """보호막 비율."""
    for b in buffs:
        if b.get("id") == "shield":
            return b["effect"].get("rate", 0)
    return 0.0


def has_revive(buffs: list[dict]) -> bool:
    return any(b.get("id") == "revive" for b in buffs)


def get_lifesteal_rate(buffs: list[dict]) -> float:
    for b in buffs:
        if b.get("id") == "lifesteal":
            return b["effect"].get("rate", 0)
    return 0.0


def get_combat_rate(buffs: list[dict], buff_id: str) -> float:
    """전투 버프 (crit/double/dodge/thorns) 확률."""
    for b in buffs:
        if b.get("id") == buff_id:
            return b["effect"].get("rate", 0)
    return 0.0


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
    current_hp: int | None = None,
    max_hp: int | None = None,
) -> dict:
    """던전 1v1 배틀 해결. current_hp/max_hp로 carry-over HP 지원.

    Returns:
        {won, remaining_hp, max_hp, turns, total_damage_dealt, total_damage_taken,
         log, revive_used, type_display, type_mult_player}
    """
    # 버프 적용된 플레이어 스탯
    p_stats = apply_buffs_to_stats(player_stats, buffs)
    e_stats = dict(enemy["stats"])

    # carry-over HP (이전 층에서 남은 HP)
    p_max_hp = max_hp if max_hp is not None else p_stats["hp"]
    p_hp = current_hp if current_hp is not None else p_max_hp
    e_hp = e_stats["hp"]

    # 보호막: 매 층 시작 시 실드 적용 (데미지 먼저 흡수)
    shield_rate = get_shield_rate(buffs)
    p_shield = int(p_max_hp * shield_rate) if shield_rate > 0 else 0

    lifesteal = get_lifesteal_rate(buffs)
    revive_available = has_revive(buffs)
    revive_used = False

    # 전투 버프
    crit_bonus = get_combat_rate(buffs, "crit")
    double_rate = get_combat_rate(buffs, "double")
    dodge_rate = get_combat_rate(buffs, "dodge")
    thorns_rate = get_combat_rate(buffs, "thorns")

    # 히든 시너지
    active_syn = {s["id"] for s in _get_active_synergies(buffs)}
    dodge_crit_ready = False  # 잔상: 회피 후 다음 크리 확정

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

            # ── 회피 (플레이어만) ──
            if tag == "enemy" and dodge_rate > 0 and random.random() < dodge_rate:
                # 시너지: 잔상 — 회피 시 다음 크리 확정
                if "phantom" in active_syn:
                    dodge_crit_ready = True
                continue

            # 물리 vs 특수
            if atk_s["atk"] >= atk_s["spa"]:
                atk_val = atk_s["atk"]
                def_val = e_stats["def"] if tag == "player" else p_stats["def"]
            else:
                atk_val = atk_s["spa"]
                def_val = e_stats["spdef"] if tag == "player" else p_stats["spdef"]

            # 기본 데미지
            base = max(1, atk_val - int(def_val * 0.4))

            # 크리티컬 (버프 + 잔상 시너지)
            effective_crit = config.DUNGEON_CRIT_RATE
            if tag == "player":
                effective_crit += crit_bonus
                if dodge_crit_ready:
                    effective_crit = 1.0  # 잔상: 확정 크리
                    dodge_crit_ready = False
            is_crit = random.random() < effective_crit
            crit_mult = config.DUNGEON_CRIT_MULT if is_crit else 1.0

            # 스킬
            skill_activated = random.random() < config.DUNGEON_SKILL_RATE
            skill_mult = config.DUNGEON_SKILL_MULT.get(rarity, 1.2) if skill_activated else 1.0

            # 편차
            variance = random.uniform(0.9, 1.1)

            damage = max(1, int(base * t_mult * crit_mult * skill_mult * variance))

            # 시너지: 풀파워 — 전체 데미지 +20%
            if tag == "player" and "power" in active_syn:
                damage = int(damage * 1.20)

            # 시너지: 철벽요새 — 받는 데미지 -15%
            if tag == "enemy" and "iron" in active_syn:
                damage = int(damage * 0.85)

            if tag == "player":
                # 시너지: 사신의 낫 — 적 HP 15% 이하 즉사
                if "reaper" in active_syn and e_hp <= e_stats["hp"] * 0.15:
                    damage = e_hp  # 즉사

                # ── 이중타격 ──
                hit_count = 1
                effective_double = double_rate
                # 시너지: 필살연격 — 크리 시 이중타격 확률 2배
                if is_crit and "fury" in active_syn:
                    effective_double = min(1.0, effective_double * 2)
                if effective_double > 0 and random.random() < effective_double:
                    hit_count = 2

                for _hit in range(hit_count):
                    e_hp -= damage
                    total_dmg_dealt += damage
                    # 흡혈
                    if lifesteal > 0:
                        heal = int(damage * lifesteal)
                        p_hp = min(p_max_hp, p_hp + heal)
            else:
                # 보호막 먼저 흡수
                if p_shield > 0:
                    absorbed = min(p_shield, damage)
                    p_shield -= absorbed
                    damage -= absorbed

                p_hp -= damage
                total_dmg_taken += damage

                # ── 가시갑옷 ──
                if thorns_rate > 0 and damage > 0:
                    reflect = max(1, int((damage) * thorns_rate))
                    e_hp -= reflect
                    total_dmg_dealt += reflect
                    # 시너지: 피의 갑옷 — 반사 데미지 흡혈
                    if "vampire" in active_syn and lifesteal > 0:
                        heal = int(reflect * lifesteal)
                        p_hp = min(p_max_hp, p_hp + heal)

        # 턴 종료 후 부활 체크
        if p_hp <= 0 and revive_available:
            p_hp = int(p_max_hp * 0.30)
            revive_available = False
            revive_used = True
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
        "revive_used": revive_used,
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

    # 실제 친밀도 사용 (육성 투자가 던전 성능에 반영)
    actual_friendship = friendship

    base_kw = get_normalized_base_stats(pid) or {}
    stats = calc_battle_stats(
        rarity, stat_type, actual_friendship, evo_stage,
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
