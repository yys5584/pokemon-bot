"""실제 유저 팀 라운드로빈 — 상성 포함, 이로치A 통일, BST 버프 비교."""
import asyncio, sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

async def main():
    from database.connection import get_db
    pool = await get_db()
    from models.pokemon_base_stats import POKEMON_BASE_STATS
    from utils.battle_calc import calc_battle_stats, get_normalized_base_stats, EVO_STAGE_MAP
    import config

    cost_map = {'common':1,'rare':2,'epic':4,'legendary':5,'ultra_legendary':6}
    rs = {'common':'C','rare':'R','epic':'E','legendary':'L','ultra_legendary':'U'}

    # 랭크전 활성 유저 팀
    ranked = await pool.fetch(
        "SELECT user_id, COUNT(*) as cnt, "
        "SUM(CASE WHEN won THEN 1 ELSE 0 END) as wins "
        "FROM battle_pokemon_stats "
        "WHERE battle_type = 'ranked' AND created_at > NOW() - INTERVAL '7 days' "
        "GROUP BY user_id HAVING COUNT(*) >= 20"
    )
    ranked_map = {r[0]: r[2]/r[1]*100 for r in ranked}

    team_rows = await pool.fetch(
        "SELECT bt.user_id, u.display_name, bt.slot, "
        "pm.id as pid, pm.name_ko, pm.rarity "
        "FROM battle_teams bt "
        "JOIN user_pokemon up ON up.id = bt.pokemon_instance_id "
        "JOIN pokemon_master pm ON up.pokemon_id = pm.id "
        "JOIN users u ON bt.user_id = u.user_id "
        "WHERE bt.team_number = 1 ORDER BY bt.user_id, bt.slot"
    )

    teams = {}
    for r in team_rows:
        uid = r[0]
        if uid not in ranked_map: continue
        if uid not in teams:
            teams[uid] = {'name': r[1], 'pokemon': []}
        teams[uid]['pokemon'].append({'pid': r[3], 'name': r[4], 'rarity': r[5]})

    full = {k: v for k, v in teams.items() if len(v['pokemon']) == 6}

    def get_types(pid):
        bs = POKEMON_BASE_STATS.get(pid)
        if bs and len(bs) > 6:
            return list(bs[6])
        return ['normal']

    def type_mult(atk_types, def_types):
        best = 1.0
        for at in atk_types:
            m = 1.0
            for dt in def_types:
                if dt in config.TYPE_IMMUNITY.get(at, []):
                    m *= 0.0
                elif dt in config.TYPE_ADVANTAGE.get(at, []):
                    m *= 2.0
                elif dt in config.TYPE_RESISTANCE.get(at, []):
                    m *= 0.5
            if m > best:
                best = m
        return best

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

    def battle_seq(team_a, team_b, seed=0):
        random.seed(seed)
        a_idx, b_idx = 0, 0
        a_hp = team_a[a_idx]['stats']['hp']
        b_hp = team_b[b_idx]['stats']['hp']

        for turn in range(300):
            if a_idx >= len(team_a) or b_idx >= len(team_b):
                break
            a = team_a[a_idx]
            b = team_b[b_idx]

            # 상성 배율
            tm_a = type_mult(a['types'], b['types'])
            tm_b = type_mult(b['types'], a['types'])

            a_atk = max(a['stats']['atk'], a['stats']['spa'])
            b_def = (b['stats']['def'] + b['stats']['spdef']) / 2
            a_dmg = max(1, int(((22*130*a_atk/b_def)/50+2) * tm_a * random.uniform(0.85, 1.0)))

            b_atk = max(b['stats']['atk'], b['stats']['spa'])
            a_def = (a['stats']['def'] + a['stats']['spdef']) / 2
            b_dmg = max(1, int(((22*130*b_atk/a_def)/50+2) * tm_b * random.uniform(0.85, 1.0)))

            # 게으름
            if a['pid'] in config.TRUANT_POKEMON and turn % 2 == 1: a_dmg = 0
            if b['pid'] in config.TRUANT_POKEMON and turn % 2 == 1: b_dmg = 0

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

        a_rem = len(team_a) - a_idx
        b_rem = len(team_b) - b_idx
        return a_rem > b_rem

    # 상위 20명 선택
    user_list = sorted(full.items(), key=lambda x: -ranked_map.get(x[0], 0))[:20]

    for label, buffs in [
        ('현재', {}),
        ('전설+50 초전설+50', {'legendary': 50, 'ultra_legendary': 50}),
        ('전설+70 초전설+50', {'legendary': 70, 'ultra_legendary': 50}),
    ]:
        # 팀 빌드
        built_teams = {}
        for uid, team in user_list:
            bt = []
            for p in team['pokemon']:
                buff = buffs.get(p['rarity'], 0)
                stats = build(p['pid'], p['rarity'], buff)
                bt.append({
                    'stats': stats, 'pid': p['pid'], 'name': p['name'],
                    'rarity': p['rarity'], 'types': get_types(p['pid']),
                })
            built_teams[uid] = bt

        # 라운드로빈 200판
        wins = {uid: 0 for uid, _ in user_list}
        games = {uid: 0 for uid, _ in user_list}

        for i, (uid_a, _) in enumerate(user_list):
            for j, (uid_b, _) in enumerate(user_list):
                if i == j: continue
                for seed in range(200):
                    a_win = battle_seq(built_teams[uid_a], built_teams[uid_b], seed)
                    games[uid_a] += 1
                    games[uid_b] += 1
                    if a_win:
                        wins[uid_a] += 1
                    else:
                        wins[uid_b] += 1

        print(f'\n=== {label} (이로치A 통일, 상성 포함, 200판) ===')
        results = []
        for uid, team in user_list:
            wr = wins[uid] / max(games[uid], 1) * 100
            comp = ''.join(rs.get(p['rarity'], '?') for p in team['pokemon'])
            real_wr = ranked_map.get(uid, 0)
            has_l = sum(1 for p in team['pokemon'] if p['rarity'] == 'legendary')
            has_u = sum(1 for p in team['pokemon'] if p['rarity'] == 'ultra_legendary')
            results.append((wr, team['name'], comp, real_wr, has_l, has_u))

        results.sort(key=lambda x: -x[0])
        print(f'  {"유저":<14} {"시뮬":>5} {"실제":>5} {"구성":>6} L U')
        for wr, name, comp, real_wr, has_l, has_u in results:
            print(f'  {name:<14} {wr:>4.0f}% {real_wr:>4.0f}% {comp:>6} {has_l} {has_u}')

asyncio.run(main())
