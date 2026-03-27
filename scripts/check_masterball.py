"""Check recent master ball usage and find users who lost their ball."""
import asyncio, asyncpg, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

async def check():
    pool = await asyncpg.create_pool(
        os.getenv("DATABASE_URL"),
        statement_cache_size=0,
    )

    rows = await pool.fetch("""
        SELECT ca.user_id, ca.session_id,
               ca.used_master_ball, ca.attempted_at,
               ss.is_resolved, ss.caught_by_user_id, ss.pokemon_id,
               ss.spawned_at,
               pm.name_ko,
               u.display_name
        FROM catch_attempts ca
        JOIN spawn_sessions ss ON ca.session_id = ss.id
        JOIN pokemon_master pm ON ss.pokemon_id = pm.id
        LEFT JOIN users u ON ca.user_id = u.user_id
        WHERE ca.used_master_ball = 1
          AND ss.spawned_at > NOW() - INTERVAL '4 hours'
        ORDER BY ss.spawned_at DESC
    """)

    if not rows:
        print("최근 4시간 내 마볼 사용 없음")
        await pool.close()
        return

    print(f"=== 마볼 사용 내역 (최근 4시간, {len(rows)}건) ===")
    for r in rows:
        won = "WIN" if r["caught_by_user_id"] == r["user_id"] else "LOST"
        resolved = "resolved" if r["is_resolved"] == 1 else "UNRESOLVED"
        name = r["display_name"] or "?"
        print(f"  {name} (id:{r['user_id']}) | {r['name_ko']} | session:{r['session_id']} | {won} | {resolved} | {r['attempted_at']}")

    lost = [r for r in rows if r["caught_by_user_id"] != r["user_id"]]
    if lost:
        print(f"\n=== 마볼 씹힌 사람 ({len(lost)}명) ===")
        for r in lost:
            name = r["display_name"] or "?"
            mb = await pool.fetchval("SELECT master_balls FROM users WHERE user_id = $1", r["user_id"])
            print(f"  {name} (id:{r['user_id']}) - {r['name_ko']} session:{r['session_id']} | 현재 마볼: {mb}개")
    else:
        print("\n마볼 씹힌 사람 없음 (전원 포획 성공)")

    await pool.close()

asyncio.run(check())
