"""Mock dashboard server for local preview (no DB required)."""
import asyncio
import json
import os
import sys
from pathlib import Path

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_DIR)
sys.path.insert(0, PROJECT_DIR)

from aiohttp import web

TEMPLATE_DIR = Path(__file__).parent / "templates"

# Mock data for preview
MOCK_OVERVIEW = {"total_users": 150, "total_pokemon": 7654, "total_chats": 25,
                 "total_spawns": 18420, "total_catches": 12350, "total_trades": 89,
                 "today_spawns": 312, "today_catches": 42, "today_active_users": 18,
                 "total_shiny": 7, "market_trades": 34, "market_volume_bp": 128500}
MOCK_USERS = [{"user_id": 1, "display_name": "트레이너A", "title_emoji": "🏆",
               "pokemon_count": 120, "pokedex_count": 95, "shiny_count": 5}]
MOCK_RANKING = [{"user_id": 1, "display_name": "챔피언", "title_emoji": "⚔️",
                 "battle_wins": 50, "battle_losses": 10, "battle_streak": 5,
                 "best_streak": 8, "bp": 1500}]


async def index(request):
    return web.FileResponse(TEMPLATE_DIR / "index.html")


async def mock_json(request):
    path = request.path
    if path == "/api/overview":
        return web.json_response(MOCK_OVERVIEW)
    if path == "/api/users":
        return web.json_response(MOCK_USERS)
    if path == "/api/battle/ranking":
        return web.json_response(MOCK_RANKING)
    if path == "/api/battle/ranking-teams":
        return web.json_response({})
    if path == "/api/ranked/season":
        return web.json_response({
            "season": {
                "season_id": "2026-S05",
                "weekly_rule": "no_normal",
                "weekly_rule_name": "🚫 노말타입 금지",
                "weekly_rule_desc": "노말 타입 포켓몬 사용 불가 (잠만보, 럭키, 해피너스, 캥카 등)",
                "starts_at": "2026-03-09 00:00:00+09:00",
                "ends_at": "2026-03-22 23:59:59+09:00",
            },
            "ranking": [
                {"user_id": 1, "display_name": "트레이너A", "title_emoji": "",
                 "rp": 2340, "tier": "challenger", "tier_display": "⚔️챌린저",
                 "ranked_wins": 35, "ranked_losses": 8, "best_ranked_streak": 9,
                 "peak_rp": 2340, "peak_tier": "challenger"},
                {"user_id": 2, "display_name": "트레이너B", "title_emoji": "",
                 "rp": 2120, "tier": "challenger", "tier_display": "⚔️챌린저",
                 "ranked_wins": 28, "ranked_losses": 12, "best_ranked_streak": 6,
                 "peak_rp": 2180, "peak_tier": "challenger"},
                {"user_id": 3, "display_name": "트레이너C", "title_emoji": "",
                 "rp": 1520, "tier": "diamond", "tier_display": "💠다이아",
                 "ranked_wins": 20, "ranked_losses": 10, "best_ranked_streak": 5,
                 "peak_rp": 1520, "peak_tier": "diamond"},
                {"user_id": 4, "display_name": "트레이너D", "title_emoji": "",
                 "rp": 890, "tier": "gold", "tier_display": "🏅골드",
                 "ranked_wins": 12, "ranked_losses": 7, "best_ranked_streak": 4,
                 "peak_rp": 920, "peak_tier": "gold"},
                {"user_id": 5, "display_name": "트레이너E", "title_emoji": "",
                 "rp": 320, "tier": "silver", "tier_display": "🥈실버",
                 "ranked_wins": 5, "ranked_losses": 5, "best_ranked_streak": 2,
                 "peak_rp": 350, "peak_tier": "silver"},
            ],
        })
    if path == "/api/type-chart":
        # Return real type chart from config
        import config
        types = list(config.TYPE_ADVANTAGE.keys())
        chart = {}
        for atk_type in types:
            row = {}
            for def_type in types:
                immunities = config.TYPE_IMMUNITY.get(atk_type, [])
                advantages = config.TYPE_ADVANTAGE.get(atk_type, [])
                disadvantages = config.TYPE_ADVANTAGE.get(def_type, [])
                if def_type in immunities:
                    row[def_type] = 0
                elif def_type in advantages:
                    row[def_type] = 2
                elif atk_type in disadvantages:
                    row[def_type] = 0.5
                else:
                    row[def_type] = 1
            chart[atk_type] = row
        return web.json_response({
            "types": types,
            "type_names": config.TYPE_NAME_KO,
            "type_emoji": config.TYPE_EMOJI,
            "chart": chart,
        })
    if path == "/api/battle/tiers":
        return web.json_response([
            {"id": 150, "name": "뮤츠", "emoji": "🔮", "rarity": "ultra_legendary", "evo_stage": 3,
             "type1": "psychic", "type2": None, "stat_ko": "공격",
             "power": 95.2, "skill_name": "사이코키네시스",
             "skill_power": 1.8, "hp": 318, "atk": 110, "def_": 90,
             "spa": 154, "spdef": 90, "spd": 130},
            {"id": 242, "name": "해피너스", "emoji": "🩷", "rarity": "epic", "evo_stage": 3,
             "type1": "normal", "type2": None, "stat_ko": "방어",
             "power": 88.7, "skill_name": "알폭탄",
             "skill_power": 1.3, "hp": 548, "atk": 23, "def_": 23,
             "spa": 65, "spdef": 85, "spd": 52},
            {"id": 250, "name": "칠색조", "emoji": "🔥", "rarity": "ultra_legendary", "evo_stage": 3,
             "type1": "fire", "type2": "flying", "stat_ko": "공격",
             "power": 85.4, "skill_name": "성스러운불꽃",
             "skill_power": 2.0, "hp": 306, "atk": 120, "def_": 88,
             "spa": 104, "spdef": 138, "spd": 88},
            {"id": 249, "name": "루기아", "emoji": "🌊", "rarity": "ultra_legendary", "evo_stage": 3,
             "type1": "psychic", "type2": "flying", "stat_ko": "방어",
             "power": 82.1, "skill_name": "에어로블라스트",
             "skill_power": 1.7, "hp": 318, "atk": 90, "def_": 130,
             "spa": 90, "spdef": 154, "spd": 110},
            {"id": 248, "name": "마기라스", "emoji": "🪨", "rarity": "epic", "evo_stage": 3,
             "type1": "rock", "type2": "dark", "stat_ko": "공격",
             "power": 67.5, "skill_name": "깨물어부수기",
             "skill_power": 1.5, "hp": 291, "atk": 123, "def_": 104,
             "spa": 93, "spdef": 97, "spd": 67},
            {"id": 149, "name": "망나뇽", "emoji": "🐉", "rarity": "epic", "evo_stage": 3,
             "type1": "dragon", "type2": "flying", "stat_ko": "공격",
             "power": 61.9, "skill_name": "역린",
             "skill_power": 1.5, "hp": 270, "atk": 123, "def_": 93,
             "spa": 97, "spdef": 97, "spd": 81},
            {"id": 148, "name": "신뇽", "emoji": "🐉", "rarity": "epic", "evo_stage": 2,
             "type1": "dragon", "type2": None, "stat_ko": "공격",
             "power": 38.4, "skill_name": "-",
             "skill_power": 1.0, "hp": 186, "atk": 82, "def_": 63,
             "spa": 65, "spdef": 65, "spd": 68},
            {"id": 131, "name": "라프라스", "emoji": "🧊", "rarity": "rare", "evo_stage": 3,
             "type1": "water", "type2": "ice", "stat_ko": "방어",
             "power": 56.0, "skill_name": "냉동빔",
             "skill_power": 1.5, "hp": 360, "atk": 85, "def_": 81,
             "spa": 85, "spdef": 93, "spd": 66},
            {"id": 25, "name": "피카츄", "emoji": "⚡", "rarity": "rare", "evo_stage": 2,
             "type1": "electric", "type2": None, "stat_ko": "속도",
             "power": 22.5, "skill_name": "10만볼트",
             "skill_power": 1.4, "hp": 156, "atk": 55, "def_": 40,
             "spa": 50, "spdef": 50, "spd": 90},
            {"id": 20, "name": "레트라", "emoji": "🐀", "rarity": "common", "evo_stage": 3,
             "type1": "normal", "type2": None, "stat_ko": "속도",
             "power": 15.2, "skill_name": "필살앞니",
             "skill_power": 1.4, "hp": 165, "atk": 62, "def_": 52,
             "spa": 43, "spdef": 55, "spd": 88},
            {"id": 19, "name": "꼬렛", "emoji": "🐀", "rarity": "common", "evo_stage": 1,
             "type1": "normal", "type2": None, "stat_ko": "속도",
             "power": 8.3, "skill_name": "-",
             "skill_power": 1.0, "hp": 126, "atk": 48, "def_": 35,
             "spa": 25, "spdef": 35, "spd": 72},
        ])
    if path == "/api/dashboard-kpi":
        return web.json_response({
            "dau": 18,
            "dau_history": [{"day": "2026-03-01", "dau": 15}, {"day": "2026-03-02", "dau": 20},
                            {"day": "2026-03-03", "dau": 18}],
            "retention": {"rate": 45, "retained": 9, "total_new": 20},
            "economy": {
                "master_balls_circulation": 1999, "master_balls_avg": 5.2, "master_balls_used_total": 1423,
                "hyper_balls_circulation": 3450, "hyper_balls_avg": 8.1, "hyper_balls_used_total": 2876,
                "bp_circulation": 205682, "bp_avg": 478.3, "bp_spent_total": 89500,
            },
            "top_channels": [
                {"chat_id": -100123, "chat_title": "TG_포켓", "member_count": 50, "today_spawns": 120, "today_catches": 95, "avg_participants": 2.7, "invite_link": "https://t.me/tgpoke_test"},
                {"chat_id": -100456, "chat_title": "포켓몬 사랑방", "member_count": 30, "today_spawns": 80, "today_catches": 60, "avg_participants": 1.8, "invite_link": None},
            ],
        })
    if path == "/api/fun-kpis":
        return web.json_response({
            "global_catch_rate": 62.5, "total_master_balls_used": 45,
            "longest_streak": {"display_name": "트레이너A", "streak": 12},
            "rare_holders": [], "escape_masters": [], "night_owls": [],
            "masterball_rich": [], "pokeball_addicts": [],
            "lucky_users": [], "unlucky_users": [], "trade_kings": [],
            "most_escaped": [], "love_leaders": [], "shiny_holders": [],
        })
    # Default empty
    return web.json_response([])


