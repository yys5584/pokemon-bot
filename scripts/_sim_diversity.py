"""덱 다양성 시뮬 — 가능한 모든 코스트18 조합을 최적 포켓몬으로 채워서 경쟁."""
import asyncio, sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

async def main():
    from models.pokemon_base_stats import POKEMON_BASE_STATS
    from models.pokemon_data import ALL_POKEMON
    from utils.battle_calc import calc_battle_stats, get_normalized_base_stats, EVO_STAGE_MAP
    import config

    cost_map = {'common':1,'rare':2,'epic':4,'legendary':5,'ultra_legendary':6}

    # 등급별 최강 포켓몬 풀 (상성 다양하게)
    def get_top_by_rarity(rarity, n=10):
        pokes = []
        for p in ALL_POKEMON:
            if p[4] != rarity: continue
            bs = POKEMON_BASE_STATS.get(p[0])
            if not bs: continue
            bst = sum(bs[:6])
            types = list(bs[6]) if len(bs) > 6 else ['normal']
            if p[0] in config.TRUANT_POKEMON: continue  # 게으름 제외
            pokes.append({'pid': p[0], 'name': p[1], 'bst': bst, 'types': types})
        pokes.sort(key=lambda x: -x['bst'])
        # 타입 다양성 확보 — 같은 타입 최대 2마리
        result = []
        type_count = {}
        for p in pokes:
            t = p['types'][0]
            if type_count.get(t, 0) >= 2: continue
            type_count[t] = type_count.get(t, 0) + 1
            result.append(p)
            if len(result) >= n: break
        return result

    pools = {r: get_top_by_rarity(r) for r in ['common','rare','epic','legendary','ultra_legendary']}

    def build(pid, rarity, buff=0):
        base_kw = get_normalized_base_stats(pid) or {}
        evo = EVO_STAGE_MAP.get(pid, 3)
        stats = calc_battle_stats(rarity, 'balanced', 7, evo, 20,20,20,20,20,20, **base_kw)
        stats['hp'] = int(stats['hp'] * config.BATTLE_HP_MULTIPLIER)
        if buff > 0:
            bs = POKEMON_BASE_STATS.get(pid)
            if bs:
                scale = (sum(bs[:6]) + buff) / sum(bs[:6])
                stats = {k: int(v * scale) for k, v in stats.items()}
        return stats

    def type_mult(atk_types, def_types):
        best = 1.0
        for at in atk_types:
            m = 1.0
            for dt in def_types:
                if dt in config.TYPE_IMMUNITY.get(at, []): m *= 0.0
                elif dt in config.TYPE_ADVANTAGE.get(at, []): m *= 2.0
                elif dt in config.TYPE_RESISTANCE.get(at, []): m *= 0.5
            if m > best: best = m
        return best

    def battle_seq(team_a, team_b, seed=0):
        random.seed(seed)
        a_idx, b_idx = 0, 0
        a_hp = team_a[0]['stats']['hp']
        b_hp = team_b[0]['stats']['hp']
        for turn in range(300):
            if a_idx >= len(team_a) or b_idx >= len(team_b): break
            a, b = team_a[a_idx], team_b[b_idx]
            tm_a = type_mult(a['types'], b['types'])
            tm_b = type_mult(b['types'], a['types'])
            a_atk = max(a['stats']['atk'], a['stats']['spa'])
            b_def = (b['stats']['def'] + b['stats']['spdef']) / 2
            a_dmg = max(1, int(((22*130*a_atk/b_def)/50+2) * tm_a * random.uniform(0.85,1.0)))
            b_atk = max(b['stats']['atk'], b['stats']['spa'])
            a_def = (a['stats']['def'] + a['stats']['spdef']) / 2
            b_dmg = max(1, int(((22*130*b_atk/a_def)/50+2) * tm_b * random.uniform(0.85,1.0)))
            if a['stats']['spd'] >= b['stats']['spd']:
                b_hp -= a_dmg
                if b_hp <= 0:
                    b_idx += 1
                    if b_idx < len(team_b): b_hp = team_b[b_idx]['stats']['hp']
                    continue
                a_hp -= b_dmg
                if a_hp <= 0:
                    a_idx += 1
                    if a_idx < len(team_a): a_hp = team_a[a_idx]['stats']['hp']
            else:
                a_hp -= b_dmg
                if a_hp <= 0:
                    a_idx += 1
                    if a_idx < len(team_a): a_hp = team_a[a_idx]['stats']['hp']
                    continue
                b_hp -= a_dmg
                if b_hp <= 0:
                    b_idx += 1
                    if b_idx < len(team_b): b_hp = team_b[b_idx]['stats']['hp']
        return (len(team_a) - a_idx) > (len(team_b) - b_idx)

    # 초전설 고정 + 나머지 5슬롯 코스트12 조합
    deck_templates = {
        'U+E2+R+C2':   [('ultra_legendary',1),('epic',2),('rare',1),('common',2)],
        'U+E+R4':      [('ultra_legendary',1),('epic',1),('rare',4)],
        'U+L+E+C3':    [('ultra_legendary',1),('legendary',1),('epic',1),('common',3)],
        'U+L+R3+C':    [('ultra_legendary',1),('legendary',1),('rare',3),('common',1)],
        'U+E+R2+C2':   [('ultra_legendary',1),('epic',1),('rare',2),('common',2)],  # cost 11
        'U+E+R3+C':    [('ultra_legendary',1),('epic',1),('rare',3),('common',1)],  # cost 13?
    }
    # 코스트 검증
    valid = {}
    for name, template in deck_templates.items():
        cost = sum(cost_map[r] * n for r, n in template)
        slots = sum(n for _, n in template)
        if cost <= 18 and slots == 6:
            valid[name] = template

    # 각 조합에서 랜덤 팀 10개 생성 (타입 다양하게)
    def make_teams(template, buffs, count=10):
        teams = []
        for seed in range(count):
            random.seed(seed * 777)
            team = []
            for rarity, n in template:
                pool = list(pools[rarity])
                random.shuffle(pool)
                for p in pool[:n]:
                    buff = buffs.get(rarity, 0)
                    stats = build(p['pid'], rarity, buff)
                    team.append({'stats': stats, 'pid': p['pid'], 'name': p['name'],
                                 'types': p['types'], 'rarity': rarity})
            teams.append(team)
        return teams

    for label, buffs in [
        ('현재', {}),
        ('전설+70 초전설+50', {'legendary': 70, 'ultra_legendary': 50}),
    ]:
        print(f'\n{"="*60}')
        print(f'=== {label} ===')
        print(f'{"="*60}')

        all_teams = {}  # {deck_type: [team1, team2, ...]}
        for name, template in valid.items():
            all_teams[name] = make_teams(template, buffs, 10)

        # 라운드로빈: 모든 덱 타입 간 대결 (각 10팀 × 50판)
        deck_wins = {name: 0 for name in valid}
        deck_games = {name: 0 for name in valid}

        deck_names = list(valid.keys())
        for i, dn_a in enumerate(deck_names):
            for j, dn_b in enumerate(deck_names):
                if i == j: continue
                for ta in all_teams[dn_a]:
                    for tb in all_teams[dn_b]:
                        for seed in range(5):
                            a_win = battle_seq(ta, tb, seed + hash(dn_a+dn_b) % 10000)
                            deck_games[dn_a] += 1
                            deck_games[dn_b] += 1
                            if a_win:
                                deck_wins[dn_a] += 1
                            else:
                                deck_wins[dn_b] += 1

        results = [(deck_wins[n]/max(deck_games[n],1)*100, n) for n in valid]
        results.sort(key=lambda x: -x[0])

        spread = results[0][0] - results[-1][0]
        print(f'\n  {"덱 조합":<20} {"승률":>6}  {"코스트":>4}')
        print(f'  {"-"*40}')
        for wr, name in results:
            cost = sum(cost_map[r]*n for r,n in valid[name])
            print(f'  {name:<20} {wr:>5.1f}%  {cost:>4}')
        print(f'\n  승률 편차: {spread:.1f}% (낮을수록 다양한 메타)')
        if spread < 15:
            print(f'  → ✅ 다양한 덱이 경쟁력 있음')
        elif spread < 25:
            print(f'  → ⚠️ 일부 덱이 우세하지만 다양성 있음')
        else:
            print(f'  → ❌ 특정 덱이 독주, 고착화 우려')

asyncio.run(main())
