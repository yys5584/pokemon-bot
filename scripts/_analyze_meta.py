"""랭크전 메타 분석 — 유저 덱 패턴 + 승률 상관관계."""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

async def main():
    from database.connection import get_db
    pool = await get_db()
    from models.pokemon_base_stats import POKEMON_BASE_STATS
    import config

    cost_map = {'common':1,'rare':2,'epic':4,'legendary':5,'ultra_legendary':6}
    rs = {'common':'C','rare':'R','epic':'E','legendary':'L','ultra_legendary':'U'}

    # 랭크전 7일 유저별 승률
    ranked = await pool.fetch(
        "SELECT user_id, COUNT(*) as cnt, "
        "SUM(CASE WHEN won THEN 1 ELSE 0 END) as wins "
        "FROM battle_pokemon_stats "
        "WHERE battle_type = 'ranked' AND created_at > NOW() - INTERVAL '7 days' "
        "GROUP BY user_id HAVING COUNT(*) >= 20"
    )
    ranked_map = {r[0]: {'cnt': r[1], 'wins': r[2]} for r in ranked}
    uids = list(ranked_map.keys())

    # 팀 가져오기
    team_rows = await pool.fetch(
        "SELECT bt.user_id, u.display_name, bt.slot, "
        "pm.id as pid, pm.name_ko, pm.rarity, up.is_shiny, "
        "up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd "
        "FROM battle_teams bt "
        "JOIN user_pokemon up ON up.id = bt.pokemon_instance_id "
        "JOIN pokemon_master pm ON up.pokemon_id = pm.id "
        "JOIN users u ON bt.user_id = u.user_id "
        "WHERE bt.team_number = 1 ORDER BY bt.user_id, bt.slot"
    )

    teams = {}
    for r in team_rows:
        uid = r[0]
        if uid not in ranked_map:
            continue
        if uid not in teams:
            teams[uid] = {'name': r[1], 'pokemon': []}
        bs = POKEMON_BASE_STATS.get(r[3])
        bst = sum(bs[:6]) if bs else 0
        iv_total = sum(x or 15 for x in [r[7],r[8],r[9],r[10],r[11],r[12]])
        grade = 'S' if iv_total>=170 else 'A' if iv_total>=130 else 'B' if iv_total>=90 else 'C'
        types = '/'.join(bs[6]) if bs and len(bs)>6 else '?'
        teams[uid]['pokemon'].append({
            'name': r[4], 'rarity': r[5], 'bst': bst, 'shiny': r[6],
            'grade': grade, 'types': types, 'pid': r[3],
        })

    full = {k:v for k,v in teams.items() if len(v['pokemon'])==6}

    results = []
    for uid, team in full.items():
        info = ranked_map[uid]
        wr = info['wins']/info['cnt']*100

        comp = ''.join(rs.get(p['rarity'],'?') for p in team['pokemon'])
        total_cost = sum(cost_map.get(p['rarity'],1) for p in team['pokemon'])
        total_bst = sum(p['bst'] for p in team['pokemon'])
        shiny_cnt = sum(1 for p in team['pokemon'] if p['shiny'])
        s_cnt = sum(1 for p in team['pokemon'] if p['grade']=='S')
        rc = {}
        for p in team['pokemon']:
            rc[p['rarity']] = rc.get(p['rarity'], 0) + 1

        results.append({
            'uid': uid, 'name': team['name'], 'wr': wr, 'cnt': info['cnt'],
            'comp': comp, 'cost': total_cost, 'total_bst': total_bst,
            'shiny': shiny_cnt, 's_grade': s_cnt, 'pokemon': team['pokemon'], 'rc': rc,
        })

    results.sort(key=lambda x: -x['wr'])

    print(f'=== 랭크전 풀팀 (20전+): {len(results)}명 ===\n')
    print(f'  {"유저":<14} {"승률":>4} {"전투":>4} {"구성":>6} {"cost":>4} {"BST":>5} {"이로":>2} {"S":>1}  라인업')
    print('='*120)

    for r in results[:25]:
        lineup = ' '.join(
            f"{'*' if p['shiny'] else ''}{p['name']}({rs[p['rarity']]}{p['bst']})"
            for p in r['pokemon']
        )
        print(f"  {r['name']:<14} {r['wr']:>3.0f}% {r['cnt']:>4} {r['comp']:>6} {r['cost']:>4} {r['total_bst']:>5} {r['shiny']:>2} {r['s_grade']:>1}  {lineup}")

    # 패턴 분석
    top = results[:10]
    bot = results[-10:] if len(results) >= 20 else results[len(results)//2:]

    print(f'\n=== 승률 상위 vs 하위 비교 ===')
    metrics = [
        ('총 BST', lambda r: r['total_bst']),
        ('이로치 수', lambda r: r['shiny']),
        ('S급 수', lambda r: r['s_grade']),
        ('초전설', lambda r: r['rc'].get('ultra_legendary',0)),
        ('전설', lambda r: r['rc'].get('legendary',0)),
        ('에픽', lambda r: r['rc'].get('epic',0)),
        ('레어', lambda r: r['rc'].get('rare',0)),
        ('일반', lambda r: r['rc'].get('common',0)),
        ('코스트', lambda r: r['cost']),
    ]
    print(f'  {"":>12}  {"상위10":>7}  {"하위10":>7}  {"차이":>6}')
    for name, fn in metrics:
        t = sum(fn(r) for r in top) / len(top)
        b = sum(fn(r) for r in bot) / len(bot)
        diff = t - b
        print(f'  {name:>12}  {t:>7.1f}  {b:>7.1f}  {diff:>+6.1f}')

    # 승률과 상관관계
    print(f'\n=== 승률 결정 요인 (상관관계) ===')
    import math
    for name, fn in metrics:
        vals = [(r['wr'], fn(r)) for r in results]
        n = len(vals)
        if n < 5:
            continue
        mx = sum(x for x,_ in vals)/n
        my = sum(y for _,y in vals)/n
        cov = sum((x-mx)*(y-my) for x,y in vals)/n
        sx = math.sqrt(sum((x-mx)**2 for x,_ in vals)/n)
        sy = math.sqrt(sum((y-my)**2 for _,y in vals)/n)
        corr = cov/(sx*sy) if sx>0 and sy>0 else 0
        bar = '#' * int(abs(corr) * 20)
        sign = '+' if corr > 0 else '-'
        print(f'  {name:>12}: r={corr:+.2f} {sign}{bar}')

asyncio.run(main())
