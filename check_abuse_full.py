import asyncio, os
from dotenv import load_dotenv
load_dotenv("/home/ubuntu/pokemon-bot/.env")
from database import connection

async def main():
    pool = await connection.get_db()

    print("(Queries 1-2 already obtained, skipping...)")

    # 3. High BP relative to account age
    print("\n" + "=" * 60)
    print("3. HIGH BP vs ACCOUNT AGE (top BP/day)")
    print("=" * 60)
    rows = await pool.fetch("""
        SELECT u.user_id, u.username, u.display_name, u.battle_points,
               u.registered_at,
               EXTRACT(DAY FROM NOW() - u.registered_at) as days_old,
               CASE WHEN EXTRACT(DAY FROM NOW() - u.registered_at) > 0
                    THEN ROUND(u.battle_points / EXTRACT(DAY FROM NOW() - u.registered_at))
                    ELSE u.battle_points END as bp_per_day
        FROM users u
        WHERE u.battle_points > 100
        ORDER BY bp_per_day DESC
        LIMIT 20
    """)
    for r in rows:
        print(f"  ID:{r['user_id']} @{r['username'] or r['display_name']} | BP:{r['battle_points']} | days:{int(r['days_old'] or 0)} | BP/day:{int(r['bp_per_day'] or 0)} | since:{r['registered_at'].strftime('%Y-%m-%d') if r['registered_at'] else '?'}")

    # 4. Suspicious trade patterns
    print("\n" + "=" * 60)
    print("4. SUSPICIOUS TRADE PAIRS (completed trades, last 14 days)")
    print("=" * 60)
    rows = await pool.fetch("""
        SELECT t.from_user_id, u1.username as sender_name,
               t.to_user_id, u2.username as receiver_name,
               COUNT(*) as trade_count
        FROM trades t
        JOIN users u1 ON u1.user_id = t.from_user_id
        JOIN users u2 ON u2.user_id = t.to_user_id
        WHERE t.created_at >= NOW() - INTERVAL '14 days'
          AND t.status = 'completed'
        GROUP BY t.from_user_id, u1.username, t.to_user_id, u2.username
        HAVING COUNT(*) >= 3
        ORDER BY trade_count DESC
        LIMIT 20
    """)
    if not rows:
        # Try without status filter
        rows = await pool.fetch("""
            SELECT t.from_user_id, u1.username as sender_name,
                   t.to_user_id, u2.username as receiver_name,
                   COUNT(*) as trade_count
            FROM trades t
            JOIN users u1 ON u1.user_id = t.from_user_id
            JOIN users u2 ON u2.user_id = t.to_user_id
            WHERE t.created_at >= NOW() - INTERVAL '14 days'
            GROUP BY t.from_user_id, u1.username, t.to_user_id, u2.username
            HAVING COUNT(*) >= 3
            ORDER BY trade_count DESC
            LIMIT 20
        """)
    if not rows:
        print("  No suspicious trade pairs found (threshold: 3+ in 14 days)")
    for r in rows:
        print(f"  {r['sender_name'] or r['from_user_id']} -> {r['receiver_name'] or r['to_user_id']} | trades: {r['trade_count']}")

    # 5. Users registered close together (possible alts)
    print("\n" + "=" * 60)
    print("5. USERS REGISTERED WITHIN 2 MINUTES (last 30 days)")
    print("=" * 60)
    rows = await pool.fetch("""
        SELECT a.user_id as uid1, a.username as name1,
               b.user_id as uid2, b.username as name2,
               a.registered_at
        FROM users a
        JOIN users b ON a.user_id < b.user_id
            AND ABS(EXTRACT(EPOCH FROM a.registered_at - b.registered_at)) < 120
        WHERE a.registered_at >= NOW() - INTERVAL '30 days'
        ORDER BY a.registered_at DESC
        LIMIT 20
    """)
    if not rows:
        print("  No users registered within 2 minutes of each other")
    for r in rows:
        print(f"  {r['registered_at']} | {r['uid1']}(@{r['name1']}) & {r['uid2']}(@{r['name2']})")

    # 6. Catch rate leaders (last 7 days)
    print("\n" + "=" * 60)
    print("6. HIGHEST CATCHES/DAY (last 7 days, min 15 catches)")
    print("=" * 60)
    rows = await pool.fetch("""
        WITH user_catches AS (
            SELECT user_id, COUNT(*) as catches,
                   COUNT(DISTINCT DATE(caught_at AT TIME ZONE 'Asia/Seoul')) as active_days
            FROM user_pokemon
            WHERE caught_at >= NOW() - INTERVAL '7 days'
            GROUP BY user_id
            HAVING COUNT(*) >= 15
        )
        SELECT uc.user_id, u.username, u.display_name,
               uc.catches, uc.active_days,
               ROUND(uc.catches::numeric / GREATEST(uc.active_days, 1), 1) as catches_per_day
        FROM user_catches uc
        JOIN users u ON u.user_id = uc.user_id
        ORDER BY catches_per_day DESC
        LIMIT 20
    """)
    for r in rows:
        print(f"  ID:{r['user_id']} @{r['username'] or r['display_name']} | catches: {r['catches']} in {r['active_days']}d | {r['catches_per_day']}/day")

    # 7. Late-night catchers (2AM-6AM KST consistently)
    print("\n" + "=" * 60)
    print("7. LATE-NIGHT CATCHERS (2AM-6AM KST, last 7 days)")
    print("=" * 60)
    rows = await pool.fetch("""
        SELECT u.user_id, u.username, u.display_name,
               COUNT(*) as night_catches,
               COUNT(DISTINCT DATE(p.caught_at AT TIME ZONE 'Asia/Seoul')) as night_days
        FROM user_pokemon p
        JOIN users u ON u.user_id = p.user_id
        WHERE p.caught_at >= NOW() - INTERVAL '7 days'
          AND EXTRACT(HOUR FROM p.caught_at AT TIME ZONE 'Asia/Seoul') BETWEEN 2 AND 5
        GROUP BY u.user_id, u.username, u.display_name
        HAVING COUNT(*) >= 5
        ORDER BY night_catches DESC
        LIMIT 15
    """)
    if not rows:
        print("  No users with 5+ catches during 2-6AM KST")
    for r in rows:
        print(f"  ID:{r['user_id']} @{r['username'] or r['display_name']} | night_catches: {r['night_catches']} over {r['night_days']} nights")

    # 8. Total pokemon count per user (wealth check)
    print("\n" + "=" * 60)
    print("8. TOP POKEMON COLLECTORS (total owned)")
    print("=" * 60)
    rows = await pool.fetch("""
        SELECT u.user_id, u.username, u.display_name,
               COUNT(*) as total_pokemon,
               u.battle_points,
               u.registered_at
        FROM user_pokemon p
        JOIN users u ON u.user_id = p.user_id
        GROUP BY u.user_id, u.username, u.display_name, u.battle_points, u.registered_at
        ORDER BY total_pokemon DESC
        LIMIT 15
    """)
    for r in rows:
        print(f"  ID:{r['user_id']} @{r['username'] or r['display_name']} | pokemon: {r['total_pokemon']} | BP:{r['battle_points']} | since:{r['registered_at'].strftime('%Y-%m-%d') if r['registered_at'] else '?'}")

asyncio.run(main())