# Mock auth state
_mock_user = None

async def mock_auth_telegram(request):
    global _mock_user
    _mock_user = {"user_id": 1832746512, "display_name": "테스트유저", "photo_url": "", "is_admin": True}
    resp = web.json_response({"ok": True, "user": _mock_user})
    resp.set_cookie("sid", "mock_session", max_age=86400)
    return resp

async def mock_auth_me(request):
    sid = request.cookies.get("sid")
    if sid and _mock_user:
        return web.json_response({"ok": True, "user": _mock_user})
    return web.json_response({"ok": False})

async def mock_auth_logout(request):
    global _mock_user
    _mock_user = None
    resp = web.json_response({"ok": True})
    resp.del_cookie("sid")
    return resp

async def mock_my_pokemon(request):
    """Mock pokemon data for preview."""
    mock_pokemon = [
        {"id":1,"pokemon_id":6,"name_ko":"리자몽","emoji":"🔥","rarity":"epic","pokemon_type":"fire","type2":"flying",
         "stat_type":"offensive","friendship":5,"is_shiny":True,"is_favorite":True,"evo_stage":3,"team_num":1,"team_slot":1,
         "ivs":{"hp":25,"atk":28,"def":15,"spa":31,"spdef":12,"spd":22},
         "stats":{"hp":285,"atk":86,"def":78,"spa":109,"spdef":85,"spd":100},
         "real_stats":{"hp":312,"atk":98,"def":81,"spa":126,"spdef":87,"spd":108},
         "power":743,"real_power":812,"iv_bonus":69,"iv_total":133,"iv_grade":"A",
         "synergy_score":85,"synergy_label":"우수","synergy_emoji":"🔥"},
        {"id":2,"pokemon_id":150,"name_ko":"뮤츠","emoji":"🔮","rarity":"ultra_legendary","pokemon_type":"psychic","type2":None,
         "stat_type":"offensive","friendship":5,"is_shiny":False,"is_favorite":False,"evo_stage":3,"team_num":1,"team_slot":2,
         "ivs":{"hp":20,"atk":18,"def":10,"spa":31,"spdef":15,"spd":28},
         "stats":{"hp":318,"atk":110,"def":90,"spa":154,"spdef":90,"spd":130},
         "real_stats":{"hp":340,"atk":118,"def":92,"spa":178,"spdef":93,"spd":143},
         "power":892,"real_power":964,"iv_bonus":72,"iv_total":122,"iv_grade":"A",
         "synergy_score":82,"synergy_label":"우수","synergy_emoji":"🔥"},
        {"id":3,"pokemon_id":131,"name_ko":"라프라스","emoji":"🧊","rarity":"rare","pokemon_type":"water","type2":"ice",
         "stat_type":"defensive","friendship":4,"is_shiny":False,"is_favorite":False,"evo_stage":3,"team_num":1,"team_slot":3,
         "ivs":{"hp":31,"atk":5,"def":28,"spa":10,"spdef":30,"spd":8},
         "stats":{"hp":360,"atk":85,"def":81,"spa":85,"spdef":93,"spd":66},
         "real_stats":{"hp":413,"atk":72,"def":103,"spa":88,"spdef":119,"spd":68},
         "power":770,"real_power":863,"iv_bonus":93,"iv_total":112,"iv_grade":"B",
         "synergy_score":92,"synergy_label":"완벽","synergy_emoji":"⚡"},
        {"id":4,"pokemon_id":25,"name_ko":"피카츄","emoji":"⚡","rarity":"common","pokemon_type":"electric","type2":None,
         "stat_type":"speedy","friendship":3,"is_shiny":False,"is_favorite":False,"evo_stage":2,
         "ivs":{"hp":10,"atk":15,"def":8,"spa":20,"spdef":5,"spd":31},
         "stats":{"hp":120,"atk":45,"def":32,"spa":42,"spdef":40,"spd":78},
         "real_stats":{"hp":121,"atk":48,"def":32,"spa":46,"spdef":39,"spd":90},
         "power":357,"real_power":376,"iv_bonus":19,"iv_total":89,"iv_grade":"C",
         "synergy_score":78,"synergy_label":"우수","synergy_emoji":"🔥"},
        {"id":5,"pokemon_id":248,"name_ko":"마기라스","emoji":"🪨","rarity":"epic","pokemon_type":"rock","type2":"dark",
         "stat_type":"offensive","friendship":5,"is_shiny":True,"is_favorite":True,"evo_stage":3,"team_num":2,"team_slot":3,
         "ivs":{"hp":28,"atk":31,"def":25,"spa":20,"spdef":22,"spd":30},
         "stats":{"hp":291,"atk":123,"def":104,"spa":93,"spdef":97,"spd":67},
         "real_stats":{"hp":324,"atk":141,"def":116,"spa":100,"spdef":105,"spd":74},
         "power":775,"real_power":860,"iv_bonus":85,"iv_total":156,"iv_grade":"A",
         "synergy_score":88,"synergy_label":"우수","synergy_emoji":"🔥"},
        {"id":6,"pokemon_id":149,"name_ko":"망나뇽","emoji":"🐉","rarity":"epic","pokemon_type":"dragon","type2":"flying",
         "stat_type":"offensive","friendship":5,"is_shiny":False,"is_favorite":False,"evo_stage":3,"team_num":2,"team_slot":1,
         "ivs":{"hp":15,"atk":25,"def":12,"spa":28,"spdef":10,"spd":20},
         "stats":{"hp":270,"atk":123,"def":93,"spa":97,"spdef":97,"spd":81},
         "real_stats":{"hp":283,"atk":137,"def":96,"spa":111,"spdef":99,"spd":87},
         "power":761,"real_power":813,"iv_bonus":52,"iv_total":110,"iv_grade":"B",
         "synergy_score":75,"synergy_label":"우수","synergy_emoji":"🔥"},
        {"id":7,"pokemon_id":376,"name_ko":"메타그로스","emoji":"⚙️","rarity":"epic","pokemon_type":"steel","type2":"psychic",
         "stat_type":"offensive","friendship":4,"is_shiny":False,"is_favorite":True,"evo_stage":3,"team_num":2,"team_slot":2,
         "ivs":{"hp":22,"atk":29,"def":20,"spa":18,"spdef":15,"spd":24},
         "stats":{"hp":270,"atk":123,"def":116,"spa":93,"spdef":86,"spd":67},
         "real_stats":{"hp":290,"atk":139,"def":128,"spa":102,"spdef":93,"spd":78},
         "power":720,"real_power":830,"iv_bonus":110,"iv_total":128,"iv_grade":"A",
         "synergy_score":82,"synergy_label":"우수","synergy_emoji":"🔥"},
        {"id":8,"pokemon_id":25,"name_ko":"피카츄","emoji":"⚡","rarity":"common","pokemon_type":"electric","type2":None,
         "stat_type":"speedy","friendship":1,"is_shiny":False,"is_favorite":False,"evo_stage":2,
         "ivs":{"hp":5,"atk":8,"def":3,"spa":12,"spdef":2,"spd":15},
         "stats":{"hp":120,"atk":45,"def":32,"spa":42,"spdef":40,"spd":78},
         "real_stats":{"hp":113,"atk":40,"def":29,"spa":40,"spdef":36,"spd":82},
         "power":357,"real_power":340,"iv_bonus":-17,"iv_total":45,"iv_grade":"D",
         "synergy_score":55,"synergy_label":"보통","synergy_emoji":"⚡"},
        {"id":9,"pokemon_id":25,"name_ko":"피카츄","emoji":"⚡","rarity":"common","pokemon_type":"electric","type2":None,
         "stat_type":"speedy","friendship":2,"is_shiny":False,"is_favorite":False,"evo_stage":2,
         "ivs":{"hp":18,"atk":22,"def":14,"spa":25,"spdef":10,"spd":28},
         "stats":{"hp":120,"atk":45,"def":32,"spa":42,"spdef":40,"spd":78},
         "real_stats":{"hp":130,"atk":55,"def":36,"spa":52,"spdef":42,"spd":92},
         "power":357,"real_power":407,"iv_bonus":50,"iv_total":117,"iv_grade":"B",
         "synergy_score":82,"synergy_label":"우수","synergy_emoji":"🔥"},
    ]
    return web.json_response(mock_pokemon)

