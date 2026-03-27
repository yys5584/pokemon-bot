import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

async def main():
    from database.connection import get_db
    pool = await get_db()

    all_ultra = [
        (385,'지라치'), (386,'테오키스'), (490,'마나피'), (491,'다크라이'), (492,'쉐이미'),
        (150,'뮤츠'), (382,'가이오가'), (384,'레쿠쟈'), (483,'디아루가'), (484,'펄기아'),
        (249,'루기아'), (250,'칠색조'), (487,'기라티나'), (493,'아르세우스'), (383,'그란돈'),
    ]

    print(f'  {"이름":<10} {"BST":>4} {"랭크전":>6} {"avg딜":>6} {"K/D":>5} {"승률":>5} {"팀등록":>5}')
    print('='*55)

    for pid, name in all_ultra:
        row = await pool.fetchrow(
            "SELECT COUNT(*) as bat, ROUND(AVG(damage_dealt)) as dmg, "
            "ROUND(AVG(kills)::numeric,2) as k, ROUND(AVG(deaths)::numeric,2) as d, "
            "SUM(CASE WHEN won THEN 1 ELSE 0 END) as w "
            "FROM battle_pokemon_stats WHERE pokemon_id = $1",
            pid
        )
        bat = row[0] or 0
        dmg = row[1] or 0
        k = float(row[2] or 0)
        d = max(float(row[3] or 0), 0.01)
        kd = k / d
        wr = (row[4] or 0) / max(bat, 1) * 100

        team_cnt = await pool.fetchval(
            "SELECT COUNT(DISTINCT bt.user_id) FROM battle_teams bt "
            "JOIN user_pokemon up ON up.id = bt.pokemon_instance_id "
            "WHERE up.pokemon_id = $1",
            pid
        )

        from models.pokemon_base_stats import POKEMON_BASE_STATS
        bs = POKEMON_BASE_STATS.get(pid)
        bst = sum(bs[:6]) if bs else 0

        marker = " ←하위" if bst <= 600 else ""
        print(f'  {name:<10} {bst:>4} {bat:>6} {dmg:>6} {kd:>5.1f} {wr:>4.0f}% {team_cnt:>5}명{marker}')

asyncio.run(main())
