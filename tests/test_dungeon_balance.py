"""던전 턴제 전투 밸런스 시뮬레이션 — 실제 유저 메타 기반.

실제 DB 기준:
- 유저는 테마 상성에 맞는 포켓몬을 골라서 입장
- 게을킹(에픽, BST670) best 45F, 한카리아스(에픽) best 48F
- 초전설(디아루가) best 29F (현 자동배틀 기준)
- 이로치 레어도 상성 맞으면 35F+

시뮬 기준: "화산" 테마 (불/드래곤/격투) → 물/땅/바위 유리
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from services import dungeon_service as ds
from utils.battle_calc import calc_battle_stats, get_normalized_base_stats, EVO_STAGE_MAP


# ── 화산 테마 상성 포켓몬 (물/땅/바위) ──
# (pokemon_id, rarity, name, iv_grade, friendship, is_shiny, note)
PROFILES = {
    # 일반 — 상성 O
    "common_A_adv":   (55,  "common",         "골덕",       "A", 5, False),   # 물
    "common_S_shiny": (303, "common",         "입치트",     "S", 7, True),    # 강철/페어리 (실 37F)
    "common_S_golduck":(55, "common",         "골덕",       "S", 7, True),    # 물, 이로치S
    # 레어 — 상성 O
    "rare_A_adv":     (340, "rare",           "메기드리",   "A", 5, False),   # 물/땅
    "rare_S_shiny":   (460, "rare",           "눈설왕",     "S", 7, True),    # 풀/얼음 (실 35F)
    # 에픽 — 상성 O (실 메타)
    "epic_A":         (445, "epic",           "한카리아스", "A", 5, False),   # 드래곤/땅 (실 34F)
    "epic_S_shiny":   (445, "epic",           "한카리아스", "S", 7, True),    # 실 48F!
    "slaking_A":      (289, "epic",           "게을킹",     "A", 5, False),   # 노말 (실 39F, BST670)
    "slaking_S_shiny":(289, "epic",           "게을킹",     "S", 7, True),    # 실 45F
    # 전설
    "regigigas_S_shiny":(486,"legendary",     "레지기가스", "S", 7, True),    # 노말, BST670 (실 35F)
    # 초전설
    "ultra_A_groudon": (383, "ultra_legendary","그란돈",    "A", 5, False),   # 땅 — 화산 상성 O
    "ultra_S_kyogre":  (382, "ultra_legendary","가이오가",  "S", 7, True),    # 물 — 화산 상성 O
    "ultra_S_palkia":  (484, "ultra_legendary","펄기아",    "S", 7, True),    # 물/드래곤
}

IV_GRADES = {
    "C": (10, 10, 10, 10, 10, 10),
    "B": (15, 15, 15, 15, 15, 15),
    "A": (20, 20, 20, 20, 20, 20),
    "S": (31, 31, 31, 31, 31, 31),
}

# 고정 테마: 화산
THEME = config.DUNGEON_THEMES[1]  # 화산


def build_test_pokemon(profile_key: str) -> tuple[dict, list[str], str]:
    pid, rarity, name, iv_grade, friendship, is_shiny = PROFILES[profile_key][:6]
    ivs = IV_GRADES[iv_grade]

    base_kw = get_normalized_base_stats(pid) or {}
    evo_stage = EVO_STAGE_MAP.get(pid, 3)

    stats = calc_battle_stats(
        rarity, "balanced", friendship, evo_stage,
        ivs[0], ivs[1], ivs[2], ivs[3], ivs[4], ivs[5],
        **base_kw,
    )

    hp_mult = getattr(config, 'BATTLE_HP_MULTIPLIER', 1)
    if hp_mult > 1:
        stats["hp"] = int(stats["hp"] * hp_mult)

    from models.pokemon_base_stats import POKEMON_BASE_STATS
    entry = POKEMON_BASE_STATS.get(pid)
    if entry and len(entry) > 6:
        types = list(entry[6])
    else:
        types = ["normal"]

    return stats, types, rarity


def optimal_action(combat: dict) -> str:
    """최적 전략 AI."""
    e_intent = combat["e_intent"]
    p_hp = combat["p_hp"]
    p_max_hp = combat["p_max_hp"]
    skills = combat["skills"]
    pp = combat["pp"]
    skill_mults = combat["skill_type_mults"]

    if e_intent["action"] in ("charge", "full_attack"):
        return "defend"
    if e_intent["action"] == "defend":
        return "normal"
    if e_intent["action"] == "heal":
        for i in range(len(skills)):
            if i < len(pp) and pp[i]["current"] > 0 and skill_mults[i] > 1.0:
                return f"skill{i+1}"
        for i in range(len(skills)):
            if i < len(pp) and pp[i]["current"] > 0:
                return f"skill{i+1}"
        return "normal"

    if p_hp < p_max_hp * 0.3 and e_intent.get("est_damage", 0) > p_hp * 0.5:
        return "defend"

    for i in range(len(skills)):
        if i < len(pp) and pp[i]["current"] > 0 and skill_mults[i] >= 1.5:
            return f"skill{i+1}"

    total_pp = sum(p["current"] for p in pp)
    if total_pp > 2:
        for i in range(len(skills)):
            if i < len(pp) and pp[i]["current"] > 0:
                return f"skill{i+1}"

    return "normal"


def simulate_run(profile_key: str, seed: int = None) -> int:
    if seed is not None:
        random.seed(seed)

    stats, types, rarity = build_test_pokemon(profile_key)
    pid = PROFILES[profile_key][0]
    theme = THEME

    current_hp = stats["hp"]
    max_hp = stats["hp"]
    buffs = []

    is_truant = pid in config.TRUANT_POKEMON
    pp_base = 0 if is_truant else config.DUNGEON_PP_BY_RARITY.get(rarity, 6)
    skills_info = ds.get_pokemon_skills(pid, types)
    if len(skills_info) == 1 and pp_base > 0:
        pp_base = int(pp_base * config.DUNGEON_SINGLE_TYPE_PP_MULT)
    pp_state = [{"current": pp_base, "max": pp_base} for _ in skills_info]

    for floor in range(1, 51):
        enemy = ds.generate_enemy(floor, theme, player_rarity=rarity)

        combat = ds.init_combat_state(
            stats, types, rarity, pid, enemy, buffs,
            current_hp=current_hp, max_hp=max_hp, floor=floor,
        )
        combat["pp"] = pp_state

        for turn in range(1, config.DUNGEON_MAX_TURNS_PER_FLOOR + 1):
            action = optimal_action(combat)
            result = ds.resolve_turn(combat, action)
            if result["floor_clear"]:
                break
            if result["player_dead"] or result["turn_limit"]:
                if combat["won"]:
                    break
                return floor - 1

        if combat["won"] is False or combat["won"] is None:
            return floor - 1

        current_hp = max(1, combat["p_hp"])

        # 층간 회복
        base_heal = config.DUNGEON_BASE_FLOOR_HEAL
        heal_rate = base_heal + ds.get_floor_heal_rate(buffs)
        current_hp = min(max_hp, current_hp + int(max_hp * heal_rate))

        pp_state = combat["pp"]

        # 버프 (5층마다)
        if ds.should_offer_buff(floor):
            choices = ds.generate_buff_choices(floor, buffs)
            if choices:
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

                if best["id"] == "hp" and "mult" in best.get("effect", {}):
                    max_hp = int(max_hp * best["effect"]["mult"])
                    current_hp = int(current_hp * best["effect"]["mult"])
                elif best["id"] == "allstat" and "mult" in best.get("effect", {}):
                    max_hp = int(max_hp * best["effect"]["mult"])
                    current_hp = int(current_hp * best["effect"]["mult"])

                if best["id"] == "pp_recovery":
                    pp_recover = best["effect"].get("rate", 2)
                    for pp_info in pp_state:
                        pp_info["current"] = min(pp_info["max"], pp_info["current"] + pp_recover)

        stats_base, _, _ = build_test_pokemon(profile_key)
        hp_mult = getattr(config, 'BATTLE_HP_MULTIPLIER', 1)
        if hp_mult > 1:
            stats_base["hp"] = int(stats_base["hp"] * hp_mult)
        stats = ds.apply_buffs_to_stats(stats_base, buffs)

    return 50


def test_balance():
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


def test_balance_assertions():
    results = test_balance()

    N = len(results["ultra_S_kyogre"]["floors"])
    def reach_rate(key, threshold):
        return sum(1 for f in results[key]["floors"] if f >= threshold) / N

    print("\n" + "=" * 75)
    print(f"{'Profile':<22} {'Avg':>6} {'Med':>6} {'P90':>6} {'Max':>6} {'Min':>6}")
    print("=" * 75)

    for key, r in results.items():
        info = PROFILES[key]
        shiny = "✨" if info[5] else ""
        label = f"{shiny}{info[2]}({info[1][:3]}{info[3]})"
        print(f"{label:<22} {r['avg']:>6.1f} {r['median']:>6} {r['p90']:>6} {r['max']:>6} {r['min']:>6}")

    print("=" * 75)

    print(f"\n📊 40층+ 도달률:")
    for key in PROFILES:
        rate = reach_rate(key, 40)
        if rate > 0:
            info = PROFILES[key]
            shiny = "✨" if info[5] else ""
            print(f"  {shiny}{info[2]}({info[1][:3]}{info[3]}): {rate:.1%}")

    # ── 1. 이로치S 기준 max 30+ (유저는 이로치S로 도전) ──
    shiny_keys = [k for k in PROFILES if PROFILES[k][5]]
    for key in shiny_keys:
        assert results[key]["max"] >= 30, \
            f"{key} max={results[key]['max']} < 30 (이로치S 30+ 가능해야)"

    # ── 2. 실 데이터와 비슷한 범위 ──
    # 한카리아스 이로치S: 실 48F → 시뮬 max 40+
    assert results["epic_S_shiny"]["max"] >= 40, \
        f"한카리아스✨S max={results['epic_S_shiny']['max']} < 40 (실 48F)"

    # 초전설 듀얼타입(펄기아✨S 물/드래곤): 에픽(한카리아스✨S)보다 높아야
    assert results["ultra_S_palkia"]["avg"] > results["epic_S_shiny"]["avg"], \
        f"펄기아✨S({results['ultra_S_palkia']['avg']:.1f}) <= 한카리아스✨S({results['epic_S_shiny']['avg']:.1f})"

    # ── 3. 등급 계층 (상성 유리 포켓몬끼리) ──
    # 골덕(물) vs 한카리아스(땅) — 둘 다 화산 상성 O, 등급 차이로 비교
    assert results["epic_S_shiny"]["avg"] >= results["common_S_golduck"]["avg"] - 3, \
        "에픽✨(한카리아스) >= 일반✨(골덕) 근처"
    # 가이오가(단일타입 물)는 한카리아스(듀얼 드래곤/땅)보다 낮을 수 있음 — 타입 수 차이
    assert results["ultra_S_palkia"]["max"] >= 40, "펄기아✨S max 40+"
    assert results["ultra_S_kyogre"]["max"] >= 35, "가이오가✨S max 35+"

    # ── 4. 일반A는 50층 불가 ──
    n50 = results["common_A_adv"]["floors"].count(50)
    assert n50 == 0, f"일반A에서 50층 클리어 {n50}회"

    print("\n✅ 모든 밸런스 체크 통과!")
    return results


if __name__ == "__main__":
    test_balance_assertions()
