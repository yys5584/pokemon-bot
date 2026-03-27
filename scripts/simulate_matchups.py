"""상위 랭커 팀 분석 + 내 포켓몬으로 카운터팀 시뮬레이션"""
import asyncio, asyncpg, os, sys, random, itertools
from dotenv import load_dotenv
load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from utils.battle_calc import (
    calc_battle_stats, get_normalized_base_stats, get_type_multiplier, EVO_STAGE_MAP
)
from models.pokemon_base_stats import POKEMON_BASE_STATS
from models.pokemon_battle_data import POKEMON_BATTLE_DATA

import re
def strip_emoji(s):
    return re.sub(r'[^\w\s.,-]', '', s or '', flags=re.UNICODE).strip()

MY_UID = 1832746512
COST_MAP = {'common':1,'rare':2,'epic':4,'legendary':5,'ultra_legendary':6}
MAX_COST = 18

def calc_pokemon_stats(pokemon_id, rarity, stat_type, ivs, friendship=5):
    """Calculate full battle stats for a pokemon."""
    evo_stage = EVO_STAGE_MAP.get(pokemon_id, 3)
    base = get_normalized_base_stats(pokemon_id)
    if base:
        return calc_battle_stats(
            rarity, stat_type, friendship, evo_stage,
            ivs['iv_hp'], ivs['iv_atk'], ivs['iv_def'],
            ivs['iv_spa'], ivs['iv_spdef'], ivs['iv_spd'],
            **base
        )
    else:
        return calc_battle_stats(
            rarity, stat_type, friendship, evo_stage,
            ivs['iv_hp'], ivs['iv_atk'], ivs['iv_def'],
            ivs['iv_spa'], ivs['iv_spdef'], ivs['iv_spd'],
        )

def simulate_1v1(atk_stats, atk_type, def_stats, def_type):
    """Simulate 1v1 damage exchange. Returns (atk_remaining_hp, def_remaining_hp) after one exchange."""
    # Determine type multiplier
    mult_ad, _ = get_type_multiplier(atk_type, def_type)
    mult_da, _ = get_type_multiplier(def_type, atk_type)

    # Determine attack stats (higher of atk/spa)
    a_atk = max(atk_stats['atk'], atk_stats['spa'])
    a_def_stat = def_stats['spdef'] if atk_stats['spa'] > atk_stats['atk'] else def_stats['def']
    d_atk = max(def_stats['atk'], def_stats['spa'])
    d_def_stat = atk_stats['spdef'] if def_stats['spa'] > def_stats['atk'] else atk_stats['def']

    # Damage formula
    base_power = config.BATTLE_BASE_POWER  # 130
    a_dmg = max(1, int((22 * base_power * a_atk / a_def_stat) / 50 + 2)) * mult_ad
    d_dmg = max(1, int((22 * base_power * d_atk / d_def_stat) / 50 + 2)) * mult_da

    return a_dmg, d_dmg

def simulate_battle(team_a, team_b, n_sims=200):
    """Simulate full 6v6 battle n times, return win rate for team_a."""
    wins = 0
    for _ in range(n_sims):
        # Copy HP
        a_hp = [p['stats']['hp'] for p in team_a]
        b_hp = [p['stats']['hp'] for p in team_b]
        a_idx, b_idx = 0, 0

        for _round in range(50):
            if a_idx >= len(team_a) or b_idx >= len(team_b):
                break

            pa, pb = team_a[a_idx], team_b[b_idx]
            a_dmg, d_dmg = simulate_1v1(pa['stats'], pa['type'], pb['stats'], pb['type'])

            # Variance + crit
            a_var = random.uniform(0.9, 1.1)
            d_var = random.uniform(0.9, 1.1)
            a_crit = 1.5 if random.random() < 0.10 else 1.0
            d_crit = 1.5 if random.random() < 0.10 else 1.0

            final_a_dmg = int(a_dmg * a_var * a_crit)
            final_d_dmg = int(d_dmg * d_var * d_crit)

            # Speed determines who goes first
            if pa['stats']['spd'] >= pb['stats']['spd']:
                b_hp[b_idx] -= final_a_dmg
                if b_hp[b_idx] <= 0:
                    b_idx += 1
                    continue
                a_hp[a_idx] -= final_d_dmg
                if a_hp[a_idx] <= 0:
                    a_idx += 1
            else:
                a_hp[a_idx] -= final_d_dmg
                if a_hp[a_idx] <= 0:
                    a_idx += 1
                    continue
                b_hp[b_idx] -= final_a_dmg
                if b_hp[b_idx] <= 0:
                    b_idx += 1

        if b_idx >= len(team_b):
            wins += 1
        elif a_idx >= len(team_a):
            pass  # loss
        else:
            # Timeout: compare remaining HP
            a_total = sum(max(0, h) for h in a_hp[a_idx:])
            b_total = sum(max(0, h) for h in b_hp[b_idx:])
            if a_total > b_total:
                wins += 1

    return wins / n_sims

