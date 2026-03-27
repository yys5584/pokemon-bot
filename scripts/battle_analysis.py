import asyncio, os, asyncpg, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from models.pokemon_base_stats import POKEMON_BASE_STATS
from models.pokemon_battle_data import POKEMON_BATTLE_DATA

ADMIN_ID = 1832746512

COST_MAP = {
    "common": 1,
    "rare": 2,
    "epic": 4,
    "legendary": 5,
    "ultra_legendary": 6,
}

def get_types(pid):
    entry = POKEMON_BASE_STATS.get(pid)
    if entry:
        return entry[6]  # list of types
    bd = POKEMON_BATTLE_DATA.get(pid)
    if bd:
        return [bd[0]]
    return ["?"]

def get_bst(pid):
    entry = POKEMON_BASE_STATS.get(pid)
    if entry:
        return sum(entry[:6])
    return 0

async def main():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)

    # 1. 현재 팀
    teams = await conn.fetch("""
        SELECT t.team_number, t.slot, up.id, up.pokemon_id, p.name_ko, p.rarity,
               up.is_shiny, up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd
        FROM battle_teams t
        JOIN user_pokemon up ON t.pokemon_instance_id = up.id
        JOIN pokemon_master p ON up.pokemon_id = p.id
        WHERE t.user_id = $1
        ORDER BY t.team_number, t.slot
    """, ADMIN_ID)

    print("=== 현재 팀 ===")
    for tn in [1, 2]:
        team = [t for t in teams if t["team_number"] == tn]
        if not team:
            continue
        cost = sum(COST_MAP.get(t["rarity"], 0) for t in team)
        print(f"\n  팀{tn} (코스트: {cost}/18, {len(team)}마리)")
        for t in team:
            iv = t["iv_hp"]+t["iv_atk"]+t["iv_def"]+t["iv_spa"]+t["iv_spdef"]+t["iv_spd"]
            sh = "✨" if t["is_shiny"] else ""
            types = "/".join(get_types(t["pokemon_id"]))
            bst = get_bst(t["pokemon_id"])
            print(f"    슬롯{t['slot']}: {sh}{t['name_ko']} [{types}] BST:{bst} IV:{iv} cost:{COST_MAP.get(t['rarity'],0)}")

    # 2. 최근 배틀 전적
    records = await conn.fetch("""
        SELECT br.winner_id, br.loser_id, br.battle_type, br.created_at
        FROM battle_records br
        WHERE (br.winner_id = $1 OR br.loser_id = $1)
        ORDER BY br.created_at DESC
        LIMIT 50
    """, ADMIN_ID)

    wins = sum(1 for r in records if r["winner_id"] == ADMIN_ID)
    losses = sum(1 for r in records if r["loser_id"] == ADMIN_ID)
    total = wins + losses
    wr = round(wins / total * 100, 1) if total > 0 else 0
    print(f"\n=== 최근 {total}전 전적: {wins}승 {losses}패 (승률 {wr}%) ===")

    # 3. 상대별 전적
    opponents = {}
    for r in records:
        if r["winner_id"] == ADMIN_ID:
            opp = r["loser_id"]
            opponents.setdefault(opp, {"w": 0, "l": 0})
            opponents[opp]["w"] += 1
        else:
            opp = r["winner_id"]
            opponents.setdefault(opp, {"w": 0, "l": 0})
            opponents[opp]["l"] += 1

    opp_ids = list(opponents.keys())
    if opp_ids:
        opp_rows = await conn.fetch(
            "SELECT user_id, display_name FROM users WHERE user_id = ANY($1)", opp_ids)
        opp_names = {r["user_id"]: r["display_name"] for r in opp_rows}
    else:
        opp_names = {}

    print(f"\n=== 상대별 전적 ===")
    sorted_opps = sorted(opponents.items(), key=lambda x: x[1]["w"]+x[1]["l"], reverse=True)
    for opp_id, stat in sorted_opps[:10]:
        name = opp_names.get(opp_id, str(opp_id))[:12]
        t = stat["w"] + stat["l"]
        owr = round(stat["w"] / t * 100) if t > 0 else 0
        print(f"  vs {name:<12s} {stat['w']}승 {stat['l']}패 ({owr}%)")

    # 4. 보유 포켓몬 전투력 Top 30
    print(f"\n=== 보유 포켓몬 Top 30 (BST+IV) ===")
    all_pokes = await conn.fetch("""
        SELECT up.id, up.pokemon_id, p.name_ko, p.rarity,
               up.is_shiny, up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd
        FROM user_pokemon up
        JOIN pokemon_master p ON up.pokemon_id = p.id
        WHERE up.user_id = $1
    """, ADMIN_ID)

    scored = []
    for p in all_pokes:
        iv = p["iv_hp"]+p["iv_atk"]+p["iv_def"]+p["iv_spa"]+p["iv_spdef"]+p["iv_spd"]
        bst = get_bst(p["pokemon_id"])
        scored.append((bst + iv, p, iv, bst))
    scored.sort(key=lambda x: -x[0])

    for i, (score, p, iv, bst) in enumerate(scored[:30], 1):
        sh = "✨" if p["is_shiny"] else ""
        types = "/".join(get_types(p["pokemon_id"]))
        cost = COST_MAP.get(p["rarity"], 0)
        print(f"  {i:2d}. {sh}{p['name_ko']:<8s} [{types:<14s}] BST:{bst:3d} IV:{iv:3d}/186 cost:{cost} (id:{p['id']})")

    await conn.close()

asyncio.run(main())
