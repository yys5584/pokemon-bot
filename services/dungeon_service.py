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


def get_zone_preview(cleared_floor: int, theme: dict) -> str | None:
    """보스 클리어 후 다음 구간 프리뷰 텍스트 반환.
    5의 배수 층 클리어 시에만 표시. 50층이면 None."""
    if cleared_floor % 5 != 0 or cleared_floor >= 50:
        return None

    next_start = cleared_floor + 1
    next_end = cleared_floor + 5
    next_boss = next_end

    # 난이도 등급
    scaling = enemy_scaling(next_boss)
    if scaling < 1.2:
        diff_label = "🟢 쉬움"
    elif scaling < 1.5:
        diff_label = "🟡 보통"
    elif scaling < 2.0:
        diff_label = "🟠 어려움"
    else:
        diff_label = "🔴 극한"

    # 상성 타입 팁
    from utils.helpers import _type_emoji
    adv_text = " / ".join(f"{_type_emoji(tp)}" for tp in theme.get("advantage", []))

    return (
        f"\n⚠️ <b>다음 구간: {theme['emoji']} {theme['name']} ({next_start}~{next_end}층)</b>\n"
        f"   난이도: {diff_label} (×{scaling:.2f})\n"
        f"   💡 유효 타입: {adv_text}\n"
        f"   👑 {next_boss}층 보스 등장!"
    )


# ══════════════════════════════════════════════════════════
# 난이도 스케일링
# ══════════════════════════════════════════════════════════

def enemy_scaling(floor: int) -> float:
    """층별 적 스탯 배율 (v5.3).
    v5.2 대비 31층+ 대폭 상향. 실 데이터 기반 조정.
    목표: 평균 20~25층, 40층 3~5%, 50층 <1%."""
    if floor <= 10:
        return 1.0 + floor * 0.012          # 1.012 ~ 1.12
    elif floor <= 20:
        return 1.12 + (floor - 10) * 0.020  # 1.14 ~ 1.32
    elif floor <= 30:
        return 1.32 + (floor - 20) * 0.030  # 1.35 ~ 1.62
    elif floor <= 40:
        return 1.62 + (floor - 30) * 0.06   # 1.68 ~ 2.22
    else:
        return 2.22 + (floor - 40) * 0.10   # 2.32 ~ 3.22


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
    """층수에 따른 적 희귀도. 30층+ 레어 제거."""
    if floor <= 5:
        return random.choice(["common"] * 8 + ["rare"] * 2)
    elif floor <= 10:
        return random.choice(["common"] * 4 + ["rare"] * 5 + ["epic"])
    elif floor <= 20:
        return random.choice(["rare"] * 5 + ["epic"] * 4 + ["legendary"])
    elif floor <= 30:
        return random.choice(["rare"] * 2 + ["epic"] * 5 + ["legendary"] * 3)
    elif floor <= 40:
        return random.choice(["epic"] * 5 + ["legendary"] * 3 + ["ultra_legendary"] * 2)
    else:
        return random.choice(["epic"] * 3 + ["legendary"] * 4 + ["ultra_legendary"] * 3)


def generate_enemy(floor: int, theme: dict, player_rarity: str = "epic") -> dict:
    """테마 기반 적 포켓몬 생성.
    player_rarity: 코스트별 적 스케일링 보정에 사용."""
    pool = _get_type_pool()
    is_boss = floor % 5 == 0
    is_elite = not is_boss and random.random() < 0.20

    # 보스는 반드시 테마 타입, 일반몹은 60% 테마 / 40% 랜덤
    if is_boss:
        chosen_type = random.choice(theme["types"])
    elif random.random() < 0.60:
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

    # 코스트별 적 스케일링 보정 (저코스트 = 적이 약해짐)
    cost_mult = config.DUNGEON_COST_SCALING.get(player_rarity, 0.75)
    scaling *= cost_mult

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
    # ── 턴제 전용 ──
    "pp_recovery": {"name": "PP 회복",    "category": "combat", "max_lv": 3,
               "levels": [{"rate": 2, "desc": "보스 클리어 시 PP +2"}, {"rate": 3, "desc": "보스 클리어 시 PP +3"}, {"rate": 4, "desc": "보스 클리어 시 PP +4"}]},
    "preemptive": {"name": "선제공격",    "category": "combat", "max_lv": 1,
               "levels": [{"desc": "속도 무관 항상 선공"}]},
    "counter":  {"name": "카운터",       "category": "combat", "max_lv": 3,
               "levels": [{"rate": 0.20, "desc": "방어 시 20% 반격"}, {"rate": 0.30, "desc": "방어 시 30% 반격"}, {"rate": 0.40, "desc": "방어 시 40% 반격"}]},
    "penetrate":{"name": "관통",         "category": "combat", "max_lv": 1,
               "levels": [{"desc": "적 방어 무시"}]},
    # ── 1회성 (레벨 없음) ──
    "revive": {"name": "부활의 깃털", "category": "unique", "max_lv": 1,
               "levels": [{"desc": "사망 시 1회 부활 (30%) — 런당 1회"}]},
    "allstat":{"name": "전능의 기운", "category": "unique", "max_lv": 1,
               "levels": [{"mult": 1.15, "desc": "전스탯 +15%"}]},
}

