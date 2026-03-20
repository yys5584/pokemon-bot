import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql://postgres.ycaxgpnxfyumejlriymk:%21dbdbstkd92@aws-1-ap-northeast-1.pooler.supabase.com:6543/postgres"

async def check():
    from database import queries
    from dashboard.api_my import _build_pokemon_data
    from dashboard.api_advisor import _get_user_battle_stats, _recommend_power, _get_battle_meta, _RARITY_COST, _pick_team
    pool = await queries.get_db()
    uid = 1832746512  # 문유
    rows = await pool.fetch(
        "SELECT up.id, up.pokemon_id, up.friendship, up.is_shiny, up.is_favorite, "
        "up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd, "
        "pm.name_ko, pm.emoji, pm.rarity, pm.pokemon_type, pm.stat_type, pm.evolves_to "
        "FROM user_pokemon up JOIN pokemon_master pm ON up.pokemon_id = pm.id "
        "WHERE up.user_id = $1 AND up.is_active = 1 ORDER BY up.id DESC", uid)
    print(f"Total pokemon: {len(rows)}")

    from collections import Counter
    rc = Counter(r["rarity"] for r in rows)
    for k, v in rc.most_common():
        print(f"  {k}: {v}")

    battle_stats = await _get_user_battle_stats(uid)
    pokemon = await _build_pokemon_data(rows, battle_stats)
    meta = await _get_battle_meta()
    team, analysis = _recommend_power(pokemon, meta)
    print(f"\nTeam size: {len(team)}")
    total_cost = 0
    for i, p in enumerate(team):
        cost = _RARITY_COST.get(p["rarity"], 1)
        total_cost += cost
        print(f"  {i+1}. {p['name_ko']:10s} | {p['rarity']:18s} | cost={cost} | power={p['real_power']}")
    print(f"Total cost: {total_cost}/18")

asyncio.run(check())