async def mock_my_pokedex(request):
    """Mock pokedex data: all 386 pokemon with some caught."""
    if not _mock_user:
        return web.json_response({"error": "Login required"}, status=401)
    import random
    random.seed(42)  # Deterministic for preview
    rarities = {1:"common",25:"common",6:"epic",131:"rare",149:"epic",150:"ultra_legendary",
                248:"epic",376:"epic",151:"legendary",243:"legendary",244:"legendary",245:"legendary",
                249:"ultra_legendary",250:"ultra_legendary",251:"legendary",
                373:"epic",384:"ultra_legendary",385:"ultra_legendary",386:"ultra_legendary"}
    types_map = {1:"grass",4:"fire",7:"water",25:"electric",6:"fire",131:"water",149:"dragon",
                 150:"psychic",248:"rock",376:"steel",151:"psychic",373:"dragon",384:"dragon",
                 385:"steel",386:"psychic"}
    type2_map = {6:"flying",131:"ice",149:"flying",248:"dark",376:"psychic",373:"flying",384:"flying"}
    methods = ["spawn","evolve","trade"]
    caught_ids = set(random.sample(range(1, 387), 180))  # ~180 caught
    # Always include our notable pokemon
    caught_ids |= {6, 25, 131, 149, 150, 248, 376}
    result = []
    names_ko = {1:"이상해씨",2:"이상해풀",3:"이상해꽃",4:"파이리",5:"리자드",6:"리자몽",
                7:"꼬부기",8:"어니부기",9:"거북왕",10:"캐터피",25:"피카츄",131:"라프라스",
                149:"망나뇽",150:"뮤츠",151:"뮤",248:"마기라스",373:"보만다",376:"메타그로스",
                384:"레쿠쟈",385:"지라치",386:"데옥시스"}
    names_en = {1:"Bulbasaur",4:"Charmander",6:"Charizard",7:"Squirtle",25:"Pikachu",
                131:"Lapras",149:"Dragonite",150:"Mewtwo",151:"Mew",248:"Tyranitar",
                373:"Salamence",376:"Metagross",384:"Rayquaza"}
    evo_chains = {1:"이상해씨 → 이상해풀 → 이상해꽃",2:"이상해씨 → 이상해풀 → 이상해꽃",3:"이상해씨 → 이상해풀 → 이상해꽃",
                  4:"파이리 → 리자드 → 리자몽",5:"파이리 → 리자드 → 리자몽",6:"파이리 → 리자드 → 리자몽",
                  7:"꼬부기 → 어니부기 → 거북왕",8:"꼬부기 → 어니부기 → 거북왕",9:"꼬부기 → 어니부기 → 거북왕",
                  25:"피카츄 → 라이츄"}
    evo_stages = {1:"기본",2:"1진화",3:"최종",4:"기본",5:"1진화",6:"최종",7:"기본",8:"1진화",9:"최종",
                  25:"기본",131:"단일",149:"최종",150:"단일",151:"단일",248:"최종",376:"최종"}
    for pid in range(1, 387):
        gen_types = ["normal","fire","water","grass","electric","ice","fighting","poison",
                     "ground","flying","psychic","bug","rock","ghost","dragon","dark","steel","fairy"]
        rarity = rarities.get(pid, random.choice(["common","common","common","rare","rare","epic"]))
        t1 = types_map.get(pid, random.choice(gen_types))
        t2 = type2_map.get(pid, None) if pid in type2_map else (random.choice(gen_types) if random.random() < 0.3 else None)
        caught = pid in caught_ids
        cr = {"common":0.5,"rare":0.3,"epic":0.15,"legendary":0.05,"ultra_legendary":0.03}.get(rarity, 0.3)
        # Mock base stats
        bs = {"hp": random.randint(40, 160), "atk": random.randint(30, 170),
              "def": random.randint(30, 160), "spa": random.randint(30, 170),
              "spdef": random.randint(30, 160), "spd": random.randint(30, 160)}
        # Known pokemon get realistic stats
        known_stats = {
            150: {"hp":146,"atk":162,"def":108,"spa":180,"spdef":108,"spd":148},
            131: {"hp":148,"atk":101,"def":96,"spa":101,"spdef":114,"spd":69},
            149: {"hp":109,"atk":170,"def":114,"spa":120,"spdef":120,"spd":96},
            6: {"hp":92,"atk":100,"def":92,"spa":145,"spdef":101,"spd":120},
            25: {"hp":50,"atk":67,"def":47,"spa":58,"spdef":58,"spd":108},
        }
        stats = known_stats.get(pid, bs)
        mock_tmis = {
            1: "사실 피카츄보다 먼저 디자인된 포켓몬 1호. 도감 번호 001은 우연이 아님.",
            6: "리자몽은 드래곤이 아니라 불/비행 타입. 메가진화X로 드래곤 타입을 얻을 수 있다.",
            25: "포켓몬의 마스코트. 원래 뚱뚱했는데 애니메이션 이후 날씬해졌다.",
            150: "인간이 만든 인공 포켓몬. 뮤의 유전자를 조작해서 탄생했다.",
        }
        result.append({
            "id": pid,
            "name_ko": names_ko.get(pid, f"푸키몬{pid}"),
            "name_en": names_en.get(pid, f"Pokemon{pid}"),
            "emoji": "🔵",
            "rarity": rarity,
            "type1": t1,
            "type2": t2,
            "catch_rate": cr,
            "caught": caught,
            "method": random.choice(methods) if caught else None,
            "evo_chain": evo_chains.get(pid),
            "stage": evo_stages.get(pid, "최종"),
            "stats": stats,
            "tmi": mock_tmis.get(pid, f"푸키몬{pid}의 알려지지 않은 이야기가 여기에 표시됩니다."),
        })
    return web.json_response(result)

async def mock_my_summary(request):
    return web.json_response({
        "total_pokemon":7,"shiny_count":2,"dex_count":45,
        "battle_points":1250,"battle_wins":35,"battle_losses":12,"best_streak":8
    })

async def mock_team_recommend(request):
    body = await request.json()
    mode = body.get("mode", "power")
    pokemon = (await mock_my_pokemon(request))
    import json as j
    pk = j.loads(pokemon.text)
    labels = {"power":"전투력 TOP 6","synergy":"시너지 최적","counter":"카운터 덱","balance":"밸런스"}
    return web.json_response({
        "team": pk[:6],
        "analysis": f"{labels.get(mode,mode)} 모드로 추천합니다. 총 전투력 {sum(p['real_power'] for p in pk[:6])}. 드래곤 + 에스퍼 위주 구성으로 페어리 타입에 주의하세요.",
        "warnings": ["팀이 페어리 타입에 취약합니다."],
        "mode": mode
    })


async def mock_fusion(request):
    """Mock fusion for preview."""
    import random
    body = await request.json()
    id_a = body.get("instance_id_a")
    id_b = body.get("instance_id_b")
    if not id_a or not id_b or id_a == id_b:
        return web.json_response({"error": "같은 개체를 선택할 수 없습니다."}, status=400)
    # Generate random IVs for mock result
    ivs = {s: random.randint(0, 31) for s in ("hp", "atk", "def", "spa", "spdef", "spd")}
    iv_t = sum(ivs.values())
    grades = [(160, "S"), (120, "A"), (93, "B"), (62, "C"), (0, "D")]
    grade = next(g for t, g in grades if iv_t >= t)
    return web.json_response({
        "success": True,
        "message": "합성 성공!",
        "result": {
            "id": random.randint(9000, 9999),
            "pokemon_id": 25, "name_ko": "피카츄", "emoji": "⚡",
            "rarity": "rare", "is_shiny": False,
            "iv_hp": ivs["hp"], "iv_atk": ivs["atk"], "iv_def": ivs["def"],
            "iv_spa": ivs["spa"], "iv_spdef": ivs["spdef"], "iv_spd": ivs["spd"],
            "iv_total": iv_t, "iv_grade": grade, "friendship": 0,
        }
    })


_mock_chat_count = 0