# ── 로그라이크 랜덤 이벤트 (8버프 포화 후) ──
# positive: 좋은 효과, negative: 디버프
ROGUELIKE_EVENTS = [
    # ── 긍정 ──
    {"id": "rogue_heal", "name": "🌿 신비한 샘물", "type": "positive",
     "desc": "HP 25% 회복!", "action": "heal", "value": 0.25},
    {"id": "rogue_atk_up", "name": "⚔️ 전사의 축복", "type": "positive",
     "desc": "다음 층 공격력 +20%", "action": "stat_mult", "stat": "atk", "value": 1.20},
    {"id": "rogue_def_up", "name": "🛡️ 수호자의 축복", "type": "positive",
     "desc": "다음 층 방어력 +20%", "action": "stat_mult", "stat": "def", "value": 1.20},
    {"id": "rogue_spd_up", "name": "💨 바람의 가호", "type": "positive",
     "desc": "다음 층 속도 +20%", "action": "stat_mult", "stat": "spd", "value": 1.20},
    {"id": "rogue_crit_up", "name": "🎯 예리한 눈", "type": "positive",
     "desc": "다음 층 크리 확률 +15%", "action": "stat_mult", "stat": "crit", "value": 0.15},
    {"id": "rogue_full_heal", "name": "✨ 기적의 빛", "type": "positive",
     "desc": "HP 전체 회복!", "action": "heal", "value": 1.0, "weight": 0.3},
    # ── 부정 ──
    {"id": "rogue_hp_drain", "name": "🩸 저주의 안개", "type": "negative",
     "desc": "HP 20% 감소!", "action": "damage", "value": 0.20},
    {"id": "rogue_atk_down", "name": "😵 약화의 주문", "type": "negative",
     "desc": "다음 층 공격력 -15%", "action": "stat_mult", "stat": "atk", "value": 0.85},
    {"id": "rogue_def_down", "name": "💀 갑옷 부식", "type": "negative",
     "desc": "다음 층 방어력 -15%", "action": "stat_mult", "stat": "def", "value": 0.85},
    {"id": "rogue_spd_down", "name": "🕸️ 거미줄 함정", "type": "negative",
     "desc": "다음 층 속도 -15%", "action": "stat_mult", "stat": "spd", "value": 0.85},
    {"id": "rogue_heavy_drain", "name": "☠️ 죽음의 손길", "type": "negative",
     "desc": "HP 35% 감소!", "action": "damage", "value": 0.35, "weight": 0.5},
]


def generate_roguelike_event() -> dict:
    """8버프 포화 후 랜덤 이벤트 생성 (로그라이크 방식)."""
    # weight가 없으면 기본 1.0
    weighted = [(e, e.get("weight", 1.0)) for e in ROGUELIKE_EVENTS]
    total = sum(w for _, w in weighted)
    r = random.random() * total
    cumulative = 0
    for event, w in weighted:
        cumulative += w
        if r <= cumulative:
            return event
    return ROGUELIKE_EVENTS[0]


def apply_roguelike_event(event: dict, current_hp: int, max_hp: int, buffs: list[dict]) -> tuple[int, list[dict], str]:
    """로그라이크 이벤트 적용. Returns (new_hp, new_buffs, log_message).
    스탯 버프/디버프는 다음 층 1턴만 적용 (_rogue_next 마커)."""
    action = event["action"]
    msg = f"🎲 {event['name']}\n   {event['desc']}"

    if action == "heal":
        heal = int(max_hp * event["value"])
        new_hp = min(max_hp, current_hp + heal)
        return new_hp, buffs, msg

    elif action == "damage":
        dmg = int(max_hp * event["value"])
        new_hp = max(1, current_hp - dmg)  # 최소 1 HP 보장
        return new_hp, buffs, msg

    elif action == "stat_mult":
        # 1턴용 마커: 다음 층 전투에서 적용 후 자동 제거
        stat = event["stat"]
        mult = event["value"]
        # 기존 로그 마커 제거 후 새로 추가
        buffs = [b for b in buffs if not (b.get("id", "").startswith("_rogue_") and b.get("rogue_stat") == stat)]
        buffs.append({
            "id": f"_rogue_{stat}", "name": event["name"], "lv": 0,
            "rogue_stat": stat, "rogue_mult": mult,
            "one_floor": True,  # 1턴 후 제거 플래그
        })
        return current_hp, buffs, msg

    return current_hp, buffs, msg


def get_rogue_stat_mults(buffs: list[dict]) -> dict:
    """현재 로그라이크 스탯 배율 반환. {stat: mult}"""
    mults = {}
    for b in buffs:
        if b.get("id", "").startswith("_rogue_") and b.get("rogue_stat"):
            mults[b["rogue_stat"]] = b.get("rogue_mult", 1.0)
    return mults


def consume_rogue_buffs(buffs: list[dict]) -> list[dict]:
    """1턴용 로그라이크 버프 제거 (전투 후 호출)."""
    return [b for b in buffs if not b.get("one_floor")]


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

    # 아직 없는 버프들 (슬롯 상한 + 생존 배타 체크)
    owned_ids = {b["id"] for b in current_buffs}
    # 부활 사용 완료 마커가 있으면 revive 재등장 차단
    if "_revive_consumed" in owned_ids:
        owned_ids.add("revive")
    at_cap = len([b for b in current_buffs if not b["id"].startswith("_")]) >= config.DUNGEON_MAX_BUFFS

    # 생존 계열 배타: 1개 선택하면 나머지 2개 차단
    _SURVIVAL_EXCLUSIVE = {"lifesteal", "heal", "shield"}
    owned_survival = owned_ids & _SURVIVAL_EXCLUSIVE
    blocked_ids = (_SURVIVAL_EXCLUSIVE - owned_survival) if owned_survival else set()

    new_available = [] if at_cap else [
        bid for bid in BUFF_DEFS
        if bid not in owned_ids and bid not in blocked_ids
    ]

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


def should_offer_buff(floor: int, pokemon_cost: int = 1) -> bool:
    """이번 층에서 버프를 줘야 하는지.
    턴제 대개편: 모든 코스트 동일하게 5층(보스)마다 버프."""
    return floor % 5 == 0


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
# 던전 전용 상성 계산
# ══════════════════════════════════════════════════════════

