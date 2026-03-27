import asyncio, asyncpg, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from models.pokemon_base_stats import POKEMON_BASE_STATS

COST = {"common":1,"rare":2,"epic":3,"legendary":5,"ultra_legendary":6}

async def main():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"), statement_cache_size=0)
    uid = 1832746512

    teams = await conn.fetch(
        "SELECT bt.team_number, bt.slot, up.pokemon_id, pm.name_ko, pm.rarity, up.is_shiny, up.friendship "
        "FROM battle_teams bt "
        "JOIN user_pokemon up ON bt.pokemon_instance_id = up.id "
        "JOIN pokemon_master pm ON up.pokemon_id = pm.id "
        "WHERE bt.user_id = $1 ORDER BY bt.team_number, bt.slot", uid)

    for tn in [1,2]:
        slots = [t for t in teams if t["team_number"] == tn]
        if not slots:
            continue
        total_cost = 0
        print(f"\n=== 팀 {tn} ===")
        for s in slots:
            pid = s["pokemon_id"]
            bs = POKEMON_BASE_STATS.get(pid)
            types = bs[6] if bs else ["?"]
            bst = sum(bs[0:6]) if bs else 0
            cost = COST.get(s["rarity"], 1)
            total_cost += cost
            shiny = "⭐" if s["is_shiny"] else ""
            print(f"  [{s['slot']}] {shiny}{s['name_ko']} ({s['rarity']}/{cost}코) BST={bst} 타입={'/'.join(types)} 친밀도={s['friendship']}")
        print(f"  총 코스트: {total_cost}/18")

    # 보유 에픽 물/얼음 포켓몬
    print("\n=== 보유 에픽 물/얼음 후보 ===")
    epics = await conn.fetch(
        "SELECT up.pokemon_id, pm.name_ko, up.is_shiny, up.friendship "
        "FROM user_pokemon up JOIN pokemon_master pm ON up.pokemon_id = pm.id "
        "WHERE up.user_id = $1 AND pm.rarity = 'epic' ORDER BY up.friendship DESC", uid)
    for e in epics:
        bs = POKEMON_BASE_STATS.get(e["pokemon_id"])
        types = bs[6] if bs else []
        if "water" in types or "ice" in types:
            bst = sum(bs[0:6]) if bs else 0
            shiny = "⭐" if e["is_shiny"] else ""
            print(f"  {shiny}{e['name_ko']} BST={bst} 타입={'/'.join(types)} 친밀도={e['friendship']}")

    # 보유 레어/커먼 강한 순
    print("\n=== 보유 레어/커먼 (BST순) ===")
    others = await conn.fetch(
        "SELECT up.pokemon_id, pm.name_ko, pm.rarity, up.is_shiny, up.friendship "
        "FROM user_pokemon up JOIN pokemon_master pm ON up.pokemon_id = pm.id "
        "WHERE up.user_id = $1 AND pm.rarity IN ('rare', 'common') "
        "ORDER BY up.friendship DESC LIMIT 30", uid)
    results = []
    for o in others:
        bs = POKEMON_BASE_STATS.get(o["pokemon_id"])
        bst = sum(bs[0:6]) if bs else 0
        types = bs[6] if bs else []
        results.append((bst, o, types))
    results.sort(key=lambda x: -x[0])
    for bst, o, types in results[:15]:
        shiny = "⭐" if o["is_shiny"] else ""
        cost = COST.get(o["rarity"], 1)
        print(f"  {shiny}{o['name_ko']} ({o['rarity']}/{cost}코) BST={bst} 타입={'/'.join(types)} 친밀도={o['friendship']}")

    await conn.close()

asyncio.run(main())
