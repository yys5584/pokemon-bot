"""
매크로 의심 유저 분석 스크립트
- 타겟: Revuildio, Turri (username 기준)
- 비교: 정상 유저 3명 (최근 7일 활동 상위)
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

import asyncpg

DATABASE_URL = os.environ["DATABASE_URL"]


async def main():
    pool = await asyncpg.create_pool(DATABASE_URL, statement_cache_size=0)

    # 1. 타겟 유저 조회
    target_usernames = ['artechowl', 'Turri0630']
    targets = await pool.fetch(
        "SELECT user_id, username, display_name FROM users WHERE username = ANY($1::text[])",
        target_usernames
    )
    if not targets:
        # case-insensitive fallback
        targets = await pool.fetch(
            "SELECT user_id, username, display_name FROM users WHERE LOWER(username) = ANY($1::text[])",
            [u.lower() for u in target_usernames]
        )

    target_ids = [r['user_id'] for r in targets]
    print("=" * 80)
    print("타겟 유저")
    print("=" * 80)
    for r in targets:
        print(f"  user_id={r['user_id']}  username={r['username']}  display_name={r['display_name']}")

    if not target_ids:
        print("타겟 유저를 찾을 수 없습니다.")
        await pool.close()
        return

    # 비교 유저: 최근 7일 포획 수 상위 3명 (타겟 제외)
    comparison = await pool.fetch("""
        SELECT u.user_id, u.username, u.display_name, COUNT(*) as catches
        FROM catch_attempts ca
        JOIN spawn_sessions ss ON ca.session_id = ss.id
        JOIN users u ON ca.user_id = u.user_id
        WHERE ss.spawned_at >= NOW() - INTERVAL '7 days'
          AND ss.caught_by_user_id = ca.user_id
          AND ca.user_id != ALL($1::bigint[])
        GROUP BY u.user_id, u.username, u.display_name
        ORDER BY catches DESC
        LIMIT 3
    """, target_ids)

    comp_ids = [r['user_id'] for r in comparison]
    print("\n비교 유저 (최근 7일 포획 상위 3명)")
    print("-" * 60)
    for r in comparison:
        print(f"  user_id={r['user_id']}  username={r['username']}  name={r['display_name']}  포획={r['catches']}")

    all_ids = target_ids + comp_ids

    # ===== 2. 포획 분석 =====
    print("\n" + "=" * 80)
    print("포획 분석 (최근 7일)")
    print("=" * 80)

    # 2-1. 응답시간 통계 (catch_attempts.attempted_at - spawn_sessions.spawned_at)
    response_stats = await pool.fetch("""
        SELECT
            ca.user_id,
            u.username,
            COUNT(*) as total_catches,
            AVG(EXTRACT(EPOCH FROM (ca.attempted_at - ss.spawned_at))) as avg_response_sec,
            STDDEV(EXTRACT(EPOCH FROM (ca.attempted_at - ss.spawned_at))) as stddev_response_sec,
            MIN(EXTRACT(EPOCH FROM (ca.attempted_at - ss.spawned_at))) as min_response_sec,
            MAX(EXTRACT(EPOCH FROM (ca.attempted_at - ss.spawned_at))) as max_response_sec,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (ca.attempted_at - ss.spawned_at))) as median_response_sec,
            PERCENTILE_CONT(0.1) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (ca.attempted_at - ss.spawned_at))) as p10_response_sec
        FROM catch_attempts ca
        JOIN spawn_sessions ss ON ca.session_id = ss.id
        JOIN users u ON ca.user_id = u.user_id
        WHERE ss.spawned_at >= NOW() - INTERVAL '7 days'
          AND ss.caught_by_user_id = ca.user_id
          AND ca.user_id = ANY($1::bigint[])
        GROUP BY ca.user_id, u.username
        ORDER BY avg_response_sec
    """, all_ids)

    print(f"\n{'유저':<16} {'포획수':>6} {'평균(초)':>8} {'표준편차':>8} {'최소':>6} {'중앙':>6} {'P10':>6} {'최대':>8}")
    print("-" * 80)
    for r in response_stats:
        tag = " ★" if r['user_id'] in target_ids else ""
        print(f"{(r['username'] or '?'):<16} {r['total_catches']:>6} "
              f"{r['avg_response_sec']:>8.1f} {(r['stddev_response_sec'] or 0):>8.1f} "
              f"{r['min_response_sec']:>6.1f} {r['median_response_sec']:>6.1f} "
              f"{r['p10_response_sec']:>6.1f} {r['max_response_sec']:>8.1f}{tag}")

    # 2-2. 1초 이내 응답 비율
    fast_response = await pool.fetch("""
        SELECT
            ca.user_id,
            u.username,
            COUNT(*) FILTER (WHERE EXTRACT(EPOCH FROM (ca.attempted_at - ss.spawned_at)) < 1) as under_1s,
            COUNT(*) FILTER (WHERE EXTRACT(EPOCH FROM (ca.attempted_at - ss.spawned_at)) < 2) as under_2s,
            COUNT(*) FILTER (WHERE EXTRACT(EPOCH FROM (ca.attempted_at - ss.spawned_at)) < 3) as under_3s,
            COUNT(*) as total
        FROM catch_attempts ca
        JOIN spawn_sessions ss ON ca.session_id = ss.id
        JOIN users u ON ca.user_id = u.user_id
        WHERE ss.spawned_at >= NOW() - INTERVAL '7 days'
          AND ss.caught_by_user_id = ca.user_id
          AND ca.user_id = ANY($1::bigint[])
        GROUP BY ca.user_id, u.username
        ORDER BY ca.user_id
    """, all_ids)

    print(f"\n{'유저':<16} {'<1초':>6} {'<2초':>6} {'<3초':>6} {'전체':>6} {'<1초%':>7} {'<2초%':>7}")
    print("-" * 60)
    for r in fast_response:
        tag = " ★" if r['user_id'] in target_ids else ""
        pct1 = r['under_1s'] / r['total'] * 100 if r['total'] else 0
        pct2 = r['under_2s'] / r['total'] * 100 if r['total'] else 0
        print(f"{(r['username'] or '?'):<16} {r['under_1s']:>6} {r['under_2s']:>6} {r['under_3s']:>6} "
              f"{r['total']:>6} {pct1:>6.1f}% {pct2:>6.1f}%{tag}")

    # 2-3. 시간대별 활동 분포 (KST)
    hourly = await pool.fetch("""
        SELECT
            ca.user_id,
            u.username,
            EXTRACT(HOUR FROM (ca.attempted_at AT TIME ZONE 'Asia/Seoul')) as hour_kst,
            COUNT(*) as cnt
        FROM catch_attempts ca
        JOIN spawn_sessions ss ON ca.session_id = ss.id
        JOIN users u ON ca.user_id = u.user_id
        WHERE ss.spawned_at >= NOW() - INTERVAL '7 days'
          AND ss.caught_by_user_id = ca.user_id
          AND ca.user_id = ANY($1::bigint[])
        GROUP BY ca.user_id, u.username, hour_kst
        ORDER BY ca.user_id, hour_kst
    """, all_ids)

    # 유저별로 그룹핑
    from collections import defaultdict
    hourly_map = defaultdict(lambda: defaultdict(int))
    username_map = {}
    for r in hourly:
        hourly_map[r['user_id']][int(r['hour_kst'])] = r['cnt']
        username_map[r['user_id']] = r['username'] or '?'

    print(f"\n시간대별 포획 분포 (KST)")
    print("-" * 80)
    header = f"{'유저':<14}" + "".join(f"{h:>4}" for h in range(24)) + "  활동시간"
    print(header)
    for uid in all_ids:
        if uid not in hourly_map:
            continue
        tag = "★" if uid in target_ids else " "
        hours = hourly_map[uid]
        active_hours = sum(1 for h in range(24) if hours.get(h, 0) > 0)
        row = f"{username_map.get(uid, '?'):<13}{tag}" + "".join(f"{hours.get(h, 0):>4}" for h in range(24))
        row += f"  {active_hours}h"
        print(row)

    # 2-4. 최장 무중단 활동 (연속 포획 간격 5분 이내)
    print(f"\n최장 무중단 활동 구간 (포획 간격 5분 이내)")
    print("-" * 80)
    for uid in all_ids:
        catches = await pool.fetch("""
            SELECT ca.attempted_at AT TIME ZONE 'Asia/Seoul' as ts
            FROM catch_attempts ca
            JOIN spawn_sessions ss ON ca.session_id = ss.id
            WHERE ss.spawned_at >= NOW() - INTERVAL '7 days'
              AND ss.caught_by_user_id = ca.user_id
              AND ca.user_id = $1
            ORDER BY ca.attempted_at
        """, uid)
        if not catches:
            continue

        # 연속 구간 계산
        max_streak_minutes = 0
        max_streak_start = None
        max_streak_end = None
        max_streak_count = 0

        streak_start = catches[0]['ts']
        streak_count = 1
        prev_ts = catches[0]['ts']

        for i in range(1, len(catches)):
            ts = catches[i]['ts']
            gap = (ts - prev_ts).total_seconds()
            if gap <= 300:  # 5분
                streak_count += 1
            else:
                streak_minutes = (prev_ts - streak_start).total_seconds() / 60
                if streak_minutes > max_streak_minutes:
                    max_streak_minutes = streak_minutes
                    max_streak_start = streak_start
                    max_streak_end = prev_ts
                    max_streak_count = streak_count
                streak_start = ts
                streak_count = 1
            prev_ts = ts

        # 마지막 구간 체크
        streak_minutes = (prev_ts - streak_start).total_seconds() / 60
        if streak_minutes > max_streak_minutes:
            max_streak_minutes = streak_minutes
            max_streak_start = streak_start
            max_streak_end = prev_ts
            max_streak_count = streak_count

        tag = " ★" if uid in target_ids else ""
        name = username_map.get(uid, '?')
        hours = max_streak_minutes / 60
        if max_streak_start:
            print(f"  {name:<14} {hours:>5.1f}시간 ({max_streak_count}회 포획)  "
                  f"{max_streak_start.strftime('%m/%d %H:%M')}~{max_streak_end.strftime('%H:%M')} KST{tag}")
        else:
            print(f"  {name:<14} 데이터 없음{tag}")

    # 2-5. 일별 포획 수
    daily_catches = await pool.fetch("""
        SELECT
            ca.user_id,
            u.username,
            (ca.attempted_at AT TIME ZONE 'Asia/Seoul')::date as day,
            COUNT(*) as cnt
        FROM catch_attempts ca
        JOIN spawn_sessions ss ON ca.session_id = ss.id
        JOIN users u ON ca.user_id = u.user_id
        WHERE ss.spawned_at >= NOW() - INTERVAL '7 days'
          AND ss.caught_by_user_id = ca.user_id
          AND ca.user_id = ANY($1::bigint[])
        GROUP BY ca.user_id, u.username, day
        ORDER BY day, ca.user_id
    """, all_ids)

    daily_map = defaultdict(lambda: defaultdict(int))
    all_days = set()
    for r in daily_catches:
        daily_map[r['user_id']][str(r['day'])] = r['cnt']
        username_map[r['user_id']] = r['username'] or '?'
        all_days.add(str(r['day']))

    sorted_days = sorted(all_days)
    print(f"\n일별 포획 수")
    print("-" * 80)
    header = f"{'유저':<14}" + "".join(f"{d[5:]:>8}" for d in sorted_days) + "    합계"
    print(header)
    for uid in all_ids:
        if uid not in daily_map:
            continue
        tag = "★" if uid in target_ids else " "
        total = sum(daily_map[uid].values())
        row = f"{username_map.get(uid, '?'):<13}{tag}" + "".join(f"{daily_map[uid].get(d, 0):>8}" for d in sorted_days)
        row += f"  {total:>6}"
        print(row)

    # ===== 3. 배틀 분석 =====
    print("\n" + "=" * 80)
    print("배틀 분석 (최근 7일)")
    print("=" * 80)

    # 3-1. 동일 상대 반복 배틀
    repeat_battles = await pool.fetch("""
        SELECT
            LEAST(winner_id, loser_id) as u1,
            GREATEST(winner_id, loser_id) as u2,
            COUNT(*) as cnt,
            u1t.username as u1_name,
            u2t.username as u2_name
        FROM battle_records br
        JOIN users u1t ON LEAST(br.winner_id, br.loser_id) = u1t.user_id
        JOIN users u2t ON GREATEST(br.winner_id, br.loser_id) = u2t.user_id
        WHERE br.created_at >= NOW() - INTERVAL '7 days'
          AND (br.winner_id = ANY($1::bigint[]) OR br.loser_id = ANY($1::bigint[]))
        GROUP BY u1, u2, u1t.username, u2t.username
        HAVING COUNT(*) >= 3
        ORDER BY cnt DESC
    """, target_ids)

    print(f"\n동일 상대 반복 배틀 (타겟 유저 관련, 3회 이상)")
    print(f"{'유저1':<16} {'유저2':<16} {'횟수':>6}")
    print("-" * 40)
    for r in repeat_battles:
        print(f"{(r['u1_name'] or '?'):<16} {(r['u2_name'] or '?'):<16} {r['cnt']:>6}")

    if not repeat_battles:
        print("  (해당 없음)")

    # 3-2. 배틀 수락 응답시간
    battle_response = await pool.fetch("""
        SELECT
            bc.challenger_id,
            bc.defender_id,
            u1.username as challenger_name,
            u2.username as defender_name,
            AVG(EXTRACT(EPOCH FROM (br.created_at - bc.created_at))) as avg_accept_sec,
            MIN(EXTRACT(EPOCH FROM (br.created_at - bc.created_at))) as min_accept_sec,
            COUNT(*) as cnt
        FROM battle_records br
        JOIN battle_challenges bc ON br.challenge_id = bc.id
        JOIN users u1 ON bc.challenger_id = u1.user_id
        JOIN users u2 ON bc.defender_id = u2.user_id
        WHERE br.created_at >= NOW() - INTERVAL '7 days'
          AND (bc.challenger_id = ANY($1::bigint[]) OR bc.defender_id = ANY($1::bigint[]))
        GROUP BY bc.challenger_id, bc.defender_id, u1.username, u2.username
        HAVING COUNT(*) >= 3
        ORDER BY avg_accept_sec
    """, target_ids)

    print(f"\n배틀 수락 응답시간 (타겟 관련 매칭, 3회 이상)")
    print(f"{'도전자':<14} {'수비자':<14} {'횟수':>5} {'평균(초)':>8} {'최소(초)':>8}")
    print("-" * 55)
    for r in battle_response:
        print(f"{(r['challenger_name'] or '?'):<14} {(r['defender_name'] or '?'):<14} "
              f"{r['cnt']:>5} {r['avg_accept_sec']:>8.1f} {r['min_accept_sec']:>8.1f}")

    if not battle_response:
        print("  (해당 없음)")

    # 3-3. 일별 배틀 수
    daily_battles = await pool.fetch("""
        SELECT
            sub.user_id,
            u.username,
            sub.day,
            sub.cnt
        FROM (
            SELECT winner_id as user_id,
                   (created_at AT TIME ZONE 'Asia/Seoul')::date as day,
                   COUNT(*) as cnt
            FROM battle_records
            WHERE created_at >= NOW() - INTERVAL '7 days'
              AND winner_id = ANY($1::bigint[])
            GROUP BY winner_id, day
            UNION ALL
            SELECT loser_id as user_id,
                   (created_at AT TIME ZONE 'Asia/Seoul')::date as day,
                   COUNT(*) as cnt
            FROM battle_records
            WHERE created_at >= NOW() - INTERVAL '7 days'
              AND loser_id = ANY($1::bigint[])
            GROUP BY loser_id, day
        ) sub
        JOIN users u ON sub.user_id = u.user_id
        ORDER BY sub.day, sub.user_id
    """, all_ids)

    battle_daily_map = defaultdict(lambda: defaultdict(int))
    battle_days = set()
    for r in daily_battles:
        battle_daily_map[r['user_id']][str(r['day'])] += r['cnt']
        username_map[r['user_id']] = r['username'] or '?'
        battle_days.add(str(r['day']))

    sorted_bdays = sorted(battle_days)
    print(f"\n일별 배틀 수")
    print("-" * 80)
    header = f"{'유저':<14}" + "".join(f"{d[5:]:>8}" for d in sorted_bdays) + "    합계"
    print(header)
    for uid in all_ids:
        if uid not in battle_daily_map:
            continue
        tag = "★" if uid in target_ids else " "
        total = sum(battle_daily_map[uid].values())
        row = f"{username_map.get(uid, '?'):<13}{tag}" + "".join(f"{battle_daily_map[uid].get(d, 0):>8}" for d in sorted_bdays)
        row += f"  {total:>6}"
        print(row)

    await pool.close()
    print("\n분석 완료.")


if __name__ == "__main__":
    asyncio.run(main())
