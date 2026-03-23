"""
Dungeon Turn-Based Combat Balance Simulation
=============================================
Simulates 1000+ dungeon runs per rarity tier to check balance.
Uses the ACTUAL damage formulas, HP scaling, buff system from codebase.

Usage: python scripts/sim_dungeon_balance.py
"""

import sys, os, random, statistics, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from utils.battle_calc import (
    calc_battle_stats, get_normalized_base_stats, EVO_STAGE_MAP,
)
from services.dungeon_service import (
    enemy_scaling, generate_enemy, BUFF_DEFS, SYNERGIES,
    apply_buffs_to_stats, get_shield_rate, get_lifesteal_rate,
    get_combat_rate, has_revive, _get_active_synergies,
    _type_multiplier, _single_type_mult, _generate_enemy_intent,
    generate_buff_choices, apply_buff_choice, should_offer_buff,
    get_floor_heal_rate, generate_roguelike_event, apply_roguelike_event,
    consume_rogue_buffs, init_combat_state, resolve_turn,
    get_pokemon_skills,
)
from models.pokemon_data import ALL_POKEMON
from models.pokemon_base_stats import POKEMON_BASE_STATS

# ─── Representative Pokemon per rarity (final evolution, strong picks) ───

# Build rarity -> list of final-evo pokemon with base stats
RARITY_POKEMON = {}
for p in ALL_POKEMON:
    pid, name_ko, _, _, rarity, _, evolves_from, evolves_to, _ = p
    if pid not in POKEMON_BASE_STATS:
        continue
    evo_stage = EVO_STAGE_MAP.get(pid, 3)
    if evo_stage < 3:
        continue  # only final evolutions
    RARITY_POKEMON.setdefault(rarity, []).append(pid)

# Pick ~5 representative strong pokemon per rarity for simulation
def get_bst(pid):
    stats = POKEMON_BASE_STATS[pid]
    return sum(stats[:6])

REPRESENTATIVE = {}
for rarity in ["common", "rare", "epic", "legendary", "ultra_legendary"]:
    pool = RARITY_POKEMON.get(rarity, [])
    # Sort by BST descending, pick top 5
    pool_sorted = sorted(pool, key=get_bst, reverse=True)
    REPRESENTATIVE[rarity] = pool_sorted[:5] if len(pool_sorted) >= 5 else pool_sorted

# ─── Simulation parameters ───

NUM_RUNS = 1000
MAX_FLOOR = 55  # simulate up to floor 55
FRIENDSHIP = 5  # max friendship
IV_GOOD = 31    # 이로치 S급 7풀강 (올맥스)
IV_AVG = 20     # average IVs

# Theme: use a balanced theme (volcano - fire/dragon/fighting)
THEME = {"name": "화산", "emoji": "🔥", "types": ["fire", "dragon", "fighting"],
         "advantage": ["water", "ground", "rock"], "bonus": "water"}


def build_player_stats(pid, rarity, friendship=5, iv=15):
    """Build player stats using the actual calc_battle_stats."""
    base_kw = get_normalized_base_stats(pid) or {}
    evo_stage = EVO_STAGE_MAP.get(pid, 3)
    stats = calc_battle_stats(
        rarity, "balanced", friendship, evo_stage,
        iv, iv, iv, iv, iv, iv,
        **base_kw,
    )
    return stats


def get_player_types(pid):
    entry = POKEMON_BASE_STATS.get(pid)
    if entry and len(entry) > 6:
        return entry[6]
    # fallback from ALL_POKEMON
    for p in ALL_POKEMON:
        if p[0] == pid:
            t = p[5]
            return [t] if isinstance(t, str) else t
    return ["normal"]


def get_pp_max(rarity, types):
    if len(types) >= 2:
        return config.DUNGEON_DUAL_TYPE_PP  # 5
    return config.DUNGEON_PP_BY_RARITY.get(rarity, 6)


# ─── AI Player Logic ───