async def mock_chat(request):
    """Mock AI chat for preview."""
    global _mock_chat_count
    _mock_chat_count += 1
    remaining = max(0, 20 - _mock_chat_count)

    body = await request.json()
    msg = body.get("message", "").lower()
    import json as j
    pokemon_resp = await mock_my_pokemon(request)
    pk = j.loads(pokemon_resp.text)

    def _resp(data):
        data["remaining"] = remaining
        data["bonus_remaining"] = 45  # mock bonus
        return web.json_response(data)

    # Simulate different response types based on keywords
    if any(k in msg for k in ["최강", "전투력", "강한", "top"]):
        team = sorted(pk, key=lambda x: x["real_power"], reverse=True)[:6]
        total = sum(p["real_power"] for p in team)
        return _resp({
            "team": team,
            "analysis": f"💪 실전투력 기준 TOP 6을 선별했습니다!\n\n총 전투력: {total}\n\n1위 {team[0]['emoji']}{team[0]['name_ko']}({team[0]['real_power']})는 압도적인 스탯으로 에이스 역할에 적합합니다.\n{team[1]['emoji']}{team[1]['name_ko']}는 서브 딜러로, 타입 커버리지를 보완해줍니다.\n\n다만 드래곤/에스퍼 편중으로 페어리 타입에 취약하니 주의하세요!",
            "warnings": ["페어리 타입에 취약합니다."]
        })
    elif any(k in msg for k in ["시너지", "iv", "궁합"]):
        team = sorted(pk, key=lambda x: x["synergy_score"], reverse=True)[:6]
        avg = sum(p["synergy_score"] for p in team) // 6
        return _resp({
            "team": team,
            "analysis": f"🎯 IV 시너지가 가장 뛰어난 팀입니다!\n\n평균 시너지: {avg}점\n\n{team[0]['emoji']}{team[0]['name_ko']}는 {team[0]['synergy_label']}({team[0]['synergy_score']}점) 등급으로, IV가 종족값 특성에 완벽히 맞습니다.\n시너지가 높을수록 같은 전투력이라도 실제 배틀에서 더 효율적으로 작동합니다.",
            "warnings": []
        })
    elif any(k in msg for k in ["메타", "승률", "요즘", "인기"]):
        return _resp({
            "team": [],
            "analysis": "📊 최근 배틀 메타 분석 (최근 100전 기준):\n\n1. 뮤츠 (에스퍼) — 승률 68.2% (15승/7패) 🟢\n2. 마기라스 (바위/악) — 승률 62.5% (10승/6패) 🟢\n3. 리자몽 (불/비행) — 승률 58.3% (7승/5패) 🟢\n4. 라프라스 (물/얼음) — 승률 52.1% (12승/11패) 🟡\n5. 망나뇽 (드래곤/비행) — 승률 47.8% (11승/12패) 🟡\n\n💡 에스퍼/바위 타입이 현재 메타에서 강세입니다.\n뮤츠는 높은 특공과 속도로 선제 공격이 가능해 승률이 높고,\n마기라스는 높은 물리 공격력으로 안정적인 성과를 보이고 있습니다.",
            "warnings": []
        })
    elif any(k in msg for k in ["육성", "키울", "성장"]):
        low_friend = [p for p in pk if p["friendship"] < 5]
        team = low_friend[:3] if low_friend else pk[:3]
        return _resp({
            "team": team,
            "analysis": f"🌱 육성 추천 포켓몬:\n\n" + "\n".join(
                f"• {p['emoji']}{p['name_ko']}: 시너지 {p['synergy_score']}점({p['synergy_label']}), 친밀도 {'♥'*p['friendship']}{'♡'*(5-p['friendship'])}\n  → 친밀도를 올리면 전스탯 +{(5-p['friendship'])*4}% 추가 가능!"
                for p in team
            ) + "\n\n밥과 놀기로 친밀도를 올리면 스탯이 최대 +20% 상승합니다.",
            "warnings": []
        })
    elif any(k in msg for k in ["약점", "취약"]):
        return _resp({
            "team": pk[:6],
            "analysis": "🔍 팀 약점 분석:\n\n현재 최적 팀 기준으로 분석했습니다.\n\n⚠️ 취약 타입:\n• 페어리 — 드래곤/에스퍼 포켓몬 3마리에 유리\n• 얼음 — 드래곤/비행 포켓몬 2마리에 유리\n\n✅ 강한 타입:\n• 에스퍼/드래곤 공격에 강한 편\n\n💡 페어리 타입 포켓몬을 보유하고 있다면 팀에 넣어 취약점을 보완하세요!",
            "warnings": ["페어리, 얼음 타입에 취약합니다."]
        })
    elif any(k in msg for k in ["카운터", "랭커", "상위"]):
        team = pk[:6]
        return _resp({
            "team": team,
            "analysis": "🛡️ 랭커 카운터 분석:\n\n상위 랭커들의 팀을 분석한 결과:\n• 에스퍼 타입 다수 사용 (뮤츠, 루기아)\n• 드래곤 타입 인기 (망나뇽, 한카리아스)\n\n추천 전략:\n1. 악 타입으로 에스퍼 견제\n2. 얼음 타입으로 드래곤 견제\n3. 페어리 타입으로 드래곤+악 동시 견제\n\n마기라스(바위/악)가 에스퍼 카운터로 특히 유효합니다!",
            "warnings": []
        })
    else:
        team = sorted(pk, key=lambda x: x["real_power"], reverse=True)[:6]
        total = sum(p["real_power"] for p in team)
        return _resp({
            "team": team,
            "analysis": f"⚖️ 밸런스 기준 추천 팀입니다.\n\n총 전투력: {total}, 타입 커버리지 4개\n\n전투력, IV 시너지, 타입 다양성을 균형있게 고려해서 선별했습니다.\n더 구체적인 질문이 있으시면 자유롭게 물어보세요!\n\n예시:\n• '요즘 승률 높은 포켓몬이 뭐야?'\n• '내 마기라스 어때?'\n• '페어리 카운터 추천해줘'",
            "warnings": []
        })


async def mock_admin_users(request):
    page = int(request.query.get("page", "1"))
    q = request.query.get("q", "")
    mock_users = [
        {"user_id": 1832746512, "username": "moon_ys_yu", "display_name": "문유", "master_balls": 12, "bp": 3500, "credits": 45, "registered_at": "2026-02-01T10:00:00", "last_active": "2026-03-05T14:30:00"},
        {"user_id": 2000000001, "username": "trainer_a", "display_name": "트레이너A", "master_balls": 8, "bp": 1250, "credits": 20, "registered_at": "2026-02-10T08:00:00", "last_active": "2026-03-05T13:00:00"},
        {"user_id": 2000000002, "username": "poke_fan", "display_name": "포켓몬팬", "master_balls": 3, "bp": 800, "credits": 5, "registered_at": "2026-02-15T12:00:00", "last_active": "2026-03-05T12:00:00"},
        {"user_id": 2000000003, "username": "", "display_name": "초보트레이너", "master_balls": 6, "bp": 500, "credits": 10, "registered_at": "2026-03-01T09:00:00", "last_active": "2026-03-04T22:00:00"},
        {"user_id": 2000000004, "username": "battle_king", "display_name": "배틀킹", "master_balls": 15, "bp": 5200, "credits": 0, "registered_at": "2026-02-05T15:00:00", "last_active": "2026-03-05T14:00:00"},
    ]
    if q:
        mock_users = [u for u in mock_users if q.lower() in u["display_name"].lower() or q in str(u["user_id"]) or q.lower() in u["username"].lower()]
    return web.json_response({"total": len(mock_users), "page": page, "per_page": 50, "users": mock_users})


async def mock_admin_orders(request):
    return web.json_response({"orders": [
        {"order_key": "order_tgpoke_1832746512_1709654321_1", "user_id": 1832746512, "price_usd": 3, "llm_quota": 20, "master_balls": 1, "fulfilled": True, "fulfilled_at": "2026-03-03T15:00:00"},
        {"order_key": "order_tgpoke_2000000001_1709654400_2", "user_id": 2000000001, "price_usd": 7, "llm_quota": 50, "master_balls": 3, "fulfilled": True, "fulfilled_at": "2026-03-04T10:00:00"},
        {"order_key": "order_tgpoke_2000000004_1709654500_1", "user_id": 2000000004, "price_usd": 3, "llm_quota": 20, "master_balls": 1, "fulfilled": False, "fulfilled_at": ""},
    ]})


async def mock_admin_action(request):
    body = await request.json()
    return web.json_response({"ok": True, "new_credits": 55, "new_master_balls": 15, "dm_sent": True})


async def mock_admin_db_overview(request):
    return web.json_response({"total_users":226,"total_pokemon":5834,"total_shiny":42,"total_masterballs":187,"total_hyperballs":340,"spawns_today":312,"caught_today":198,"catch_rate_today":63.5,"shiny_spawned":85,"shiny_caught":42,"total_spawns":18420})


async def mock_admin_db_shiny(request):
    items = [
        {"pokemon":"앤테이","rarity":"legendary","rarity_label":"전설","chat":"tg_poke","caught_by":"크립토비밥","caught_uid":53720317,"time":"2026-03-05T23:46:00","iv_grade":"B","iv_total":112,"ivs":{"hp":16,"atk":18,"def":23,"spa":16,"spdef":25,"spd":14}},
        {"pokemon":"에브이","rarity":"rare","rarity_label":"희귀","chat":"tg_poke","caught_by":"문유","caught_uid":123,"time":"2026-03-04T15:30:00","iv_grade":"A","iv_total":155,"ivs":{"hp":28,"atk":25,"def":27,"spa":26,"spdef":24,"spd":25}},
        {"pokemon":"잠만보","rarity":"epic","rarity_label":"에픽","chat":"tg_poke","caught_by":None,"caught_uid":None,"time":"2026-03-03T12:00:00","iv_grade":None,"iv_total":None,"ivs":None},
    ]
    return web.json_response({"items":items,"total":3,"page":1,"pages":1,"summary":{"total":85,"caught":42,"escaped":43}})


async def mock_admin_db_spawns(request):
    items = [
        {"pokemon":"피카츄","rarity":"common","rarity_label":"일반","shiny":False,"chat":"tg_poke","caught_by":"코인한나","participants":3,"time":"2026-03-05T23:50:00"},
        {"pokemon":"앤테이","rarity":"legendary","rarity_label":"전설","shiny":True,"chat":"tg_poke","caught_by":"크립토비밥","participants":5,"time":"2026-03-05T23:46:00"},
        {"pokemon":"이상해씨","rarity":"common","rarity_label":"일반","shiny":False,"chat":"tg_poke","caught_by":None,"participants":0,"time":"2026-03-05T23:30:00"},
    ]
    return web.json_response({"items":items,"total":3,"page":1,"pages":1})


async def mock_admin_db_user_pokemon(request):
    q = request.query.get("q", "")
    if not q:
        return web.json_response({"error": "q required"})
    items = [
        {"id":13987,"name":"옥타콘","rarity":"rare","rarity_label":"희귀","shiny":True,"active":True,"time":"2026-03-05T23:49:00","iv_grade":"A","iv_total":148,"ivs":{"hp":25,"atk":22,"def":28,"spa":24,"spdef":26,"spd":23}},
        {"id":13985,"name":"앤테이","rarity":"legendary","rarity_label":"전설","shiny":True,"active":True,"time":"2026-03-05T23:46:00","iv_grade":"B","iv_total":112,"ivs":{"hp":16,"atk":18,"def":23,"spa":16,"spdef":25,"spd":14}},
    ]
    return web.json_response({"user":{"id":53720317,"name":"크립토비밥","username":"phyllrar"},"items":items,"total":2,"summary":{"total":45,"shiny":3,"by_rarity":{"common":{"count":20,"shiny":0},"rare":{"count":15,"shiny":1},"epic":{"count":7,"shiny":1},"legendary":{"count":3,"shiny":1}}}})


