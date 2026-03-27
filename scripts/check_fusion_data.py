import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv('/home/ubuntu/pokemon-bot/.env')

async def main():
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'), statement_cache_size=0)
    uid = 1832746512

    # Species with 2+ active copies
    rows = await conn.fetch(
        """SELECT pm.name_ko, up.pokemon_id, COUNT(*) as cnt
           FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.user_id = $1 AND up.is_active = 1
           GROUP BY pm.name_ko, up.pokemon_id
           HAVING COUNT(*) >= 2
           ORDER BY COUNT(*) DESC""",
        uid,
    )
    print("=== Species with 2+ copies ===")
    for r in rows:
        print(f"  {r['name_ko']} (id={r['pokemon_id']}) x{r['cnt']}")

    # Battle team details
    protected = await conn.fetch(
        """SELECT bt.pokemon_instance_id, pm.name_ko, bt.team_number, bt.slot
           FROM battle_teams bt
           JOIN user_pokemon up ON up.id = bt.pokemon_instance_id
           JOIN pokemon_master pm ON pm.id = up.pokemon_id
           WHERE bt.user_id = $1
           ORDER BY bt.team_number, bt.slot""",
        uid,
    )
    print("\n=== Battle team members ===")
    for r in protected:
        print(f"  Team{r['team_number']} Slot{r['slot']}: {r['name_ko']} (instance={r['pokemon_instance_id']})")

    # Protected IDs
    prot = await conn.fetch(
        """SELECT pokemon_instance_id AS pid FROM battle_teams WHERE user_id = $1
           UNION
           SELECT partner_pokemon_id FROM users WHERE user_id = $1 AND partner_pokemon_id IS NOT NULL
           UNION
           SELECT pokemon_instance_id FROM market_listings WHERE seller_id = $1 AND status = 'active'
           UNION
           SELECT offer_pokemon_instance_id FROM trades WHERE from_user_id = $1 AND status = 'pending'""",
        uid,
    )
    pids = {r['pid'] for r in prot if r['pid'] is not None}
    print(f"\n=== All protected instance_ids ({len(pids)}) ===")
    print(sorted(pids))

    # For each species with 2+, check which are protected/favorited
    for r in rows:
        pid = r['pokemon_id']
        copies = await conn.fetch(
            """SELECT up.id, up.is_favorite, up.is_shiny
               FROM user_pokemon up
               WHERE up.user_id = $1 AND up.pokemon_id = $2 AND up.is_active = 1""",
            uid, pid,
        )
        protected_copies = [c for c in copies if c['id'] in pids]
        fav_copies = [c for c in copies if c['is_favorite']]
        free = [c for c in copies if c['id'] not in pids and not c['is_favorite']]
        if len(free) < 2:
            print(f"\n  !! {r['name_ko']}: {len(copies)} total, {len(protected_copies)} protected, {len(fav_copies)} fav, {len(free)} fusable -> CAN'T FUSE")

    await conn.close()

asyncio.run(main())
