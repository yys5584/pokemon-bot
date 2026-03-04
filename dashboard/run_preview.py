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
                 "today_catches": 42, "today_active_users": 18}
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
            {"id": 150, "name": "뮤츠", "emoji": "🔮", "rarity": "legendary",
             "type1": "psychic", "type2": None, "stat_ko": "공격",
             "power": 95.2, "skill_name": "사이코키네시스",
             "skill_power": 1.8, "hp": 318, "atk": 110, "def_": 90,
             "spa": 154, "spdef": 90, "spd": 130},
            {"id": 242, "name": "해피너스", "emoji": "🩷", "rarity": "epic",
             "type1": "normal", "type2": None, "stat_ko": "방어",
             "power": 88.7, "skill_name": "알폭탄",
             "skill_power": 1.3, "hp": 548, "atk": 23, "def_": 23,
             "spa": 65, "spdef": 85, "spd": 52},
            {"id": 250, "name": "칠색조", "emoji": "🔥", "rarity": "legendary",
             "type1": "fire", "type2": "flying", "stat_ko": "공격",
             "power": 85.4, "skill_name": "성스러운불꽃",
             "skill_power": 2.0, "hp": 306, "atk": 120, "def_": 88,
             "spa": 104, "spdef": 138, "spd": 88},
            {"id": 249, "name": "루기아", "emoji": "🌊", "rarity": "legendary",
             "type1": "psychic", "type2": "flying", "stat_ko": "방어",
             "power": 82.1, "skill_name": "에어로블라스트",
             "skill_power": 1.7, "hp": 318, "atk": 90, "def_": 130,
             "spa": 90, "spdef": 154, "spd": 110},
            {"id": 248, "name": "마기라스", "emoji": "🪨", "rarity": "epic",
             "type1": "rock", "type2": "dark", "stat_ko": "공격",
             "power": 67.5, "skill_name": "깨물어부수기",
             "skill_power": 1.5, "hp": 291, "atk": 123, "def_": 104,
             "spa": 93, "spdef": 97, "spd": 67},
            {"id": 149, "name": "망나뇽", "emoji": "🐉", "rarity": "epic",
             "type1": "dragon", "type2": "flying", "stat_ko": "공격",
             "power": 61.9, "skill_name": "역린",
             "skill_power": 1.5, "hp": 270, "atk": 123, "def_": 93,
             "spa": 97, "spdef": 97, "spd": 81},
            {"id": 131, "name": "라프라스", "emoji": "🧊", "rarity": "rare",
             "type1": "water", "type2": "ice", "stat_ko": "방어",
             "power": 56.0, "skill_name": "냉동빔",
             "skill_power": 1.5, "hp": 360, "atk": 85, "def_": 81,
             "spa": 85, "spdef": 93, "spd": 66},
            {"id": 20, "name": "레트라", "emoji": "🐀", "rarity": "common",
             "type1": "normal", "type2": None, "stat_ko": "속도",
             "power": 15.2, "skill_name": "필살앞니",
             "skill_power": 1.4, "hp": 165, "atk": 62, "def_": 52,
             "spa": 43, "spdef": 55, "spd": 88},
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
            "top_channels": [],
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
    _mock_user = {"user_id": 1832746512, "display_name": "테스트유저", "photo_url": ""}
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
         "stat_type":"offensive","friendship":5,"is_shiny":True,"is_favorite":True,"evo_stage":3,
         "ivs":{"hp":25,"atk":28,"def":15,"spa":31,"spdef":12,"spd":22},
         "stats":{"hp":285,"atk":86,"def":78,"spa":109,"spdef":85,"spd":100},
         "real_stats":{"hp":312,"atk":98,"def":81,"spa":126,"spdef":87,"spd":108},
         "power":743,"real_power":812,"iv_bonus":69,"iv_total":133,"iv_grade":"B",
         "synergy_score":85,"synergy_label":"우수","synergy_emoji":"🔥"},
        {"id":2,"pokemon_id":150,"name_ko":"뮤츠","emoji":"🔮","rarity":"legendary","pokemon_type":"psychic","type2":None,
         "stat_type":"offensive","friendship":5,"is_shiny":False,"is_favorite":False,"evo_stage":3,
         "ivs":{"hp":20,"atk":18,"def":10,"spa":31,"spdef":15,"spd":28},
         "stats":{"hp":318,"atk":110,"def":90,"spa":154,"spdef":90,"spd":130},
         "real_stats":{"hp":340,"atk":118,"def":92,"spa":178,"spdef":93,"spd":143},
         "power":892,"real_power":964,"iv_bonus":72,"iv_total":122,"iv_grade":"B",
         "synergy_score":82,"synergy_label":"우수","synergy_emoji":"🔥"},
        {"id":3,"pokemon_id":131,"name_ko":"라프라스","emoji":"🧊","rarity":"rare","pokemon_type":"water","type2":"ice",
         "stat_type":"defensive","friendship":4,"is_shiny":False,"is_favorite":False,"evo_stage":3,
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
         "stat_type":"offensive","friendship":5,"is_shiny":True,"is_favorite":True,"evo_stage":3,
         "ivs":{"hp":28,"atk":31,"def":25,"spa":20,"spdef":22,"spd":30},
         "stats":{"hp":291,"atk":123,"def":104,"spa":93,"spdef":97,"spd":67},
         "real_stats":{"hp":324,"atk":141,"def":116,"spa":100,"spdef":105,"spd":74},
         "power":775,"real_power":860,"iv_bonus":85,"iv_total":156,"iv_grade":"A",
         "synergy_score":88,"synergy_label":"우수","synergy_emoji":"🔥"},
        {"id":6,"pokemon_id":149,"name_ko":"망나뇽","emoji":"🐉","rarity":"epic","pokemon_type":"dragon","type2":"flying",
         "stat_type":"offensive","friendship":5,"is_shiny":False,"is_favorite":False,"evo_stage":3,
         "ivs":{"hp":15,"atk":25,"def":12,"spa":28,"spdef":10,"spd":20},
         "stats":{"hp":270,"atk":123,"def":93,"spa":97,"spdef":97,"spd":81},
         "real_stats":{"hp":283,"atk":137,"def":96,"spa":111,"spdef":99,"spd":87},
         "power":761,"real_power":813,"iv_bonus":52,"iv_total":110,"iv_grade":"B",
         "synergy_score":75,"synergy_label":"우수","synergy_emoji":"🔥"},
    ]
    return web.json_response(mock_pokemon)

