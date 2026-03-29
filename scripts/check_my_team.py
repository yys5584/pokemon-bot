import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
from database.connection import get_db

UID = 1832746512

async def main():
    pool = await get_db()

    rows = await pool.fetch("""
        SELECT up.id, up.pokemon_id, pm.name_ko, pm.rarity, pm.pokemon_type,
               up.friendship, up.is_shiny,
               COALESCE(up.iv_hp,0)+COALESCE(up.iv_atk,0)+COALESCE(up.iv_def,0)+
               COALESCE(up.iv_spa,0)+COALESCE(up.iv_spdef,0)+COALESCE(up.iv_spd,0) as iv_total
        FROM user_pokemon up
        JOIN pokemon_master pm ON up.pokemon_id = pm.id
        WHERE up.user_id = $1 AND up.is_active = 1
        ORDER BY
            CASE pm.rarity
                WHEN 'ultra_legendary' THEN 1 WHEN 'legendary' THEN 2
                WHEN 'epic' THEN 3 WHEN 'rare' THEN 4 ELSE 5 END,
            iv_total DESC
    """, UID)

    print(f"Total: {len(rows)}")
    for r in rows[:30]:
        iv = r["iv_total"] or 0
        sh = "*" if r["is_shiny"] else " "
        g = "S" if iv >= 160 else "A" if iv >= 120 else "B" if iv >= 93 else "C" if iv >= 62 else "D"
        print(f"  {sh} #{r['pokemon_id']:>3} {r['name_ko']:<8} {r['rarity']:<17} [{g}]{iv:>4} f{r['friendship']} {r['pokemon_type']}")

    teams = await pool.fetch("""
        SELECT bt.team_num, bt.slot, pm.name_ko, pm.rarity, pm.pokemon_type,
               COALESCE(up.iv_hp,0)+COALESCE(up.iv_atk,0)+COALESCE(up.iv_def,0)+
               COALESCE(up.iv_spa,0)+COALESCE(up.iv_spdef,0)+COALESCE(up.iv_spd,0) as iv_total
        FROM battle_teams bt
        JOIN user_pokemon up ON bt.pokemon_instance_id = up.id
        JOIN pokemon_master pm ON up.pokemon_id = pm.id
        WHERE bt.user_id = $1 ORDER BY bt.team_num, bt.slot
    """, UID)
    print()
    print("=== Current Teams ===")
    for t in teams:
        print(f"  T{t['team_num']}S{t['slot']}: {t['name_ko']} ({t['rarity']}) IV{t['iv_total'] or 0} {t['pokemon_type']}")

asyncio.run(main())
