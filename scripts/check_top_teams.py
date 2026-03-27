import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
from database.connection import get_db
from utils.battle_calc import calc_battle_stats, calc_power, get_normalized_base_stats, EVO_STAGE_MAP, iv_total
import config

async def main():
    pool = await get_db()

    # 모든 유저의 활성 팀 조회
    rows = await pool.fetch("""
        SELECT bt.user_id, u.display_name, bt.slot, bt.team_number,
               up.pokemon_id, pm.name_ko, pm.rarity, pm.pokemon_type, pm.stat_type,
               up.friendship, up.is_shiny,
               up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd
        FROM battle_teams bt
        JOIN user_pokemon up ON bt.pokemon_instance_id = up.id
        JOIN pokemon_master pm ON up.pokemon_id = pm.id
        JOIN users u ON bt.user_id = u.user_id
        WHERE bt.team_number = COALESCE(
            (SELECT active_team FROM users WHERE user_id = bt.user_id), 1
        )
        ORDER BY bt.user_id, bt.slot
    """)

    # 유저별 팀 구성
    teams = {}
    for r in rows:
        uid = r["user_id"]
        if uid not in teams:
            teams[uid] = {"name": r["display_name"], "members": []}

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
        cost = config.RANKED_COST.get(r["rarity"], 1)

        teams[uid]["members"].append({
            "name": r["name_ko"], "rarity": r["rarity"], "type": r["pokemon_type"],
            "power": power, "iv_sum": iv_sum, "cost": cost, "shiny": r["is_shiny"],
        })

    # 팀 전투력 합산 순으로 정렬
    ranked = []
    for uid, data in teams.items():
        total_power = sum(m["power"] for m in data["members"])
        total_cost = sum(m["cost"] for m in data["members"])
        types = [m["type"] for m in data["members"]]
        ranked.append({
            "uid": uid, "name": data["name"], "members": data["members"],
            "total_power": total_power, "total_cost": total_cost, "types": types,
        })

    ranked.sort(key=lambda x: -x["total_power"])

    cost_short = {"common": "C", "rare": "R", "epic": "E", "legendary": "L", "ultra_legendary": "UL"}
    grade = lambda iv: "S" if iv >= 160 else "A" if iv >= 120 else "B" if iv >= 93 else "C"

    for i, t in enumerate(ranked[:15]):
        print(f"\n#{i+1} {t['name']} — 총 전투력 {t['total_power']} (코스트 {t['total_cost']})")
        for m in t["members"]:
            sh = "*" if m["shiny"] else " "
            print(f"  {sh} {m['name']:<8} {cost_short[m['rarity']]:>2} 전투력{m['power']:>5} [{grade(m['iv_sum'])}]{m['iv_sum']:>4} {m['type']}")
        # 타입 분포
        type_count = {}
        for tp in t["types"]:
            type_count[tp] = type_count.get(tp, 0) + 1
        print(f"  타입: {dict(type_count)}")

asyncio.run(main())