async def mock_admin_db_economy(request):
    return web.json_response({
        "masterballs":[{"uid":1,"name":"코인한나","val":15},{"uid":2,"name":"크립토비밥","val":12},{"uid":3,"name":"문유","val":8}],
        "hyperballs":[{"uid":1,"name":"크립토비밥","val":25},{"uid":2,"name":"코인한나","val":18}],
        "bp":[{"uid":1,"name":"살려주세요","val":3200},{"uid":2,"name":"크립토비밥","val":2800}],
        "credits":[{"uid":1,"name":"문유","val":50},{"uid":2,"name":"코인한나","val":30}],
    })


async def mock_admin_db_optout(request):
    return web.json_response({
        "total": 2,
        "users": [
            {"uid": 123456, "name": "테스트유저", "username": "testuser", "last_active": "2026-03-06T12:30:00"},
            {"uid": 789012, "name": "크립토비밥", "username": None, "last_active": "2026-03-05T18:00:00"},
        ]
    })


async def mock_admin_db_optout_remove(request):
    return web.json_response({"ok": True})


async def mock_analytics_pageview(request):
    """Silently accept pageview events (no DB in preview)."""
    return web.json_response({"ok": True})


async def mock_analytics_session(request):
    """Silently accept session events (no DB in preview)."""
    return web.json_response({"ok": True})


async def mock_admin_kpi(request):
    """Return mock KPI data for preview."""
    import datetime
    today = datetime.date.today()
    daily = []
    for i in range(6, -1, -1):
        d = today - datetime.timedelta(days=i)
        daily.append({
            "date": d.isoformat(),
            "visitors": 15 + (i * 3) % 20,
            "pageviews": 40 + (i * 7) % 60,
        })
    cf_data = []
    for i in range(6, -1, -1):
        d = today - datetime.timedelta(days=i)
        cf_data.append({
            "date": d.isoformat(),
            "requests": 8000 + (i * 3000) % 15000,
            "pageviews": 150 + (i * 30) % 200,
            "visitors": 80 + (i * 20) % 100,
        })
    return web.json_response({
        "today": {"visitors": 42, "pageviews": 185, "avg_duration": 312},
        "daily": daily,
        "by_page": [
            {"page": "home", "views": 80},
            {"page": "battlerank", "views": 45},
            {"page": "stats", "views": 38},
            {"page": "mypokemon", "views": 32},
            {"page": "simulator", "views": 28},
            {"page": "tier", "views": 22},
            {"page": "typechart", "views": 15},
            {"page": "patchnotes", "views": 12},
        ],
        "by_hour": [
            {"hour": h, "views": max(1, int(20 * (1 + __import__('math').sin(
                (h - 14) * 3.14159 / 12))))} for h in range(24)
        ],
        "cloudflare": cf_data,
    })


async def mock_admin_battle_analytics(request):
    """Return mock battle analytics data for preview."""
    import datetime
    today = datetime.date.today()
    daily = []
    for i in range(6, -1, -1):
        d = today - datetime.timedelta(days=i)
        total = 30 + (i * 13) % 50
        ranked = int(total * 0.4)
        daily.append({"date": d.isoformat(), "total": total, "ranked": ranked, "normal": total - ranked})
    return web.json_response({
        "filters": {"days": "7", "battle_type": "all", "rarity": "all", "tier": "all"},
        "summary": {"total_battles": 847, "today_battles": 42, "avg_rounds": 12.3, "total_pokemon_used": 5082},
        "pokemon_ranking": [
            {"pokemon_id": 376, "name_ko": "메타그로스", "emoji": "", "rarity": "epic", "uses": 234, "wins": 145, "win_rate": 62.0, "avg_damage": 850, "avg_kills": 1.8, "avg_deaths": 0.4},
            {"pokemon_id": 384, "name_ko": "레쿠쟈", "emoji": "", "rarity": "ultra_legendary", "uses": 189, "wins": 118, "win_rate": 62.4, "avg_damage": 1420, "avg_kills": 2.3, "avg_deaths": 0.5},
            {"pokemon_id": 445, "name_ko": "한카리아스", "emoji": "", "rarity": "legendary", "uses": 156, "wins": 89, "win_rate": 57.1, "avg_damage": 1180, "avg_kills": 1.9, "avg_deaths": 0.6},
            {"pokemon_id": 130, "name_ko": "갸라도스", "emoji": "", "rarity": "epic", "uses": 142, "wins": 75, "win_rate": 52.8, "avg_damage": 780, "avg_kills": 1.5, "avg_deaths": 0.7},
            {"pokemon_id": 248, "name_ko": "마기라스", "emoji": "", "rarity": "legendary", "uses": 128, "wins": 70, "win_rate": 54.7, "avg_damage": 1050, "avg_kills": 1.7, "avg_deaths": 0.6},
            {"pokemon_id": 149, "name_ko": "망나뇽", "emoji": "", "rarity": "legendary", "uses": 115, "wins": 58, "win_rate": 50.4, "avg_damage": 980, "avg_kills": 1.6, "avg_deaths": 0.8},
            {"pokemon_id": 6, "name_ko": "리자몽", "emoji": "", "rarity": "epic", "uses": 98, "wins": 42, "win_rate": 42.9, "avg_damage": 680, "avg_kills": 1.2, "avg_deaths": 0.9},
            {"pokemon_id": 25, "name_ko": "피카츄", "emoji": "", "rarity": "rare", "uses": 85, "wins": 30, "win_rate": 35.3, "avg_damage": 320, "avg_kills": 0.8, "avg_deaths": 1.0},
        ],
        "rarity_stats": [
            {"rarity": "common", "uses": 1200, "wins": 480, "win_rate": 40.0, "avg_damage": 280},
            {"rarity": "rare", "uses": 980, "wins": 430, "win_rate": 43.9, "avg_damage": 420},
            {"rarity": "epic", "uses": 1560, "wins": 820, "win_rate": 52.6, "avg_damage": 750},
            {"rarity": "legendary", "uses": 890, "wins": 510, "win_rate": 57.3, "avg_damage": 1100},
            {"rarity": "ultra_legendary", "uses": 452, "wins": 280, "win_rate": 61.9, "avg_damage": 1380},
        ],
        "daily_battles": daily,
        "crit_skill_rates": {"actual_crit_rate": 10.2, "expected_crit_rate": 10.0, "actual_skill_rate": 29.8, "expected_skill_rate": 30.0, "total_turns": 42350},
    })


# ============================================================
# Mock Board Data
# ============================================================
import math as _math

_mock_board_posts = {
    "notice": [
        {"id": 1, "board_type": "notice", "tag": "패치노트", "title": "v1.7.0 — 3세대 호연 포켓몬 135종 추가!", "user_id": 1832746512, "display_name": "관리자", "content": "3세대 포켓몬 135종(#252-386)이 추가되었습니다!\n\n■ 주요 변경사항\n• 호연 포켓몬 135종 추가 (나무지기~테오키스)\n• 배틀 시스템에 3세대 종족값/스킬 반영\n• 호연 칭호 4개 추가\n• 교환 진화: 빈티나→밀로틱, 진주몽→헌테일\n• 도감 TMI 135개 추가\n\n즐거운 수집 되세요!", "image_filename": None, "view_count": 245, "like_count": 18, "comment_count": 7, "is_pinned": 1, "created_at": "2026-03-07T10:00:00+09:00"},
        {"id": 2, "board_type": "notice", "tag": "공지", "title": "서버 점검 안내 (3/6 02:00~04:00)", "user_id": 1832746512, "display_name": "관리자", "content": "안녕하세요, 서버 안정화를 위해 아래 시간에 점검이 진행됩니다.\n\n■ 점검 시간: 3월 6일(목) 02:00 ~ 04:00 (약 2시간)\n■ 점검 내용: DB 마이그레이션 및 성능 최적화\n\n점검 중에는 봇 이용이 불가합니다. 양해 부탁드립니다.", "image_filename": None, "view_count": 189, "like_count": 5, "comment_count": 2, "is_pinned": 1, "created_at": "2026-03-05T18:00:00+09:00"},
        {"id": 3, "board_type": "notice", "tag": "패치노트", "title": "v1.6.0 — 대화형 튜토리얼 & AI 어드바이저", "user_id": 1832746512, "display_name": "관리자", "content": "v1.6.0 업데이트가 적용되었습니다.\n\n■ 주요 변경사항\n• 대화형 튜토리얼 시스템 추가\n• AI 어드바이저 (Gemini 기반) 도입\n• 배틀 밸런스 조정\n• 대시보드 UI 개선", "image_filename": None, "view_count": 167, "like_count": 12, "comment_count": 5, "is_pinned": 0, "created_at": "2026-03-01T14:00:00+09:00"},
        {"id": 4, "board_type": "notice", "tag": "공지", "title": "커뮤니티 게시판 오픈!", "user_id": 1832746512, "display_name": "관리자", "content": "유저 게시판이 오픈되었습니다!\n\n자유롭게 공략, 질문, 팀 공유 등을 올려주세요.\n추천과 댓글 기능도 있습니다.\n\n건전한 커뮤니티 문화를 만들어주세요 :)", "image_filename": None, "view_count": 312, "like_count": 25, "comment_count": 8, "is_pinned": 0, "created_at": "2026-03-07T12:00:00+09:00"},
    ],
    "community": [
        {"id": 100, "board_type": "community", "tag": None, "title": "[공략] 3세대 최강 팀 조합 추천", "user_id": 2000000001, "display_name": "트레이너A", "content": "3세대 업데이트 이후 테스트해본 최강 팀 조합입니다.\n\n1. 메타그로스 (강철/에스퍼) — 600족 답게 안정적\n2. 레쿠쟈 (드래곤/비행) — 초전설 원탑\n3. 가디안 (에스퍼/페어리) — 타입 커버리지 최고\n4. 밀로틱 (물) — 방어 특화\n5. 앱솔 (악) — 에스퍼 카운터\n6. 게을킹 (노말) — 종족값 깡패\n\n이 조합이면 대부분의 상대에게 유리합니다!", "image_filename": None, "view_count": 87, "like_count": 15, "comment_count": 4, "is_pinned": 0, "created_at": "2026-03-07T15:30:00+09:00"},
        {"id": 101, "board_type": "community", "tag": None, "title": "[질문] 밀로틱 교환진화 같이 하실 분?", "user_id": 2000000002, "display_name": "포켓몬팬", "content": "빈티나 가지고 있는데 밀로틱으로 진화시키고 싶습니다.\n교환진화 같이 해주실 분 계신가요?\n\n빈티나 IV등급 A입니다!", "image_filename": None, "view_count": 45, "like_count": 3, "comment_count": 6, "is_pinned": 0, "created_at": "2026-03-07T14:00:00+09:00"},
        {"id": 102, "board_type": "community", "tag": None, "title": "[팀공유] 이로치 앱솔 잡았습니다!", "user_id": 2000000003, "display_name": "초보트레이너", "content": "방금 이로치 앱솔 잡았어요!!\n너무 기쁩니다 ㅠㅠ\n\nIV는 B등급이지만 이로치니까 만족합니다.\n빨간색 앱솔 너무 멋있어요!", "image_filename": "sample.jpg", "view_count": 156, "like_count": 32, "comment_count": 12, "is_pinned": 0, "created_at": "2026-03-07T11:20:00+09:00"},
        {"id": 103, "board_type": "community", "tag": None, "title": "[잡담] 레쿠쟈 포획률 1%는 너무한거 아닌가요", "user_id": 2000000004, "display_name": "배틀킹", "content": "레쿠쟈 10번 만났는데 한번도 못잡았습니다...\n마스터볼 쓰기엔 아깝고\n1%는 진짜 너무하지 않나요 ㅋㅋ\n\n혹시 잡으신 분 계신가요?", "image_filename": None, "view_count": 98, "like_count": 21, "comment_count": 15, "is_pinned": 0, "created_at": "2026-03-07T09:45:00+09:00"},
        {"id": 104, "board_type": "community", "tag": None, "title": "[공략] 배틀 승률 올리는 팁", "user_id": 2000000001, "display_name": "트레이너A", "content": "배틀 승률 60% 넘기는 노하우 공유합니다.\n\n1. IV 시너지가 높은 포켓몬 위주로 편성\n2. 타입 커버리지를 최소 4개 이상 확보\n3. 초전설/전설은 1마리씩만 (밸런스)\n4. 친밀도 5 찍으면 스탯 +20% 효과가 큼\n\n자세한건 AI 어드바이저한테 물어보세요!", "image_filename": None, "view_count": 134, "like_count": 28, "comment_count": 9, "is_pinned": 0, "created_at": "2026-03-06T20:15:00+09:00"},
        {"id": 105, "board_type": "community", "tag": None, "title": "[질문] 신규인데 뭐부터 해야하나요?", "user_id": 2000000005, "display_name": "뉴비", "content": "어제 시작했는데 뭐부터 해야할지 모르겠어요.\n포켓몬은 어떻게 잡나요?\n배틀은 언제부터 할 수 있나요?", "image_filename": None, "view_count": 67, "like_count": 5, "comment_count": 8, "is_pinned": 0, "created_at": "2026-03-06T16:00:00+09:00"},
    ],
}