def ai_choose_action(state):
    """실제 유저 플레이 모방:
    - 강공격/차지 → 무조건 방어
    - HP 30% 이하 + 적 공격 예고 → 방어 (생존 우선)
    - HP 50% 이하 + 적 일반공격 → 50% 확률 방어
    - 적 방어/힐 → 일반공격 (PP 아끼기)
    - 그 외 → 스킬 적극 사용
    """
    e_intent = state["e_intent"]
    e_action = e_intent["action"]
    is_charged = state["e_charged"]
    hp_ratio = state["p_hp"] / state["p_max_hp"] if state["p_max_hp"] > 0 else 1.0

    # 강공격/차지 후속 → 무조건 방어
    if is_charged or e_action == "full_attack":
        return "defend"

    # HP 30% 이하 + 적 공격 → 방어 우선
    if hp_ratio <= 0.3 and e_action in ("normal_attack", "type_attack"):
        return "defend"

    # HP 50% 이하 + 적 일반공격 → 50% 확률 방어
    if hp_ratio <= 0.5 and e_action == "normal_attack":
        if random.random() < 0.5:
            return "defend"

    # 적 차지 중 → 무료 공격 기회
    if e_action == "charge":
        return _best_skill_or_normal(state)

    # 적 방어 → 일반공격 (PP 아끼기)
    if e_action == "defend":
        return "normal"

    # 적 힐 → 강한 공격
    if e_action == "heal":
        return _best_skill_or_normal(state)

    # 그 외 → 스킬 적극 사용
    return _best_skill_or_normal(state)


def _best_skill_or_normal(state):
    """유저처럼 스킬 적극 사용. PP 1 이하일 때만 일반공격."""
    best_idx = -1
    best_mult = 0

    for i, sk in enumerate(state["skills"]):
        if i < len(state["pp"]) and state["pp"][i]["current"] > 0:
            mult = state["skill_type_mults"][i]
            if mult > best_mult:
                best_mult = mult
                best_idx = i

    # 상성 유리 → 무조건 스킬
    if best_idx >= 0 and best_mult >= 1.5:
        return f"skill{best_idx + 1}"

    # 상성 보통 이상 → PP 2 이상이면 스킬
    if best_idx >= 0 and best_mult >= 1.0:
        if state["pp"][best_idx]["current"] >= 2:
            return f"skill{best_idx + 1}"

    # 상성 불리해도 PP 여유 있으면 스킬 (유저는 이렇게 함)
    if best_idx >= 0 and state["pp"][best_idx]["current"] >= 3:
        return f"skill{best_idx + 1}"

    return "normal"


# ─── AI Buff Selection ───

def ai_choose_buff(choices, current_buffs, floor):
    """Smart buff selection priority:
    1. Offensive: atk, spa (early), crit, double
    2. Survival: lifesteal/heal/shield (one of them)
    3. Utility: dodge, thorns, allstat, preemptive, penetrate
    """
    priority = [
        "atk", "spa", "crit", "lifesteal", "double", "allstat",
        "hp", "def", "spdef", "dodge", "thorns", "preemptive",
        "penetrate", "counter", "pp_recovery", "shield", "heal",
        "spd", "revive",
    ]

    # Prefer upgrades for already-owned buffs
    best = None
    best_score = 999

    for c in choices:
        bid = c["id"]
        if bid in priority:
            score = priority.index(bid)
            # Prefer upgrades slightly
            if c.get("is_upgrade"):
                score -= 0.5
            if score < best_score:
                best_score = score
                best = c

    return best if best else choices[0]


# ─── Resolve Turn (simplified from dungeon_service.py) ───

