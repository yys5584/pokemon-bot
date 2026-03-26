"""중복 지급된 이로치 11건 비활성화 (is_active=0)."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
from database.connection import get_db

DUPE_IDS = [144921, 144922, 144923, 144924, 144925, 144926, 144927, 144928, 144929, 144930, 144931]

async def main():
    pool = await get_db()
    result = await pool.execute(
        "UPDATE user_pokemon SET is_active = 0 WHERE id = ANY($1)", DUPE_IDS
    )
    print(f"비활성화 완료: {result}")

    # 배틀팀에 들어있으면 제거
    result2 = await pool.execute(
        "DELETE FROM battle_teams WHERE pokemon_instance_id = ANY($1)", DUPE_IDS
    )
    print(f"배틀팀 제거: {result2}")

asyncio.run(main())