async def mock_my_summary(request):
    return web.json_response({
        "total_pokemon":6,"shiny_count":2,"dex_count":45,
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


def create_preview_app():
    app = web.Application()
    app.router.add_get("/", index)
    # Static files (type icons etc.)
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.router.add_static("/static", static_dir, show_index=False)
    # Auth routes (mock)
    app.router.add_post("/api/auth/telegram", mock_auth_telegram)
    app.router.add_get("/api/auth/me", mock_auth_me)
    app.router.add_post("/api/auth/logout", mock_auth_logout)
    # My data routes (mock)
    app.router.add_get("/api/my/pokemon", mock_my_pokemon)
    app.router.add_get("/api/my/summary", mock_my_summary)
    app.router.add_post("/api/my/team-recommend", mock_team_recommend)
    app.router.add_post("/api/my/chat", mock_chat)
    app.router.add_get("/api/my/quota", lambda r: web.json_response({"remaining": max(0, 20 - _mock_chat_count), "bonus_remaining": 45}))
    app.router.add_get("/api/donation", lambda r: web.json_response({"current": 75, "goal": 200}))
    app.router.add_post("/api/payment/create", lambda r: web.json_response({"ok": True, "invoice_url": "https://nowpayments.io/payment/?iid=mock_preview", "invoice_id": "mock_123"}))
    # Catch-all for API routes
    for api_path in [
        "/api/overview", "/api/chats", "/api/users", "/api/spawns/recent",
        "/api/pokemon/stats", "/api/events", "/api/fun-kpis",
        "/api/battle/ranking", "/api/battle/ranking-teams", "/api/battle/tiers",
        "/api/dashboard-kpi", "/api/type-chart",
        "/api/tournament/winners", "/api/iv-ranking",
    ]:
        app.router.add_get(api_path, mock_json)
    # SPA catch-all
    for p in ["/channels", "/battle", "/tier", "/types", "/stats", "/mypokemon", "/ai"]:
        app.router.add_get(p, index)
    return app


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