def resolve_turn_sim(state, player_action):
    """Simplified resolve_turn for simulation - mirrors the actual logic."""
    buffs = state["buffs"]
    p_stats = state["p_stats"]
    e_stats = state["e_stats"]
    e_intent = state["e_intent"]

    # Truant: even turns forced defend
    if state.get("is_truant") and state["turn"] % 2 == 0:
        player_action = "defend"

    crit_bonus = get_combat_rate(buffs, "crit")
    double_rate = get_combat_rate(buffs, "double")
    dodge_rate = get_combat_rate(buffs, "dodge")
    thorns_rate = get_combat_rate(buffs, "thorns")
    lifesteal = get_lifesteal_rate(buffs)
    active_syn = {s["id"] for s in _get_active_synergies(buffs)}

    has_preemptive = any(b.get("id") == "preemptive" for b in buffs)
    has_penetrate = any(b.get("id") == "penetrate" for b in buffs)
    counter_rate = 0.0
    for b in buffs:
        if b.get("id") == "counter":
            counter_rate = b["effect"].get("rate", 0.30)

    floor_clear = False
    player_dead = False

    # ── Player damage ──
    player_dmg = 0
    player_defending = False

    if player_action == "defend":
        player_defending = True
    elif player_action in ("skill1", "skill2"):
        idx = 0 if player_action == "skill1" else 1
        if idx < len(state["skills"]) and idx < len(state["pp"]) and state["pp"][idx]["current"] > 0:
            state["pp"][idx]["current"] -= 1
            atk_val = p_stats["spa"]
            def_val = e_stats["spdef"]
            type_mult = state["skill_type_mults"][idx]
            base = max(int(atk_val * config.DUNGEON_MIN_DMG_RATIO),
                       atk_val - int(def_val * config.DUNGEON_DEF_FACTOR))
            variance = random.uniform(0.9, 1.1)
            effective_crit = config.DUNGEON_CRIT_RATE + crit_bonus
            is_crit = random.random() < effective_crit
            crit_mult = config.DUNGEON_CRIT_MULT if is_crit else 1.0
            player_dmg = max(1, int(base * config.DUNGEON_SPECIAL_MULT * type_mult * crit_mult * variance))
            if "power" in active_syn:
                player_dmg = int(player_dmg * 1.20)
        else:
            player_action = "normal"

    if player_action == "normal":
        atk_val = p_stats["atk"]
        def_val = e_stats["def"]
        normal_mult = config.DUNGEON_NORMAL_ATK_MULT.get(state["p_rarity"], 1.0)
        base = max(int(atk_val * config.DUNGEON_MIN_DMG_RATIO),
                   atk_val - int(def_val * config.DUNGEON_DEF_FACTOR))
        variance = random.uniform(0.9, 1.1)
        effective_crit = config.DUNGEON_CRIT_RATE + crit_bonus
        is_crit = random.random() < effective_crit
        crit_mult = config.DUNGEON_CRIT_MULT if is_crit else 1.0
        player_dmg = max(1, int(base * normal_mult * crit_mult * variance))
        if "power" in active_syn:
            player_dmg = int(player_dmg * 1.20)

    # ── Enemy damage ──
    enemy_dmg = 0
    e_action = e_intent["action"]

    if state["e_charged"]:
        e_atk = max(e_stats["atk"], e_stats["spa"])
        enemy_dmg = max(1, int(e_atk * 2.0 * random.uniform(0.9, 1.1)))
        state["e_charged"] = False
    elif e_action == "normal_attack":
        e_atk = e_stats["atk"]
        p_def = p_stats["def"]
        base = max(int(e_atk * config.DUNGEON_MIN_DMG_RATIO),
                   e_atk - int(p_def * config.DUNGEON_DEF_FACTOR))
        enemy_dmg = max(1, int(base * 0.8 * random.uniform(0.9, 1.1)))
    elif e_action == "type_attack":
        atk_type = e_intent.get("type", "normal")
        e_atk = e_stats["spa"]
        p_def = p_stats["spdef"]
        type_mult = _single_type_mult(atk_type, state["p_types"]) if isinstance(atk_type, str) else 1.0
        base = max(int(e_atk * config.DUNGEON_MIN_DMG_RATIO),
                   e_atk - int(p_def * config.DUNGEON_DEF_FACTOR))
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

    # Boss rage at 30% HP
    if state["enemy"]["is_boss"] and state["e_hp"] <= state["e_max_hp"] * 0.3 and not state["e_rage"]:
        state["e_rage"] = True
        state["e_stats"]["atk"] = int(state["e_stats"]["atk"] * 1.5)
        state["e_stats"]["spa"] = int(state["e_stats"]["spa"] * 1.5)

    # ── Speed order ──
    p_first = p_stats["spd"] >= e_stats["spd"]
    if p_stats["spd"] == e_stats["spd"]:
        p_first = random.random() < 0.5
    if has_preemptive:
        p_first = True

    # ── Apply attacks ──
    def do_player_attack():
        nonlocal player_dmg
        if player_defending:
            return
        if state["e_defending"] and not has_penetrate:
            player_dmg = max(1, player_dmg // 2)
        if "reaper" in active_syn and state["e_hp"] <= state["e_max_hp"] * 0.15:
            player_dmg = state["e_hp"]

        hit_count = 1
        effective_double = double_rate
        if "fury" in active_syn:
            effective_double = min(1.0, effective_double * 2)
        if effective_double > 0 and random.random() < effective_double:
            hit_count = 2

        for _ in range(hit_count):
            state["e_hp"] -= player_dmg
            if lifesteal > 0:
                heal = int(player_dmg * lifesteal)
                state["p_hp"] = min(state["p_max_hp"], state["p_hp"] + heal)

    def do_enemy_attack():
        nonlocal enemy_dmg
        if enemy_dmg <= 0:
            return
        if player_defending:
            enemy_dmg = max(1, int(enemy_dmg * config.DUNGEON_DEFEND_REDUCE))
        if "iron" in active_syn:
            enemy_dmg = int(enemy_dmg * 0.85)
        if dodge_rate > 0 and random.random() < dodge_rate:
            return  # dodged

        # Shield absorb
        if state["p_shield"] > 0:
            absorbed = min(state["p_shield"], enemy_dmg)
            state["p_shield"] -= absorbed
            enemy_dmg -= absorbed

        state["p_hp"] -= enemy_dmg

        # Thorns
        if thorns_rate > 0 and enemy_dmg > 0:
            reflect = max(1, int(enemy_dmg * thorns_rate))
            state["e_hp"] -= reflect
            if "vampire" in active_syn and lifesteal > 0:
                heal = int(reflect * lifesteal)
                state["p_hp"] = min(state["p_max_hp"], state["p_hp"] + heal)

        # Counter
        if player_defending and counter_rate > 0 and enemy_dmg > 0:
            counter_dmg = max(1, int(enemy_dmg * counter_rate))
            state["e_hp"] -= counter_dmg

    if p_first:
        do_player_attack()
        if state["e_hp"] > 0:
            do_enemy_attack()
    else:
        do_enemy_attack()
        if state["p_hp"] > 0:
            do_player_attack()

    state["e_defending"] = False

    # Revive
    if state["p_hp"] <= 0 and has_revive(buffs) and not state.get("revive_used"):
        state["p_hp"] = int(state["p_max_hp"] * 0.30)
        state["revive_used"] = True
        # Remove revive buff
        state["buffs"] = [b for b in state["buffs"] if b.get("id") != "revive"]
        state["buffs"].append({"id": "_revive_consumed", "name": "_", "lv": 0, "effect": {}, "category": "system"})

    # Win/lose
    if state["e_hp"] <= 0:
        floor_clear = True
    elif state["p_hp"] <= 0:
        player_dead = True
    elif state["turn"] >= config.DUNGEON_MAX_TURNS_PER_FLOOR:
        p_ratio = state["p_hp"] / state["p_max_hp"]
        e_ratio = state["e_hp"] / state["e_max_hp"]
        if p_ratio > e_ratio:
            floor_clear = True
        else:
            player_dead = True

    if not floor_clear and not player_dead:
        state["turn"] += 1
        state["e_intent"] = _generate_enemy_intent(state["enemy"], state["floor"])

    return floor_clear, player_dead


# ─── Single Run Simulation ───

def simulate_run(pid, rarity, iv_val, buff_luck="average"):
    """실제 resolve_turn + init_combat_state 사용 시뮬."""
    types = get_player_types(pid)
    base_stats = build_player_stats(pid, rarity, FRIENDSHIP, iv_val)

    dg_mult = config.DUNGEON_RARITY_STAT_MULT.get(rarity, 1.0)
    base_stats = {k: int(v * dg_mult) for k, v in base_stats.items()}

    max_hp = base_stats["hp"]
    current_hp = max_hp
    buffs = []
    floor_reached = 0

    for floor in range(1, MAX_FLOOR + 1):
        enemy = generate_enemy(floor, THEME, rarity)

        # 실제 init_combat_state 사용 — 보호막, PP, 시너지 등 모두 반영
        combat = init_combat_state(
            base_stats, types, rarity, pid, enemy, buffs,
            current_hp=current_hp, max_hp=max_hp, floor=floor,
        )

        # 전투
        won = False
        for turn in range(config.DUNGEON_MAX_TURNS_PER_FLOOR):
            action = ai_choose_action(combat)
            result = resolve_turn(combat, action)

            if result.get("floor_clear"):
                won = True
                break
            if result.get("player_dead"):
                break

        if not won:
            floor_reached = floor - 1
            break

        floor_reached = floor
        current_hp = combat["p_hp"]
        buffs = consume_rogue_buffs(combat["buffs"])

        # 층간 회복 (30층+ 감소)
        if floor >= config.DUNGEON_HARD_FLOOR_THRESHOLD:
            base_heal = config.DUNGEON_HARD_FLOOR_HEAL
        else:
            base_heal = config.DUNGEON_BASE_FLOOR_HEAL
        heal_rate = base_heal + get_floor_heal_rate(buffs)
        current_hp = min(max_hp, current_hp + int(max_hp * heal_rate))

        # 버프 선택 (보스층)
        if should_offer_buff(floor, 1):
            real_buffs = [b for b in buffs if not b["id"].startswith("_")]
            if len(real_buffs) < config.DUNGEON_MAX_BUFFS:
                choices = generate_buff_choices(floor, buffs, count=3)
                if choices:
                    chosen = ai_choose_buff(choices, buffs, floor)
                    buffs = apply_buff_choice(buffs, chosen)
            else:
                event = generate_roguelike_event()
                current_hp, buffs, _ = apply_roguelike_event(event, current_hp, max_hp, buffs)

        # max_hp 갱신
        new_stats = apply_buffs_to_stats(base_stats, buffs)
        max_hp = new_stats["hp"]
        current_hp = min(max_hp, current_hp)

    return floor_reached


# ─── Run Simulation ───

def run_simulation():
    print("=" * 70)
    print("  DUNGEON TURN-BASED COMBAT BALANCE SIMULATION")
    print("=" * 70)
    print(f"  Runs per config: {NUM_RUNS}")
    print(f"  Max floor: {MAX_FLOOR}")
    print(f"  Theme: {THEME['name']} ({', '.join(THEME['types'])})")
    print(f"  Friendship: {FRIENDSHIP} (max)")
    print()

    # Show enemy scaling
    print("─── Enemy Scaling (floor → multiplier) ───")
    for f in [1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50]:
        s = enemy_scaling(f)
        print(f"  Floor {f:2d}: ×{s:.3f}")
    print()

    # Show cost scaling
    print("─── Cost Scaling (player rarity → enemy scaling mult) ───")
    for r in ["common", "rare", "epic", "legendary", "ultra_legendary"]:
        cs = config.DUNGEON_COST_SCALING.get(r, 1.0)
        print(f"  {r:18s}: ×{cs:.2f}")
    print()

    results = {}

    for rarity in ["common", "rare", "epic", "legendary", "ultra_legendary"]:
        poke_pool = REPRESENTATIVE.get(rarity, [])
        if not poke_pool:
            print(f"  [SKIP] No pokemon for rarity {rarity}")
            continue

        for scenario_name, iv_val, buff_luck in [
            ("avg_iv_avg_buff", IV_AVG, "average"),
            ("good_iv_good_buff", IV_GOOD, "good"),
        ]:
            key = f"{rarity}_{scenario_name}"
            floors = []

            for run in range(NUM_RUNS):
                pid = random.choice(poke_pool)
                floor = simulate_run(pid, rarity, iv_val, buff_luck)
                floors.append(floor)

            avg = statistics.mean(floors)
            med = statistics.median(floors)
            std = statistics.stdev(floors) if len(floors) > 1 else 0
            mx = max(floors)
            mn = min(floors)
            p30 = sum(1 for f in floors if f >= 30) / len(floors) * 100
            p40 = sum(1 for f in floors if f >= 40) / len(floors) * 100
            p50 = sum(1 for f in floors if f >= 50) / len(floors) * 100

            results[key] = {
                "rarity": rarity,
                "scenario": scenario_name,
                "avg": avg,
                "median": med,
                "std": std,
                "max": mx,
                "min": mn,
                "p30": p30,
                "p40": p40,
                "p50": p50,
            }

    # Print results
    print("=" * 70)
    print("  RESULTS")
    print("=" * 70)
    print()
    print(f"{'Rarity':<20} {'Scenario':<22} {'Avg':>5} {'Med':>5} {'Std':>5} {'Min':>4} {'Max':>4} {'≥30':>6} {'≥40':>6} {'≥50':>6}")
    print("─" * 98)

    for key in sorted(results.keys()):
        r = results[key]
        print(f"{r['rarity']:<20} {r['scenario']:<22} {r['avg']:5.1f} {r['median']:5.1f} {r['std']:5.1f} {r['min']:4d} {r['max']:4d} {r['p30']:5.1f}% {r['p40']:5.1f}% {r['p50']:5.1f}%")

    print()
    print("=" * 70)
    print("  BALANCE TARGETS")
    print("=" * 70)
    print("  Floor 30: Most good players should reach (>50% for epic+)")
    print("  Floor 40: Very hard, needs great buffs + luck (<10%)")
    print("  Floor 50: Nearly impossible, incredible luck only (<1%)")
    print()

    # Assessment
    print("=" * 70)
    print("  BALANCE ASSESSMENT")
    print("=" * 70)
    for rarity in ["common", "rare", "epic", "legendary", "ultra_legendary"]:
        avg_key = f"{rarity}_avg_iv_avg_buff"
        good_key = f"{rarity}_good_iv_good_buff"
        if avg_key in results and good_key in results:
            ra = results[avg_key]
            rg = results[good_key]
            print(f"\n  [{rarity.upper()}]")
            print(f"    Average player: avg floor {ra['avg']:.1f}, ≥30: {ra['p30']:.1f}%, ≥40: {ra['p40']:.1f}%, ≥50: {ra['p50']:.1f}%")
            print(f"    Good player:    avg floor {rg['avg']:.1f}, ≥30: {rg['p30']:.1f}%, ≥40: {rg['p40']:.1f}%, ≥50: {rg['p50']:.1f}%")

            # Assessment
            if rg['p40'] > 15:
                print(f"    ⚠️  Floor 40+ too easy! ({rg['p40']:.1f}% reach 40)")
            elif rg['p40'] < 1:
                print(f"    ⚠️  Floor 40 might be too hard ({rg['p40']:.1f}% reach 40)")
            else:
                print(f"    ✅ Floor 40 difficulty looks good")

            if rg['p50'] > 3:
                print(f"    ⚠️  Floor 50 too easy! ({rg['p50']:.1f}% reach 50)")
            elif rg['p50'] == 0:
                print(f"    ✅ Floor 50 nearly impossible (as intended)")
            else:
                print(f"    ✅ Floor 50 very rare ({rg['p50']:.1f}%)")

    # Floor distribution histogram for best rarity
    print()
    print("=" * 70)
    print("  FLOOR DISTRIBUTION (ultra_legendary, good scenario)")
    print("=" * 70)
    ul_key = "ultra_legendary_good_iv_good_buff"
    if ul_key in results:
        # Re-run to get distribution
        poke_pool = REPRESENTATIVE.get("ultra_legendary", [])
        dist = {}
        for _ in range(NUM_RUNS):
            pid = random.choice(poke_pool)
            f = simulate_run(pid, "ultra_legendary", IV_GOOD, "good")
            bucket = (f // 5) * 5
            dist[bucket] = dist.get(bucket, 0) + 1

        for bucket in sorted(dist.keys()):
            count = dist[bucket]
            bar = "█" * (count * 50 // NUM_RUNS)
            pct = count / NUM_RUNS * 100
            print(f"  {bucket:2d}-{bucket+4:2d}: {bar:<50} {pct:5.1f}% ({count})")

    print("\nDone!")


if __name__ == "__main__":
    run_simulation()
