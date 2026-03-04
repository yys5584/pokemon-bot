"""Round-robin simulation: every final-evo pokemon vs every other, N times each.
Outputs win-rate based ranking.
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from utils.battle_calc import calc_battle_stats, get_type_multiplier, EVO_STAGE_MAP, get_normalized_base_stats
from models.pokemon_skills import POKEMON_SKILLS

# ---------- lightweight battle sim (no DB, no logging) ----------

def make_combatant(pid, name, emoji, rarity, ptype, stat_type):
    base = get_normalized_base_stats(pid)
    stats = calc_battle_stats(
        rarity, stat_type, 5,  # friendship=5 baseline
        evo_stage=3 if base else EVO_STAGE_MAP.get(pid, 3),
        **(base or {}),
    )
    skill = POKEMON_SKILLS.get(pid, ("몸통박치기", 1.2))
    return {
        "pid": pid, "name": name, "emoji": emoji,
        "type": ptype, "rarity": rarity,
        "stats": stats,
        "skill_power": skill[1],
    }


def sim_1v1(a, b):
    """Simulate a single 1v1 battle. Returns 'a' or 'b'."""
    a_hp = a["stats"]["hp"]
    b_hp = b["stats"]["hp"]

    for _ in range(config.BATTLE_MAX_ROUNDS):
        # Speed determines first
        if a["stats"]["spd"] >= b["stats"]["spd"]:
            first, second = "a", "b"
        else:
            first, second = "b", "a"

        for attacker_key, defender_key in [(first, second), (second, first)]:
            atk = a if attacker_key == "a" else b
            dfn = a if defender_key == "a" else b
            atk_hp_ref = "a_hp" if attacker_key == "a" else "b_hp"
            dfn_hp_ref = "a_hp" if defender_key == "a" else "b_hp"

            # Check if attacker is alive
            if (a_hp if attacker_key == "a" else b_hp) <= 0:
                continue

            # Physical vs Special
            atk_p, atk_s = atk["stats"]["atk"], atk["stats"]["spa"]
            if atk_s > atk_p:
                off, dfs = atk_s, dfn["stats"]["spdef"]
            else:
                off, dfs = atk_p, dfn["stats"]["def"]
            base_dmg = max(1, off - dfs * 0.4)
            type_mult = get_type_multiplier(atk["type"], dfn["type"])
            crit = 1.5 if random.random() < config.BATTLE_CRIT_RATE else 1.0
            skill_mult = atk["skill_power"] if random.random() < config.BATTLE_SKILL_RATE else 1.0
            variance = random.uniform(0.9, 1.1)
            dmg = max(1, int(base_dmg * type_mult * crit * skill_mult * variance))

            if defender_key == "a":
                a_hp -= dmg
            else:
                b_hp -= dmg

            if a_hp <= 0:
                return "b"
            if b_hp <= 0:
                return "a"

    # Timeout: whoever has more HP% wins
    a_pct = a_hp / a["stats"]["hp"]
    b_pct = b_hp / b["stats"]["hp"]
    return "a" if a_pct >= b_pct else "b"


def main():
    # Load all final-evo pokemon from DB schema (use pokemon_master via sync query)
    # Since no DB, read from pokemon_base_stats + config
    from models.pokemon_base_stats import POKEMON_BASE_STATS

    # We need pokemon_master data. Let's use a simpler approach:
    # Read from config's POKEMON_LIST or build from base_stats
    # Actually, we need name_ko, emoji, rarity, pokemon_type, stat_type, evolves_to
    # These are in DB. Let's do a synchronous DB read or use cached data.

    # Simpler: use asyncio to query DB once
    import asyncio
    from database.connection import get_db

    async def load_pokemon():
        pool = await get_db()
        rows = await pool.fetch("""
            SELECT id, name_ko, emoji, rarity, pokemon_type, stat_type, evolves_to
            FROM pokemon_master ORDER BY id
        """)
        return [dict(r) for r in rows if r["evolves_to"] is None]

    final_evos = asyncio.run(load_pokemon())
    print(f"Final evolutions: {len(final_evos)}")

    # Build combatants
    combatants = []
    for r in final_evos:
        c = make_combatant(r["id"], r["name_ko"], r["emoji"],
                           r["rarity"], r["pokemon_type"], r["stat_type"])
        combatants.append(c)

    N_SIMS = 100  # battles per matchup
    n = len(combatants)
    wins = {c["pid"]: 0 for c in combatants}
    total = {c["pid"]: 0 for c in combatants}

    print(f"Running {n*(n-1)//2 * N_SIMS} total battles...")

    for i in range(n):
        for j in range(i + 1, n):
            a, b = combatants[i], combatants[j]
            for _ in range(N_SIMS):
                result = sim_1v1(a, b)
                if result == "a":
                    wins[a["pid"]] += 1
                else:
                    wins[b["pid"]] += 1
                total[a["pid"]] += 1
                total[b["pid"]] += 1

    # Calculate win rates and sort
    results = []
    for c in combatants:
        pid = c["pid"]
        wr = wins[pid] / total[pid] * 100 if total[pid] > 0 else 0
        results.append({
            "pid": pid, "name": c["name"], "emoji": c["emoji"],
            "rarity": c["rarity"], "type": c["type"],
            "win_rate": round(wr, 1),
            "wins": wins[pid], "total": total[pid],
            "hp": c["stats"]["hp"], "atk": c["stats"]["atk"],
            "def": c["stats"]["def"], "spa": c["stats"]["spa"],
            "spdef": c["stats"]["spdef"], "spd": c["stats"]["spd"],
        })

    results.sort(key=lambda x: -x["win_rate"])

    # Output as JSON
    import json
    out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Results saved to {out_path}")


if __name__ == "__main__":
    main()
