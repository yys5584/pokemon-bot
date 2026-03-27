"""배틀팀 메타 분석 — 현재 덱 조합 + BST 상한 적용 시 변화."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

async def main():
    from database.connection import get_db
    pool = await get_db()

    rows = await pool.fetch(
        "SELECT bt.user_id, u.display_name, bt.slot, "
        "pm.name_ko, pm.rarity, up.is_shiny, pm.id as pid "
        "FROM battle_teams bt "
        "JOIN user_pokemon up ON up.id = bt.pokemon_instance_id "
        "JOIN pokemon_master pm ON up.pokemon_id = pm.id "
        "JOIN users u ON bt.user_id = u.user_id "
        "ORDER BY bt.user_id, bt.slot"
    )

    cost_map = {"common": 1, "rare": 2, "epic": 4, "legendary": 5, "ultra_legendary": 6}
    rs = {"common": "C", "rare": "R", "epic": "E", "legendary": "L", "ultra_legendary": "U"}

    teams = {}
    for r in rows:
        uid = r[0]
        if uid not in teams:
            teams[uid] = {"name": r[1], "pokes": [], "rarities": [], "pids": []}
        rarity = r[4] or "common"
        shiny = "*" if r[5] else ""
        tag = rs.get(rarity, "?")
        teams[uid]["pokes"].append(f"{shiny}{r[3]}({tag})")
        teams[uid]["rarities"].append(rarity)
        teams[uid]["pids"].append(r[6])

    full = {k: v for k, v in teams.items() if len(v["pokes"]) == 6}
    print(f"=== 풀팀 보유: {len(full)}명 ===\n")

    # 덱 조합별 분류
    groups = {}
    for uid, t in full.items():
        key = "".join(sorted(rs.get(r, "?") for r in t["rarities"]))
        tc = sum(cost_map.get(r, 1) for r in t["rarities"])
        if key not in groups:
            groups[key] = []
        groups[key].append((t["name"], tc, t["pokes"], t["pids"]))

    print("=== 인기 덱 조합 TOP 15 ===\n")
    for key, users in sorted(groups.items(), key=lambda x: -len(x[1]))[:15]:
        c = users[0][1]
        # 등급별 카운트
        counts = {}
        for ch in key:
            counts[ch] = counts.get(ch, 0) + 1
        desc = "+".join(f"{k}x{v}" for k,v in sorted(counts.items()))
        print(f"[{len(users):>2}명] {desc} (cost {c})")
        for u in users[:3]:
            print(f"  {u[0]:<14} {' | '.join(u[2])}")
        print()

    # 가장 많이 쓰이는 포켓몬 TOP 20
    poke_count = {}
    for uid, t in full.items():
        for i, pid in enumerate(t["pids"]):
            name = t["pokes"][i]
            if pid not in poke_count:
                poke_count[pid] = {"name": name, "count": 0}
            poke_count[pid]["count"] += 1

    print("=== 가장 많이 쓰이는 포켓몬 TOP 20 ===\n")
    for pid, info in sorted(poke_count.items(), key=lambda x: -x[1]["count"])[:20]:
        print(f"  {info['name']:<20} {info['count']:>3}팀")

asyncio.run(main())
