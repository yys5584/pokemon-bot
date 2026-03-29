import asyncio
import asyncpg
import ssl

DSN = "postgresql://postgres.ycaxgpnxfyumejlriymk:!dbdbstkd92@aws-1-ap-northeast-1.pooler.supabase.com:6543/postgres"

def make_ssl():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

async def main():
    conn = await asyncpg.connect(dsn=DSN, ssl=make_ssl(), statement_cache_size=0, timeout=15)

    print("=" * 70)
    print("POKEMON BOT ENGAGEMENT ANALYSIS REPORT")
    print("=" * 70)

    # 1. DAU trend - last 14 days
    print("\n## 1. DAU Trend (Last 14 Days)")
    print("   (Users who caught at least 1 pokemon)")
    rows = await conn.fetch("""
        SELECT d::date AS day,
               COUNT(DISTINCT sl.caught_by_user_id) AS dau
        FROM generate_series(
            (NOW() AT TIME ZONE 'Asia/Seoul')::date - INTERVAL '13 days',
            (NOW() AT TIME ZONE 'Asia/Seoul')::date,
            '1 day'
        ) d
        LEFT JOIN spawn_log sl
            ON (sl.spawned_at AT TIME ZONE 'Asia/Seoul')::date = d::date
            AND sl.caught_by_user_id IS NOT NULL
        GROUP BY d::date
        ORDER BY d::date
    """)
    for r in rows:
        print(f"   {r['day']}  DAU: {r['dau']}")

    # 2. Session depth - avg catches per active user per day (last 7 days)
    print("\n## 2. Session Depth (Last 7 Days)")
    print("   (Average catches per active user per day)")
    rows = await conn.fetch("""
        SELECT (sl.spawned_at AT TIME ZONE 'Asia/Seoul')::date AS day,
               COUNT(*) AS total_catches,
               COUNT(DISTINCT sl.caught_by_user_id) AS active_users,
               ROUND(COUNT(*)::numeric / NULLIF(COUNT(DISTINCT sl.caught_by_user_id), 0), 1) AS avg_catches
        FROM spawn_log sl
        WHERE sl.caught_by_user_id IS NOT NULL
          AND sl.spawned_at >= (NOW() AT TIME ZONE 'Asia/Seoul')::date - INTERVAL '6 days'
        GROUP BY (sl.spawned_at AT TIME ZONE 'Asia/Seoul')::date
        ORDER BY 1
    """)
    for r in rows:
        print(f"   {r['day']}  catches={r['total_catches']}  users={r['active_users']}  avg={r['avg_catches']}")

    # 3. Feature usage breakdown (last 7 days daily)
    print("\n## 3. Feature Usage Breakdown (Last 7 Days Avg)")

    # 3a. Battle users
    battle_row = await conn.fetchrow("""
        SELECT ROUND(AVG(cnt), 1) AS avg_daily
        FROM (
            SELECT (br.created_at AT TIME ZONE 'Asia/Seoul')::date AS day,
                   COUNT(DISTINCT u) AS cnt
            FROM battle_records br,
                 LATERAL (VALUES (br.winner_id), (br.loser_id)) AS t(u)
            WHERE br.created_at >= (NOW() AT TIME ZONE 'Asia/Seoul')::date - INTERVAL '6 days'
            GROUP BY (br.created_at AT TIME ZONE 'Asia/Seoul')::date
        ) sub
    """)
    print(f"   Battle users/day (avg): {battle_row['avg_daily']}")

    # 3b. Trade users
    trade_row = await conn.fetchrow("""
        SELECT ROUND(AVG(cnt), 1) AS avg_daily
        FROM (
            SELECT (t.created_at AT TIME ZONE 'Asia/Seoul')::date AS day,
                   COUNT(DISTINCT u) AS cnt
            FROM trades t,
                 LATERAL (VALUES (t.from_user_id), (t.to_user_id)) AS v(u)
            WHERE t.status = 'accepted'
              AND t.created_at >= (NOW() AT TIME ZONE 'Asia/Seoul')::date - INTERVAL '6 days'
            GROUP BY (t.created_at AT TIME ZONE 'Asia/Seoul')::date
        ) sub
    """)
    print(f"   Trade users/day (avg): {trade_row['avg_daily']}")

    # 3c. Camp users (placements)
    camp_row = await conn.fetchrow("""
        SELECT ROUND(AVG(cnt), 1) AS avg_daily
        FROM (
            SELECT (cp.placed_at AT TIME ZONE 'Asia/Seoul')::date AS day,
                   COUNT(DISTINCT cp.user_id) AS cnt
            FROM camp_placements cp
            WHERE cp.placed_at >= (NOW() AT TIME ZONE 'Asia/Seoul')::date - INTERVAL '6 days'
            GROUP BY (cp.placed_at AT TIME ZONE 'Asia/Seoul')::date
        ) sub
    """)
    print(f"   Camp users/day (avg): {camp_row['avg_daily']}")

    # 3d. Ranked battle users
    ranked_row = await conn.fetchrow("""
        SELECT ROUND(AVG(cnt), 1) AS avg_daily
        FROM (
            SELECT (rbl.created_at AT TIME ZONE 'Asia/Seoul')::date AS day,
                   COUNT(DISTINCT u) AS cnt
            FROM ranked_battle_log rbl
            JOIN battle_records br ON br.id = rbl.battle_record_id,
                 LATERAL (VALUES (br.winner_id), (br.loser_id)) AS t(u)
            WHERE rbl.created_at >= (NOW() AT TIME ZONE 'Asia/Seoul')::date - INTERVAL '6 days'
            GROUP BY (rbl.created_at AT TIME ZONE 'Asia/Seoul')::date
        ) sub
    """)
    print(f"   Ranked battle users/day (avg): {ranked_row['avg_daily']}")

    # Daily breakdown for last 7 days
    print("\n   Daily breakdown (battle / trade / camp / ranked):")
    rows = await conn.fetch("""
        WITH days AS (
            SELECT d::date AS day FROM generate_series(
                (NOW() AT TIME ZONE 'Asia/Seoul')::date - INTERVAL '6 days',
                (NOW() AT TIME ZONE 'Asia/Seoul')::date, '1 day') d
        ),
        battle_daily AS (
            SELECT (br.created_at AT TIME ZONE 'Asia/Seoul')::date AS day,
                   COUNT(DISTINCT u) AS cnt
            FROM battle_records br,
                 LATERAL (VALUES (br.winner_id), (br.loser_id)) AS t(u)
            WHERE br.created_at >= (NOW() AT TIME ZONE 'Asia/Seoul')::date - INTERVAL '6 days'
            GROUP BY 1
        ),
        trade_daily AS (
            SELECT (t.created_at AT TIME ZONE 'Asia/Seoul')::date AS day,
                   COUNT(DISTINCT u) AS cnt
            FROM trades t,
                 LATERAL (VALUES (t.from_user_id), (t.to_user_id)) AS v(u)
            WHERE t.status = 'accepted'
              AND t.created_at >= (NOW() AT TIME ZONE 'Asia/Seoul')::date - INTERVAL '6 days'
            GROUP BY 1
        ),
        camp_daily AS (
            SELECT (cp.placed_at AT TIME ZONE 'Asia/Seoul')::date AS day,
                   COUNT(DISTINCT cp.user_id) AS cnt
            FROM camp_placements cp
            WHERE cp.placed_at >= (NOW() AT TIME ZONE 'Asia/Seoul')::date - INTERVAL '6 days'
            GROUP BY 1
        ),
        ranked_daily AS (
            SELECT (rbl.created_at AT TIME ZONE 'Asia/Seoul')::date AS day,
                   COUNT(DISTINCT u) AS cnt
            FROM ranked_battle_log rbl
            JOIN battle_records br ON br.id = rbl.battle_record_id,
                 LATERAL (VALUES (br.winner_id), (br.loser_id)) AS t(u)
            WHERE rbl.created_at >= (NOW() AT TIME ZONE 'Asia/Seoul')::date - INTERVAL '6 days'
            GROUP BY 1
        )
        SELECT d.day,
               COALESCE(b.cnt, 0) AS battle,
               COALESCE(t.cnt, 0) AS trade,
               COALESCE(c.cnt, 0) AS camp,
               COALESCE(r.cnt, 0) AS ranked
        FROM days d
        LEFT JOIN battle_daily b ON b.day = d.day
        LEFT JOIN trade_daily t ON t.day = d.day
        LEFT JOIN camp_daily c ON c.day = d.day
        LEFT JOIN ranked_daily r ON r.day = d.day
        ORDER BY d.day
    """)
    for r in rows:
        print(f"   {r['day']}  battle={r['battle']}  trade={r['trade']}  camp={r['camp']}  ranked={r['ranked']}")

    # 4. Retention cohort: active 7 days ago vs still active today
    print("\n## 4. 7-Day Retention")
    ret_row = await conn.fetchrow("""
        WITH day7_users AS (
            SELECT DISTINCT caught_by_user_id AS uid
            FROM spawn_log
            WHERE caught_by_user_id IS NOT NULL
              AND (spawned_at AT TIME ZONE 'Asia/Seoul')::date = (NOW() AT TIME ZONE 'Asia/Seoul')::date - INTERVAL '7 days'
        ),
        today_users AS (
            SELECT DISTINCT caught_by_user_id AS uid
            FROM spawn_log
            WHERE caught_by_user_id IS NOT NULL
              AND (spawned_at AT TIME ZONE 'Asia/Seoul')::date = (NOW() AT TIME ZONE 'Asia/Seoul')::date
        )
        SELECT
            (SELECT COUNT(*) FROM day7_users) AS cohort_size,
            COUNT(*) AS retained
        FROM day7_users d7
        JOIN today_users t ON t.uid = d7.uid
    """)
    cohort = ret_row['cohort_size']
    retained = ret_row['retained']
    pct = round(retained / cohort * 100, 1) if cohort > 0 else 0
    print(f"   Users active 7 days ago: {cohort}")
    print(f"   Still active today: {retained}")
    print(f"   7-day retention rate: {pct}%")

    # 5. Power distribution
    print("\n## 5. Power Distribution")
    total_pokemon_count = await conn.fetchval("SELECT COUNT(*) FROM pokemon_master")
    power_rows = await conn.fetch("""
        WITH user_rarity AS (
            SELECT up.user_id,
                   pm.rarity,
                   COUNT(*) AS cnt
            FROM user_pokemon up
            JOIN pokemon_master pm ON pm.id = up.pokemon_id
            WHERE up.is_active = 1
            GROUP BY up.user_id, pm.rarity
        ),
        user_summary AS (
            SELECT user_id,
                   COALESCE(SUM(cnt) FILTER (WHERE rarity IN ('epic','legendary','ultra_legendary')), 0) AS high_rarity,
                   COALESCE(SUM(cnt), 0) AS total
            FROM user_rarity
            GROUP BY user_id
        )
        SELECT
            CASE
                WHEN high_rarity >= 18 THEN 'A_maxed (18+ epic+)'
                WHEN high_rarity >= 10 THEN 'B_strong (10-17 epic+)'
                WHEN high_rarity >= 3 THEN 'C_mid (3-9 epic+)'
                ELSE 'D_casual (0-2 epic+)'
            END AS tier,
            COUNT(*) AS users,
            ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) AS pct
        FROM user_summary
        WHERE total > 0
        GROUP BY 1
        ORDER BY 1
    """)
    for r in power_rows:
        label = r['tier'][2:]  # strip sort prefix
        print(f"   {label}: {r['users']} users ({r['pct']}%)")

    # Total registered users for context
    total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
    active_users = await conn.fetchval("""
        SELECT COUNT(DISTINCT caught_by_user_id) FROM spawn_log
        WHERE caught_by_user_id IS NOT NULL
          AND spawned_at >=NOW() - INTERVAL '30 days'
    """)
    print(f"\n   Total registered users: {total_users}")
    print(f"   Active in last 30 days: {active_users}")

    # 6. Time-of-day activity (KST hours, last 7 days)
    print("\n## 6. Time-of-Day Activity (KST, Last 7 Days)")
    rows = await conn.fetch("""
        SELECT EXTRACT(HOUR FROM spawned_at AT TIME ZONE 'Asia/Seoul')::int AS hr,
               COUNT(*) AS catches
        FROM spawn_log
        WHERE caught_by_user_id IS NOT NULL
          AND spawned_at >=(NOW() AT TIME ZONE 'Asia/Seoul')::date - INTERVAL '6 days'
        GROUP BY 1
        ORDER BY 1
    """)
    max_catches = max(r['catches'] for r in rows) if rows else 1
    for r in rows:
        bar_len = int(30 * r['catches'] / max_catches)
        bar = '#' * bar_len
        print(f"   {r['hr']:02d}:00  {r['catches']:>5}  {bar}")

    # 7. Content saturation signals
    print("\n## 7. Content Saturation Signals")

    # 7a. Pokedex completion rate
    total_pokemon = await conn.fetchval("SELECT COUNT(*) FROM pokemon_master WHERE rarity != 'ultra_legendary'")
    dex_row = await conn.fetchrow(f"""
        SELECT ROUND(AVG(cnt), 1) AS avg_dex,
               ROUND(AVG(cnt)::numeric / {total_pokemon} * 100, 1) AS avg_pct,
               MAX(cnt) AS max_dex,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY cnt) AS median_dex
        FROM (
            SELECT user_id, COUNT(*) AS cnt FROM pokedex GROUP BY user_id
        ) sub
    """)
    print(f"   Total catchable pokemon: {total_pokemon}")
    print(f"   Average pokedex entries: {dex_row['avg_dex']} ({dex_row['avg_pct']}%)")
    print(f"   Median pokedex entries: {dex_row['median_dex']}")
    print(f"   Max pokedex entries: {dex_row['max_dex']}")

    # Top dex completionists
    dex_top = await conn.fetch(f"""
        SELECT p.user_id, u.display_name, COUNT(*) AS dex_count,
               ROUND(COUNT(*)::numeric / {total_pokemon} * 100, 1) AS pct
        FROM pokedex p
        JOIN users u ON u.user_id = p.user_id
        GROUP BY p.user_id, u.display_name
        ORDER BY dex_count DESC
        LIMIT 10
    """)
    print("\n   Top 10 Pokedex completionists:")
    for r in dex_top:
        print(f"     {r['display_name']}: {r['dex_count']}/{total_pokemon} ({r['pct']}%)")

    # 7b. Veteran users with declining activity
    print("\n   Veteran users (30+ days) with declining activity:")
    decline_rows = await conn.fetch("""
        WITH veterans AS (
            SELECT user_id, display_name, registered_at
            FROM users
            WHERE registered_at <= NOW() - INTERVAL '30 days'
        ),
        recent_activity AS (
            SELECT sl.caught_by_user_id AS user_id,
                   COUNT(*) FILTER (WHERE sl.spawned_at >= NOW() - INTERVAL '7 days') AS last_7d,
                   COUNT(*) FILTER (WHERE sl.spawned_at >= NOW() - INTERVAL '14 days'
                                     AND sl.spawned_at < NOW() - INTERVAL '7 days') AS prev_7d
            FROM spawn_log sl
            WHERE sl.caught_by_user_id IS NOT NULL
              AND sl.spawned_at >= NOW() - INTERVAL '14 days'
            GROUP BY sl.caught_by_user_id
        )
        SELECT v.display_name,
               COALESCE(ra.prev_7d, 0) AS prev_7d,
               COALESCE(ra.last_7d, 0) AS last_7d,
               CASE WHEN COALESCE(ra.prev_7d, 0) > 0
                    THEN ROUND((COALESCE(ra.last_7d, 0) - ra.prev_7d)::numeric / ra.prev_7d * 100, 1)
                    ELSE NULL END AS change_pct
        FROM veterans v
        LEFT JOIN recent_activity ra ON ra.user_id = v.user_id
        WHERE COALESCE(ra.prev_7d, 0) >= 10
        ORDER BY change_pct ASC NULLS LAST
        LIMIT 15
    """)
    print(f"   (Showing veterans with 10+ catches prev week, sorted by decline)")
    for r in decline_rows:
        sign = "+" if (r['change_pct'] or 0) >= 0 else ""
        chg = f"{sign}{r['change_pct']}%" if r['change_pct'] is not None else "N/A"
        print(f"     {r['display_name']}: prev_7d={r['prev_7d']} -> last_7d={r['last_7d']} ({chg})")

    # 8. Bonus: Churn risk - active users who stopped
    print("\n## 8. Bonus: Churn Signals")
    churn_row = await conn.fetchrow("""
        WITH prev_week AS (
            SELECT DISTINCT caught_by_user_id AS uid FROM spawn_log
            WHERE caught_by_user_id IS NOT NULL
              AND (spawned_at AT TIME ZONE 'Asia/Seoul')::date
                  BETWEEN (NOW() AT TIME ZONE 'Asia/Seoul')::date - INTERVAL '14 days'
                      AND (NOW() AT TIME ZONE 'Asia/Seoul')::date - INTERVAL '8 days'
        ),
        this_week AS (
            SELECT DISTINCT caught_by_user_id AS uid FROM spawn_log
            WHERE caught_by_user_id IS NOT NULL
              AND spawned_at >=(NOW() AT TIME ZONE 'Asia/Seoul')::date - INTERVAL '7 days'
        )
        SELECT
            (SELECT COUNT(*) FROM prev_week) AS prev_active,
            (SELECT COUNT(*) FROM prev_week WHERE uid NOT IN (SELECT uid FROM this_week)) AS churned
    """)
    pa = churn_row['prev_active']
    ch = churn_row['churned']
    churn_pct = round(ch / pa * 100, 1) if pa > 0 else 0
    print(f"   Users active 8-14 days ago: {pa}")
    print(f"   Not seen in last 7 days: {ch} ({churn_pct}% week-over-week churn)")

    await conn.close()
    print("\n" + "=" * 70)
    print("END OF REPORT")

asyncio.run(main())
