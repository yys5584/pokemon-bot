import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
import asyncpg

async def main():
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL'], statement_cache_size=0)
    rows = await pool.fetch("""
        SELECT u.username, u.display_name,
            COUNT(*) FILTER (WHERE p.rarity = 'common') as common,
            COUNT(*) FILTER (WHERE p.rarity = 'rare') as rare,
            COUNT(*) FILTER (WHERE p.rarity = 'epic') as epic,
            COUNT(*) FILTER (WHERE p.rarity = 'legendary') as legendary,
            COUNT(*) FILTER (WHERE p.rarity = 'ultra_legendary') as ultra,
            COUNT(*) FILTER (WHERE up.is_shiny > 0) as shiny,
            COUNT(*) as total
        FROM users u
        JOIN user_pokemon up ON up.user_id = u.user_id AND up.is_active = 1
        JOIN pokemon_master p ON p.id = up.pokemon_id
        GROUP BY u.user_id, u.username, u.display_name
        ORDER BY COUNT(*) DESC
        LIMIT 15
    """)
    header = f"{'유저':15s} {'일반':>5s} {'레어':>5s} {'에픽':>5s} {'전설':>5s} {'초전':>5s} {'이로':>5s} {'합계':>5s}"
    print(header)
    print('-' * 70)
    for r in rows:
        name = (r['username'] or r['display_name'] or '?')[:15]
        print(f"{name:15s} {r['common']:5d} {r['rare']:5d} {r['epic']:5d} {r['legendary']:5d} {r['ultra']:5d} {r['shiny']:5d} {r['total']:5d}")
    await pool.close()

asyncio.run(main())
