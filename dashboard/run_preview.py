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
            "economy": {"total_pokeballs": 5000, "total_master_balls": 120,
                         "total_bp": 25000, "avg_pokeballs": 33},
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


def create_preview_app():
    app = web.Application()
    app.router.add_get("/", index)
    # Static files (type icons etc.)
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.router.add_static("/static", static_dir, show_index=False)
    # Catch-all for API routes
    for api_path in [
        "/api/overview", "/api/chats", "/api/users", "/api/spawns/recent",
        "/api/pokemon/stats", "/api/events", "/api/fun-kpis",
        "/api/battle/ranking", "/api/battle/ranking-teams", "/api/battle/tiers",
        "/api/dashboard-kpi", "/api/type-chart",
    ]:
        app.router.add_get(api_path, mock_json)
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