def _type_multiplier(atk_types: list[str], def_types: list[str], is_dungeon: bool = True) -> tuple[float, int]:
    """상성 배율 계산. Returns (multiplier, best_atk_type_index)."""
    best_mult = 0.0
    best_idx = 0

    for i, at in enumerate(atk_types):
        mult = 1.0
        for dt in def_types:
            if dt in config.TYPE_IMMUNITY.get(at, []):
                mult *= config.DUNGEON_TYPE_IMMUNE_MULT if is_dungeon else 0.0
            elif dt in config.TYPE_ADVANTAGE.get(at, []):
                mult *= config.DUNGEON_TYPE_ADVANTAGE_MULT
            elif dt in config.TYPE_RESISTANCE.get(at, []):
                mult *= config.DUNGEON_TYPE_DISADVANTAGE_MULT
        if mult > best_mult:
            best_mult = mult
            best_idx = i

    return max(best_mult, 0.01), best_idx


def _single_type_mult(atk_type: str, def_types: list[str]) -> float:
    """단일 공격 타입 vs 방어 타입 배율."""
    mult = 1.0
    for dt in def_types:
        if dt in config.TYPE_IMMUNITY.get(atk_type, []):
            mult *= config.DUNGEON_TYPE_IMMUNE_MULT
        elif dt in config.TYPE_ADVANTAGE.get(atk_type, []):
            mult *= config.DUNGEON_TYPE_ADVANTAGE_MULT
        elif dt in config.TYPE_RESISTANCE.get(atk_type, []):
            mult *= config.DUNGEON_TYPE_DISADVANTAGE_MULT
    return max(mult, 0.01)


# ══════════════════════════════════════════════════════════
# 턴제 전투 시스템 — 전투 상태 초기화
# ══════════════════════════════════════════════════════════

def get_pokemon_skills(pokemon_id: int, types: list[str]) -> list[dict]:
    """포켓몬의 던전 전용 특수기 목록 반환.

    Returns: [{"name": str, "type": str, "emoji": str}, ...]
    단일 타입 → 1개, 듀얼 타입 → 2개
    """
    skills = []
    for tp in types:
        name = config.DUNGEON_TYPE_SKILLS.get(tp, "몸통박치기")
        emoji = config.TYPE_EMOJI.get(tp, "⚪")
        skills.append({"name": name, "type": tp, "emoji": emoji})
    return skills


def init_combat_state(
    player_stats: dict,
    player_types: list[str],
    player_rarity: str,
    pokemon_id: int,
    enemy: dict,
    buffs: list[dict],
    current_hp: int,
    max_hp: int,
    floor: int,
) -> dict:
    """새 층 전투 시작 시 전투 상태 초기화.

    이 state는 context.user_data["dungeon"]["combat"]에 저장.
    """
    # 버프 적용된 플레이어 스탯
    p_stats = apply_buffs_to_stats(player_stats, buffs)
    e_stats = dict(enemy["stats"])

    # 보호막: 매 층 시작 시 실드 적용
    shield_rate = get_shield_rate(buffs)
    p_shield = int(max_hp * shield_rate) if shield_rate > 0 else 0

    # PP 설정
    pp_max = config.DUNGEON_PP_BY_RARITY.get(player_rarity, 6)
    skills = get_pokemon_skills(pokemon_id, player_types)

    # 상성 계산
    type_mult_p, best_atk_idx = _type_multiplier(player_types, enemy["types"])
    type_mult_e, _ = _type_multiplier(enemy["types"], player_types)

    # 각 특수기별 상성 배율
    skill_type_mults = []
    for sk in skills:
        skill_type_mults.append(_single_type_mult(sk["type"], enemy["types"]))

    # 적 첫 의도 생성
    intent = _generate_enemy_intent(enemy, floor)

    return {
        "floor": floor,
        "turn": 1,
        # 플레이어
        "p_stats": p_stats,
        "p_types": player_types,
        "p_rarity": player_rarity,
        "p_hp": current_hp,
        "p_max_hp": max_hp,
        "p_shield": p_shield,
        # PP (런 전체에서 관리되므로 핸들러가 주입)
        "pp": [],  # 핸들러에서 설정 [{current, max}]
        "pp_max": pp_max,
        "skills": skills,
        "skill_type_mults": skill_type_mults,
        # 적
        "enemy": enemy,
        "e_stats": e_stats,
        "e_hp": e_stats["hp"],
        "e_max_hp": e_stats["hp"],
        "e_intent": intent,
        "e_charged": False,     # 힘 모으기 상태
        "e_defending": False,   # 방어 상태
        "e_rage": False,        # 분노 (HP 30% 이하)
        # 상성
        "type_mult_p": type_mult_p,
        "type_mult_e": type_mult_e,
        "best_atk_idx": best_atk_idx,
        # 버프 참조
        "buffs": buffs,
        # 게으름 특성 (게을킹/레지기가스)
        "is_truant": pokemon_id in config.TRUANT_POKEMON,
        # 전투 로그
        "log": [],
        "total_dmg_dealt": 0,
        "total_dmg_taken": 0,
        "highlights": {
            "crit": 0, "dodge": 0, "double": 0,
            "thorns_dmg": 0, "lifesteal_heal": 0, "shield_absorbed": 0,
            "special_used": 0, "defend_used": 0,
        },
        "revive_used": False,
        "won": None,  # None=진행중, True=승리, False=패배
    }


# ══════════════════════════════════════════════════════════
# 적 의도 시스템 (Into the Breach 스타일)
# ══════════════════════════════════════════════════════════

