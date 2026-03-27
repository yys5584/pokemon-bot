"""Check current battle meta - top rankers and their teams."""
import asyncio
import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

async def main():
    from database.connection import get_db
    pool = await get_db()

    # Top 10 rankers and their teams
    rows = await pool.fetch("""
        SELECT u.user_id, u.display_name, u.battle_wins, u.battle_losses, u.battle_points,
               pm.name_ko, pm.rarity, pm.pokemon_type, up.is_shiny,
               pm.id as pokemon_id, bt.slot
        FROM users u
        JOIN battle_teams bt ON bt.user_id = u.user_id
        JOIN user_pokemon up ON bt.pokemon_instance_id = up.id
        JOIN pokemon_master pm ON up.pokemon_id = pm.id
        WHERE u.battle_points > 0 OR u.battle_wins > 0
        ORDER BY u.battle_points DESC, u.battle_wins DESC, bt.slot ASC
        LIMIT 80
    """)

    current_user = None
    count = 0
    for r in rows:
        if r["user_id"] != current_user:
            current_user = r["user_id"]
            count += 1
            if count > 10:
                break
            print(f"\n=== {r['display_name']} (W{r['battle_wins']}/L{r['battle_losses']} BP:{r['battle_points']}) ===")
        shiny = " SHINY" if r["is_shiny"] else ""
        print(f"  #{r['pokemon_id']:03d} {r['name_ko']}{shiny} [{r['rarity']}] ({r['pokemon_type']}) slot:{r['slot']}")

    # Type frequency across all rankers with teams
    type_rows = await pool.fetch("""
        SELECT pm.pokemon_type, COUNT(*) as cnt
        FROM users u
        JOIN battle_teams bt ON bt.user_id = u.user_id
        JOIN user_pokemon up ON bt.pokemon_instance_id = up.id
        JOIN pokemon_master pm ON up.pokemon_id = pm.id
        WHERE u.battle_points > 100
        GROUP BY pm.pokemon_type
        ORDER BY cnt DESC
    """)
    print("\n\n== Type Distribution (BP>100 rankers) ==")
    for r in type_rows:
        print(f"  {r['pokemon_type']}: {r['cnt']}")

    # Most used Pokemon
    poke_rows = await pool.fetch("""
        SELECT pm.name_ko, pm.rarity, pm.pokemon_type, pm.id as pokemon_id,
               COUNT(*) as usage
        FROM battle_teams bt
        JOIN user_pokemon up ON bt.pokemon_instance_id = up.id
        JOIN pokemon_master pm ON up.pokemon_id = pm.id
        GROUP BY pm.id, pm.name_ko, pm.rarity, pm.pokemon_type
        ORDER BY usage DESC
        LIMIT 25
    """)
    print("\n\n== Most Used Pokemon ==")
    for r in poke_rows:
        print(f"  #{r['pokemon_id']:03d} {r['name_ko']} [{r['rarity']}] ({r['pokemon_type']}) x{r['usage']}")

asyncio.run(main())
