import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv('/home/ubuntu/pokemon-bot/.env')

async def main():
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'), statement_cache_size=0)
    uid = 1832746512

    # Find all Lugia
    rows = await conn.fetch(
        """SELECT up.id, up.pokemon_id, pm.name_ko, up.is_active, up.is_favorite,
                  bt.slot AS team_slot, bt.team_number AS team_num
           FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           LEFT JOIN battle_teams bt ON bt.pokemon_instance_id = up.id
           WHERE up.user_id = $1 AND pm.name_ko = '루기아' AND up.is_active = 1""",
        uid,
    )
    print("=== Lugia instances ===")
    for r in rows:
        print(f"  instance_id={r['id']} pokemon_id={r['pokemon_id']} fav={r['is_favorite']} team={r['team_num']} slot={r['team_slot']}")

    # Get protected ids
    protected = await conn.fetch(
        """SELECT pokemon_instance_id AS pid FROM battle_teams WHERE user_id = $1
           UNION
           SELECT partner_pokemon_id FROM users WHERE user_id = $1 AND partner_pokemon_id IS NOT NULL
           UNION
           SELECT pokemon_instance_id FROM market_listings WHERE seller_id = $1 AND status = 'active'
           UNION
           SELECT offer_pokemon_instance_id FROM trades WHERE from_user_id = $1 AND status = 'pending'""",
        uid,
    )
    pids = {r['pid'] for r in protected if r['pid'] is not None}
    print(f"\n=== Protected instance_ids ({len(pids)}) ===")
    print(pids)

    await conn.close()

asyncio.run(main())
