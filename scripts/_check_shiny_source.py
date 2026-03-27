"""이로치 포획 소스 추적."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

async def main():
    from database.connection import get_db
    pool = await get_db()

    # spawn_log 컬럼
    sl_cols = await pool.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'spawn_log' ORDER BY ordinal_position")
    print("spawn_log 컬럼:", [r["column_name"] for r in sl_cols])

    ss_cols = await pool.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'spawn_sessions' ORDER BY ordinal_position")
    print("spawn_sessions 컬럼:", [r["column_name"] for r in ss_cols])

    # spawn_log에 있는 이로치 vs user_pokemon 이로치
    in_spawn = await pool.fetchval("""
        SELECT COUNT(*) FROM spawn_log
        WHERE is_shiny = 1 AND caught_by_user_id IS NOT NULL
          AND spawned_at >= NOW() - INTERVAL '7 days'
    """)
    total_shiny = await pool.fetchval("""
        SELECT COUNT(*) FROM user_pokemon
        WHERE is_shiny = 1 AND caught_at >= NOW() - INTERVAL '7 days'
    """)
    print(f"\nspawn_log 이로치: {in_spawn}")
    print(f"user_pokemon 이로치: {total_shiny}")
    print(f"차이(spawn_log 밖): {total_shiny - in_spawn}")

    # caught_in_chat_id 분포
    chat_stats = await pool.fetch("""
        SELECT
            CASE WHEN caught_in_chat_id IS NULL THEN 'NULL(DM/강스?)' ELSE 'GROUP' END as src,
            COUNT(*) as cnt
        FROM user_pokemon
        WHERE is_shiny = 1 AND caught_at >= NOW() - INTERVAL '7 days'
        GROUP BY src
    """)
    print("\ncaught_in_chat_id 분포:")
    for r in chat_stats:
        print(f"  {r['src']}: {r['cnt']}")

    # PEPECAT 보만다 — caught_in_chat_id 확인
    rows = await pool.fetch("""
        SELECT up.caught_at AT TIME ZONE 'Asia/Seoul' as t,
               up.caught_in_chat_id, cr.chat_title, pm.name_ko
        FROM user_pokemon up
        JOIN pokemon_master pm ON up.pokemon_id = pm.id
        LEFT JOIN chat_rooms cr ON up.caught_in_chat_id = cr.chat_id
        WHERE up.user_id = (SELECT user_id FROM users WHERE display_name LIKE 'PEPECAT%' LIMIT 1)
          AND up.is_shiny = 1 AND pm.name_ko = '보만다'
          AND up.caught_at >= NOW() - INTERVAL '7 days'
        ORDER BY up.caught_at LIMIT 25
    """)
    print("\nPEPECAT 보만다 이로치:")
    for r in rows:
        chat = (r["chat_title"] or "NULL")[:25]
        print(f"  [{r['t'].strftime('%m/%d %H:%M')}] chat={chat}")

    # 강스 세션 확인
    forced_check = await pool.fetch("""
        SELECT ss.is_forced, ss.pokemon_id, pm.name_ko, COUNT(*) as cnt
        FROM spawn_sessions ss
        JOIN spawn_log sl ON sl.spawn_session_id = ss.id
        JOIN pokemon_master pm ON ss.pokemon_id = pm.id
        WHERE sl.is_shiny = 1 AND sl.caught_by_user_id IS NOT NULL
          AND sl.spawned_at >= NOW() - INTERVAL '7 days'
        GROUP BY ss.is_forced, ss.pokemon_id, pm.name_ko
        ORDER BY cnt DESC LIMIT 20
    """)
    print("\n이로치 by is_forced & 포켓몬:")
    for r in forced_check:
        label = "강스" if r["is_forced"] else "자연"
        print(f"  [{label}] {r['name_ko']:10} {r['cnt']}마리")

asyncio.run(main())
