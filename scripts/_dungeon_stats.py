"""던전 플레이 데이터 분석 — 대개편 기획용."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

async def main():
    from database.connection import get_db
    pool = await get_db()

    print("=" * 60)
    print("🏰 던전 플레이 데이터 분석")
    print("=" * 60)

    # 테이블 존재 확인
    tables = await pool.fetch("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name LIKE 'dungeon%' ORDER BY table_name
    """)
    print("\n던전 테이블:", [r['table_name'] for r in tables])

    if not any(r['table_name'] == 'dungeon_runs' for r in tables):
        print("dungeon_runs 테이블 없음!")
        return

    # 컬럼 확인
    cols = await pool.fetch("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'dungeon_runs' ORDER BY ordinal_position
    """)
    print("dungeon_runs 컬럼:", [r['column_name'] for r in cols])

    # 1. 전체 통계
    total = await pool.fetchrow("""
        SELECT COUNT(*) as runs,
               COUNT(DISTINCT user_id) as users,
               AVG(floor_reached) as avg_floor,
               MAX(floor_reached) as max_floor,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY floor_reached) as median_floor
        FROM dungeon_runs
    """)
    print(f"\n📊 전체: {total['runs']}런, {total['users']}명, 평균 {total['avg_floor']:.1f}층, 중앙값 {int(total['median_floor'])}층, 최고 {total['max_floor']}층")

    # 2. 최근 7일 통계
    recent = await pool.fetchrow("""
        SELECT COUNT(*) as runs,
               COUNT(DISTINCT user_id) as users,
               AVG(floor_reached) as avg_floor,
               MAX(floor_reached) as max_floor
        FROM dungeon_runs WHERE started_at >= NOW() - INTERVAL '7 days'
    """)
    print(f"📊 최근 7일: {recent['runs']}런, {recent['users']}명, 평균 {recent['avg_floor']:.1f}층, 최고 {recent['max_floor']}층")

    # 3. 희귀도별 평균 도달 층
    by_rarity = await pool.fetch("""
        SELECT pm.rarity, COUNT(*) as runs,
               AVG(dr.floor_reached) as avg_floor,
               MAX(dr.floor_reached) as max_floor
        FROM dungeon_runs dr
        JOIN user_pokemon up ON dr.pokemon_instance_id = up.id
        JOIN pokemon_master pm ON up.pokemon_id = pm.id
        GROUP BY pm.rarity ORDER BY avg_floor DESC
    """)
    print("\n🎖️ 희귀도별 도달 층:")
    for r in by_rarity:
        print(f"  {r['rarity']:20} | {r['runs']:>4}런 | 평균 {r['avg_floor']:.1f}층 | 최고 {r['max_floor']}층")

    # 4. 포켓몬별 최고 기록 Top 20
    by_pokemon = await pool.fetch("""
        SELECT pm.name_ko, pm.rarity, up.is_shiny,
               MAX(dr.floor_reached) as max_floor,
               COUNT(*) as runs,
               AVG(dr.floor_reached) as avg_floor
        FROM dungeon_runs dr
        JOIN user_pokemon up ON dr.pokemon_instance_id = up.id
        JOIN pokemon_master pm ON up.pokemon_id = pm.id
        GROUP BY pm.name_ko, pm.rarity, up.is_shiny
        ORDER BY max_floor DESC LIMIT 20
    """)
    print("\n🏆 포켓몬별 최고 기록 Top 20:")
    for r in by_pokemon:
        shiny = "✨" if r['is_shiny'] else "  "
        print(f"  {shiny}{r['name_ko']:12} [{r['rarity']:15}] | {r['runs']:>3}런 | 평균 {r['avg_floor']:.1f} | 최고 {r['max_floor']}층")

    # 5. 유저별 최고 기록 Top 20
    by_user = await pool.fetch("""
        SELECT dr.user_id, u.display_name,
               MAX(dr.floor_reached) as max_floor,
               COUNT(*) as runs,
               AVG(dr.floor_reached) as avg_floor
        FROM dungeon_runs dr
        JOIN users u ON dr.user_id = u.user_id
        GROUP BY dr.user_id, u.display_name
        ORDER BY max_floor DESC LIMIT 20
    """)
    print("\n👤 유저별 최고 기록 Top 20:")
    for r in by_user:
        print(f"  {r['display_name'][:15]:15} | {r['runs']:>4}런 | 평균 {r['avg_floor']:.1f} | 최고 {r['max_floor']}층")

    # 6. 층수별 사망 분포 (어디서 많이 죽는가)
    death_dist = await pool.fetch("""
        SELECT floor_reached, COUNT(*) as deaths
        FROM dungeon_runs
        WHERE floor_reached > 0
        GROUP BY floor_reached
        ORDER BY floor_reached
    """)
    print("\n💀 층수별 사망 분포:")
    for r in death_dist:
        bar = "█" * (r['deaths'] // 2)
        boss = " 👑BOSS" if r['floor_reached'] % 5 == 0 else ""
        print(f"  {r['floor_reached']:>3}층 | {r['deaths']:>4}명 {bar}{boss}")

    # 7. 테마별 통계
    try:
        by_theme = await pool.fetch("""
            SELECT theme, COUNT(*) as runs,
                   AVG(floor_reached) as avg_floor,
                   MAX(floor_reached) as max_floor
            FROM dungeon_runs
            WHERE theme IS NOT NULL
            GROUP BY theme ORDER BY runs DESC
        """)
        print("\n🎨 테마별 통계:")
        for r in by_theme:
            print(f"  {r['theme']:15} | {r['runs']:>4}런 | 평균 {r['avg_floor']:.1f} | 최고 {r['max_floor']}층")
    except Exception:
        print("\n(theme 컬럼 없음)")

    # 8. 버프 인기도 (어떤 버프를 많이 선택하는가)
    try:
        buff_rows = await pool.fetch("""
            SELECT buffs_json FROM dungeon_runs
            WHERE buffs_json IS NOT NULL AND floor_reached >= 5
            ORDER BY started_at DESC LIMIT 500
        """)
        import json
        buff_counter = {}
        for r in buff_rows:
            try:
                buffs = json.loads(r['buffs_json']) if isinstance(r['buffs_json'], str) else r['buffs_json']
                for b in buffs:
                    bid = b.get('id', '?')
                    if bid.startswith('_'):
                        continue
                    buff_counter[bid] = buff_counter.get(bid, 0) + 1
            except Exception:
                pass
        print("\n🎯 버프 인기도 (5층+ 런, 최근 500런):")
        for bid, cnt in sorted(buff_counter.items(), key=lambda x: -x[1])[:15]:
            print(f"  {bid:20} | {cnt}회")
    except Exception as e:
        print(f"\n(버프 분석 실패: {e})")

    # 9. 일일 던전 런 수 추이
    daily = await pool.fetch("""
        SELECT (started_at AT TIME ZONE 'Asia/Seoul')::date as day,
               COUNT(*) as runs, COUNT(DISTINCT user_id) as users
        FROM dungeon_runs
        WHERE started_at >= NOW() - INTERVAL '14 days'
        GROUP BY day ORDER BY day
    """)
    print("\n📈 일일 던전 런 수 (최근 14일):")
    for r in daily:
        bar = "█" * (r['runs'] // 5)
        print(f"  {r['day']} | {r['runs']:>4}런 {r['users']:>3}명 {bar}")

asyncio.run(main())
