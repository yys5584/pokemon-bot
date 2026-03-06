"""Generate comprehensive analytics report from DB."""
import asyncio
import os
import ssl
import asyncpg
from dotenv import load_dotenv

load_dotenv()


async def main():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    pool = await asyncpg.create_pool(os.getenv("DATABASE_URL"), ssl=ctx, statement_cache_size=0)

    # 1. 유저 통계
    r = await pool.fetchrow("""
        SELECT COUNT(*) as total,
               COUNT(CASE WHEN last_active_at > NOW() - INTERVAL '7 days' THEN 1 END) as wau,
               COUNT(CASE WHEN last_active_at > NOW() - INTERVAL '1 day' THEN 1 END) as dau
        FROM users
    """)
    print("=" * 50)
    print("📊 포켓몬봇 종합 리포트")
    print("=" * 50)
    print(f"\n👥 유저")
    print(f"  총 가입자: {r['total']}")
    print(f"  WAU (7일 활성): {r['wau']}")
    print(f"  DAU (1일 활성): {r['dau']}")
    if r['total'] > 0:
        print(f"  리텐션(WAU/총): {r['wau']*100/r['total']:.1f}%")

    # 2. 채팅방
    r = await pool.fetchrow("SELECT COUNT(*) as total, COUNT(CASE WHEN is_active=1 THEN 1 END) as active FROM chat_rooms")
    print(f"\n💬 채팅방")
    print(f"  총: {r['total']}, 활성: {r['active']}")

    # 3. 포켓몬 통계
    r = await pool.fetchrow("SELECT COUNT(*) as total, COUNT(CASE WHEN is_shiny=1 THEN 1 END) as shiny FROM user_pokemon WHERE is_active=1")
    print(f"\n🎒 보유 포켓몬")
    print(f"  총: {r['total']}, 이로치: {r['shiny']}")
    if r['total'] > 0:
        print(f"  이로치 비율: {r['shiny']*100/r['total']:.2f}%")

    # 4. 스폰/포획
    r = await pool.fetchrow("SELECT COUNT(*) as spawns, COUNT(caught_by_user_id) as catches FROM spawn_log")
    print(f"\n🎯 스폰/포획")
    print(f"  총 스폰: {r['spawns']}, 포획: {r['catches']}")
    if r['spawns'] > 0:
        print(f"  포획률: {r['catches']*100/r['spawns']:.1f}%")

    # 5. 최근 7일 일별
    rows = await pool.fetch("""
        SELECT DATE(spawned_at AT TIME ZONE 'Asia/Seoul') as d,
               COUNT(*) as spawns,
               COUNT(caught_by_user_id) as catches
        FROM spawn_log
        WHERE spawned_at > NOW() - INTERVAL '7 days'
        GROUP BY d ORDER BY d
    """)
    print(f"\n📅 최근 7일 일별 스폰/포획")
    for row in rows:
        rate = row['catches']*100/row['spawns'] if row['spawns'] > 0 else 0
        print(f"  {row['d']}: 스폰 {row['spawns']}, 포획 {row['catches']} ({rate:.0f}%)")

    # 6. 희귀도별 보유
    rows = await pool.fetch("""
        SELECT pm.rarity, COUNT(*) as cnt
        FROM user_pokemon up JOIN pokemon_master pm ON up.pokemon_id = pm.id
        WHERE up.is_active = 1
        GROUP BY pm.rarity ORDER BY cnt DESC
    """)
    print(f"\n⭐ 희귀도별 보유")
    for row in rows:
        print(f"  {row['rarity']}: {row['cnt']}")

    # 7. 이로치 희귀도별
    rows = await pool.fetch("""
        SELECT pm.rarity, COUNT(*) as cnt
        FROM user_pokemon up JOIN pokemon_master pm ON up.pokemon_id = pm.id
        WHERE up.is_active = 1 AND up.is_shiny = 1
        GROUP BY pm.rarity ORDER BY cnt DESC
    """)
    print(f"\n✨ 이로치 희귀도별")
    for row in rows:
        print(f"  {row['rarity']}: {row['cnt']}")

    # 8. 배틀
    r = await pool.fetchrow("SELECT COUNT(*) as cnt FROM battle_records")
    print(f"\n⚔️ 배틀: 총 {r['cnt']}회")

    # 9. 거래
    r = await pool.fetchrow("SELECT COUNT(*) as total, COUNT(CASE WHEN status='accepted' THEN 1 END) as accepted FROM trades")
    print(f"\n🤝 거래: 총 {r['total']}, 성사 {r['accepted']}")

    # 10. 도감 TOP 10
    rows = await pool.fetch("""
        SELECT u.display_name, COUNT(p.pokemon_id) as dex_cnt
        FROM pokedex p JOIN users u ON p.user_id = u.user_id
        GROUP BY u.user_id, u.display_name
        ORDER BY dex_cnt DESC LIMIT 10
    """)
    print(f"\n📕 도감 TOP 10")
    for i, row in enumerate(rows, 1):
        pct = row['dex_cnt']*100/251
        print(f"  {i}. {row['display_name']}: {row['dex_cnt']}/251 ({pct:.0f}%)")

    # 11. 포획왕 TOP 10
    rows = await pool.fetch("""
        SELECT u.display_name, COUNT(*) as cnt
        FROM spawn_log sl JOIN users u ON sl.caught_by_user_id = u.user_id
        GROUP BY u.user_id, u.display_name
        ORDER BY cnt DESC LIMIT 10
    """)
    print(f"\n🏆 포획왕 TOP 10")
    for i, row in enumerate(rows, 1):
        print(f"  {i}. {row['display_name']}: {row['cnt']}마리")

    # 12. 경제
    r = await pool.fetchrow("SELECT SUM(master_balls) as mb, SUM(hyper_balls) as hb, SUM(battle_points) as bp FROM users")
    print(f"\n💰 경제")
    print(f"  마스터볼 총량: {r['mb']}")
    print(f"  하이퍼볼 총량: {r['hb']}")
    print(f"  BP 총량: {r['bp']}")

    # 13. 결제
    try:
        r = await pool.fetchrow("SELECT COUNT(*) as cnt, COALESCE(SUM(price_usd),0) as total_usd FROM orders WHERE payment_status = 'fulfilled'")
        print(f"\n💳 결제")
        print(f"  완료 주문: {r['cnt']}건, 총 ${r['total_usd']}")
    except Exception:
        print(f"\n💳 결제: 조회 실패")

    # 14. 튜토리얼
    r = await pool.fetchrow("""
        SELECT COUNT(CASE WHEN tutorial_step=0 THEN 1 END) as not_started,
               COUNT(CASE WHEN tutorial_step=99 THEN 1 END) as completed,
               COUNT(CASE WHEN tutorial_step NOT IN (0,99) THEN 1 END) as in_progress
        FROM users
    """)
    print(f"\n📖 튜토리얼")
    print(f"  미시작: {r['not_started']}, 진행중: {r['in_progress']}, 완료: {r['completed']}")

    # 15. 채팅방 TOP 5
    rows = await pool.fetch("""
        SELECT cr.chat_title, cr.member_count, COUNT(sl.id) as total_spawns
        FROM chat_rooms cr
        LEFT JOIN spawn_log sl ON cr.chat_id = sl.chat_id
        WHERE cr.is_active = 1 AND cr.chat_title IS NOT NULL
        GROUP BY cr.chat_id, cr.chat_title, cr.member_count
        ORDER BY total_spawns DESC LIMIT 5
    """)
    print(f"\n🏠 채팅방 TOP 5 (스폰 기준)")
    for i, row in enumerate(rows, 1):
        print(f"  {i}. {row['chat_title']} ({row['member_count']}명): 스폰 {row['total_spawns']}")

    # 16. 신규 가입 (7일)
    rows = await pool.fetch("""
        SELECT DATE(registered_at AT TIME ZONE 'Asia/Seoul') as d, COUNT(*) as cnt
        FROM users
        WHERE registered_at > NOW() - INTERVAL '7 days'
        GROUP BY d ORDER BY d
    """)
    print(f"\n📈 신규 가입 (최근 7일)")
    for row in rows:
        print(f"  {row['d']}: {row['cnt']}명")

    # 17. 시간대별 활동 (포획 기준)
    rows = await pool.fetch("""
        SELECT EXTRACT(HOUR FROM spawned_at AT TIME ZONE 'Asia/Seoul')::int as h,
               COUNT(*) as cnt
        FROM spawn_log
        WHERE caught_by_user_id IS NOT NULL AND spawned_at > NOW() - INTERVAL '7 days'
        GROUP BY h ORDER BY h
    """)
    print(f"\n⏰ 시간대별 포획 (최근 7일, KST)")
    for row in rows:
        bar = "█" * (row['cnt'] // 5)
        print(f"  {row['h']:02d}시: {row['cnt']:>4} {bar}")

    # 18. 미등록 포켓몬 (도감에 한 명도 안 잡은)
    rows = await pool.fetch("""
        SELECT pm.id, pm.name_ko, pm.rarity
        FROM pokemon_master pm
        LEFT JOIN pokedex p ON pm.id = p.pokemon_id
        WHERE p.pokemon_id IS NULL
        ORDER BY pm.id
    """)
    print(f"\n❓ 아무도 안 잡은 포켓몬: {len(rows)}종")
    if rows:
        for row in rows[:20]:
            print(f"  #{row['id']:03d} {row['name_ko']} ({row['rarity']})")
        if len(rows) > 20:
            print(f"  ... 외 {len(rows)-20}종")

    await pool.close()


asyncio.run(main())
