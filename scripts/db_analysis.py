"""DB 유저 패턴 분석 스크립트 — 수익화 가격 추천용."""
import asyncio, asyncpg, os, json

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://pokemon:pokemon@localhost/pokemon_bot")

async def main():
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
    results = {}

    # 1. 전체 유저 & 활동도
    r = await pool.fetchrow("SELECT COUNT(*) as total FROM users")
    results["total_users"] = r["total"]

    r = await pool.fetchrow("SELECT COUNT(*) as c FROM users WHERE last_active_at >= NOW() - INTERVAL '1 day'")
    results["active_1d"] = r["c"]
    r = await pool.fetchrow("SELECT COUNT(*) as c FROM users WHERE last_active_at >= NOW() - INTERVAL '7 days'")
    results["active_7d"] = r["c"]
    r = await pool.fetchrow("SELECT COUNT(*) as c FROM users WHERE last_active_at >= NOW() - INTERVAL '30 days'")
    results["active_30d"] = r["c"]

    # 2. 마스터볼 분포
    rows = await pool.fetch("""
        SELECT
            CASE
                WHEN master_balls = 0 THEN '0'
                WHEN master_balls BETWEEN 1 AND 5 THEN '1-5'
                WHEN master_balls BETWEEN 6 AND 20 THEN '6-20'
                WHEN master_balls BETWEEN 21 AND 50 THEN '21-50'
                ELSE '51+'
            END as bucket,
            COUNT(*) as cnt
        FROM users
        WHERE last_active_at >= NOW() - INTERVAL '30 days'
        GROUP BY bucket ORDER BY cnt DESC
    """)
    results["masterball_dist"] = {r["bucket"]: r["cnt"] for r in rows}

    # 3. BP 분포
    rows = await pool.fetch("""
        SELECT
            CASE
                WHEN battle_points < 100 THEN '0-99'
                WHEN battle_points BETWEEN 100 AND 499 THEN '100-499'
                WHEN battle_points BETWEEN 500 AND 1999 THEN '500-1999'
                WHEN battle_points BETWEEN 2000 AND 9999 THEN '2000-9999'
                ELSE '10000+'
            END as bucket,
            COUNT(*) as cnt
        FROM users
        WHERE last_active_at >= NOW() - INTERVAL '30 days'
        GROUP BY bucket ORDER BY cnt DESC
    """)
    results["bp_dist"] = {r["bucket"]: r["cnt"] for r in rows}

    # 4. 포켓몬 보유 분포 (활성 유저)
    rows = await pool.fetch("""
        SELECT
            CASE
                WHEN poke_cnt BETWEEN 1 AND 5 THEN '1-5'
                WHEN poke_cnt BETWEEN 6 AND 20 THEN '6-20'
                WHEN poke_cnt BETWEEN 21 AND 50 THEN '21-50'
                WHEN poke_cnt BETWEEN 51 AND 100 THEN '51-100'
                ELSE '100+'
            END as bucket,
            COUNT(*) as cnt
        FROM (
            SELECT up.user_id, COUNT(*) as poke_cnt
            FROM user_pokemon up
            JOIN users u ON u.user_id = up.user_id
            WHERE up.is_active = 1 AND u.last_active_at >= NOW() - INTERVAL '30 days'
            GROUP BY up.user_id
        ) sub
        GROUP BY bucket ORDER BY cnt DESC
    """)
    results["pokemon_ownership"] = {r["bucket"]: r["cnt"] for r in rows}

    # 5. 이로치 보유 분포
    rows = await pool.fetch("""
        SELECT
            CASE
                WHEN shiny_cnt = 0 THEN '0'
                WHEN shiny_cnt BETWEEN 1 AND 3 THEN '1-3'
                WHEN shiny_cnt BETWEEN 4 AND 10 THEN '4-10'
                ELSE '10+'
            END as bucket,
            COUNT(*) as cnt
        FROM (
            SELECT up.user_id, COUNT(*) FILTER (WHERE up.is_shiny = 1) as shiny_cnt
            FROM user_pokemon up
            JOIN users u ON u.user_id = up.user_id
            WHERE up.is_active = 1 AND u.last_active_at >= NOW() - INTERVAL '30 days'
            GROUP BY up.user_id
        ) sub
        GROUP BY bucket ORDER BY cnt DESC
    """)
    results["shiny_dist"] = {r["bucket"]: r["cnt"] for r in rows}

    # 6. 도감 완성도 분포
    rows = await pool.fetch("""
        SELECT
            CASE
                WHEN dex_cnt < 10 THEN '1-9'
                WHEN dex_cnt BETWEEN 10 AND 30 THEN '10-30'
                WHEN dex_cnt BETWEEN 31 AND 80 THEN '31-80'
                WHEN dex_cnt BETWEEN 81 AND 150 THEN '81-150'
                ELSE '150+'
            END as bucket,
            COUNT(*) as cnt
        FROM (
            SELECT p.user_id, COUNT(*) as dex_cnt
            FROM pokedex p
            JOIN users u ON u.user_id = p.user_id
            WHERE u.last_active_at >= NOW() - INTERVAL '30 days'
            GROUP BY p.user_id
        ) sub
        GROUP BY bucket ORDER BY cnt DESC
    """)
    results["pokedex_dist"] = {r["bucket"]: r["cnt"] for r in rows}

    # 7. 배틀 참여도 (30일)
    r = await pool.fetchrow("""
        SELECT COUNT(DISTINCT u) as battlers FROM (
            SELECT winner_id as u FROM battle_records WHERE created_at >= NOW() - INTERVAL '30 days'
            UNION
            SELECT loser_id as u FROM battle_records WHERE created_at >= NOW() - INTERVAL '30 days'
        ) sub
    """)
    results["battlers_30d"] = r["battlers"]
    r = await pool.fetchrow("SELECT COUNT(*) as c FROM battle_records WHERE created_at >= NOW() - INTERVAL '30 days'")
    results["battles_30d"] = r["c"]

    # 8. 거래소 활동
    r = await pool.fetchrow("SELECT COUNT(*) as c FROM market_listings WHERE created_at >= NOW() - INTERVAL '30 days'")
    results["market_listings_30d"] = r["c"]
    r = await pool.fetchrow("SELECT COUNT(*) as c FROM market_listings WHERE status = 'sold' AND sold_at >= NOW() - INTERVAL '30 days'")
    results["market_sold_30d"] = r["c"]

    # 9. 아케이드 패스
    r = await pool.fetchrow("SELECT COUNT(*) as c FROM arcade_passes")
    results["total_arcade_passes"] = r["c"]
    r = await pool.fetchrow("SELECT COUNT(*) as c FROM arcade_passes WHERE activated_at >= NOW() - INTERVAL '30 days'")
    results["arcade_passes_30d"] = r["c"]

    # 10. 강제스폰 티켓 분포
    rows = await pool.fetch("""
        SELECT
            CASE
                WHEN force_spawn_tickets = 0 THEN '0'
                WHEN force_spawn_tickets BETWEEN 1 AND 5 THEN '1-5'
                ELSE '6+'
            END as bucket,
            COUNT(*) as cnt
        FROM users
        WHERE last_active_at >= NOW() - INTERVAL '30 days'
        GROUP BY bucket ORDER BY cnt DESC
    """)
    results["force_spawn_dist"] = {r["bucket"]: r["cnt"] for r in rows}

    # 11. 하이퍼볼 분포
    rows = await pool.fetch("""
        SELECT
            CASE
                WHEN hyper_balls = 0 THEN '0'
                WHEN hyper_balls BETWEEN 1 AND 10 THEN '1-10'
                ELSE '10+'
            END as bucket,
            COUNT(*) as cnt
        FROM users
        WHERE last_active_at >= NOW() - INTERVAL '30 days'
        GROUP BY bucket ORDER BY cnt DESC
    """)
    results["hyperball_dist"] = {r["bucket"]: r["cnt"] for r in rows}

    # 12. 일별 포획 시도 (최근 7일)
    rows = await pool.fetch("""
        SELECT date, SUM(attempt_count) as total_attempts, COUNT(DISTINCT user_id) as unique_catchers
        FROM catch_limits
        WHERE date >= to_char(CURRENT_DATE - INTERVAL '7 days', 'YYYY-MM-DD')
        GROUP BY date ORDER BY date DESC
    """)
    results["daily_catch_7d"] = [{"date": r["date"], "attempts": r["total_attempts"], "catchers": r["unique_catchers"]} for r in rows]

    # 13. 마스터볼/하이퍼볼 사용량 (30일)
    r = await pool.fetchrow("""
        SELECT
            COUNT(*) FILTER (WHERE used_master_ball = 1) as masterball_used,
            COUNT(*) FILTER (WHERE used_hyper_ball = 1) as hyperball_used
        FROM catch_attempts
        WHERE attempted_at >= NOW() - INTERVAL '30 days'
    """)
    results["ball_usage_30d"] = {"masterball": r["masterball_used"], "hyperball": r["hyperball_used"]}

    # 14. 교환 활동
    r = await pool.fetchrow("SELECT COUNT(*) as c FROM trades WHERE created_at >= NOW() - INTERVAL '30 days'")
    results["trades_30d"] = r["c"]
    r = await pool.fetchrow("SELECT COUNT(*) as c FROM trades WHERE status = 'accepted' AND created_at >= NOW() - INTERVAL '30 days'")
    results["trades_accepted_30d"] = r["c"]

    # 15. 채팅방 통계
    r = await pool.fetchrow("SELECT COUNT(*) as c FROM chat_rooms WHERE is_active = 1")
    results["active_chats"] = r["c"]
    r = await pool.fetchrow("SELECT COUNT(*) as c FROM chat_rooms WHERE is_arcade = 1")
    results["arcade_chats"] = r["c"]

    # 16. 상위 유저 BP (top 20 7일 활성)
    rows = await pool.fetch("""
        SELECT display_name, battle_points, master_balls, hyper_balls, force_spawn_tickets, arcade_tickets
        FROM users
        WHERE last_active_at >= NOW() - INTERVAL '7 days'
        ORDER BY battle_points DESC LIMIT 20
    """)
    results["top20_bp"] = [dict(r) for r in rows]

    # 17. BP 구매 로그 (아이템별 인기도)
    rows = await pool.fetch("""
        SELECT item, SUM(amount) as total_purchased, COUNT(DISTINCT user_id) as unique_buyers
        FROM bp_purchase_log
        WHERE purchased_at >= NOW() - INTERVAL '30 days'
        GROUP BY item ORDER BY total_purchased DESC
    """)
    results["bp_purchases_30d"] = [{"item": r["item"], "total": r["total_purchased"], "buyers": r["unique_buyers"]} for r in rows]

    # 18. 스폰 통계 (7일)
    r = await pool.fetchrow("""
        SELECT COUNT(*) as spawns, COUNT(caught_by_user_id) as caught
        FROM spawn_log WHERE spawned_at >= NOW() - INTERVAL '7 days'
    """)
    results["spawn_stats_7d"] = {"spawns": r["spawns"], "caught": r["caught"]}

    # 19. 랭크전 참여
    r = await pool.fetchrow("SELECT COUNT(*) as c FROM season_records")
    results["ranked_participants"] = r["c"]

    # 20. 일일 미션 완료율 (7일)
    r = await pool.fetchrow("""
        SELECT
            COUNT(*) as total_missions,
            COUNT(*) FILTER (WHERE completed = TRUE) as completed
        FROM daily_missions
        WHERE mission_date >= to_char(CURRENT_DATE - INTERVAL '7 days', 'YYYY-MM-DD')
    """)
    results["mission_stats_7d"] = {"total": r["total_missions"], "completed": r["completed"]}

    # 21. 유저 가입 추세 (주간)
    rows = await pool.fetch("""
        SELECT
            date_trunc('week', registered_at)::date as week,
            COUNT(*) as new_users
        FROM users
        WHERE registered_at >= NOW() - INTERVAL '60 days'
        GROUP BY week ORDER BY week DESC
    """)
    results["signup_trend"] = [{"week": str(r["week"]), "new_users": r["new_users"]} for r in rows]

    # 22. 리텐션 (가입 후 7일 이상 활동)
    r = await pool.fetchrow("""
        SELECT
            COUNT(*) as total_recent,
            COUNT(*) FILTER (WHERE last_active_at >= registered_at + INTERVAL '7 days') as retained
        FROM users
        WHERE registered_at >= NOW() - INTERVAL '60 days'
    """)
    results["retention_60d"] = {"total_signups": r["total_recent"], "retained_7d": r["retained"]}

    # 23. 평균 일일 포획 시도 (유저당)
    r = await pool.fetchrow("""
        SELECT ROUND(AVG(attempt_count), 1) as avg_attempts, MAX(attempt_count) as max_attempts
        FROM catch_limits
        WHERE date = to_char(CURRENT_DATE - INTERVAL '1 day', 'YYYY-MM-DD')
    """)
    results["yesterday_catch"] = {"avg_per_user": float(r["avg_attempts"]) if r["avg_attempts"] else 0, "max": r["max_attempts"]}

    # 24. 아케이드 티켓 분포
    rows = await pool.fetch("""
        SELECT
            CASE
                WHEN arcade_tickets = 0 THEN '0'
                WHEN arcade_tickets BETWEEN 1 AND 5 THEN '1-5'
                ELSE '6+'
            END as bucket,
            COUNT(*) as cnt
        FROM users
        WHERE last_active_at >= NOW() - INTERVAL '30 days'
        GROUP BY bucket ORDER BY cnt DESC
    """)
    results["arcade_ticket_dist"] = {r["bucket"]: r["cnt"] for r in rows}

    # 25. 채팅방별 활동 (상위 10)
    rows = await pool.fetch("""
        SELECT cr.chat_id, cr.chat_title, cr.member_count, cr.chat_level,
               cr.daily_spawn_count, cr.is_arcade
        FROM chat_rooms cr
        WHERE cr.is_active = 1
        ORDER BY cr.chat_level DESC, cr.member_count DESC
        LIMIT 10
    """)
    results["top10_chats"] = [dict(r) for r in rows]

    await pool.close()

    # Pretty print
    for k, v in results.items():
        print(f"\n=== {k} ===")
        if isinstance(v, dict):
            for kk, vv in v.items():
                print(f"  {kk}: {vv}")
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    parts = [f"{kk}={vv}" for kk, vv in item.items()]
                    print(f"  {', '.join(parts)}")
                else:
                    print(f"  {item}")
        else:
            print(f"  {v}")

asyncio.run(main())
