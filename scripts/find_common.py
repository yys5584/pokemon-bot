import asyncio, os, sys, asyncpg, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
from models.pokemon_base_stats import POKEMON_BASE_STATS

async def main():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)

    for rarity, label in [("epic", "에픽(4코스트)"), ("common", "커먼(1코스트)")]:
        rows = await conn.fetch("""
            SELECT up.id, up.pokemon_id, p.name_ko, up.is_shiny,
                   up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd
            FROM user_pokemon up
            JOIN pokemon_master p ON up.pokemon_id = p.id
            WHERE up.user_id = 1832746512 AND p.rarity = $1
        """, rarity)
        scored = []
        for r in rows:
            iv = r["iv_hp"]+r["iv_atk"]+r["iv_def"]+r["iv_spa"]+r["iv_spdef"]+r["iv_spd"]
            entry = POKEMON_BASE_STATS.get(r["pokemon_id"])
            bst = sum(entry[:6]) if entry else 0
            types = "/".join(entry[6]) if entry else "?"
            scored.append((bst+iv, r, iv, bst, types))
        scored.sort(key=lambda x: -x[0])
        print(f"\n=== {label} Top 10 ===")
        for i, (score, r, iv, bst, types) in enumerate(scored[:10], 1):
            sh = "✨" if r["is_shiny"] else ""
            print(f"  {i}. {sh}{r['name_ko']:<8s} [{types:<14s}] BST:{bst} IV:{iv}/186 total:{score} (id:{r['id']})")

    await conn.close()

asyncio.run(main())