_mock_board_comments = {
    100: [
        {"id": 1, "user_id": 2000000002, "display_name": "포켓몬팬", "content": "메타그로스 진짜 사기에요 ㄷㄷ", "created_at": "2026-03-07T16:00:00+09:00"},
        {"id": 2, "user_id": 2000000003, "display_name": "초보트레이너", "content": "저는 레쿠쟈가 없어서... 대체 포켓몬 추천해주실 수 있나요?", "created_at": "2026-03-07T16:30:00+09:00"},
        {"id": 3, "user_id": 2000000001, "display_name": "트레이너A", "content": "레쿠쟈 없으면 망나뇽이나 한카리아스도 괜찮아요!", "created_at": "2026-03-07T17:00:00+09:00"},
    ],
    102: [
        {"id": 4, "user_id": 2000000001, "display_name": "트레이너A", "content": "축하해요!! 이로치 앱솔 부럽다 ㅠ", "created_at": "2026-03-07T11:30:00+09:00"},
        {"id": 5, "user_id": 2000000004, "display_name": "배틀킹", "content": "이로치 앱솔 디자인 진짜 미쳤죠", "created_at": "2026-03-07T12:00:00+09:00"},
    ],
}

_mock_board_likes = set()  # set of (user_id, post_id)
_mock_board_next_id = 200


