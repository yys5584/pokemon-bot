import asyncio, asyncpg, re, os, sys
from dotenv import load_dotenv
load_dotenv()

sys.stdout.reconfigure(encoding='utf-8')

def strip_emoji(s):
    return re.sub(r'[^\w\s.,-]', '', s or '', flags=re.UNICODE).strip()

async def main():
    db_url = os.getenv('DATABASE_URL')
    conn = await asyncpg.connect(db_url, statement_cache_size=0)

    # Top 8
    rows = await conn.fetch('''
        SELECT sr.user_id, u.display_name, sr.ranked_wins, sr.ranked_losses,
               ROUND(100.0 * sr.ranked_wins / NULLIF(sr.ranked_wins + sr.ranked_losses, 0), 1) as win_rate
        FROM season_records sr
        JOIN users u ON u.user_id = sr.user_id
        WHERE sr.ranked_wins + sr.ranked_losses >= 5
        ORDER BY sr.ranked_wins - sr.ranked_losses DESC
        LIMIT 8
    ''')

    print('=== TOP 8 RANKED PLAYERS ===')
    user_ids = []
    for r in rows:
        name = strip_emoji(r['display_name'])
        print(f'{name} (uid:{r["user_id"]}) | {r["ranked_wins"]}W {r["ranked_losses"]}L | WR {r["win_rate"]}%')
        user_ids.append(r['user_id'])

    print()
    all_teams = {}
    for uid in user_ids:
        team_rows = await conn.fetch('''
            SELECT bt.slot, bt.team_number, pm.name_ko, pm.rarity,
                   (up.iv_hp+up.iv_atk+up.iv_def+up.iv_spa+up.iv_spdef+up.iv_spd) as iv_total,
                   pm.pokemon_type, pm.stat_type, pm.id as pokemon_id
            FROM battle_teams bt
            JOIN user_pokemon up ON up.id = bt.pokemon_instance_id
            JOIN pokemon_master pm ON pm.id = up.pokemon_id
            WHERE bt.user_id = $1
            ORDER BY bt.team_number, bt.slot
        ''', uid)

        name = strip_emoji([r for r in rows if r['user_id'] == uid][0]['display_name'])
        cost_map = {'common':1,'rare':2,'epic':4,'legendary':5,'ultra_legendary':6}
        total_cost = 0
        print(f'--- {name} ---')
        team_pokemon = []
        for tr in team_rows:
            c = cost_map.get(tr['rarity'], 0)
            total_cost += c
            print(f'  T{tr["team_number"]}S{tr["slot"]}: {tr["name_ko"]} IV{tr["iv_total"]} [{tr["rarity"]}={c}] {tr["pokemon_type"]}/{tr["stat_type"]}')
            team_pokemon.append({
                'name': tr['name_ko'], 'rarity': tr['rarity'], 'cost': c,
                'iv': tr['iv_total'], 'type': tr['pokemon_type'], 'stat': tr['stat_type'],
                'pid': tr['pokemon_id']
            })
        print(f'  Total cost: {total_cost}')
        all_teams[uid] = {'name': name, 'team': team_pokemon, 'cost': total_cost,
                          'wins': rows[[r['user_id'] for r in rows].index(uid)]['ranked_wins'],
                          'losses': rows[[r['user_id'] for r in rows].index(uid)]['ranked_losses']}
        print()

    # My Pokemon (user 1832746512)
    my_uid = 1832746512
    my_pokemon = await conn.fetch('''
        SELECT up.id as instance_id, pm.id as pokemon_id, pm.name_ko, pm.rarity,
               (up.iv_hp+up.iv_atk+up.iv_def+up.iv_spa+up.iv_spdef+up.iv_spd) as iv_total,
               pm.pokemon_type, pm.stat_type
        FROM user_pokemon up
        JOIN pokemon_master pm ON pm.id = up.pokemon_id
        WHERE up.user_id = $1
        ORDER BY
            CASE pm.rarity
                WHEN 'ultra_legendary' THEN 1 WHEN 'legendary' THEN 2
                WHEN 'epic' THEN 3 WHEN 'rare' THEN 4 ELSE 5 END,
            (up.iv_hp+up.iv_atk+up.iv_def+up.iv_spa+up.iv_spdef+up.iv_spd) DESC
    ''', my_uid)

    print(f'\n=== MY POKEMON ({len(my_pokemon)} total) ===')
    cost_map = {'common':1,'rare':2,'epic':4,'legendary':5,'ultra_legendary':6}
    by_rarity = {}
    for p in my_pokemon:
        r = p['rarity']
        if r not in by_rarity:
            by_rarity[r] = []
        by_rarity[r].append(p)

    for rarity in ['ultra_legendary','legendary','epic','rare','common']:
        if rarity in by_rarity:
            plist = by_rarity[rarity]
            print(f'\n[{rarity.upper()}] ({len(plist)}마리, cost={cost_map[rarity]})')
            for p in plist[:10]:
                print(f'  {p["name_ko"]} IV{p["iv_total"]} {p["pokemon_type"]}/{p["stat_type"]}')
            if len(plist) > 10:
                print(f'  ... +{len(plist)-10} more')

    await conn.close()

asyncio.run(main())
