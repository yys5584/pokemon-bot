import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
from database.connection import get_db
from utils.battle_calc import calc_battle_stats, calc_power, get_normalized_base_stats, EVO_STAGE_MAP, iv_total

UID = 1832746512

async def main():
    pool = await get_db()
    rows = await pool.fetch("""
        SELECT up.id, up.pokemon_id, pm.name_ko, pm.rarity, pm.pokemon_type, pm.stat_type,
               up.friendship, up.is_shiny,
               up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd
        FROM user_pokemon up
        JOIN pokemon_master pm ON up.pokemon_id = pm.id
        WHERE up.user_id = $1 AND up.is_active = 1
    """, UID)

    pokemon = []
    for r in rows:
        pid = r["pokemon_id"]
        base_kw = get_normalized_base_stats(pid) or {}
        evo_stage = 3 if base_kw else EVO_STAGE_MAP.get(pid, 3)
        friendship = 7 if r["is_shiny"] else 5
        stats = calc_battle_stats(
            r["rarity"], r["stat_type"], friendship, evo_stage,
            r["iv_hp"], r["iv_atk"], r["iv_def"],
            r["iv_spa"], r["iv_spdef"], r["iv_spd"],
            **base_kw,
        )
        power = calc_power(stats)
        iv_sum = iv_total(r["iv_hp"], r["iv_atk"], r["iv_def"],
                          r["iv_spa"], r["iv_spdef"], r["iv_spd"])
        cost = {"common": 1, "rare": 2, "epic": 4, "legendary": 5, "ultra_legendary": 6}.get(r["rarity"], 1)
        pokemon.append({
            "id": r["id"], "pid": pid, "name": r["name_ko"], "rarity": r["rarity"],
            "type": r["pokemon_type"], "cost": cost, "power": power,
            "iv_sum": iv_sum, "friendship": r["friendship"],
            "shiny": r["is_shiny"], "stats": stats,
        })

    # 등급별 전투력 순 출력
    pokemon.sort(key=lambda x: -x["power"])

    cost_label = {"common": "C", "rare": "R", "epic": "E", "legendary": "L", "ultra_legendary": "UL"}
    grade = lambda iv: "S" if iv >= 160 else "A" if iv >= 120 else "B" if iv >= 93 else "C" if iv >= 62 else "D"

    for rarity in ["ultra_legendary", "legendary", "epic", "rare", "common"]:
        subset = [p for p in pokemon if p["rarity"] == rarity]
        if not subset:
            continue
        print(f"\n=== {rarity.upper()} (코스트{subset[0]['cost']}) — {len(subset)}마리 ===")
        for p in subset[:15]:
            sh = "*" if p["shiny"] else " "
            print(f"  {sh} id={p['id']:>5} #{p['pid']:>3} {p['name']:<8} 전투력{p['power']:>5} [{grade(p['iv_sum'])}]{p['iv_sum']:>4} f{p['friendship']} {p['type']}")

    print(f"\n총 {len(pokemon)}마리")

asyncio.run(main())
