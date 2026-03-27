"""특정 유저 보상 지급 확인."""
import asyncio, asyncpg, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

async def main():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"), statement_cache_size=0)

    # 딸딸기
    row = await conn.fetchrow("SELECT user_id, display_name FROM users WHERE username = 'holysouling'")
    if not row:
        print("유저 없음")
        return
    uid = row["user_id"]
    print(f"유저: {row['display_name']} (id={uid})")

    # IV스톤
    item = await conn.fetchrow("SELECT quantity FROM user_items WHERE user_id = $1 AND item_type = 'iv_stone_3'", uid)
    print(f"IV+3 스톤 보유: {item['quantity'] if item else 0}개")

    # 이로치 킹드라
    poke = await conn.fetchrow("SELECT id, pokemon_id, is_shiny, caught_at FROM user_pokemon WHERE user_id = $1 AND pokemon_id = 230 AND is_shiny = 1", uid)
    if poke:
        print(f"이로치 킹드라: id={poke['id']} shiny={poke['is_shiny']} caught={poke['caught_at']}")
    else:
        print("이로치 킹드라: 없음")

    # 최근 추가된 포켓몬 (id 143000+)
    recent = await conn.fetch("SELECT up.id, up.pokemon_id, pm.name_ko, up.is_shiny FROM user_pokemon up JOIN pokemon_master pm ON up.pokemon_id = pm.id WHERE up.user_id = $1 AND up.id >= 143270 ORDER BY up.id", uid)
    print(f"\n최근 지급 포켓몬:")
    for r in recent:
        print(f"  id={r['id']} {r['name_ko']} shiny={r['is_shiny']}")

    await conn.close()

asyncio.run(main())