def _generate_enemy_intent(enemy: dict, floor: int) -> dict:
    """적의 다음 행동 결정. 전투 시작 시 & 매 턴 결과 후 호출."""
    is_boss = enemy.get("is_boss", False)
    intent_table = config.DUNGEON_BOSS_INTENT if is_boss else config.DUNGEON_ENEMY_INTENT

    # 가중치 기반 선택
    r = random.random()
    cumulative = 0.0
    chosen = "normal_attack"
    for action, prob in intent_table.items():
        cumulative += prob
        if r <= cumulative:
            chosen = action
            break

    # 의도별 세부 정보
    e_types = enemy.get("types", ["normal"])
    e_stats = enemy.get("stats", {})
    e_atk = max(e_stats.get("atk", 100), e_stats.get("spa", 100))

    if chosen == "normal_attack":
        est_dmg = int(e_atk * 0.8 * random.uniform(0.9, 1.1))
        return {"action": "normal_attack", "name": "일반공격",
                "emoji": "⚔️", "est_damage": est_dmg}

    elif chosen == "type_attack":
        atk_type = random.choice(e_types)
        type_name = config.TYPE_NAME_KO.get(atk_type, atk_type)
        skill_name = config.DUNGEON_TYPE_SKILLS.get(atk_type, "특수공격")
        est_dmg = int(e_atk * config.DUNGEON_SPECIAL_MULT * random.uniform(0.9, 1.1))
        return {"action": "type_attack", "name": skill_name,
                "emoji": config.TYPE_EMOJI.get(atk_type, "💥"),
                "type": atk_type, "est_damage": est_dmg}

    elif chosen == "charge":
        return {"action": "charge", "name": "힘 모으기",
                "emoji": "💪", "est_damage": 0,
                "desc": "다음 턴 강공격!"}

    elif chosen == "defend":
        return {"action": "defend", "name": "방어 태세",
                "emoji": "🛡️", "est_damage": 0}

    elif chosen == "full_attack":
        est_dmg = int(e_atk * 2.0 * random.uniform(0.9, 1.1))
        return {"action": "full_attack", "name": "전체기",
                "emoji": "☠️", "est_damage": est_dmg}

    elif chosen == "heal":
        heal_amt = int(e_stats.get("hp", 500) * 0.15)
        return {"action": "heal", "name": "회복",
                "emoji": "💚", "est_damage": 0, "heal": heal_amt}

    return {"action": "normal_attack", "name": "일반공격",
            "emoji": "⚔️", "est_damage": int(e_atk * 0.8)}


def get_intent_warning(intent: dict, player_types: list[str]) -> str:
    """적 의도를 유저에게 보여줄 경고 텍스트."""
    action = intent["action"]
    emoji = intent["emoji"]
    name = intent["name"]

    if action == "normal_attack":
        return f"⚠️ 예고: {emoji} {name} → ~{intent['est_damage']} 데미지"
    elif action == "type_attack":
        type_name = config.TYPE_NAME_KO.get(intent.get("type", ""), "")
        return f"⚠️ 예고: {emoji} {name}({type_name}) → ~{intent['est_damage']} 데미지!"
    elif action == "charge":
        return f"⚠️ 예고: {emoji} {name} → 이번 턴 공격 없음, 다음 턴 강공격!"
    elif action == "defend":
        return f"⚠️ 예고: {emoji} {name} → 공격해도 효과 낮음"
    elif action == "full_attack":
        return f"⚠️ 예고: {emoji} 전체기! → ~{intent['est_damage']} 데미지! ☠️"
    elif action == "heal":
        return f"⚠️ 예고: {emoji} 회복 → HP +{intent.get('heal', 0)}"
    return f"⚠️ 예고: {name}"


def _enemy_trait(e_stats: dict) -> str:
    """적 성향 한 줄 힌트."""
    atk = max(e_stats.get("atk", 0), e_stats.get("spa", 0))
    dfn = min(e_stats.get("def", 0), e_stats.get("spdef", 0))
    spd = e_stats.get("spd", 0)
    hp = e_stats.get("hp", 0)

    if atk > dfn * 1.5:
        return "💪 공격형 — 공격↑ 방어↓"
    elif dfn > atk * 1.3:
        return "🛡️ 방어형 — 방어↑ 공격↓"
    elif spd > atk and spd > dfn:
        return "💨 속공형 — 속도↑"
    elif hp > atk * 1.5:
        return "❤️ 체력형 — HP↑"
    else:
        return "⚖️ 균형형"


def get_type_hint(player_types: list[str], enemy_types: list[str],
                  skills: list[dict], skill_type_mults: list[float],
                  e_stats: dict | None = None) -> str:
    """상성 팁 + 적 성향 텍스트."""
    type_mult, _ = _type_multiplier(player_types, enemy_types)

    # 적 성향
    trait = _enemy_trait(e_stats) if e_stats else ""

    if type_mult > 1.0:
        best_skill = None
        best_mult = 0
        for i, sk in enumerate(skills):
            if skill_type_mults[i] > best_mult:
                best_mult = skill_type_mults[i]
                best_skill = sk
        hint = f"🔮 상성: 유리! (×{type_mult:.1f})"
        if best_skill and best_mult > 1.0:
            hint += f"\n💡 '{best_skill['name']}' 효과적!"
        if trait:
            hint += f"\n{trait}"
        return hint
    elif type_mult < 1.0:
        hint = f"🔮 상성: 불리 (×{type_mult:.2f})"
        hint += "\n💡 방어 위주로, 일반공격으로 버텨보세요."
        if trait:
            hint += f"\n{trait}"
        return hint
    else:
        hint = "🔮 상성: 보통 (×1.0)"
        if trait:
            hint += f"\n{trait}"
        return hint


