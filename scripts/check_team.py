import asyncio, os, asyncpg
from dotenv import load_dotenv
load_dotenv()

async def main():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)

    teams = await conn.fetch("""
        SELECT t.team_number, t.slot, up.id, p.name_ko, p.rarity,
               up.is_shiny, up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd
        FROM battle_teams t
        JOIN user_pokemon up ON t.pokemon_instance_id = up.id
        JOIN pokemon_master p ON up.pokemon_id = p.id
        WHERE t.user_id = 1832746512
        ORDER BY t.team_number, t.slot
    """)
    print("=== 현재 팀 ===")
    for t in teams:
        iv = t["iv_hp"]+t["iv_atk"]+t["iv_def"]+t["iv_spa"]+t["iv_spdef"]+t["iv_spd"]
        sh = "✨" if t["is_shiny"] else ""
        print(f"  팀{t['team_number']} 슬롯{t['slot']}: {sh}{t['name_ko']} [{t['rarity']}] IV:{iv}/186 (id:{t['id']})")

    print()
    print("=== 보유 마기라스 계열 ===")
    magis = await conn.fetch("""
        SELECT up.id, p.name_ko, up.is_shiny,
               up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd
        FROM user_pokemon up
        JOIN pokemon_master p ON up.pokemon_id = p.id
        WHERE up.user_id = 1832746512 AND p.name_ko IN ('마기라스', '애버라스', '데기라스')
        ORDER BY (up.iv_hp+up.iv_atk+up.iv_def+up.iv_spa+up.iv_spdef+up.iv_spd) DESC
    """)
    for m in magis:
        iv = m["iv_hp"]+m["iv_atk"]+m["iv_def"]+m["iv_spa"]+m["iv_spdef"]+m["iv_spd"]
        sh = "✨" if m["is_shiny"] else ""
        print(f"  {sh}{m['name_ko']} IV:{iv}/186 (id:{m['id']})")

    await conn.close()

asyncio.run(main())
