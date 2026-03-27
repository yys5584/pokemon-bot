import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

async def main():
    from database.connection import get_db
    pool = await get_db()

    user = await pool.fetchrow("SELECT user_id FROM users WHERE display_name LIKE '%Turri%'")
    uid = user[0]

    rows = await pool.fetch(
        "SELECT pm.name_ko, pm.rarity, bps.pokemon_id, "
        "COUNT(*) as bat, "
        "ROUND(AVG(bps.damage_dealt)) as dmg, "
        "ROUND(AVG(bps.kills)::numeric,2) as kills, "
        "ROUND(AVG(bps.deaths)::numeric,2) as deaths, "
        "ROUND(AVG(bps.turns_alive)::numeric,1) as alive, "
        "ROUND(AVG(bps.super_effective_hits)::numeric,2) as se_hits, "
        "ROUND(AVG(bps.not_effective_hits)::numeric,2) as ne_hits, "
        "ROUND(AVG(bps.skills_activated)::numeric,2) as skills "
        "FROM battle_pokemon_stats bps "
        "JOIN pokemon_master pm ON bps.pokemon_id = pm.id "
        "WHERE bps.user_id = $1 "
        "GROUP BY pm.name_ko, pm.rarity, bps.pokemon_id "
        "ORDER BY dmg DESC",
        uid
    )

    rs_map = {'common':'C','rare':'R','epic':'E','legendary':'L','ultra_legendary':'U'}
    print(f"=== Turri 포켓몬별 전체 성적 ===")
    print(f"  {'이름':<12} {'등급':<3} {'전투':>4} {'딜':>5} {'킬':>4} {'데스':>4} {'생존':>4} {'상성+':>4} {'상성-':>4} {'스킬':>4}")
    for r in rows:
        tag = rs_map.get(r[1], '?')
        print(f"  {r[0]:<12} {tag:<3} {r[3]:>4} {r[4]:>5} {r[5]:>4} {r[6]:>4} {r[7]:>4} {r[8]:>4} {r[9]:>4} {r[10]:>4}")

    # 상대 팀의 물/비행 비율 (썬더 상성)
    print()
    print("=== 썬더 상성 분석 ===")
    from models.pokemon_base_stats import POKEMON_BASE_STATS
    # 전체 배틀팀 중 물/비행 타입 비율
    type_rows = await pool.fetch(
        "SELECT pm.id, pm.rarity FROM battle_teams bt "
        "JOIN user_pokemon up ON up.id = bt.pokemon_instance_id "
        "JOIN pokemon_master pm ON up.pokemon_id = pm.id "
        "WHERE bt.team_number = 1"
    )
    water_fly = 0
    total = 0
    for r in type_rows:
        bs = POKEMON_BASE_STATS.get(r[0])
        if not bs or len(bs) <= 6: continue
        types = bs[6]
        total += 1
        if 'water' in types or 'flying' in types:
            water_fly += 1
    print(f"  전체 배틀팀 포켓몬 중 물/비행 타입: {water_fly}/{total} ({water_fly/total*100:.0f}%)")
    print(f"  → 썬더(전기)가 상성 유리한 대상이 {water_fly/total*100:.0f}%")

asyncio.run(main())