# ══════════════════════════════════════════════════════════
# 턴 실행 엔진
# ══════════════════════════════════════════════════════════

def resolve_turn(state: dict, player_action: str) -> dict:
    """플레이어 행동 선택 후 한 턴 실행.

    player_action: "normal" | "skill1" | "skill2" | "defend"

    state를 직접 수정하고, 턴 결과를 반환.
    Returns: {
        "player_line": str,   # 플레이어 행동 결과 텍스트
        "enemy_line": str,    # 적 행동 결과 텍스트
        "extra_lines": list,  # 추가 효과 (부활, 흡혈 등)
        "floor_clear": bool,  # 층 클리어 여부
        "player_dead": bool,  # 플레이어 사망 여부
        "turn_limit": bool,   # 턴 제한 초과 여부
    }
    """
    buffs = state["buffs"]
    p_stats = state["p_stats"]
    e_stats = state["e_stats"]
    e_intent = state["e_intent"]

    # ── 게으름 특성: 짝수 턴에 빈둥빈둥 (방어만 가능) ──
    if state.get("is_truant") and state["turn"] % 2 == 0:
        player_action = "defend"  # 강제 방어

    # 전투 버프 참조
    crit_bonus = get_combat_rate(buffs, "crit")
    double_rate = get_combat_rate(buffs, "double")
    dodge_rate = get_combat_rate(buffs, "dodge")
    thorns_rate = get_combat_rate(buffs, "thorns")
    lifesteal = get_lifesteal_rate(buffs)
    active_syn = {s["id"] for s in _get_active_synergies(buffs)}

    # 선제공격 버프 체크
    has_preemptive = any(b.get("id") == "preemptive" for b in buffs)
    # 관통 버프 체크
    has_penetrate = any(b.get("id") == "penetrate" for b in buffs)
    # 카운터 버프 체크
    counter_rate = 0.0
    for b in buffs:
        if b.get("id") == "counter":
            counter_rate = b["effect"].get("rate", 0.30)

    result = {
        "player_line": "",
        "enemy_line": "",
        "extra_lines": [],
        "floor_clear": False,
        "player_dead": False,
        "turn_limit": False,
    }

    # ── 1. 플레이어 행동 계산 ──
    player_dmg = 0
    player_defending = False
    player_action_name = ""
    player_action_emoji = ""
    pp_used = False

    if player_action == "defend":
        player_defending = True
        player_action_name = "방어"
        player_action_emoji = "🛡️"
        state["highlights"]["defend_used"] += 1
    elif player_action in ("skill1", "skill2"):
        idx = 0 if player_action == "skill1" else 1
        if idx < len(state["skills"]) and idx < len(state["pp"]) and state["pp"][idx]["current"] > 0:
            sk = state["skills"][idx]
            # PP 소모
            state["pp"][idx]["current"] -= 1
            pp_used = True
            state["highlights"]["special_used"] += 1

            # 특수기 데미지: SPA × 1.5 × 타입상성
            atk_val = p_stats["spa"]
            def_val = e_stats["spdef"]
            type_mult = state["skill_type_mults"][idx]
            base = max(int(atk_val * config.DUNGEON_MIN_DMG_RATIO), atk_val - int(def_val * config.DUNGEON_DEF_FACTOR))
            variance = random.uniform(0.9, 1.1)

            # 크리 체크
            effective_crit = config.DUNGEON_CRIT_RATE + crit_bonus
            is_crit = random.random() < effective_crit
            crit_mult = config.DUNGEON_CRIT_MULT if is_crit else 1.0
            if is_crit:
                state["highlights"]["crit"] += 1

            player_dmg = max(1, int(base * config.DUNGEON_SPECIAL_MULT * type_mult * crit_mult * variance))
            player_action_name = sk["name"]
            player_action_emoji = sk["emoji"]

            # 시너지: 풀파워
            if "power" in active_syn:
                player_dmg = int(player_dmg * 1.20)
        else:
            # PP 부족 → 일반공격으로 폴백
            player_action = "normal"

    if player_action == "normal":
        atk_val = p_stats["atk"]
        def_val = e_stats["def"]
        normal_mult = config.DUNGEON_NORMAL_ATK_MULT.get(state["p_rarity"], 1.0)
        base = max(int(atk_val * config.DUNGEON_MIN_DMG_RATIO), atk_val - int(def_val * config.DUNGEON_DEF_FACTOR))
        variance = random.uniform(0.9, 1.1)

        # 크리 체크
        effective_crit = config.DUNGEON_CRIT_RATE + crit_bonus
        is_crit = random.random() < effective_crit
        crit_mult = config.DUNGEON_CRIT_MULT if is_crit else 1.0
        if is_crit:
            state["highlights"]["crit"] += 1

        player_dmg = max(1, int(base * normal_mult * crit_mult * variance))
        player_action_name = "일반공격"
        player_action_emoji = "⚔️"

        # 시너지: 풀파워
        if "power" in active_syn:
            player_dmg = int(player_dmg * 1.20)

    # ── 2. 적 행동 계산 ──
    enemy_dmg = 0
    enemy_action_name = e_intent["name"]
    enemy_action_emoji = e_intent["emoji"]
    e_action = e_intent["action"]

    # 힘 모으기 후 강공격
    if state["e_charged"]:
        e_atk = max(e_stats["atk"], e_stats["spa"])
        enemy_dmg = max(1, int(e_atk * 2.0 * random.uniform(0.9, 1.1)))
        enemy_action_name = "강공격!"
        enemy_action_emoji = "💥"
        state["e_charged"] = False

    elif e_action == "normal_attack":
        e_atk = e_stats["atk"]
        p_def = p_stats["def"]
        base = max(int(e_atk * config.DUNGEON_MIN_DMG_RATIO), e_atk - int(p_def * config.DUNGEON_DEF_FACTOR))
        enemy_dmg = max(1, int(base * 0.8 * random.uniform(0.9, 1.1)))

    elif e_action == "type_attack":
        atk_type = e_intent.get("type", enemy_dmg)
        e_atk = e_stats["spa"]
        p_def = p_stats["spdef"]
        type_mult = _single_type_mult(atk_type, state["p_types"]) if isinstance(atk_type, str) else 1.0
        base = max(int(e_atk * config.DUNGEON_MIN_DMG_RATIO), e_atk - int(p_def * config.DUNGEON_DEF_FACTOR))
        enemy_dmg = max(1, int(base * config.DUNGEON_SPECIAL_MULT * type_mult * random.uniform(0.9, 1.1)))

    elif e_action == "charge":
        state["e_charged"] = True
        enemy_dmg = 0

    elif e_action == "defend":
        state["e_defending"] = True
        enemy_dmg = 0

    elif e_action == "full_attack":
        e_atk = max(e_stats["atk"], e_stats["spa"])
        enemy_dmg = max(1, int(e_atk * 2.0 * random.uniform(0.9, 1.1)))

    elif e_action == "heal":
        heal_amt = int(state["e_max_hp"] * 0.15)
        state["e_hp"] = min(state["e_max_hp"], state["e_hp"] + heal_amt)
        enemy_dmg = 0
        result["enemy_line"] = f"{enemy_action_emoji} 적의 {enemy_action_name}! HP +{heal_amt}"

    # 보스 분노: HP 30% 이하 시 공격력 1.5배
    if state["enemy"]["is_boss"] and state["e_hp"] <= state["e_max_hp"] * 0.3 and not state["e_rage"]:
        state["e_rage"] = True
        state["e_stats"]["atk"] = int(state["e_stats"]["atk"] * 1.5)
        state["e_stats"]["spa"] = int(state["e_stats"]["spa"] * 1.5)
        result["extra_lines"].append("🔥 보스의 분노! 공격력 1.5배!")

    # ── 3. 속도 결정 → 행동 순서 ──
    p_first = p_stats["spd"] >= e_stats["spd"]
    if p_stats["spd"] == e_stats["spd"]:
        p_first = random.random() < 0.5
    if has_preemptive:
        p_first = True

    # ── 4. 순서대로 실행 ──
    def apply_player_attack():
        nonlocal player_dmg
        if player_defending:
            return

        # 적이 방어 중이면 데미지 반감 (관통 버프 무시)
        if state["e_defending"] and not has_penetrate:
            player_dmg = max(1, player_dmg // 2)

        # 시너지: 사신의 낫 — 적 HP 15% 이하 즉사
        if "reaper" in active_syn and state["e_hp"] <= state["e_max_hp"] * 0.15:
            player_dmg = state["e_hp"]

        # 이중타격
        hit_count = 1
        effective_double = double_rate
        if state["highlights"]["crit"] > 0 and "fury" in active_syn:
            effective_double = min(1.0, effective_double * 2)
        if effective_double > 0 and random.random() < effective_double:
            hit_count = 2
            state["highlights"]["double"] += 1

        total_dealt = 0
        for _ in range(hit_count):
            state["e_hp"] -= player_dmg
            total_dealt += player_dmg
            state["total_dmg_dealt"] += player_dmg
            # 흡혈
            if lifesteal > 0:
                heal = int(player_dmg * lifesteal)
                state["p_hp"] = min(state["p_max_hp"], state["p_hp"] + heal)
                state["highlights"]["lifesteal_heal"] += heal

        crit_text = " 💥크리!" if (state["highlights"]["crit"] > 0 and
                                    state["turn"] == state["highlights"]["crit"]) else ""
        # 크리 텍스트 재계산
        is_crit_this = player_action != "defend" and random.random() < 0.001  # already calculated above
        double_text = " (x2!)" if hit_count > 1 else ""
        type_eff = ""
        if player_action in ("skill1", "skill2"):
            idx = 0 if player_action == "skill1" else 1
            if idx < len(state["skill_type_mults"]):
                m = state["skill_type_mults"][idx]
                if m > 1.0:
                    type_eff = " 💥효과발군!"
                elif m < 1.0:
                    type_eff = " 😐효과별로..."

        result["player_line"] = (
            f"{player_action_emoji} {player_action_name}! → {total_dealt}{double_text}{type_eff}"
        )

    def apply_enemy_attack():
        nonlocal enemy_dmg
        if enemy_dmg <= 0:
            if not result["enemy_line"]:
                result["enemy_line"] = f"{enemy_action_emoji} 적의 {enemy_action_name}"
            return

        # 플레이어 방어 중이면 데미지 반감
        if player_defending:
            enemy_dmg = max(1, int(enemy_dmg * config.DUNGEON_DEFEND_REDUCE))

        # 시너지: 철벽요새
        if "iron" in active_syn:
            enemy_dmg = int(enemy_dmg * 0.85)

        # 회피 체크
        if dodge_rate > 0 and random.random() < dodge_rate:
            state["highlights"]["dodge"] += 1
            result["enemy_line"] = f"{enemy_action_emoji} 적의 {enemy_action_name}! → 💨 회피!"
            # 시너지: 잔상
            return

        # 보호막 흡수
        if state["p_shield"] > 0:
            absorbed = min(state["p_shield"], enemy_dmg)
            state["p_shield"] -= absorbed
            enemy_dmg -= absorbed
            state["highlights"]["shield_absorbed"] += absorbed

        state["p_hp"] -= enemy_dmg
        state["total_dmg_taken"] += enemy_dmg

        # 가시갑옷
        if thorns_rate > 0 and enemy_dmg > 0:
            reflect = max(1, int(enemy_dmg * thorns_rate))
            state["e_hp"] -= reflect
            state["total_dmg_dealt"] += reflect
            state["highlights"]["thorns_dmg"] += reflect
            result["extra_lines"].append(f"🌵 가시갑옷! {reflect} 반사!")
            # 시너지: 피의 갑옷
            if "vampire" in active_syn and lifesteal > 0:
                heal = int(reflect * lifesteal)
                state["p_hp"] = min(state["p_max_hp"], state["p_hp"] + heal)
                result["extra_lines"].append(f"🩸 피의 갑옷! +{heal}HP 흡혈!")

        # 방어 중 카운터
        if player_defending and counter_rate > 0 and enemy_dmg > 0:
            counter_dmg = max(1, int(enemy_dmg * counter_rate))
            state["e_hp"] -= counter_dmg
            state["total_dmg_dealt"] += counter_dmg
            result["extra_lines"].append(f"↩️ 카운터! {counter_dmg} 반격!")

        defend_text = " (🛡️방어)" if player_defending else ""
        result["enemy_line"] = (
            f"{enemy_action_emoji} 적의 {enemy_action_name}! → {enemy_dmg}{defend_text}"
        )

    # 실행 순서
    if p_first:
        apply_player_attack()
        if state["e_hp"] > 0:
            apply_enemy_attack()
    else:
        apply_enemy_attack()
        if state["p_hp"] > 0:
            apply_player_attack()

    # 방어 상태 리셋 (이번 턴만)
    state["e_defending"] = False

    # ── 5. 턴 종료 판정 ──
    # 부활 체크
    if state["p_hp"] <= 0 and has_revive(buffs):
        state["p_hp"] = int(state["p_max_hp"] * 0.30)
        state["revive_used"] = True
        result["extra_lines"].append("💫 부활의 깃털 발동! HP 30% 회복")

    # 승패 판정
    if state["e_hp"] <= 0:
        state["won"] = True
        result["floor_clear"] = True
    elif state["p_hp"] <= 0:
        state["won"] = False
        result["player_dead"] = True
    elif state["turn"] >= config.DUNGEON_MAX_TURNS_PER_FLOOR:
        # 턴 제한 초과 → HP 비율 판정
        p_ratio = state["p_hp"] / state["p_max_hp"]
        e_ratio = state["e_hp"] / state["e_max_hp"]
        if p_ratio > e_ratio:
            state["won"] = True
            result["floor_clear"] = True
        else:
            state["won"] = False
            result["player_dead"] = True
        result["turn_limit"] = True

    # 다음 턴 준비 (전투 계속 시)
    if state["won"] is None:
        state["turn"] += 1
        state["e_intent"] = _generate_enemy_intent(state["enemy"], state["floor"])

    return result


# ══════════════════════════════════════════════════════════
# 하위호환 — 자동배틀 (기존 코드 호환용, 추후 삭제)
# ══════════════════════════════════════════════════════════

def resolve_dungeon_battle(
    player_stats: dict,
    player_types: list[str],
    player_rarity: str,
    enemy: dict,
    buffs: list[dict],
    current_hp: int | None = None,
    max_hp: int | None = None,
) -> dict:
    """레거시 자동배틀 — 턴제 UI가 완성될 때까지 폴백용."""
    p_stats = apply_buffs_to_stats(player_stats, buffs)
    e_stats = dict(enemy["stats"])

    p_max_hp = max_hp if max_hp is not None else p_stats["hp"]
    p_hp = current_hp if current_hp is not None else p_max_hp
    e_hp = e_stats["hp"]

    shield_rate = get_shield_rate(buffs)
    p_shield = int(p_max_hp * shield_rate) if shield_rate > 0 else 0
    lifesteal = get_lifesteal_rate(buffs)
    revive_available = has_revive(buffs)
    revive_used = False

    crit_bonus = get_combat_rate(buffs, "crit")
    double_rate = get_combat_rate(buffs, "double")
    dodge_rate = get_combat_rate(buffs, "dodge")
    thorns_rate = get_combat_rate(buffs, "thorns")
    active_syn = {s["id"] for s in _get_active_synergies(buffs)}

    log_lines = []
    total_dmg_dealt = 0
    total_dmg_taken = 0
    _cnt = {"crit": 0, "skill": 0, "dodge": 0, "double": 0,
            "thorns_dmg": 0, "lifesteal_heal": 0, "shield_absorbed": 0}

    type_mult_p, _ = _type_multiplier(player_types, enemy["types"])
    type_mult_e, _ = _type_multiplier(enemy["types"], player_types)

    type_display = ""
    if type_mult_p > 1.0:
        type_display = f"유리! (×{type_mult_p:.1f})"
    elif type_mult_p < 1.0:
        type_display = f"불리 (×{type_mult_p:.2f})"
    else:
        type_display = "보통 (×1.0)"

    turn = 0
    for turn in range(1, config.DUNGEON_MAX_ROUNDS + 1):
        if p_hp <= 0 or e_hp <= 0:
            break

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
            if tag == "enemy" and dodge_rate > 0 and random.random() < dodge_rate:
                _cnt["dodge"] += 1
                continue

            if atk_s["atk"] >= atk_s["spa"]:
                atk_val, def_val = atk_s["atk"], (e_stats["def"] if tag == "player" else p_stats["def"])
            else:
                atk_val, def_val = atk_s["spa"], (e_stats["spdef"] if tag == "player" else p_stats["spdef"])

            base = max(1, atk_val - int(def_val * 0.4))
            effective_crit = config.DUNGEON_CRIT_RATE + (crit_bonus if tag == "player" else 0)
            is_crit = random.random() < effective_crit
            crit_m = config.DUNGEON_CRIT_MULT if is_crit else 1.0
            if is_crit and tag == "player":
                _cnt["crit"] += 1

            skill_on = random.random() < config.DUNGEON_SKILL_RATE
            skill_m = config.DUNGEON_SKILL_MULT.get(rarity, 1.2) if skill_on else 1.0
            if skill_on and tag == "player":
                _cnt["skill"] += 1

            damage = max(1, int(base * t_mult * crit_m * skill_m * random.uniform(0.9, 1.1)))
            if tag == "player" and "power" in active_syn:
                damage = int(damage * 1.20)
            if tag == "enemy" and "iron" in active_syn:
                damage = int(damage * 0.85)

            if tag == "player":
                if "reaper" in active_syn and e_hp <= e_stats["hp"] * 0.15:
                    damage = e_hp
                hit_count = 1
                eff_d = double_rate
                if is_crit and "fury" in active_syn:
                    eff_d = min(1.0, eff_d * 2)
                if eff_d > 0 and random.random() < eff_d:
                    hit_count = 2
                    _cnt["double"] += 1
                for _ in range(hit_count):
                    e_hp -= damage
                    total_dmg_dealt += damage
                    if lifesteal > 0:
                        h = int(damage * lifesteal)
                        p_hp = min(p_max_hp, p_hp + h)
                        _cnt["lifesteal_heal"] += h
            else:
                if p_shield > 0:
                    ab = min(p_shield, damage)
                    p_shield -= ab
                    damage -= ab
                    _cnt["shield_absorbed"] += ab
                p_hp -= damage
                total_dmg_taken += damage
                if thorns_rate > 0 and damage > 0:
                    ref = max(1, int(damage * thorns_rate))
                    e_hp -= ref
                    total_dmg_dealt += ref
                    _cnt["thorns_dmg"] += ref
                    if "vampire" in active_syn and lifesteal > 0:
                        p_hp = min(p_max_hp, p_hp + int(ref * lifesteal))

        if p_hp <= 0 and revive_available:
            p_hp = int(p_max_hp * 0.30)
            revive_available = False
            revive_used = True
            log_lines.append("💫 부활의 깃털 발동! HP 30% 회복 (런당 1회 — 소멸)")

    won = p_hp > 0 and e_hp <= 0
    if p_hp > 0 and e_hp > 0:
        won = (p_hp / p_max_hp) > (e_hp / e_stats["hp"])

    return {
        "won": won, "remaining_hp": max(0, p_hp), "max_hp": p_max_hp,
        "turns": min(turn, config.DUNGEON_MAX_ROUNDS),
        "total_damage_dealt": total_dmg_dealt, "total_damage_taken": total_dmg_taken,
        "type_display": type_display, "type_mult_player": type_mult_p,
        "log": log_lines, "revive_used": revive_used,
        "revive_consumed": revive_used, "highlights": _cnt,
        "type_mult_enemy": type_mult_e,
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
    crystals = 0
    rainbow = 0
    iv_stones = 0
    items: dict[str, int] = {}
    milestones = []

    # 마일스톤 보상 합산
    for milestone_floor, rewards in sorted(config.DUNGEON_MILESTONE_REWARDS.items()):
        if floor_reached >= milestone_floor:
            bp += rewards.get("bp", 0)
            fragments += rewards.get("fragments", 0)
            tickets += rewards.get("tickets", 0)
            crystals += rewards.get("crystals", 0)
            rainbow += rewards.get("rainbow", 0)
            iv_stones += rewards.get("iv_stones", 0)
            for item_type, qty in rewards.get("items", {}).items():
                items[item_type] = items.get(item_type, 0) + qty
            milestones.append(milestone_floor)

    # 구독 배율 — BP는 ×1.5, 나머지(조각/결정/아이템)는 ×2/×3
    if sub_tier == "channel_owner":
        bp_mult, item_mult = 1.5, 3.0
    elif sub_tier == "basic":
        bp_mult, item_mult = 1.2, 2.0
    else:
        bp_mult, item_mult = 1.0, 1.0

    bp = int(bp * bp_mult)
    if item_mult > 1.0:
        fragments = int(fragments * item_mult)
        crystals = int(crystals * item_mult)
        rainbow = int(rainbow * item_mult)
        iv_stones = int(iv_stones * item_mult)
        tickets = int(tickets * item_mult)
        items = {k: max(v, int(v * item_mult + 0.5)) for k, v in items.items()}

    # BP 상한
    bp = min(bp, config.DUNGEON_MAX_BP)

    # 던전 테마 → 캠프 필드 매핑
    field_type = config.DUNGEON_THEME_TO_FIELD.get(theme, "forest")

    # 칭호 체크
    new_titles = []
    for t_floor, (title, emoji) in config.DUNGEON_MILESTONE_TITLES.items():
        if floor_reached >= t_floor:
            new_titles.append({"floor": t_floor, "title": title, "emoji": emoji})

    return {
        "bp": bp,
        "fragments": fragments,
        "tickets": tickets,
        "crystals": crystals,
        "rainbow": rainbow,
        "iv_stones": iv_stones,
        "items": items,
        "field_type": field_type,
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

    # 던전 전용 등급 배율 — BST 하한 도입으로 1.0 통일, 사실상 미적용
    # rmult = config.DUNGEON_RARITY_STAT_MULT.get(rarity, 1.0)

    # 타입
    entry = POKEMON_BASE_STATS.get(pid)
    if entry and len(entry) > 6:
        types = list(entry[6])
    else:
        types = [pokemon.get("pokemon_type", "normal")]

    return stats, types