async def main():
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'), statement_cache_size=0)

    # 1. Top players
    top_rows = await conn.fetch('''
        SELECT sr.user_id, u.display_name, sr.ranked_wins, sr.ranked_losses
        FROM season_records sr
        JOIN users u ON u.user_id = sr.user_id
        WHERE sr.ranked_wins + sr.ranked_losses >= 5
        ORDER BY sr.ranked_wins - sr.ranked_losses DESC
        LIMIT 8
    ''')

    # 2. Get their teams
    top_teams = {}
    for r in top_rows:
        uid = r['user_id']
        if uid == MY_UID:
            continue
        rows = await conn.fetch('''
            SELECT bt.team_number, pm.id as pokemon_id, pm.name_ko, pm.rarity,
                   up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd,
                   pm.pokemon_type, pm.stat_type, up.friendship
            FROM battle_teams bt
            JOIN user_pokemon up ON up.id = bt.pokemon_instance_id
            JOIN pokemon_master pm ON pm.id = up.pokemon_id
            WHERE bt.user_id = $1 AND bt.team_number = 1
            ORDER BY bt.slot
        ''', uid)

        team = []
        for tr in rows:
            ptype = tr['pokemon_type']
            # Parse dual type
            if '/' in ptype:
                types = ptype.split('/')
            else:
                types = [ptype]
            # Also check POKEMON_BATTLE_DATA for canonical type
            bd = POKEMON_BATTLE_DATA.get(tr['pokemon_id'])
            if bd:
                types = bd[0] if isinstance(bd[0], list) else [bd[0]]

            ivs = {k: tr[k] or 15 for k in ['iv_hp','iv_atk','iv_def','iv_spa','iv_spdef','iv_spd']}
            stats = calc_pokemon_stats(tr['pokemon_id'], tr['rarity'], tr['stat_type'], ivs, tr['friendship'] or 0)
            team.append({
                'pid': tr['pokemon_id'], 'name': tr['name_ko'],
                'rarity': tr['rarity'], 'cost': COST_MAP[tr['rarity']],
                'type': types, 'stat_type': tr['stat_type'],
                'stats': stats, 'ivs': ivs,
            })
        name = strip_emoji(r['display_name'])
        top_teams[uid] = {'name': name, 'team': team,
                          'wins': r['ranked_wins'], 'losses': r['ranked_losses']}

    # 3. My pokemon
    my_rows = await conn.fetch('''
        SELECT up.id as iid, pm.id as pokemon_id, pm.name_ko, pm.rarity,
               up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd,
               pm.pokemon_type, pm.stat_type, up.friendship
        FROM user_pokemon up
        JOIN pokemon_master pm ON pm.id = up.pokemon_id
        WHERE up.user_id = $1
        ORDER BY
            CASE pm.rarity
                WHEN 'ultra_legendary' THEN 1 WHEN 'legendary' THEN 2
                WHEN 'epic' THEN 3 WHEN 'rare' THEN 4 ELSE 5 END,
            (up.iv_hp+up.iv_atk+up.iv_def+up.iv_spa+up.iv_spdef+up.iv_spd) DESC
    ''', MY_UID)

    my_pokemon = []
    seen_pids = set()
    for mr in my_rows:
        # 같은 포켓몬 중 최고 IV만 사용
        if mr['pokemon_id'] in seen_pids:
            continue
        seen_pids.add(mr['pokemon_id'])

        bd = POKEMON_BATTLE_DATA.get(mr['pokemon_id'])
        types = bd[0] if (bd and isinstance(bd[0], list)) else ([bd[0]] if bd else [mr['pokemon_type']])

        ivs = {k: mr[k] or 15 for k in ['iv_hp','iv_atk','iv_def','iv_spa','iv_spdef','iv_spd']}
        stats = calc_pokemon_stats(mr['pokemon_id'], mr['rarity'], mr['stat_type'], ivs, mr['friendship'] or 0)
        my_pokemon.append({
            'pid': mr['pokemon_id'], 'name': mr['name_ko'],
            'rarity': mr['rarity'], 'cost': COST_MAP[mr['rarity']],
            'type': types, 'stat_type': mr['stat_type'],
            'stats': stats, 'ivs': ivs, 'iid': mr['iid'],
            'iv_total': sum(ivs.values()),
            'power': sum(stats.values()),
        })

    await conn.close()

    # 4. Analyze each top player's team
    print("=" * 70)
    print("상위 랭커 팀 분석 + 카운터 시뮬레이션")
    print("=" * 70)

    for uid, info in top_teams.items():
        team = info['team']
        if not team:
            continue

        print(f"\n{'='*60}")
        print(f"📋 {info['name']} ({info['wins']}승 {info['losses']}패)")
        print(f"{'='*60}")
        total_cost = sum(p['cost'] for p in team)
        total_power = sum(sum(p['stats'].values()) for p in team)
        types_in_team = set()
        for p in team:
            for t in (p['type'] if isinstance(p['type'], list) else [p['type']]):
                types_in_team.add(t)

        print(f"총 코스트: {total_cost}/18 | 총 전투력: {total_power}")
        for p in team:
            pwr = sum(p['stats'].values())
            t_str = '/'.join(p['type']) if isinstance(p['type'], list) else p['type']
            print(f"  {p['name']:<8} [{p['rarity'][:3]}={p['cost']}] {t_str:<15} 전투력:{pwr:>5} HP:{p['stats']['hp']:>4}")

        # Find type weaknesses of their team
        print(f"\n팀 타입: {', '.join(types_in_team)}")

        # Find best types to counter their team
        type_scores = {}
        for attack_type in config.TYPE_ADVANTAGE:
            score = 0
            for p in team:
                m, _ = get_type_multiplier([attack_type], p['type'] if isinstance(p['type'], list) else [p['type']])
                if m > 1.0:
                    score += m * sum(p['stats'].values())  # weighted by power
                elif 0 < m < 1.0:
                    score -= (1/m) * sum(p['stats'].values()) * 0.3
                elif m == 0:
                    score -= sum(p['stats'].values()) * 0.5
            type_scores[attack_type] = score

        best_types = sorted(type_scores.items(), key=lambda x: -x[1])[:5]
        print(f"카운터 유리한 타입: {', '.join(f'{t}({s:.0f})' for t,s in best_types if s > 0)}")

        # 5. Greedy team builder against this opponent
        # Score each of my pokemon vs this team
        my_scored = []
        for mp in my_pokemon:
            score = 0
            for ep in team:
                a_dmg, d_dmg = simulate_1v1(mp['stats'], mp['type'], ep['stats'], ep['type'])
                # Net advantage: how much more damage I deal vs receive
                score += (a_dmg - d_dmg) * 0.3
                # Type advantage bonus
                m, _ = get_type_multiplier(mp['type'], ep['type'] if isinstance(ep['type'], list) else [ep['type']])
                if m > 1.0:
                    score += m * 30
            # Raw power is very important - weak pokemon lose regardless of type
            score += mp['power'] * 0.5
            my_scored.append((mp, score))

        my_scored.sort(key=lambda x: -x[1])

        # Greedy: pick best pokemon within cost budget, MUST be 6
        picked = []
        remaining_cost = MAX_COST
        picked_pids = set()
        for mp, sc in my_scored:
            if mp['pid'] in picked_pids:
                continue
            # Check if we can still fill remaining slots
            slots_left = 6 - len(picked) - 1  # after picking this one
            min_cost_needed = slots_left * 1  # at minimum 1 cost per slot (common)
            if mp['cost'] <= remaining_cost - min_cost_needed:
                picked.append((mp, sc))
                picked_pids.add(mp['pid'])
                remaining_cost -= mp['cost']
            if len(picked) == 6:
                break

        # Fill remaining slots
        if len(picked) < 6:
            for mp, sc in my_scored:
                if mp['pid'] not in picked_pids and mp['cost'] <= remaining_cost and len(picked) < 6:
                    picked.append((mp, sc))
                    picked_pids.add(mp['pid'])
                    remaining_cost -= mp['cost']

        print(f"\n🎯 추천 카운터팀 (코스트: {MAX_COST - remaining_cost}/{MAX_COST}):")
        my_team = []
        for mp, sc in picked:
            t_str = '/'.join(mp['type']) if isinstance(mp['type'], list) else mp['type']
            print(f"  {mp['name']:<8} [{mp['rarity'][:3]}={mp['cost']}] {t_str:<15} 전투력:{mp['power']:>5} IV:{mp['iv_total']:>3} 점수:{sc:>+.0f}")
            my_team.append(mp)

        # 6. Simulate
        if my_team and team:
            wr = simulate_battle(my_team, team, n_sims=500)
            print(f"\n⚔️ 시뮬레이션 결과 (500회): 승률 {wr*100:.1f}%")
            if wr >= 0.6:
                print("  → ✅ 유리한 매칭!")
            elif wr >= 0.45:
                print("  → ⚖️ 호각 승부")
            else:
                print("  → ⚠️ 불리한 매칭")

    # 7. Summary: Best overall team - try many combinations
    print(f"\n{'='*60}")
    print("📊 종합 추천: 전체 상위권 대응 최적팀")
    print(f"{'='*60}")

    # Strategy: try multiple team compositions (자유 조합)
    by_power = sorted(my_pokemon, key=lambda x: -x['power'])

    # Candidate anchors: top 5 most powerful affordable combos
    best_overall = None
    best_avg_wr = 0

    # Try different anchor strategies
    anchor_sets = []
    # Strategy 1: Strongest UL + strong fillers
    ul_list = [p for p in by_power if p['rarity'] == 'ultra_legendary'][:3]
    leg_list = [p for p in by_power if p['rarity'] == 'legendary'][:5]
    epic_list = [p for p in by_power if p['rarity'] == 'epic'][:10]
    rare_list = [p for p in by_power if p['rarity'] == 'rare'][:15]
    common_list = [p for p in by_power if p['rarity'] == 'common'][:15]

    # Generate candidate teams (MUST be exactly 6 members)
    candidates = []

    def fill_team(core, remaining_budget, pool):
        """Fill team to 6 members from pool within budget."""
        team = list(core)
        used = {p['pid'] for p in team}
        r = remaining_budget
        for f in pool:
            if f['pid'] in used: continue
            slots_left_after = 6 - len(team) - 1
            min_needed = slots_left_after * 1
            if f['cost'] <= r - min_needed and len(team) < 6:
                team.append(f)
                used.add(f['pid'])
                r -= f['cost']
            if len(team) == 6: break
        # backfill with cheapest if still < 6
        if len(team) < 6:
            for f in sorted(pool, key=lambda x: x['cost']):
                if f['pid'] not in used and f['cost'] <= r and len(team) < 6:
                    team.append(f)
                    used.add(f['pid'])
                    r -= f['cost']
        return team if len(team) == 6 else None

    all_fillers = rare_list + common_list

    # === 자유 조합: 다양한 코스트 구조 시도 ===

    # UL(6) + Epic(4)*2 + fill(4) = 18
    for ul in ul_list[:3]:
        for e1 in epic_list[:10]:
            for e2 in epic_list[:10]:
                if e2['pid'] == e1['pid']: continue
                t = fill_team([ul, e1, e2], 4, all_fillers)
                if t: candidates.append(t)

    # UL(6)*2 + Rare(2)*3 = 18
    for i, u1 in enumerate(ul_list[:3]):
        for u2 in ul_list[i+1:]:
            t = fill_team([u1, u2], 6, all_fillers)
            if t: candidates.append(t)

    # UL(6) + Leg(5) + Epic(4) + fill(3) = 18
    for ul in ul_list[:3]:
        for leg in leg_list[:5]:
            for ep in epic_list[:10]:
                if ep['pid'] in {ul['pid'], leg['pid']}: continue
                t = fill_team([ul, leg, ep], 3, common_list)
                if t: candidates.append(t)

    # UL(6) + Leg(5) + fill(7) = 18
    for ul in ul_list[:3]:
        for leg in leg_list[:5]:
            t = fill_team([ul, leg], 7, all_fillers)
            if t: candidates.append(t)

    # UL(6) + Epic(4) + fill(8) = 18
    for ul in ul_list[:3]:
        for ep in epic_list[:10]:
            t = fill_team([ul, ep], 8, all_fillers)
            if t: candidates.append(t)

    # Epic(4)*4 + Common(1)*2 = 18
    for i, e1 in enumerate(epic_list[:8]):
        for j, e2 in enumerate(epic_list[:8]):
            if j <= i: continue
            for k, e3 in enumerate(epic_list[:8]):
                if k <= j: continue
                for l, e4 in enumerate(epic_list[:8]):
                    if l <= k: continue
                    t = fill_team([e1, e2, e3, e4], 2, common_list)
                    if t: candidates.append(t)

    # Epic(4)*3 + Rare(2)*3 = 18
    for i, e1 in enumerate(epic_list[:8]):
        for j, e2 in enumerate(epic_list[:8]):
            if j <= i: continue
            for k, e3 in enumerate(epic_list[:8]):
                if k <= j: continue
                t = fill_team([e1, e2, e3], 6, all_fillers)
                if t: candidates.append(t)

    # Leg(5) + Epic(4)*2 + fill(5) = 18
    for leg in leg_list[:5]:
        for e1 in epic_list[:8]:
            for e2 in epic_list[:8]:
                if e2['pid'] == e1['pid'] or e1['pid'] == leg['pid'] or e2['pid'] == leg['pid']: continue
                t = fill_team([leg, e1, e2], 5, all_fillers)
                if t: candidates.append(t)

    print(f"후보 팀 수: {len(candidates)}개 테스트 중...")

    # Evaluate each candidate against all top teams (quick sim)
    scored_candidates = []
    for team in candidates:
        total_wr = 0
        n_opp = 0
        for uid, info in top_teams.items():
            if info['team']:
                wr = simulate_battle(team, info['team'], n_sims=50)
                total_wr += wr
                n_opp += 1
        avg = total_wr / max(1, n_opp)
        scored_candidates.append((team, avg))

    scored_candidates.sort(key=lambda x: -x[1])

    # Top 3 teams → 배치(슬롯 순서) 최적화
    print(f"\n{'='*60}")
    print("🔄 상위 3개 팀 배치 최적화 (720 순열 x 상대별 시뮬)")
    print(f"{'='*60}")

    opp_teams = [(uid, info) for uid, info in top_teams.items() if info['team']]

    for rank, (team, avg_wr) in enumerate(scored_candidates[:3], 1):
        total_cost = sum(p['cost'] for p in team)
        total_power = sum(p['power'] for p in team)
        print(f"\n{'='*55}")
        print(f"🏅 {rank}위 팀 (코스트: {total_cost}/{MAX_COST}, 전투력: {total_power})")
        print(f"{'='*55}")
        for mp in team:
            t_str = '/'.join(mp['type']) if isinstance(mp['type'], list) else mp['type']
            print(f"  {mp['name']:<8} [{mp['rarity'][:3]}={mp['cost']}] {t_str:<15} 전투력:{mp['power']:>5} IV:{mp['iv_total']:>3}")

        # 기본 순서 승률
        print(f"\n  [기본 순서] 대전 시뮬레이션 (500회):")
        total = 0
        n = 0
        for uid, info in opp_teams:
            wr = simulate_battle(team, info['team'], n_sims=500)
            total += wr
            n += 1
            emoji = "✅" if wr >= 0.55 else ("⚖️" if wr >= 0.45 else "⚠️")
            print(f"    vs {info['name']:<12} → {wr*100:.1f}% {emoji}")
        base_avg = total / max(1, n)
        print(f"    ── 평균 승률: {base_avg*100:.1f}% ──")

        # 배치 최적화: 모든 순열 시도 (6! = 720)
        print(f"\n  [배치 최적화] 720 순열 x {len(opp_teams)}상대 x 50회 시뮬...")
        best_perm = None
        best_perm_wr = 0
        all_perms = list(itertools.permutations(range(6)))

        for perm in all_perms:
            ordered = [team[i] for i in perm]
            t_wr = 0
            for uid, info in opp_teams:
                wr = simulate_battle(ordered, info['team'], n_sims=50)
                t_wr += wr
            avg = t_wr / len(opp_teams)
            if avg > best_perm_wr:
                best_perm_wr = avg
                best_perm = perm

        # 최적 배치로 정밀 시뮬
        best_team = [team[i] for i in best_perm]
        print(f"\n  ✨ 최적 배치 (정밀 1000회 시뮬):")
        for slot, mp in enumerate(best_team, 1):
            t_str = '/'.join(mp['type']) if isinstance(mp['type'], list) else mp['type']
            print(f"    슬롯{slot}: {mp['name']:<8} [{mp['rarity'][:3]}={mp['cost']}] {t_str:<15} 전투력:{mp['power']:>5}")

        total = 0
        n = 0
        per_opp = {}
        for uid, info in opp_teams:
            wr = simulate_battle(best_team, info['team'], n_sims=1000)
            total += wr
            n += 1
            per_opp[info['name']] = wr
            emoji = "✅" if wr >= 0.55 else ("⚖️" if wr >= 0.45 else "⚠️")
            print(f"    vs {info['name']:<12} → {wr*100:.1f}% {emoji}")
        opt_avg = total / max(1, n)
        print(f"    ── 최적 배치 평균 승률: {opt_avg*100:.1f}% (기본 대비 {(opt_avg-base_avg)*100:+.1f}%) ──")

asyncio.run(main())
