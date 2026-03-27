import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
import asyncpg

async def main():
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL'], statement_cache_size=0)

    rows = await pool.fetch('''
        WITH top_users AS (
            SELECT u.user_id, u.username, u.display_name
            FROM users u
            ORDER BY (SELECT COUNT(*) FROM user_pokemon up WHERE up.user_id = u.user_id AND up.is_active = 1) DESC
            LIMIT 15
        )
        SELECT tu.username, tu.display_name, pm.rarity,
            SUM(CASE WHEN up.is_shiny = 0 THEN 1 ELSE 0 END) as normal_cnt,
            SUM(CASE WHEN up.is_shiny = 1 THEN 1 ELSE 0 END) as shiny_cnt
        FROM top_users tu
        JOIN user_pokemon up ON up.user_id = tu.user_id AND up.is_active = 1
        JOIN pokemon_master pm ON pm.id = up.pokemon_id
        GROUP BY tu.username, tu.display_name, pm.rarity
        ORDER BY tu.username, pm.rarity
    ''')

    # 유저별로 그룹핑
    from collections import defaultdict
    users = defaultdict(dict)
    for r in rows:
        name = r['username'] or r['display_name']
        rarity = r['rarity']
        users[name][rarity] = {'normal': r['normal_cnt'], 'shiny': r['shiny_cnt']}

    print(f"{'유저':20s} | {'일반':>12s} | {'레어':>12s} | {'에픽':>12s} | {'전설':>12s} | {'초전설':>12s} | {'총':>5s}")
    print("-" * 110)
    for name, grades in sorted(users.items(), key=lambda x: sum(v['normal']+v['shiny'] for v in x[1].values()), reverse=True):
        parts = []
        total = 0
        for g in ['common', 'rare', 'epic', 'legendary', 'ultra_legendary']:
            d = grades.get(g, {'normal': 0, 'shiny': 0})
            n, s = d['normal'], d['shiny']
            total += n + s
            parts.append(f"{n:>4d}+{s:<3d}✨")
        print(f"{name:20s} | {' | '.join(parts)} | {total:>5d}")

    await pool.close()

asyncio.run(main())
