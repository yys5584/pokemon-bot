"""BST 상향 배틀 시뮬 — 전부 이로치 A급 가정."""
import asyncio, sys, os, random, math
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

    # 랭크전 활성 유저 팀 가져오기
    team_rows = await pool.fetch(
        "SELECT bt.user_id, u.display_name, bt.slot, "
        "pm.id as pid, pm.name_ko, pm.rarity "
        "FROM battle_teams bt "
        "JOIN user_pokemon up ON up.id = bt.pokemon_instance_id "
        "JOIN pokemon_master pm ON up.pokemon_id = pm.id "
        "JOIN users u ON bt.user_id = u.user_id "
        "WHERE bt.team_number = 1 ORDER BY bt.user_id, bt.slot"
    )

    ranked_users = await pool.fetch(
        "SELECT user_id, COUNT(*) as cnt, "
        "SUM(CASE WHEN won THEN 1 ELSE 0 END) as wins "
        "FROM battle_pokemon_stats "
        "WHERE battle_type = 'ranked' AND created_at > NOW() - INTERVAL '7 days' "
        "GROUP BY user_id HAVING COUNT(*) >= 20"
    )
    ranked_map = {r[0]: r[2]/r[1]*100 for r in ranked_users}

    teams = {}
    for r in team_rows:
        uid = r[0]
        if uid not in ranked_map: continue
        if uid not in teams:
            teams[uid] = {'name': r[1], 'pokemon': []}
        teams[uid]['pokemon'].append({'pid': r[3], 'name': r[4], 'rarity': r[5]})

    full = {k:v for k,v in teams.items() if len(v['pokemon'])==6}

    def build_stats(pid, rarity, bst_buff):
        base_kw = get_normalized_base_stats(pid) or {}
        evo = EVO_STAGE_MAP.get(pid, 3)
        # 전부 이로치 A급
        stats = calc_battle_stats(rarity, 'balanced', 7, evo, 20,20,20,20,20,20, **base_kw)
        stats['hp'] = int(stats['hp'] * config.BATTLE_HP_MULTIPLIER)

        buff = bst_buff.get(rarity, 0)
        if buff > 0:
            bs = POKEMON_BASE_STATS.get(pid)
            if bs:
                orig_bst = sum(bs[:6])
                scale = (orig_bst + buff) / orig_bst
                stats = {k: int(v * scale) for k, v in stats.items()}
        return stats

    def battle_1v1(stats_a, pid_a, stats_b, pid_b, turn_start=0):
        """1v1 전투. 남은 HP 반환."""
        hp_a = stats_a['hp']
        hp_b = stats_b['hp']

        a_atk = max(stats_a['atk'], stats_a['spa'])
        b_def_a = (stats_b['def'] + stats_b['spdef']) / 2
        a_dmg_base = (22 * 130 * a_atk / b_def_a) / 50 + 2

        b_atk = max(stats_b['atk'], stats_b['spa'])
        a_def_b = (stats_a['def'] + stats_a['spdef']) / 2
        b_dmg_base = (22 * 130 * b_atk / a_def_b) / 50 + 2

        for t in range(50):
            turn = turn_start + t
            # 게으름
            a_skip = pid_a in config.TRUANT_POKEMON and turn % 2 == 1
            b_skip = pid_b in config.TRUANT_POKEMON and turn % 2 == 1

            a_dmg = 0 if a_skip else int(a_dmg_base * random.uniform(0.85, 1.0))
            b_dmg = 0 if b_skip else int(b_dmg_base * random.uniform(0.85, 1.0))

            if stats_a['spd'] >= stats_b['spd']:
                hp_b -= a_dmg
                if hp_b <= 0: return hp_a, 0
                hp_a -= b_dmg
                if hp_a <= 0: return 0, hp_b
            else:
                hp_a -= b_dmg
                if hp_a <= 0: return 0, hp_b
                hp_b -= a_dmg
                if hp_b <= 0: return hp_a, 0

        return hp_a, hp_b

    def simulate_match(team_a_pokes, team_b_pokes, bst_buff, seed=0):
        random.seed(seed)
        a_stats = [(build_stats(p['pid'], p['rarity'], bst_buff), p['pid']) for p in team_a_pokes]
        b_stats = [(build_stats(p['pid'], p['rarity'], bst_buff), p['pid']) for p in team_b_pokes]

        a_idx = 0
        b_idx = 0
        a_hp = a_stats[0][0]['hp']
        turn = 0

        while a_idx < 6 and b_idx < 6:
            a_s, a_pid = a_stats[a_idx]
            b_s, b_pid = b_stats[b_idx]
            # 현재 HP 세팅
            a_s_copy = dict(a_s)
            a_s_copy['hp'] = a_hp
            b_s_copy = dict(b_s)

            rem_a, rem_b = battle_1v1(a_s_copy, a_pid, b_s_copy, b_pid, turn)
            turn += 10

            if rem_a <= 0:
                a_idx += 1
                if a_idx < 6:
                    a_hp = a_stats[a_idx][0]['hp']
            else:
                a_hp = rem_a

            if rem_b <= 0:
                b_idx += 1

        return (6 - a_idx) > (6 - b_idx)  # a가 더 많이 살아남으면 승

    user_list = sorted(full.items(), key=lambda x: -ranked_map.get(x[0], 0))[:20]

    for label, buff in [
        ('현재', {}),
        ('전설+50 초전설+50', {'legendary':50, 'ultra_legendary':50}),
        ('전설+70 초전설+50', {'legendary':70, 'ultra_legendary':50}),
    ]:
        wins = {uid: 0 for uid, _ in user_list}
        games = {uid: 0 for uid, _ in user_list}

        for i, (uid_a, ta) in enumerate(user_list):
            for j, (uid_b, tb) in enumerate(user_list):
                if i == j: continue
                for seed in range(10):
                    a_win = simulate_match(ta['pokemon'], tb['pokemon'], buff, seed*100+i*10+j)
                    games[uid_a] += 1
                    games[uid_b] += 1
                    if a_win:
                        wins[uid_a] += 1
                    else:
                        wins[uid_b] += 1

        print(f'\n=== {label} (전부 이로치A, 상위20명 라운드로빈) ===')
        ranked_results = []
        for uid, team in user_list:
            wr = wins[uid] / max(games[uid],1) * 100
            comp = ''.join(rs.get(p['rarity'],'?') for p in team['pokemon'])
            has_u = 'U' if any(p['rarity']=='ultra_legendary' for p in team['pokemon']) else ''
            has_l = 'L' if any(p['rarity']=='legendary' for p in team['pokemon']) else ''
            tag = has_u or has_l or 'E'
            real_wr = ranked_map.get(uid, 0)
            ranked_results.append((wr, team['name'], comp, tag, real_wr))

        ranked_results.sort(key=lambda x: -x[0])
        print(f'  {"유저":<14} {"시뮬승률":>6} {"실제승률":>6} {"구성":>6} {"타입":>3}')
        for wr, name, comp, tag, real_wr in ranked_results:
            print(f'  {name:<14} {wr:>5.0f}% {real_wr:>5.0f}% {comp:>6} [{tag}]')

asyncio.run(main())
