import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
import asyncpg

async def main():
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL'], statement_cache_size=0)

    rows = await pool.fetch('''
        SELECT u.user_id, u.username, u.display_name, u.battle_points as bp, u.master_balls,
            u.battle_wins, u.battle_losses, u.iv_stones, u.universal_fragments,
            u.dungeon_best_floor, u.hyper_balls,
            (SELECT COUNT(*) FROM user_pokemon up WHERE up.user_id = u.user_id AND up.is_active = 1) as total_pokemon,
            (SELECT COUNT(*) FROM user_pokemon up WHERE up.user_id = u.user_id AND up.is_active = 1 AND up.is_shiny = 1) as shiny_count,
            (SELECT COUNT(DISTINCT up.pokemon_id) FROM user_pokemon up WHERE up.user_id = u.user_id AND up.is_active = 1) as unique_pokemon
        FROM users u
        WHERE u.battle_wins > 0 OR (SELECT COUNT(*) FROM user_pokemon up WHERE up.user_id = u.user_id AND up.is_active = 1) > 10
        ORDER BY (SELECT COUNT(*) FROM user_pokemon up WHERE up.user_id = u.user_id AND up.is_active = 1) DESC
        LIMIT 30
    ''')

    print(f"{'유저':20s} | {'포켓':>5s} {'이로치':>5s} {'도감':>4s} | {'BP':>7s} {'마볼':>4s} {'IV돌':>4s} {'조각':>4s} | {'승':>5s} {'패':>5s} {'승률':>5s} | {'던전':>4s}")
    print("-" * 110)
    for r in rows:
        name = r['username'] or r['display_name'] or '?'
        total_battles = r['battle_wins'] + r['battle_losses']
        wr = r['battle_wins'] / max(total_battles, 1) * 100
        df = r['dungeon_best_floor'] or 0
        iv = r['iv_stones'] or 0
        frags = r['universal_fragments'] or 0
        print(f"{name:20s} | {r['total_pokemon']:>5d} {r['shiny_count']:>5d} {r['unique_pokemon']:>4d} | {r['bp']:>7d} {r['master_balls']:>4d} {iv:>4d} {frags:>4d} | {r['battle_wins']:>5d} {r['battle_losses']:>5d} {wr:>4.0f}% | {df:>4d}F")

    # 등급별 이로치 보유 현황
    print("\n\n=== 상위 10명 등급별 이로치 보유 ===")
    top_ids = [r['user_id'] for r in rows[:10]]
    for uid in top_ids:
        name_row = await pool.fetchrow("SELECT username, display_name FROM users WHERE user_id = $1", uid)
        name = name_row['username'] or name_row['display_name']
        grade_rows = await pool.fetch('''
            SELECT p.grade, COUNT(*) as cnt
            FROM user_pokemon up
            JOIN pokemon p ON up.pokemon_id = p.id
            WHERE up.user_id = $1 AND up.is_active = 1 AND up.is_shiny = 1
            GROUP BY p.grade
            ORDER BY CASE p.grade
                WHEN 'ultra_legendary' THEN 5
                WHEN 'legendary' THEN 4
                WHEN 'epic' THEN 3
                WHEN 'rare' THEN 2
                WHEN 'common' THEN 1
            END DESC
        ''', uid)
        grades = {r['grade']: r['cnt'] for r in grade_rows}
        ul = grades.get('ultra_legendary', 0)
        lg = grades.get('legendary', 0)
        ep = grades.get('epic', 0)
        ra = grades.get('rare', 0)
        co = grades.get('common', 0)
        print(f"{name:20s} | 초전설{ul:>3d} 전설{lg:>3d} 에픽{ep:>3d} 레어{ra:>3d} 일반{co:>3d}")

    await pool.close()

asyncio.run(main())
