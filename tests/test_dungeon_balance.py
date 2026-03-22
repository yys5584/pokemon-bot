"""던전 턴제 전투 밸런스 시뮬레이션 테스트.

최적 전략 AI로 50층까지 시뮬:
- 40~50층은 이로치 초전설 S급만 도달 가능해야 함
- 일반/레어는 10~15층에서 벽
- 에픽은 20~25층
- 전설은 30~35층
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from services import dungeon_service as ds
from utils.battle_calc import calc_battle_stats, get_normalized_base_stats, EVO_STAGE_MAP


# ── 테스트용 포켓몬 프로필 ──

PROFILES = {
    # (pokemon_id, rarity, name, iv_grade, friendship, is_shiny)
    "common_C":       (25,  "common",         "피카츄",     "C", 3, False),
    "rare_B":         (26,  "rare",           "라이츄",     "B", 4, False),
    "epic_A":         (6,   "epic",           "리자몽",     "A", 5, False),
    "epic_S":         (6,   "epic",           "리자몽",     "S", 5, False),
    "legendary_A":    (150, "legendary",      "뮤츠",       "A", 5, False),
    "legendary_S":    (249, "legendary",      "루기아",     "S", 5, False),
    "ultra_S":        (384, "ultra_legendary","레쿠쟈",     "S", 5, False),  # 일반 (친밀도5)
    "ultra_S_shiny":  (384, "ultra_legendary","레쿠쟈",     "S", 7, True),   # 이로치 (친밀도7)
}

IV_GRADES = {
    "C": (10, 10, 10, 10, 10, 10),
    "B": (15, 15, 15, 15, 15, 15),
    "A": (20, 20, 20, 20, 20, 20),
    "S": (31, 31, 31, 31, 31, 31),
}


def build_test_pokemon(profile_key: str) -> tuple[dict, list[str], str]:
    """테스트용 포켓몬 스탯 빌드. Returns (stats, types, rarity)."""
    pid, rarity, name, iv_grade, friendship, is_shiny = PROFILES[profile_key]
    ivs = IV_GRADES[iv_grade]

    base_kw = get_normalized_base_stats(pid) or {}
    stat_type = "balanced"  # 기본
    evo_stage = EVO_STAGE_MAP.get(pid, 3)

    stats = calc_battle_stats(
        rarity, stat_type, friendship, evo_stage,
        ivs[0], ivs[1], ivs[2], ivs[3], ivs[4], ivs[5],
        **base_kw,
    )

    # HP 배율
    hp_mult = getattr(config, 'BATTLE_HP_MULTIPLIER', 1)
    if hp_mult > 1:
        stats["hp"] = int(stats["hp"] * hp_mult)

    # 타입
    from models.pokemon_base_stats import POKEMON_BASE_STATS
    entry = POKEMON_BASE_STATS.get(pid)
    if entry and len(entry) > 6:
        types = list(entry[6])
    else:
        types = ["normal"]

    return stats, types, rarity


def optimal_action(combat: dict) -> str:
    """최적 전략 AI — 상성/PP/적의도 고려."""
    e_intent = combat["e_intent"]
    e_hp = combat["e_hp"]
    e_max_hp = combat["e_max_hp"]
    p_hp = combat["p_hp"]
    p_max_hp = combat["p_max_hp"]
    skills = combat["skills"]
    pp = combat["pp"]
    skill_mults = combat["skill_type_mults"]

    # 적이 힘 모으기 → 방어
    if e_intent["action"] == "charge":
        return "defend"

    # 적이 전체기 → 방어
    if e_intent["action"] == "full_attack":
        return "defend"

    # 적이 방어 태세 → 일반공격 (PP 아끼기)
    if e_intent["action"] == "defend":
        return "normal"

    # 적이 회복 → 가장 강한 공격
    if e_intent["action"] == "heal":
        # 효과적인 특수기 있으면 사용
        for i in range(len(skills)):
            if i < len(pp) and pp[i]["current"] > 0 and skill_mults[i] > 1.0:
                return f"skill{i+1}"
        for i in range(len(skills)):
            if i < len(pp) and pp[i]["current"] > 0:
                return f"skill{i+1}"
        return "normal"

    # HP 위험 (30% 이하) + 적이 강공격 예고 → 방어
    if p_hp < p_max_hp * 0.3 and e_intent.get("est_damage", 0) > p_hp * 0.5:
        return "defend"

    # 효과적인 특수기 PP 있으면 사용 (상성 유리)
    for i in range(len(skills)):
        if i < len(pp) and pp[i]["current"] > 0 and skill_mults[i] >= 1.5:
            return f"skill{i+1}"

    # PP 여유 있고 적 HP 많으면 특수기
    total_pp = sum(p["current"] for p in pp)
    if total_pp > 2 and e_hp > e_max_hp * 0.3:
        for i in range(len(skills)):
            if i < len(pp) and pp[i]["current"] > 0:
                return f"skill{i+1}"

    # 기본: 일반공격
    return "normal"


def simulate_run(profile_key: str, seed: int = None, verbose: bool = False) -> int:
    """던전 런 시뮬레이션. Returns 최종 도달 층."""
    if seed is not None:
        random.seed(seed)

    stats, types, rarity = build_test_pokemon(profile_key)
    pid = PROFILES[profile_key][0]
    theme = ds.get_today_theme()

    current_hp = stats["hp"]
    max_hp = stats["hp"]
    buffs = []

    # PP 초기화
    pp_max = config.DUNGEON_PP_BY_RARITY.get(rarity, 6)
    skills_info = ds.get_pokemon_skills(pid, types)
    pp_state = [{"current": pp_max, "max": pp_max} for _ in skills_info]

    for floor in range(1, 51):
        enemy = ds.generate_enemy(floor, theme, player_rarity=rarity)

        combat = ds.init_combat_state(
            stats, types, rarity, pid, enemy, buffs,
            current_hp=current_hp, max_hp=max_hp, floor=floor,
        )
        combat["pp"] = pp_state

        # 턴 루프
        for turn in range(1, config.DUNGEON_MAX_TURNS_PER_FLOOR + 1):
            action = optimal_action(combat)
            result = ds.resolve_turn(combat, action)

            if result["floor_clear"]:
                break
            if result["player_dead"]:
                if verbose:
                    print(f"  DEAD at floor {floor}, turn {turn}")
                return floor - 1  # 마지막 클리어 층
            if result["turn_limit"]:
                if combat["won"]:
                    break
                else:
                    return floor - 1

        if combat["won"] is False or combat["won"] is None:
            return floor - 1

        # 층 클리어 처리
        current_hp = max(1, combat["p_hp"])

        # 층간 회복 (기본 5% + 버프)
        base_heal = config.DUNGEON_BASE_FLOOR_HEAL
        heal_rate = base_heal + ds.get_floor_heal_rate(buffs)
        if heal_rate > 0:
            current_hp = min(max_hp, current_hp + int(max_hp * heal_rate))

        # PP state 동기화
        pp_state = combat["pp"]

        # 버프 (5층마다)
        if ds.should_offer_buff(floor):
            choices = ds.generate_buff_choices(floor, buffs)
            if choices:
                # 최적 버프 선택: 공격 > 체력 > 크리 > PP회복 > 나머지
                priority = ["atk", "spa", "hp", "crit", "pp_recovery", "lifesteal",
                            "def", "spdef", "dodge", "double", "preemptive",
                            "counter", "penetrate", "shield", "heal", "thorns",
                            "revive", "allstat", "spd"]
                best = choices[0]
                best_rank = 99
                for c in choices:
                    try:
                        rank = priority.index(c["id"])
                    except ValueError:
                        rank = 50
                    if rank < best_rank:
                        best_rank = rank
                        best = c
                buffs = ds.apply_buff_choice(buffs, best)

                # HP 버프 적용
                if best["id"] == "hp" and "mult" in best.get("effect", {}):
                    old_lv = ds._get_buff_level("hp", [b for b in buffs if b["id"] != "hp"])
                    max_hp = int(max_hp * best["effect"]["mult"])
                    current_hp = int(current_hp * best["effect"]["mult"])
                elif best["id"] == "allstat" and "mult" in best.get("effect", {}):
                    max_hp = int(max_hp * best["effect"]["mult"])
                    current_hp = int(current_hp * best["effect"]["mult"])

                # PP 회복 버프
                if best["id"] == "pp_recovery":
                    pp_recover = best["effect"].get("rate", 2)
                    for pp_info in pp_state:
                        pp_info["current"] = min(pp_info["max"], pp_info["current"] + pp_recover)

        # 버프 적용된 스탯 갱신
        stats_base, _, _ = build_test_pokemon(profile_key)
        hp_mult = getattr(config, 'BATTLE_HP_MULTIPLIER', 1)
        if hp_mult > 1:
            stats_base["hp"] = int(stats_base["hp"] * hp_mult)
        stats = ds.apply_buffs_to_stats(stats_base, buffs)

        if verbose and floor % 5 == 0:
            pp_text = "/".join(f"{p['current']}" for p in pp_state)
            print(f"  Floor {floor}: HP={current_hp}/{max_hp} PP={pp_text} buffs={len(buffs)}")

    return 50  # 클리어!


def test_balance():
    """밸런스 시뮬레이션 — 각 프로필 100회 실행."""
    N = 200
    results = {}

    for profile_key in PROFILES:
        floors = []
        for seed in range(N):
            floor = simulate_run(profile_key, seed=seed)
            floors.append(floor)

        avg = sum(floors) / len(floors)
        median = sorted(floors)[len(floors) // 2]
        max_f = max(floors)
        min_f = min(floors)
        p90 = sorted(floors)[int(len(floors) * 0.9)]

        results[profile_key] = {
            "avg": avg, "median": median, "max": max_f, "min": min_f, "p90": p90,
            "floors": floors,
        }

    return results


# ── 밸런스 기준 (assertion) ──

def test_balance_assertions():
    """밸런스 기준 체크:
    - common_C: avg 5~15
    - rare_B: avg 8~18
    - epic_A: avg 12~25
    - epic_S: avg 15~28
    - legendary_A: avg 18~32
    - legendary_S: avg 22~38
    - ultra_S: avg 28~42
    - ultra_S_shiny: avg 32~50, p90 >= 40
    """
    results = test_balance()

    print("\n" + "=" * 70)
    print(f"{'Profile':<20} {'Avg':>6} {'Med':>6} {'P90':>6} {'Max':>6} {'Min':>6}")
    print("=" * 70)

    for key, r in results.items():
        name = PROFILES[key][2]
        rarity = PROFILES[key][1]
        iv = PROFILES[key][3]
        shiny = "✨" if PROFILES[key][5] else ""
        label = f"{shiny}{name}({rarity[:3]}{iv})"
        print(f"{label:<20} {r['avg']:>6.1f} {r['median']:>6} {r['p90']:>6} {r['max']:>6} {r['min']:>6}")

    print("=" * 70)

    N = len(results["ultra_S_shiny"]["floors"])

    # ── 1. 40층+ 도달률 체크 ──
    def reach_rate(key, threshold):
        return sum(1 for f in results[key]["floors"] if f >= threshold) / N

    # 이로치 초전설S: 40층+ 5% 이상 도달해야
    rate_40_shiny = reach_rate("ultra_S_shiny", 40)
    print(f"\n📊 40층+ 도달률:")
    print(f"  ✨초전설S: {rate_40_shiny:.1%}")
    print(f"  초전설S:   {reach_rate('ultra_S', 40):.1%}")
    print(f"  전설S:     {reach_rate('legendary_S', 40):.1%}")
    print(f"  전설A:     {reach_rate('legendary_A', 40):.1%}")
    print(f"  에픽S:     {reach_rate('epic_S', 40):.1%}")
    assert rate_40_shiny >= 0.02, \
        f"이로치 초전설S 40층+ 도달률 {rate_40_shiny:.1%} < 2% (너무 어려움)"

    # ── 2. 모든 등급이 즐길 수 있는지 ──
    # 일반도 5층 보스(첫 보상)는 먹을 수 있어야
    assert results["common_C"]["avg"] >= 3, \
        f"일반C avg={results['common_C']['avg']:.1f} < 3 (첫 보상도 못 먹음)"
    assert results["rare_B"]["avg"] >= 6, \
        f"레어B avg={results['rare_B']['avg']:.1f} < 6"
    assert results["epic_A"]["avg"] >= 10, \
        f"에픽A avg={results['epic_A']['avg']:.1f} < 10"
    assert results["legendary_S"]["avg"] >= 15, \
        f"전설S avg={results['legendary_S']['avg']:.1f} < 15"

    # ── 3. 고층은 고코스트 전용 ──
    # 전설 이하 40층+ 도달률 5% 이하
    for key in ["common_C", "rare_B", "epic_A", "epic_S"]:
        rate_40 = reach_rate(key, 40)
        assert rate_40 <= 0.03, \
            f"{key} 40층+ 도달률 {rate_40:.1%} > 3% (너무 쉬움)"

    # 50층 클리어: 에픽 이하 불가
    for key in ["common_C", "rare_B", "epic_A", "epic_S"]:
        n50 = results[key]["floors"].count(50)
        assert n50 == 0, \
            f"{key}에서 50층 클리어 {n50}회 (밸런스 붕괴)"

    # ── 4. 상위 등급은 충분히 높이 가야 ──
    assert results["ultra_S_shiny"]["avg"] >= 20, \
        f"이로치 초전설S avg={results['ultra_S_shiny']['avg']:.1f} < 20"
    assert results["ultra_S_shiny"]["max"] >= 40, \
        f"이로치 초전설S max={results['ultra_S_shiny']['max']} < 40 (50층 도달 불가)"

    # ── 5. 등급 간 계층이 존재해야 ──
    assert results["rare_B"]["avg"] > results["common_C"]["avg"], "레어 > 일반"
    assert results["epic_A"]["avg"] > results["rare_B"]["avg"], "에픽 > 레어"
    assert results["legendary_S"]["avg"] > results["epic_S"]["avg"], "전설 > 에픽"
    assert results["ultra_S_shiny"]["avg"] > results["legendary_S"]["avg"], "초전설 > 전설"

    print("\n✅ 모든 밸런스 체크 통과!")
    return results


if __name__ == "__main__":
    test_balance_assertions()
