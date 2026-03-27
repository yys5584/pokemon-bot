"""시니어 전략기획자 관점 메타 분석 리포트.
실제 battle_pokemon_stats DB 기반."""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

async def main():
    from database.connection import get_db
    pool = await get_db()
    from models.pokemon_base_stats import POKEMON_BASE_STATS
    import config

    rs = {'common':'C','rare':'R','epic':'E','legendary':'L','ultra_legendary':'U'}

    def get_types(pid):
        bs = POKEMON_BASE_STATS.get(pid)
        return list(bs[6]) if bs and len(bs) > 6 else ['normal']

    # ═══════════════════════════════════════════
    # 1. OP 포켓몬 — 킬/데스 비율 기준
    # ═══════════════════════════════════════════
    rows = await pool.fetch(
        "SELECT pokemon_id, rarity, is_shiny, "
        "COUNT(*) as bat, "
        "ROUND(AVG(damage_dealt)) as dmg, "
        "ROUND(AVG(kills)::numeric,2) as kills, "
        "ROUND(AVG(deaths)::numeric,2) as deaths, "
        "ROUND(AVG(turns_alive)::numeric,1) as alive, "
        "ROUND(AVG(super_effective_hits)::numeric,2) as se, "
        "ROUND(AVG(not_effective_hits)::numeric,2) as ne, "
        "ROUND(AVG(skills_activated)::numeric,2) as skills, "
        "SUM(CASE WHEN won THEN 1 ELSE 0 END) as wins "
        "FROM battle_pokemon_stats "
        "WHERE battle_type = 'ranked' "
        "GROUP BY pokemon_id, rarity, is_shiny "
        "HAVING COUNT(*) >= 20"
    )

    # 포켓몬 이름
    pm_rows = await pool.fetch("SELECT id, name_ko FROM pokemon_master")
    names = {r[0]: r[1] for r in pm_rows}

    pokes = []
    for r in rows:
        pid = r[0]
        kd = float(r[5]) / max(float(r[6]), 0.01)
        wr = r[11] / r[3] * 100
        types = get_types(pid)
        pokes.append({
            'pid': pid, 'name': names.get(pid, '?'), 'rarity': r[1],
            'shiny': r[2], 'bat': r[3], 'dmg': r[4], 'kills': float(r[5]),
            'deaths': float(r[6]), 'kd': kd, 'alive': float(r[7]),
            'se': float(r[8]), 'ne': float(r[9]), 'skills': float(r[10]),
            'wr': wr, 'types': types,
        })

    print("=" * 80)
    print("       TG포켓 랭크전 메타 분석 리포트")
    print("=" * 80)

    # ── OP 티어 (KD 1.5+, 승률 55%+) ──
    print("\n\n[1] OP 포켓몬 — K/D 1.5+ & 승률 55%+")
    print("-" * 70)
    op = sorted([p for p in pokes if p['kd'] >= 1.5 and p['wr'] >= 55], key=lambda x: -x['kd'])
    print(f"  {'이름':<10} {'등급':<3} {'전투':>4} {'딜':>5} {'킬':>4} {'데스':>4} {'K/D':>5} {'승률':>4} {'상성+':>4} {'타입'}")
    for p in op[:15]:
        s = '*' if p['shiny'] else ' '
        t = rs.get(p['rarity'], '?')
        print(f"  {s}{p['name']:<9} {t:<3} {p['bat']:>4} {p['dmg']:>5} {p['kills']:>4} {p['deaths']:>4} {p['kd']:>5.1f} {p['wr']:>3.0f}% {p['se']:>4} {'/'.join(p['types'])}")

    # ── 밸류 포켓몬 (코스트 대비 최고 효율) ──
    print("\n\n[2] 가성비 포켓몬 — 코스트 대비 K/D")
    print("-" * 70)
    cost_map = {'common':1,'rare':2,'epic':4,'legendary':5,'ultra_legendary':6}
    for p in pokes:
        p['cost'] = cost_map.get(p['rarity'], 1)
        p['kd_per_cost'] = p['kd'] / p['cost']
    value = sorted([p for p in pokes if p['bat'] >= 30], key=lambda x: -x['kd_per_cost'])
    print(f"  {'이름':<10} {'등급':<3} {'cost':>4} {'K/D':>5} {'K/D÷cost':>8} {'승률':>4} {'타입'}")
    for p in value[:15]:
        s = '*' if p['shiny'] else ' '
        t = rs.get(p['rarity'], '?')
        print(f"  {s}{p['name']:<9} {t:<3} {p['cost']:>4} {p['kd']:>5.1f} {p['kd_per_cost']:>8.2f} {p['wr']:>3.0f}% {'/'.join(p['types'])}")

    # ── 상성 메타 — 가장 많이 상성 유리 치는 타입 ──
    print("\n\n[3] 상성 메타 — 상성유리 타격 평균")
    print("-" * 70)
    se_rank = sorted([p for p in pokes if p['bat'] >= 30], key=lambda x: -x['se'])
    print(f"  {'이름':<10} {'등급':<3} {'상성+':>5} {'상성-':>5} {'순상성':>5} {'딜':>5} {'타입'}")
    for p in se_rank[:15]:
        s = '*' if p['shiny'] else ' '
        t = rs.get(p['rarity'], '?')
        net_se = p['se'] - p['ne']
        print(f"  {s}{p['name']:<9} {t:<3} {p['se']:>5} {p['ne']:>5} {net_se:>+5.1f} {p['dmg']:>5} {'/'.join(p['types'])}")

    # ── 탱커 — 가장 오래 사는 포켓몬 ──
    print("\n\n[4] 탱커 — 평균 생존 턴수")
    print("-" * 70)
    tanks = sorted([p for p in pokes if p['bat'] >= 30], key=lambda x: -x['alive'])
    print(f"  {'이름':<10} {'등급':<3} {'생존턴':>5} {'데스':>4} {'딜':>5} {'킬':>4} {'타입'}")
    for p in tanks[:10]:
        s = '*' if p['shiny'] else ' '
        t = rs.get(p['rarity'], '?')
        print(f"  {s}{p['name']:<9} {t:<3} {p['alive']:>5} {p['deaths']:>4} {p['dmg']:>5} {p['kills']:>4} {'/'.join(p['types'])}")

    # ── 함정 포켓몬 — 많이 쓰이지만 성적 나쁜 ──
    print("\n\n[5] 함정 포켓몬 — 50전+ & K/D 0.8 이하")
    print("-" * 70)
    traps = sorted([p for p in pokes if p['bat'] >= 50 and p['kd'] <= 0.8], key=lambda x: x['kd'])
    print(f"  {'이름':<10} {'등급':<3} {'전투':>4} {'K/D':>5} {'승률':>4} {'딜':>5} {'상성-':>4}")
    for p in traps[:10]:
        s = '*' if p['shiny'] else ' '
        t = rs.get(p['rarity'], '?')
        print(f"  {s}{p['name']:<9} {t:<3} {p['bat']:>4} {p['kd']:>5.2f} {p['wr']:>3.0f}% {p['dmg']:>5} {p['ne']:>4}")

    # ── 타입별 메타 점유율 ──
    print("\n\n[6] 타입별 메타 — 사용률 & 평균 성적")
    print("-" * 70)
    type_stats = {}
    for p in pokes:
        for tp in p['types']:
            if tp not in type_stats:
                type_stats[tp] = {'bat': 0, 'dmg': 0, 'kills': 0, 'deaths': 0, 'count': 0}
            type_stats[tp]['bat'] += p['bat']
            type_stats[tp]['dmg'] += p['dmg'] * p['bat']
            type_stats[tp]['kills'] += p['kills'] * p['bat']
            type_stats[tp]['deaths'] += p['deaths'] * p['bat']
            type_stats[tp]['count'] += 1
    total_bat = sum(v['bat'] for v in type_stats.values())
    print(f"  {'타입':<10} {'사용률':>6} {'avg딜':>6} {'avg킬':>5} {'avgK/D':>6}")
    for tp, v in sorted(type_stats.items(), key=lambda x: -x[1]['bat']):
        pct = v['bat'] / total_bat * 100
        avg_dmg = v['dmg'] / max(v['bat'], 1)
        avg_kills = v['kills'] / max(v['bat'], 1)
        avg_deaths = v['deaths'] / max(v['bat'], 1)
        kd = avg_kills / max(avg_deaths, 0.01)
        print(f"  {tp:<10} {pct:>5.1f}% {avg_dmg:>6.0f} {avg_kills:>5.2f} {kd:>6.2f}")

    # ── 결론 ──
    print("\n\n" + "=" * 80)
    print("[결론] 메타 진단")
    print("=" * 80)

    # OP 독점도
    top5_bat = sum(p['bat'] for p in sorted(pokes, key=lambda x: -x['bat'])[:5])
    all_bat = sum(p['bat'] for p in pokes)
    print(f"\n  사용률 TOP5 점유율: {top5_bat/all_bat*100:.0f}%")

    # 등급별 평균 K/D
    for rar in ['common','rare','epic','legendary','ultra_legendary']:
        rar_pokes = [p for p in pokes if p['rarity'] == rar]
        if rar_pokes:
            avg_kd = sum(p['kills']*p['bat'] for p in rar_pokes) / max(sum(p['deaths']*p['bat'] for p in rar_pokes), 1)
            avg_wr = sum(p['wr']*p['bat'] for p in rar_pokes) / max(sum(p['bat'] for p in rar_pokes), 1)
            print(f"  {rar:<18} avg K/D={avg_kd:.2f}  avg 승률={avg_wr:.0f}%")

asyncio.run(main())