def _mock_time_ago(iso_str):
    import datetime as _dt
    dt = _dt.datetime.fromisoformat(iso_str)
    now = _dt.datetime.now(_dt.timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    diff = now - dt
    secs = int(diff.total_seconds())
    if secs < 60: return "방금 전"
    if secs < 3600: return f"{secs // 60}분 전"
    if secs < 86400: return f"{secs // 3600}시간 전"
    if secs < 604800: return f"{secs // 86400}일 전"
    return dt.strftime("%m.%d")


async def mock_board_posts(request):
    board_type = request.query.get("board_type", "notice")
    tag = request.query.get("tag", "")
    page = max(1, int(request.query.get("page", "1")))

    posts = _mock_board_posts.get(board_type, [])
    if tag:
        posts = [p for p in posts if p.get("tag") == tag]

    total = len(posts)
    per_page = 20
    start = (page - 1) * per_page
    page_posts = posts[start:start + per_page]

    result = []
    for p in page_posts:
        result.append({
            "id": p["id"], "board_type": p["board_type"], "tag": p.get("tag"),
            "title": p["title"], "display_name": p["display_name"],
            "has_image": bool(p.get("image_filename")),
            "view_count": p["view_count"], "like_count": p["like_count"],
            "comment_count": p["comment_count"], "is_pinned": p.get("is_pinned", 0),
            "time_ago": _mock_time_ago(p["created_at"]),
            "created_at": p["created_at"],
        })

    return web.json_response({
        "total": total, "page": page,
        "total_pages": _math.ceil(total / per_page) if total else 1,
        "posts": result,
    })


async def mock_board_post_detail(request):
    post_id = int(request.match_info["id"])
    for bt in _mock_board_posts.values():
        for p in bt:
            if p["id"] == post_id:
                comments = _mock_board_comments.get(post_id, [])
                comment_list = [{
                    "id": c["id"], "user_id": c["user_id"],
                    "display_name": c["display_name"], "content": c["content"],
                    "time_ago": _mock_time_ago(c["created_at"]),
                    "created_at": c["created_at"],
                } for c in comments]

                uid = _mock_user["user_id"] if _mock_user else 0
                liked = (uid, post_id) in _mock_board_likes

                post = {**p, "time_ago": _mock_time_ago(p["created_at"])}
                post["view_count"] += 1
                return web.json_response({"post": post, "comments": comment_list, "liked": liked})
    return web.json_response({"error": "Not found"}, status=404)


async def mock_board_post_create(request):
    global _mock_board_next_id
    if not _mock_user:
        return web.json_response({"error": "Login required"}, status=401)

    reader = await request.multipart()
    board_type = "community"
    tag = None
    title = ""
    content = ""

    while True:
        part = await reader.next()
        if part is None:
            break
        if part.name == "board_type":
            board_type = (await part.text()).strip()
        elif part.name == "tag":
            tag = (await part.text()).strip() or None
        elif part.name == "title":
            title = (await part.text()).strip()
        elif part.name == "content":
            content = (await part.text()).strip()

    import datetime as _dt
    new_post = {
        "id": _mock_board_next_id, "board_type": board_type, "tag": tag,
        "title": title, "user_id": _mock_user["user_id"],
        "display_name": _mock_user["display_name"], "content": content,
        "image_filename": None, "view_count": 0, "like_count": 0,
        "comment_count": 0, "is_pinned": 0,
        "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }
    _mock_board_posts.setdefault(board_type, []).insert(0, new_post)
    _mock_board_next_id += 1
    return web.json_response({"ok": True, "id": new_post["id"]})


async def mock_board_post_delete(request):
    if not _mock_user:
        return web.json_response({"error": "Login required"}, status=401)
    post_id = int(request.match_info["id"])
    for bt in _mock_board_posts.values():
        for i, p in enumerate(bt):
            if p["id"] == post_id:
                bt.pop(i)
                return web.json_response({"ok": True})
    return web.json_response({"error": "Not found"}, status=404)


async def mock_board_post_pin(request):
    post_id = int(request.match_info["id"])
    for bt in _mock_board_posts.values():
        for p in bt:
            if p["id"] == post_id:
                p["is_pinned"] = 0 if p.get("is_pinned") else 1
                return web.json_response({"ok": True, "is_pinned": p["is_pinned"]})
    return web.json_response({"error": "Not found"}, status=404)


async def mock_board_post_like(request):
    if not _mock_user:
        return web.json_response({"error": "Login required"}, status=401)
    post_id = int(request.match_info["id"])
    uid = _mock_user["user_id"]
    key = (uid, post_id)

    for bt in _mock_board_posts.values():
        for p in bt:
            if p["id"] == post_id:
                if key in _mock_board_likes:
                    _mock_board_likes.discard(key)
                    p["like_count"] = max(0, p["like_count"] - 1)
                    return web.json_response({"ok": True, "liked": False, "like_count": p["like_count"]})
                else:
                    _mock_board_likes.add(key)
                    p["like_count"] += 1
                    return web.json_response({"ok": True, "liked": True, "like_count": p["like_count"]})
    return web.json_response({"error": "Not found"}, status=404)


async def mock_board_comment_create(request):
    if not _mock_user:
        return web.json_response({"error": "Login required"}, status=401)
    post_id = int(request.match_info["id"])
    body = await request.json()
    content = body.get("content", "").strip()

    import datetime as _dt
    comment = {
        "id": 1000 + len(_mock_board_comments.get(post_id, [])),
        "user_id": _mock_user["user_id"],
        "display_name": _mock_user["display_name"],
        "content": content,
        "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }
    _mock_board_comments.setdefault(post_id, []).append(comment)

    for bt in _mock_board_posts.values():
        for p in bt:
            if p["id"] == post_id:
                p["comment_count"] += 1
                break
    return web.json_response({"ok": True, "id": comment["id"]})


async def mock_board_comment_delete(request):
    if not _mock_user:
        return web.json_response({"error": "Login required"}, status=401)
    comment_id = int(request.match_info["id"])
    for post_id, comments in _mock_board_comments.items():
        for i, c in enumerate(comments):
            if c["id"] == comment_id:
                comments.pop(i)
                for bt in _mock_board_posts.values():
                    for p in bt:
                        if p["id"] == post_id:
                            p["comment_count"] = max(0, p["comment_count"] - 1)
                return web.json_response({"ok": True})
    return web.json_response({"error": "Not found"}, status=404)


# ── Marketplace mock data ──
import math as _math

MOCK_MARKET_LISTINGS = [
    {"id":1,"pokemon_name":"리자몽","pokemon_id":6,"emoji":"🔥","rarity":"epic","pokemon_type":"fire","type2":"flying","is_shiny":True,"price_bp":8500,"seller_id":9999,"seller_name":"트레이너A","iv_hp":25,"iv_atk":28,"iv_def":15,"iv_spa":31,"iv_spdef":12,"iv_spd":22,"iv_total":133,"iv_grade":"A","friendship":5,"created_at":"2026-03-08T10:00:00+09:00","time_remaining":"5일 12시간"},
    {"id":2,"pokemon_name":"뮤츠","pokemon_id":150,"emoji":"🔮","rarity":"ultra_legendary","pokemon_type":"psychic","type2":None,"is_shiny":False,"price_bp":25000,"seller_id":1832746512,"seller_name":"테스트유저","iv_hp":20,"iv_atk":18,"iv_def":10,"iv_spa":31,"iv_spdef":15,"iv_spd":28,"iv_total":122,"iv_grade":"A","friendship":5,"created_at":"2026-03-07T14:30:00+09:00","time_remaining":"4일 2시간"},
    {"id":3,"pokemon_name":"피카츄","pokemon_id":25,"emoji":"⚡","rarity":"rare","pokemon_type":"electric","type2":None,"is_shiny":False,"price_bp":500,"seller_id":9998,"seller_name":"초보트레이너","iv_hp":10,"iv_atk":15,"iv_def":12,"iv_spa":8,"iv_spdef":20,"iv_spd":14,"iv_total":79,"iv_grade":"C","friendship":3,"created_at":"2026-03-09T08:00:00+09:00","time_remaining":"6일 20시간"},
    {"id":4,"pokemon_name":"마기라스","pokemon_id":248,"emoji":"🏔️","rarity":"legendary","pokemon_type":"rock","type2":"dark","is_shiny":False,"price_bp":15000,"seller_id":9997,"seller_name":"고수트레이너","iv_hp":28,"iv_atk":31,"iv_def":25,"iv_spa":20,"iv_spdef":22,"iv_spd":30,"iv_total":156,"iv_grade":"S","friendship":5,"created_at":"2026-03-08T22:15:00+09:00","time_remaining":"6일 10시간"},
    {"id":5,"pokemon_name":"메타그로스","pokemon_id":376,"emoji":"⚙️","rarity":"epic","pokemon_type":"steel","type2":"psychic","is_shiny":True,"price_bp":12000,"seller_id":9996,"seller_name":"배틀마스터","iv_hp":22,"iv_atk":30,"iv_def":28,"iv_spa":15,"iv_spdef":18,"iv_spd":25,"iv_total":138,"iv_grade":"A","friendship":7,"created_at":"2026-03-07T18:45:00+09:00","time_remaining":"5일 6시간"},
    {"id":6,"pokemon_name":"이상해꽃","pokemon_id":3,"emoji":"🌸","rarity":"rare","pokemon_type":"grass","type2":"poison","is_shiny":False,"price_bp":800,"seller_id":9999,"seller_name":"트레이너A","iv_hp":18,"iv_atk":12,"iv_def":20,"iv_spa":25,"iv_spdef":22,"iv_spd":10,"iv_total":107,"iv_grade":"B","friendship":5,"created_at":"2026-03-09T01:30:00+09:00","time_remaining":"6일 13시간"},
    {"id":7,"pokemon_name":"갸라도스","pokemon_id":130,"emoji":"🐲","rarity":"epic","pokemon_type":"water","type2":"flying","is_shiny":False,"price_bp":3500,"seller_id":9995,"seller_name":"수집가","iv_hp":20,"iv_atk":26,"iv_def":18,"iv_spa":10,"iv_spdef":15,"iv_spd":22,"iv_total":111,"iv_grade":"B","friendship":4,"created_at":"2026-03-08T06:00:00+09:00","time_remaining":"5일 18시간"},
    {"id":8,"pokemon_name":"잠만보","pokemon_id":143,"emoji":"😴","rarity":"epic","pokemon_type":"normal","type2":None,"is_shiny":False,"price_bp":4000,"seller_id":1832746512,"seller_name":"테스트유저","iv_hp":31,"iv_atk":15,"iv_def":28,"iv_spa":8,"iv_spdef":30,"iv_spd":5,"iv_total":117,"iv_grade":"B","friendship":3,"created_at":"2026-03-08T12:00:00+09:00","time_remaining":"5일 0시간"},
    {"id":9,"pokemon_name":"꼬부기","pokemon_id":7,"emoji":"🐢","rarity":"common","pokemon_type":"water","type2":None,"is_shiny":False,"price_bp":200,"seller_id":9994,"seller_name":"뉴비","iv_hp":8,"iv_atk":10,"iv_def":15,"iv_spa":12,"iv_spdef":8,"iv_spd":10,"iv_total":63,"iv_grade":"C","friendship":1,"created_at":"2026-03-09T05:00:00+09:00","time_remaining":"6일 17시간"},
    {"id":10,"pokemon_name":"루기아","pokemon_id":249,"emoji":"🌊","rarity":"ultra_legendary","pokemon_type":"psychic","type2":"flying","is_shiny":True,"price_bp":50000,"seller_id":9993,"seller_name":"레전드헌터","iv_hp":30,"iv_atk":25,"iv_def":31,"iv_spa":28,"iv_spdef":31,"iv_spd":20,"iv_total":165,"iv_grade":"S","friendship":7,"created_at":"2026-03-07T09:00:00+09:00","time_remaining":"4일 21시간"},
]


async def mock_market_listings(request):
    """Mock: browse market listings with filters."""
    listings = list(MOCK_MARKET_LISTINGS)
    q = request.query
    if q.get("rarity"):
        listings = [l for l in listings if l["rarity"] == q["rarity"]]
    if q.get("q"):
        s = q["q"].lower()
        listings = [l for l in listings if s in l["pokemon_name"].lower()]
    if q.get("shiny") == "1":
        listings = [l for l in listings if l["is_shiny"]]
    if q.get("iv_grade"):
        thresholds = {"S": 160, "A": 120, "B": 93, "C": 62}
        min_iv = thresholds.get(q["iv_grade"], 0)
        listings = [l for l in listings if l["iv_total"] >= min_iv]
    if q.get("price_min", "").isdigit():
        listings = [l for l in listings if l["price_bp"] >= int(q["price_min"])]
    if q.get("price_max", "").isdigit():
        listings = [l for l in listings if l["price_bp"] <= int(q["price_max"])]
    sort = q.get("sort", "newest")
    if sort == "price_asc":
        listings.sort(key=lambda x: x["price_bp"])
    elif sort == "price_desc":
        listings.sort(key=lambda x: -x["price_bp"])
    elif sort == "rarity":
        ro = {"ultra_legendary": 1, "legendary": 2, "epic": 3, "rare": 4, "common": 5}
        listings.sort(key=lambda x: ro.get(x["rarity"], 9))
    page = int(q.get("page", 0))
    ps = int(q.get("page_size", 20))
    total = len(listings)
    listings = listings[page * ps:(page + 1) * ps]
    return web.json_response({"listings": listings, "total": total, "page": page, "page_size": ps, "fee_rate": 0.05})


async def mock_market_stats(request):
    return web.json_response({"total_active": len(MOCK_MARKET_LISTINGS), "total_sold_24h": 5, "avg_price": 4200, "volume_24h": 21000})


async def mock_market_my_listings(request):
    if not _mock_user:
        return web.json_response({"error": "Login required"}, status=401)
    mine = [l for l in MOCK_MARKET_LISTINGS if l["seller_id"] == _mock_user["user_id"]]
    return web.json_response(mine)


async def mock_market_my_balance(request):
    if not _mock_user:
        return web.json_response({"error": "Login required"}, status=401)
    return web.json_response({"bp": 12500})


async def mock_market_my_sellable(request):
    if not _mock_user:
        return web.json_response({"error": "Login required"}, status=401)
    sellable = [
        {"id":101,"pokemon_id":94,"name_ko":"팬텀","emoji":"👻","rarity":"epic","pokemon_type":"ghost","type2":"poison","is_shiny":False,"friendship":5,"iv_total":128,"iv_grade":"A"},
        {"id":102,"pokemon_id":131,"name_ko":"라프라스","emoji":"🦕","rarity":"epic","pokemon_type":"water","type2":"ice","is_shiny":True,"friendship":7,"iv_total":145,"iv_grade":"A"},
        {"id":103,"pokemon_id":59,"name_ko":"윈디","emoji":"🐕","rarity":"rare","pokemon_type":"fire","type2":None,"is_shiny":False,"friendship":5,"iv_total":98,"iv_grade":"B"},
        {"id":104,"pokemon_id":65,"name_ko":"후딘","emoji":"🧙","rarity":"epic","pokemon_type":"psychic","type2":None,"is_shiny":False,"friendship":4,"iv_total":110,"iv_grade":"B"},
        {"id":105,"pokemon_id":149,"name_ko":"망나뇽","emoji":"🐉","rarity":"legendary","pokemon_type":"dragon","type2":"flying","is_shiny":False,"friendship":5,"iv_total":155,"iv_grade":"S"},
    ]
    q = request.query.get("q", "").strip().lower()
    if q:
        sellable = [s for s in sellable if q in s["name_ko"].lower()]
    return web.json_response(sellable)


async def mock_market_sell(request):
    if not _mock_user:
        return web.json_response({"error": "Login required"}, status=401)
    body = await request.json()
    price = int(body.get("price_bp", 0))
    if price < 100:
        return web.json_response({"error": "최소 가격: 100 BP"}, status=400)
    fee = max(1, _math.ceil(price * 0.05))
    return web.json_response({"ok": True, "listing_id": 999, "fee": fee, "seller_gets": price - fee, "message": "거래소 등록 완료!"})


async def mock_market_buy(request):
    if not _mock_user:
        return web.json_response({"error": "Login required"}, status=401)
    body = await request.json() if request.content_length else {}
    listing_id = body.get("listing_id", 0)
    # Simulate pending_evo for listing_id ending in odd number (교환진화 대상)
    has_evo = (int(listing_id) % 2 == 1) if listing_id else False
    return web.json_response({"ok": True, "message": "구매 완료!", "pokemon_name": "리자몽", "price": 8500, "new_bp": 4000, "pending_evo": has_evo})


async def mock_market_cancel(request):
    if not _mock_user:
        return web.json_response({"error": "Login required"}, status=401)
    return web.json_response({"ok": True, "message": "거래소 등록 취소!"})


def create_preview_app():
    app = web.Application()
    app.router.add_get("/", index)
    # Static files (type icons etc.)
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.router.add_static("/static", static_dir, show_index=False)
    # Pokemon sprites
    sprite_dir = Path(__file__).resolve().parent.parent / "assets" / "pokemon"
    if sprite_dir.exists():
        app.router.add_static("/sprites", sprite_dir, show_index=False)
    # Auth routes (mock)
    app.router.add_post("/api/auth/telegram", mock_auth_telegram)
    app.router.add_get("/api/auth/me", mock_auth_me)
    app.router.add_post("/api/auth/logout", mock_auth_logout)
    # My data routes (mock)
    app.router.add_get("/api/my/pokemon", mock_my_pokemon)
    app.router.add_get("/api/my/pokedex", mock_my_pokedex)
    app.router.add_get("/api/my/summary", mock_my_summary)
    app.router.add_post("/api/my/team-recommend", mock_team_recommend)
    app.router.add_post("/api/my/chat", mock_chat)
    app.router.add_post("/api/my/fusion", mock_fusion)
    app.router.add_get("/api/my/quota", lambda r: web.json_response({"remaining": max(0, 20 - _mock_chat_count), "bonus_remaining": 45}))
    app.router.add_get("/api/donation", lambda r: web.json_response({"current": 75, "goal": 200}))
    app.router.add_post("/api/payment/create", lambda r: web.json_response({"ok": True, "invoice_url": "https://nowpayments.io/payment/?iid=mock_preview", "invoice_id": "mock_123"}))
    # Admin routes (mock)
    app.router.add_get("/api/admin/users", mock_admin_users)
    app.router.add_get("/api/admin/orders", mock_admin_orders)
    app.router.add_post("/api/admin/grant-credit", mock_admin_action)
    app.router.add_post("/api/admin/grant-bp", mock_admin_action)
    app.router.add_post("/api/admin/grant-masterball", mock_admin_action)
    app.router.add_post("/api/admin/fulfill-order", mock_admin_action)
    app.router.add_post("/api/admin/send-dm", mock_admin_action)
    # Admin DB Browser (mock)
    app.router.add_get("/api/admin/db/overview", mock_admin_db_overview)
    app.router.add_get("/api/admin/db/shiny", mock_admin_db_shiny)
    app.router.add_get("/api/admin/db/spawns", mock_admin_db_spawns)
    app.router.add_get("/api/admin/db/user-pokemon", mock_admin_db_user_pokemon)
    app.router.add_get("/api/admin/db/economy", mock_admin_db_economy)
    app.router.add_get("/api/admin/db/optout", mock_admin_db_optout)
    app.router.add_post("/api/admin/db/optout-remove", mock_admin_db_optout_remove)
    # Analytics & KPI (mock)
    app.router.add_post("/api/analytics/pageview", mock_analytics_pageview)
    app.router.add_post("/api/analytics/session", mock_analytics_session)
    app.router.add_get("/api/admin/kpi", mock_admin_kpi)
    app.router.add_get("/api/admin/battle-analytics", mock_admin_battle_analytics)
    # Catch-all for API routes
    for api_path in [
        "/api/overview", "/api/chats", "/api/users", "/api/spawns/recent",
        "/api/pokemon/stats", "/api/events", "/api/fun-kpis",
        "/api/battle/ranking", "/api/battle/ranking-teams", "/api/battle/tiers",
        "/api/ranked/season", "/api/dashboard-kpi", "/api/type-chart",
        "/api/tournament/winners", "/api/iv-ranking",
    ]:
        app.router.add_get(api_path, mock_json)
    # Board (Community) routes
    app.router.add_get("/api/board/posts", mock_board_posts)
    app.router.add_get("/api/board/posts/{id}", mock_board_post_detail)
    app.router.add_post("/api/board/posts", mock_board_post_create)
    app.router.add_delete("/api/board/posts/{id}", mock_board_post_delete)
    app.router.add_post("/api/board/posts/{id}/pin", mock_board_post_pin)
    app.router.add_post("/api/board/posts/{id}/like", mock_board_post_like)
    app.router.add_post("/api/board/posts/{id}/comments", mock_board_comment_create)
    app.router.add_delete("/api/board/comments/{id}", mock_board_comment_delete)
    # Marketplace (mock)
    app.router.add_get("/api/market/listings", mock_market_listings)
    app.router.add_get("/api/market/stats", mock_market_stats)
    app.router.add_get("/api/market/my-listings", mock_market_my_listings)
    app.router.add_get("/api/market/my-balance", mock_market_my_balance)
    app.router.add_get("/api/market/my-sellable", mock_market_my_sellable)
    app.router.add_post("/api/market/sell", mock_market_sell)
    app.router.add_post("/api/market/buy", mock_market_buy)
    app.router.add_post("/api/market/cancel", mock_market_cancel)
    # Markdown doc viewer
    app.router.add_get("/docs/{name}", serve_markdown_doc)
    # SPA catch-all
    for p in ["/channels", "/patchnotes", "/board", "/battle", "/tier", "/types", "/guide", "/stats", "/mypokemon", "/pokedex", "/ai", "/admin", "/market"]:
        app.router.add_get(p, index)
    # Board deep-link sub-routes
    app.router.add_get("/board/post/{id}", index)
    app.router.add_get("/board/{sub}", index)
    return app


async def serve_markdown_doc(request):
    """Serve a markdown file from docs/ as rendered HTML."""
    import re as _re
    name = request.match_info["name"]
    if not _re.match(r'^[\w-]+$', name):
        return web.Response(text="Not found", status=404)
    doc_path = Path(__file__).parent.parent / "docs" / f"{name}.md"
    if not doc_path.exists():
        return web.Response(text="Not found", status=404)
    content = doc_path.read_text(encoding="utf-8")
    escaped = content.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
    html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name}</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:900px;margin:0 auto;padding:20px 24px;background:#FFFDF7;color:#333;line-height:1.7}}
h1{{color:#B71C1C;border-bottom:3px solid #B71C1C;padding-bottom:8px}}
h2{{color:#C62828;margin-top:2em;border-bottom:1px solid #eee;padding-bottom:4px}}
h3{{color:#D32F2F;margin-top:1.5em}}
table{{border-collapse:collapse;width:100%;margin:12px 0;font-size:14px}}
th,td{{border:1px solid #ddd;padding:8px 10px;text-align:left}}
th{{background:#FFEBEE;font-weight:700}}
tr:nth-child(even){{background:#FFF8F0}}
code{{background:#f5f5f5;padding:2px 5px;border-radius:3px;font-size:13px}}
pre{{background:#263238;color:#ECEFF1;padding:16px;border-radius:8px;overflow-x:auto;font-size:13px}}
pre code{{background:none;color:inherit}}
blockquote{{border-left:4px solid #B71C1C;margin:12px 0;padding:8px 16px;background:#FFF3E0;color:#555}}
a{{color:#1565C0}}
hr{{border:none;border-top:2px solid #eee;margin:2em 0}}
.back{{display:inline-block;margin-bottom:16px;padding:6px 14px;background:#B71C1C;color:#fff;text-decoration:none;border-radius:6px;font-size:13px}}
</style></head><body>
<a class="back" href="/">← 대시보드</a>
<div id="content"></div>
<script>
document.getElementById('content').innerHTML=marked.parse(`{escaped}`);
</script></body></html>"""
    return web.Response(text=html, content_type="text/html")


async def main():
    app = create_preview_app()
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("DASHBOARD_PREVIEW_PORT", "8090"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Dashboard preview at http://localhost:{port}")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
