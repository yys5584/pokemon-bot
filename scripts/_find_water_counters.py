import asyncio, asyncpg, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from models.pokemon_base_stats import POKEMON_BASE_STATS

async def main():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"), statement_cache_size=0)
    uid = 1832746512
    rows = await conn.fetch(
        "SELECT up.pokemon_id, pm.name_ko, pm.rarity, up.is_shiny, up.friendship "
        "FROM user_pokemon up JOIN pokemon_master pm ON up.pokemon_id = pm.id "
        "WHERE up.user_id = $1 AND pm.rarity IN ('rare', 'common') "
        "ORDER BY up.friendship DESC", uid)

    results = []
    for o in rows:
        bs = POKEMON_BASE_STATS.get(o["pokemon_id"])
        if not bs:
            continue
        types = bs[6]
        if "electric" in types or "grass" in types:
            bst = sum(bs[0:6])
            cost = 2 if o["rarity"] == "rare" else 1
            shiny = "S" if o["is_shiny"] else " "
            results.append((bst, shiny, o["name_ko"], o["rarity"], cost, types, o["friendship"]))

    results.sort(key=lambda x: -x[0])
    print("=== 보유 전기/풀 타입 (물 카운터) ===")
    for bst, shiny, name, rarity, cost, types, friend in results:
        tstr = "/".join(types)
        print(f"  [{shiny}] {name:10s} ({rarity}/{cost}코) BST={bst} 타입={tstr:16s} 친밀도={friend}")

    await conn.close()

asyncio.run(main())
