"""던전 턴제 전투 밸런스 시뮬레이션 — 전 등급 상성 매칭.

모든 테마 × 상성 맞는 포켓몬으로 시뮬.
던전 전용 등급 배율(DUNGEON_RARITY_STAT_MULT) 적용.
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from services import dungeon_service as ds
from utils.battle_calc import calc_battle_stats, get_normalized_base_stats, EVO_STAGE_MAP
from models.pokemon_data import ALL_POKEMON
from models.pokemon_base_stats import POKEMON_BASE_STATS

# 던전 전용 등급 배율 — BST 하한 도입으로 1.0 통일
DUNGEON_RARITY_STAT_MULT = {
    "common": 1.0, "rare": 1.0, "epic": 1.0,
    "legendary": 1.0, "ultra_legendary": 1.0,
}

# ── 테마별 상성 타입 ──
THEME_ADVANTAGE = {}
for theme in config.DUNGEON_THEMES:
    THEME_ADVANTAGE[theme["name"]] = set(theme["advantage"])


def get_pokemon_types(pid):
    entry = POKEMON_BASE_STATS.get(pid)
    if entry and len(entry) > 6:
        return list(entry[6])
    return ["normal"]


def pokemon_matches_theme(pid, theme_name):
    """포켓몬이 테마 상성에 맞는지."""
    types = set(get_pokemon_types(pid))
    adv = THEME_ADVANTAGE.get(theme_name, set())
    return bool(types & adv)


def build_pokemon_stats(pid, rarity, iv_grade="S", friendship=7):
    """던전용 스탯 빌드 (등급 배율 적용)."""
    ivs = {"S": 31, "A": 20, "B": 15, "C": 10}
    iv = ivs.get(iv_grade, 20)

    base_kw = get_normalized_base_stats(pid) or {}
    evo = EVO_STAGE_MAP.get(pid, 3)
    stats = calc_battle_stats(
        rarity, "balanced", friendship, evo,
        iv, iv, iv, iv, iv, iv, **base_kw,
    )
    hp_mult = getattr(config, 'BATTLE_HP_MULTIPLIER', 1)
    if hp_mult > 1:
        stats["hp"] = int(stats["hp"] * hp_mult)

    # 던전 등급 배율
    rmult = DUNGEON_RARITY_STAT_MULT.get(rarity, 1.0)
    if rmult != 1.0:
        stats = {k: int(v * rmult) for k, v in stats.items()}

    types = get_pokemon_types(pid)
    return stats, types


def optimal_action(combat):
    e_intent = combat["e_intent"]
    p_hp, p_max_hp = combat["p_hp"], combat["p_max_hp"]
    skills, pp = combat["skills"], combat["pp"]
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


def simulate_run(pid, rarity, theme, seed=None, iv_grade="S", friendship=7):
    if seed is not None:
        random.seed(seed)

    stats, types = build_pokemon_stats(pid, rarity, iv_grade, friendship)
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
        heal_rate = config.DUNGEON_BASE_FLOOR_HEAL + ds.get_floor_heal_rate(buffs)
        current_hp = min(max_hp, current_hp + int(max_hp * heal_rate))
        pp_state = combat["pp"]

        if ds.should_offer_buff(floor):
            choices = ds.generate_buff_choices(floor, buffs)
            if choices:
                priority = ["atk", "spa", "hp", "crit", "pp_recovery", "lifesteal",
                            "def", "spdef", "dodge", "double", "preemptive",
                            "counter", "penetrate", "shield", "heal", "thorns",
                            "revive", "allstat", "spd"]
                best = min(choices, key=lambda c: priority.index(c["id"]) if c["id"] in priority else 50)
                buffs = ds.apply_buff_choice(buffs, best)
                if best["id"] == "hp" and "mult" in best.get("effect", {}):
                    max_hp = int(max_hp * best["effect"]["mult"])
                    current_hp = int(current_hp * best["effect"]["mult"])
                elif best["id"] == "allstat" and "mult" in best.get("effect", {}):
                    max_hp = int(max_hp * best["effect"]["mult"])
                    current_hp = int(current_hp * best["effect"]["mult"])
                if best["id"] == "pp_recovery":
                    for pp_info in pp_state:
                        pp_info["current"] = min(pp_info["max"], pp_info["current"] + best["effect"].get("rate", 2))

        stats_base, _ = build_pokemon_stats(pid, rarity, iv_grade, friendship)
        stats = ds.apply_buffs_to_stats(stats_base, buffs)

    return 50


def find_best_pokemon_per_theme():
    """각 테마 × 등급별 상성 맞는 포켓몬 찾기."""
    result = {}
    for theme in config.DUNGEON_THEMES:
        theme_name = theme["name"]
        by_rarity = {}
        for p in ALL_POKEMON:
            pid, name, _, _, rarity = p[0], p[1], p[2], p[3], p[4]
            if not pokemon_matches_theme(pid, theme_name):
                continue
            bs = POKEMON_BASE_STATS.get(pid)
            if not bs:
                continue
            bst = sum(bs[:6])
            by_rarity.setdefault(rarity, []).append((pid, name, bst))

        # 등급별 BST 상위 1개
        picks = {}
        for rarity in ["common", "rare", "epic", "legendary", "ultra_legendary"]:
            candidates = by_rarity.get(rarity, [])
            if candidates:
                candidates.sort(key=lambda x: x[2], reverse=True)
                picks[rarity] = candidates[0]  # BST 최고
        result[theme_name] = picks
    return result


def main():
    N = 100
    theme_picks = find_best_pokemon_per_theme()

    print("=" * 85)
    print(f"{'테마':<8} {'등급':<8} {'포켓몬':<12} {'BST':>4} {'타입':<14} {'avg':>6} {'med':>6} {'p90':>6} {'max':>5}")
    print("=" * 85)

    all_results = {}

    for theme in config.DUNGEON_THEMES:
        tname = theme["name"]
        picks = theme_picks[tname]

        for rarity in ["common", "rare", "epic", "legendary", "ultra_legendary"]:
            if rarity not in picks:
                continue
            pid, pname, bst = picks[rarity]
            types = get_pokemon_types(pid)
            type_str = "/".join(types)

            # 이로치S 기준
            floors = [simulate_run(pid, rarity, theme, seed=s, iv_grade="S", friendship=7) for s in range(N)]
            avg = sum(floors) / len(floors)
            med = sorted(floors)[len(floors) // 2]
            p90 = sorted(floors)[int(len(floors) * 0.9)]
            max_f = max(floors)

            key = f"{tname}_{rarity}"
            all_results[key] = {"avg": avg, "med": med, "p90": p90, "max": max_f,
                                "name": pname, "rarity": rarity, "theme": tname}

            truant = " [T]" if pid in config.TRUANT_POKEMON else ""
            rar_short = {"common": "com", "rare": "rar", "epic": "epi",
                         "legendary": "leg", "ultra_legendary": "ult"}[rarity]
            print(f"{tname:<8} {rar_short:<8} {pname:<12} {bst:>4} {type_str:<14} {avg:>6.1f} {med:>6} {p90:>6} {max_f:>5}{truant}")

        print("-" * 85)

    # ── 등급별 평균 요약 ──
    print()
    print("=== 등급별 전체 평균 (이로치S, 상성 맞는 최적 포켓몬) ===")
    for rarity in ["common", "rare", "epic", "legendary", "ultra_legendary"]:
        vals = [v for k, v in all_results.items() if v["rarity"] == rarity]
        if vals:
            total_avg = sum(v["avg"] for v in vals) / len(vals)
            total_max = max(v["max"] for v in vals)
            total_p90 = sum(v["p90"] for v in vals) / len(vals)
            rar_ko = {"common": "일반", "rare": "레어", "epic": "에픽",
                      "legendary": "전설", "ultra_legendary": "초전설"}[rarity]
            # 40층+, 50층 도달률
            all_floors = []
            for v in vals:
                # 각 테마의 개별 런 결과가 없으므로 avg/p90/max로 추정
                pass
            print(f"  {rar_ko:<6} avg={total_avg:>5.1f}  p90={total_p90:>5.1f}  max={total_max:>3}")

    # 40/50층 도달률 (테마별 개별 데이터)
    print()
    print("=== 40층+/50층 도달률 ===")
    for rarity in ["common", "rare", "epic", "legendary", "ultra_legendary"]:
        keys = [k for k in all_results if all_results[k]["rarity"] == rarity]
        # p90이 40 이상이면 ~10%가 40층+
        vals = [all_results[k] for k in keys]
        if vals:
            avg_p90 = sum(v["p90"] for v in vals) / len(vals)
            n50 = sum(1 for v in vals if v["max"] >= 50)
            rar_ko = {"common": "일반", "rare": "레어", "epic": "에픽",
                      "legendary": "전설", "ultra_legendary": "초전설"}[rarity]
            rate_40 = "~10%+" if avg_p90 >= 40 else "~5-10%" if avg_p90 >= 35 else "<5%"
            print(f"  {rar_ko:<6} 40층+: {rate_40}  50층: {n50}/{len(vals)} 테마")

    # ── 밸런스 체크 ──
    print()
    rarity_avgs = {}
    for rarity in ["common", "rare", "epic", "legendary", "ultra_legendary"]:
        vals = [v["avg"] for k, v in all_results.items() if v["rarity"] == rarity]
        if vals:
            rarity_avgs[rarity] = sum(vals) / len(vals)

    checks_passed = True
    # 등급 계층
    pairs = [("common", "rare"), ("rare", "epic"), ("epic", "legendary"), ("legendary", "ultra_legendary")]
    for lower, higher in pairs:
        if lower in rarity_avgs and higher in rarity_avgs:
            if rarity_avgs[higher] <= rarity_avgs[lower]:
                print(f"  ❌ {higher}({rarity_avgs[higher]:.1f}) <= {lower}({rarity_avgs[lower]:.1f})")
                checks_passed = False
            else:
                gap = rarity_avgs[higher] - rarity_avgs[lower]
                print(f"  ✅ {higher}({rarity_avgs[higher]:.1f}) > {lower}({rarity_avgs[lower]:.1f}) [+{gap:.1f}]")

    if checks_passed:
        print("\n✅ 모든 밸런스 체크 통과!")
    else:
        print("\n❌ 밸런스 체크 실패")
        sys.exit(1)


if __name__ == "__main__":
    main()
