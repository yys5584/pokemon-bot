"""
Abuse analysis script - READ ONLY, no data modifications.
Analyzes suspected bot/alt accounts.
"""
import asyncio
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv('/home/ubuntu/pokemon-bot/.env')

# All suspect IDs (known)
HIGH_PRIORITY = {
    7609021791: 'Turri0630',
    1386472342: 'fowlartemiss',
    6795306901: 'Y_THEBEST',
    7050637391: 'peterchat7',
    6007036282: 'holysouling',
    7437353379: 'Keepgoingthat',
}

CLUSTER_USERNAMES = ['jojokor', 'nomadyam', 'imverysorry77', 'farmsang', 'liveanzel365', 'bitbehind8']
ALT_USERNAMES = ['alcheowl', 'artechowl']

async def main():
    from database import connection
    pool = await connection.get_db()

    # ============================================================
    # STEP 1: Resolve unknown IDs
    # ============================================================
    print("=" * 80)
    print("STEP 1: RESOLVING USER IDS")
    print("=" * 80)

    all_usernames = CLUSTER_USERNAMES + ALT_USERNAMES
    resolved = await pool.fetch(
        "SELECT user_id, username, display_name, registered_at AT TIME ZONE 'Asia/Seoul' as reg_kst, "
        "master_balls, hyper_balls, battle_points, battle_wins, battle_losses "
        "FROM users WHERE LOWER(username) = ANY($1)",
        [u.lower() for u in all_usernames]
    )

    cluster_ids = {}
    alt_ids = {}
    for r in resolved:
        uname = r['username'].lower() if r['username'] else ''
        if uname in [u.lower() for u in CLUSTER_USERNAMES]:
            cluster_ids[r['user_id']] = r['username']
        elif uname in [u.lower() for u in ALT_USERNAMES]:
            alt_ids[r['user_id']] = r['username']
        print(f"  @{r['username']} -> ID: {r['user_id']}, display: {r['display_name']}, "
              f"registered: {r['reg_kst']}, BP: {r['battle_points']}, "
              f"MB: {r['master_balls']}, HB: {r['hyper_balls']}")

    # Combine all suspect IDs
    ALL_IDS = dict(HIGH_PRIORITY)
    ALL_IDS.update(cluster_ids)
    ALL_IDS.update(alt_ids)

    id_list = list(ALL_IDS.keys())

    # ============================================================
    # STEP 2: Account overview for ALL suspects
    # ============================================================
    print("\n" + "=" * 80)
    print("STEP 2: ACCOUNT OVERVIEW")
    print("=" * 80)

    for uid, uname in ALL_IDS.items():
        user = await pool.fetchrow(
            "SELECT user_id, username, display_name, "
            "registered_at AT TIME ZONE 'Asia/Seoul' as reg_kst, "
            "last_active_at AT TIME ZONE 'Asia/Seoul' as last_active_kst, "
            "master_balls, hyper_balls, battle_points, battle_wins, battle_losses, "
            "battle_streak, best_streak "
            "FROM users WHERE user_id = $1", uid
        )
        if not user:
            print(f"\n  @{uname} (ID: {uid}) - NOT FOUND IN DB")
            continue

        pokemon_count = await pool.fetchval(
            "SELECT COUNT(*) FROM user_pokemon WHERE user_id = $1", uid
        )
        shiny_count = await pool.fetchval(
            "SELECT COUNT(*) FROM user_pokemon WHERE user_id = $1 AND is_shiny = 1", uid
        )

        print(f"\n--- @{user['username']} (ID: {uid}) ---")
        print(f"  Display name: {user['display_name']}")
        print(f"  Registered: {user['reg_kst']}")
        print(f"  Last active: {user['last_active_kst']}")
        print(f"  Pokemon owned: {pokemon_count} (shiny: {shiny_count})")
        print(f"  BP: {user['battle_points']}, Master balls: {user['master_balls']}, Hyper balls: {user['hyper_balls']}")
        print(f"  Battle W/L: {user['battle_wins']}/{user['battle_losses']}, streak: {user['battle_streak']}, best: {user['best_streak']}")

    # ============================================================
    # STEP 3: HOURLY CATCH DISTRIBUTION (last 7 days)
    # ============================================================
    print("\n" + "=" * 80)
    print("STEP 3: HOURLY CATCH DISTRIBUTION (last 7 days, KST)")
    print("=" * 80)

    for uid, uname in ALL_IDS.items():
        rows = await pool.fetch("""
            SELECT EXTRACT(HOUR FROM caught_at AT TIME ZONE 'Asia/Seoul')::int as hour,
                   COUNT(*) as cnt
            FROM user_pokemon
            WHERE user_id = $1 AND caught_at >= NOW() - INTERVAL '7 days'
            GROUP BY hour ORDER BY hour
        """, uid)

        hour_map = {r['hour']: r['cnt'] for r in rows}
        total = sum(hour_map.values())

        print(f"\n--- @{uname} (ID: {uid}) --- total catches: {total}")
        for h in range(24):
            cnt = hour_map.get(h, 0)
            bar = '#' * min(cnt, 80)
            print(f"  {h:02d}:00  {cnt:4d}  {bar}")

    # ============================================================
    # STEP 4: DAILY CATCH COUNTS (last 7 days)
    # ============================================================
    print("\n" + "=" * 80)
    print("STEP 4: DAILY CATCH COUNTS (last 7 days, KST)")
    print("=" * 80)

    for uid, uname in ALL_IDS.items():
        rows = await pool.fetch("""
            SELECT (caught_at AT TIME ZONE 'Asia/Seoul')::date as day,
                   COUNT(*) as cnt
            FROM user_pokemon
            WHERE user_id = $1 AND caught_at >= NOW() - INTERVAL '7 days'
            GROUP BY day ORDER BY day
        """, uid)

        print(f"\n--- @{uname} (ID: {uid}) ---")
        for r in rows:
            print(f"  {r['day']}  {r['cnt']:4d} catches")

    # ============================================================
    # STEP 5: AVG TIME BETWEEN CATCHES (last 7 days)
    # ============================================================
    print("\n" + "=" * 80)
    print("STEP 5: CATCH INTERVAL STATS (last 7 days)")
    print("=" * 80)

    for uid, uname in ALL_IDS.items():
        rows = await pool.fetch("""
            SELECT caught_at FROM user_pokemon
            WHERE user_id = $1 AND caught_at >= NOW() - INTERVAL '7 days'
            ORDER BY caught_at
        """, uid)

        if len(rows) < 2:
            print(f"\n--- @{uname}: insufficient data ({len(rows)} catches)")
            continue

        intervals = []
        for i in range(1, len(rows)):
            delta = (rows[i]['caught_at'] - rows[i-1]['caught_at']).total_seconds()
            if delta < 3600:  # only count intervals < 1 hour (same session)
                intervals.append(delta)

        if intervals:
            avg_int = sum(intervals) / len(intervals)
            min_int = min(intervals)
            max_int = max(intervals)
            # Standard deviation
            variance = sum((x - avg_int) ** 2 for x in intervals) / len(intervals)
            std_int = variance ** 0.5

            # Count very fast catches (< 5 seconds)
            fast_catches = sum(1 for x in intervals if x < 5)

            print(f"\n--- @{uname} (ID: {uid}) --- {len(intervals)} intervals (within-session)")
            print(f"  Avg: {avg_int:.1f}s, Std: {std_int:.1f}s, Min: {min_int:.1f}s, Max: {max_int:.1f}s")
            print(f"  Catches < 5s apart: {fast_catches}")
        else:
            print(f"\n--- @{uname}: no within-session intervals")

    # ============================================================
    # STEP 6: CATCH ATTEMPTS vs SUCCESSES
    # ============================================================
    print("\n" + "=" * 80)
    print("STEP 6: CATCH ATTEMPTS (last 7 days)")
    print("=" * 80)

    for uid, uname in ALL_IDS.items():
        row = await pool.fetchrow("""
            SELECT COUNT(*) as total_attempts,
                   SUM(CASE WHEN used_master_ball THEN 1 ELSE 0 END) as master_used,
                   SUM(CASE WHEN used_hyper_ball THEN 1 ELSE 0 END) as hyper_used
            FROM catch_attempts
            WHERE user_id = $1 AND attempted_at >= NOW() - INTERVAL '7 days'
        """, uid)

        catches = await pool.fetchval("""
            SELECT COUNT(*) FROM user_pokemon
            WHERE user_id = $1 AND caught_at >= NOW() - INTERVAL '7 days'
        """, uid)

        attempts = row['total_attempts']
        rate = (catches / attempts * 100) if attempts > 0 else 0

        print(f"\n--- @{uname} (ID: {uid}) ---")
        print(f"  Attempts: {attempts}, Catches: {catches}, Rate: {rate:.1f}%")
        print(f"  Master balls used: {row['master_used']}, Hyper balls used: {row['hyper_used']}")

    # ============================================================
    # STEP 7: CHAT ROOMS THEY OPERATE IN
    # ============================================================
    print("\n" + "=" * 80)
    print("STEP 7: CATCH ROOMS (last 7 days)")
    print("=" * 80)

    for uid, uname in ALL_IDS.items():
        rows = await pool.fetch("""
            SELECT up.caught_in_chat_id, cr.title as chat_title, COUNT(*) as cnt
            FROM user_pokemon up
            LEFT JOIN chat_rooms cr ON cr.chat_id = up.caught_in_chat_id
            WHERE up.user_id = $1 AND up.caught_at >= NOW() - INTERVAL '7 days'
            GROUP BY up.caught_in_chat_id, cr.title
            ORDER BY cnt DESC
            LIMIT 10
        """, uid)

        print(f"\n--- @{uname} (ID: {uid}) ---")
        for r in rows:
            title = r['chat_title'] or 'Unknown'
            print(f"  {title[:40]:40s}  (chat_id: {r['caught_in_chat_id']})  {r['cnt']:4d} catches")

    # ============================================================
    # STEP 8: TRADE PARTNERS
    # ============================================================
    print("\n" + "=" * 80)
    print("STEP 8: TRADE PARTNERS (all time)")
    print("=" * 80)

    for uid, uname in ALL_IDS.items():
        # Trades sent
        sent = await pool.fetch("""
            SELECT to_user_id, u.username, COUNT(*) as cnt
            FROM trades t
            LEFT JOIN users u ON u.user_id = t.to_user_id
            WHERE t.from_user_id = $1 AND t.status = 'completed'
            GROUP BY to_user_id, u.username
            ORDER BY cnt DESC LIMIT 5
        """, uid)

        # Trades received
        recv = await pool.fetch("""
            SELECT from_user_id, u.username, COUNT(*) as cnt
            FROM trades t
            LEFT JOIN users u ON u.user_id = t.from_user_id
            WHERE t.to_user_id = $1 AND t.status = 'completed'
            GROUP BY from_user_id, u.username
            ORDER BY cnt DESC LIMIT 5
        """, uid)

        print(f"\n--- @{uname} (ID: {uid}) ---")
        print(f"  SENT TO:")
        for r in sent:
            partner = r['username'] or str(r['to_user_id'])
            is_suspect = ' *** SUSPECT' if r['to_user_id'] in ALL_IDS else ''
            print(f"    @{partner}: {r['cnt']} trades{is_suspect}")
        if not sent:
            print(f"    (none)")

        print(f"  RECEIVED FROM:")
        for r in recv:
            partner = r['username'] or str(r['from_user_id'])
            is_suspect = ' *** SUSPECT' if r['from_user_id'] in ALL_IDS else ''
            print(f"    @{partner}: {r['cnt']} trades{is_suspect}")
        if not recv:
            print(f"    (none)")

    # ============================================================
    # STEP 9: CLUSTER CROSS-ANALYSIS
    # ============================================================
    print("\n" + "=" * 80)
    print("STEP 9: 6-ACCOUNT CLUSTER CROSS-ANALYSIS")
    print("=" * 80)

    if cluster_ids:
        cluster_id_list = list(cluster_ids.keys())

        # Internal trades
        internal = await pool.fetch("""
            SELECT t.from_user_id, u1.username as from_user,
                   t.to_user_id, u2.username as to_user,
                   COUNT(*) as cnt
            FROM trades t
            JOIN users u1 ON u1.user_id = t.from_user_id
            JOIN users u2 ON u2.user_id = t.to_user_id
            WHERE t.from_user_id = ANY($1) AND t.to_user_id = ANY($1)
              AND t.status = 'completed'
            GROUP BY t.from_user_id, u1.username, t.to_user_id, u2.username
            ORDER BY cnt DESC
        """, cluster_id_list)

        print("\n  INTERNAL TRADES (within cluster):")
        for r in internal:
            print(f"    @{r['from_user']} -> @{r['to_user']}: {r['cnt']} trades")
        if not internal:
            print("    (none)")

        # Shared chat rooms
        print("\n  SHARED CATCH ROOMS:")
        for uid in cluster_id_list:
            rooms = await pool.fetch("""
                SELECT DISTINCT caught_in_chat_id FROM user_pokemon
                WHERE user_id = $1 AND caught_at >= NOW() - INTERVAL '30 days'
            """, uid)
            room_set = {r['caught_in_chat_id'] for r in rooms}
            print(f"    @{cluster_ids[uid]}: {room_set}")

    # ============================================================
    # STEP 10: ALT ACCOUNT COMPARISON (alcheowl vs artechowl)
    # ============================================================
    print("\n" + "=" * 80)
    print("STEP 10: ALCHEOWL vs ARTECHOWL COMPARISON")
    print("=" * 80)

    if len(alt_ids) == 2:
        for uid, uname in alt_ids.items():
            rows = await pool.fetch("""
                SELECT EXTRACT(HOUR FROM caught_at AT TIME ZONE 'Asia/Seoul')::int as hour,
                       COUNT(*) as cnt
                FROM user_pokemon
                WHERE user_id = $1 AND caught_at >= NOW() - INTERVAL '14 days'
                GROUP BY hour ORDER BY hour
            """, uid)
            hour_map = {r['hour']: r['cnt'] for r in rows}
            print(f"\n  @{uname} hourly (14 days):")
            for h in range(24):
                cnt = hour_map.get(h, 0)
                bar = '#' * min(cnt, 60)
                print(f"    {h:02d}:00  {cnt:4d}  {bar}")

        # Internal trades between the two
        alt_list = list(alt_ids.keys())
        internal = await pool.fetch("""
            SELECT t.from_user_id, u1.username as from_user,
                   t.to_user_id, u2.username as to_user,
                   COUNT(*) as cnt
            FROM trades t
            JOIN users u1 ON u1.user_id = t.from_user_id
            JOIN users u2 ON u2.user_id = t.to_user_id
            WHERE t.from_user_id = ANY($1) AND t.to_user_id = ANY($1)
              AND t.status = 'completed'
            GROUP BY t.from_user_id, u1.username, t.to_user_id, u2.username
            ORDER BY cnt DESC
        """, alt_list)

        print("\n  TRADES BETWEEN ALCHEOWL <-> ARTECHOWL:")
        for r in internal:
            print(f"    @{r['from_user']} -> @{r['to_user']}: {r['cnt']} trades")
        if not internal:
            print("    (none)")

    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)

asyncio.run(main())
