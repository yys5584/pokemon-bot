"""Battle meta analysis script - one-time use."""
import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv("/home/ubuntu/pokemon-bot/.env")

async def main():
    pool = await asyncpg.create_pool(os.environ.get("DATABASE_URL"), statement_cache_size=0)

    print("=== ZERO_EPIC ===")
    rows = await pool.fetch("""
        SELECT bps.pokemon_id, pm.name_ko,
               COUNT(*) AS uses,
               COUNT(DISTINCT bps.user_id) AS unique_users,
               SUM(CASE WHEN bps.won THEN 1 ELSE 0 END) AS wins,
               ROUND(AVG(bps.damage_dealt)) AS avg_dmg,
               ROUND(AVG(bps.turns_alive)::numeric, 1) AS avg_turns,
               ROUND(AVG(bps.kills)::numeric, 2) AS avg_kills
        FROM battle_pokemon_stats bps
        JOIN pokemon_master pm ON bps.pokemon_id = pm.id
        WHERE bps.pokemon_id IN (196, 38, 130, 254, 169, 73, 6, 135, 257, 217, 55, 350, 131, 78, 127)
        GROUP BY bps.pokemon_id, pm.name_ko
        ORDER BY uses DESC
    """)
    for r in rows:
        print(f"{r[0]}|{r[1]}|uses={r[2]}|users={r[3]}|wins={r[4]}|dmg={r[5]}|turns={r[6]}|K={r[7]}")

    print("=== OVERPERFORM ===")
    rows = await pool.fetch("""
        SELECT bps.pokemon_id, pm.name_ko,
               COUNT(*) AS uses,
               COUNT(DISTINCT bps.user_id) AS unique_users,
               SUM(CASE WHEN bps.won THEN 1 ELSE 0 END) AS wins,
               ROUND(AVG(bps.damage_dealt)) AS avg_dmg,
               ROUND(AVG(bps.turns_alive)::numeric, 1) AS avg_turns
        FROM battle_pokemon_stats bps
        JOIN pokemon_master pm ON bps.pokemon_id = pm.id
        WHERE bps.pokemon_id IN (85, 36, 141, 190, 83, 228, 81, 303)
        GROUP BY bps.pokemon_id, pm.name_ko
        ORDER BY uses DESC
    """)
    for r in rows:
        print(f"{r[0]}|{r[1]}|uses={r[2]}|users={r[3]}|wins={r[4]}|dmg={r[5]}|turns={r[6]}")

    # 전설/초전설 저승률
    print("=== LEGEND_LOW ===")
    rows = await pool.fetch("""
        SELECT bps.pokemon_id, pm.name_ko, bps.rarity,
               COUNT(*) AS uses,
               COUNT(DISTINCT bps.user_id) AS unique_users,
               SUM(CASE WHEN bps.won THEN 1 ELSE 0 END) AS wins,
               ROUND(100.0 * SUM(CASE WHEN bps.won THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) AS win_rate,
               ROUND(AVG(bps.damage_dealt)) AS avg_dmg
        FROM battle_pokemon_stats bps
        JOIN pokemon_master pm ON bps.pokemon_id = pm.id
        WHERE bps.rarity IN ('legendary','ultra_legendary')
        GROUP BY bps.pokemon_id, pm.name_ko, bps.rarity
        HAVING COUNT(*) >= 3
        ORDER BY win_rate ASC
    """)
    for r in rows:
        print(f"{r[0]}|{r[1]}|{r[2]}|uses={r[3]}|users={r[4]}|wins={r[5]}|wr={r[6]}|dmg={r[7]}")

    await pool.close()

asyncio.run(main())
