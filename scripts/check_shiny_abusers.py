"""Check shiny-selective catching patterns for suspected abusers."""
import asyncio
from database.connection import get_db, close_db


TARGETS = {
    7437353379: "Keepgoing",
    # 딸딸기, Yun — user_id 모르면 이름으로 검색
}


async def check():
    pool = await get_db()

    # 먼저 딸딸기, Yun user_id 찾기
    extra = await pool.fetch(
        "SELECT user_id, display_name, username FROM users "
        "WHERE display_name ILIKE '%딸딸기%' OR display_name ILIKE '%Yun%' "
        "OR username ILIKE '%yun%'"
    )
    for r in extra:
        TARGETS[r["user_id"]] = r["display_name"]

    print(f"=== Targets: {TARGETS}\n")

    for uid, name in TARGETS.items():
        print(f"── {name} (uid={uid}) ──")

        # 7일간 포획 통계
        stats = await pool.fetchrow("""
            SELECT
                COUNT(*) as total_catches,
                COUNT(CASE WHEN ss.is_shiny = 1 THEN 1 END) as shiny_catches,
                COUNT(CASE WHEN ca.used_master_ball = 1 THEN 1 END) as master_used,
                COUNT(CASE WHEN ca.used_hyper_ball = 1 THEN 1 END) as hyper_used
            FROM catch_attempts ca
            JOIN spawn_sessions ss ON ca.session_id = ss.id
            WHERE ca.user_id = $1
              AND ca.attempted_at > NOW() - interval '7 days'
        """, uid)

        total = stats["total_catches"] or 0
        shiny = stats["shiny_catches"] or 0
        master = stats["master_used"] or 0
        hyper = stats["hyper_used"] or 0
        ratio = (shiny / total * 100) if total > 0 else 0
        print(f"  7일: 총 {total}건, 이로치 {shiny}건 ({ratio:.1f}%), 마볼 {master}, 하볼 {hyper}")

        # 24시간 포획 통계
        stats24 = await pool.fetchrow("""
            SELECT
                COUNT(*) as total_catches,
                COUNT(CASE WHEN ss.is_shiny = 1 THEN 1 END) as shiny_catches
            FROM catch_attempts ca
            JOIN spawn_sessions ss ON ca.session_id = ss.id
            WHERE ca.user_id = $1
              AND ca.attempted_at > NOW() - interval '24 hours'
        """, uid)
        t24 = stats24["total_catches"] or 0
        s24 = stats24["shiny_catches"] or 0
        r24 = (s24 / t24 * 100) if t24 > 0 else 0
        print(f"  24h: 총 {t24}건, 이로치 {s24}건 ({r24:.1f}%)")

        # 이로치 스폰 시 포획 성공률 vs 일반 포켓몬
        shiny_spawn_catch = await pool.fetchrow("""
            SELECT
                COUNT(*) as shiny_spawns,
                COUNT(CASE WHEN ss.caught_by_user_id = $1 THEN 1 END) as caught_by_me
            FROM spawn_sessions ss
            JOIN catch_attempts ca ON ca.session_id = ss.id AND ca.user_id = $1
            WHERE ss.is_shiny = 1
              AND ss.spawned_at > NOW() - interval '7 days'
        """, uid)
        normal_spawn_catch = await pool.fetchrow("""
            SELECT
                COUNT(*) as normal_spawns,
                COUNT(CASE WHEN ss.caught_by_user_id = $1 THEN 1 END) as caught_by_me
            FROM spawn_sessions ss
            JOIN catch_attempts ca ON ca.session_id = ss.id AND ca.user_id = $1
            WHERE ss.is_shiny = 0
              AND ss.spawned_at > NOW() - interval '7 days'
        """, uid)
        sc = shiny_spawn_catch
        nc = normal_spawn_catch
        s_rate = (sc["caught_by_me"] / sc["shiny_spawns"] * 100) if sc["shiny_spawns"] else 0
        n_rate = (nc["caught_by_me"] / nc["normal_spawns"] * 100) if nc["normal_spawns"] else 0
        print(f"  이로치 시도 {sc['shiny_spawns']}건 중 포획 {sc['caught_by_me']}건 ({s_rate:.1f}%)")
        print(f"  일반 시도 {nc['normal_spawns']}건 중 포획 {nc['caught_by_me']}건 ({n_rate:.1f}%)")

        # 시간대별 포획 분포 (봇은 24시간 활동)
        hourly = await pool.fetch("""
            SELECT EXTRACT(HOUR FROM ca.attempted_at AT TIME ZONE 'Asia/Seoul') as hr,
                   COUNT(*) as cnt
            FROM catch_attempts ca
            WHERE ca.user_id = $1
              AND ca.attempted_at > NOW() - interval '7 days'
            GROUP BY hr ORDER BY hr
        """, uid)
        print(f"  시간대별(KST): ", end="")
        for h in hourly:
            print(f"{int(h['hr'])}시={h['cnt']}", end=" ")
        print()
        print()

    await close_db()


asyncio.run(check())
