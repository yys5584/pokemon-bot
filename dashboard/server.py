"""Dashboard web server using aiohttp."""

import asyncio
import json
import logging
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from aiohttp import web

from database import queries
from database import battle_queries as bq

logger = logging.getLogger(__name__)


class PGJsonEncoder(json.JSONEncoder):
    """JSON encoder that handles PostgreSQL types (datetime, Decimal)."""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def pg_json_response(data, **kwargs):
    """pg_json_response with PG-compatible JSON encoder."""
    return web.Response(
        text=json.dumps(data, cls=PGJsonEncoder, ensure_ascii=False),
        content_type="application/json",
        **kwargs,
    )

TEMPLATE_DIR = Path(__file__).parent / "templates"


# --- API Handlers ---

async def api_overview(request):
    total = await queries.get_total_stats()
    today = await queries.get_today_stats()
    return pg_json_response({**total, **today})


async def api_chats(request):
    rooms = await queries.get_all_chat_rooms()
    return pg_json_response(rooms)


async def api_users(request):
    users = await queries.get_user_rankings(20)
    return pg_json_response(users)


async def api_spawns_recent(request):
    spawns = await queries.get_recent_spawns_global(50)
    return pg_json_response(spawns)


async def api_pokemon_stats(request):
    stats = await queries.get_top_pokemon_caught(20)
    return pg_json_response(stats)


async def api_events(request):
    await queries.cleanup_expired_events()
    events = await queries.get_active_events()
    return pg_json_response(events)


async def api_fun_kpis(request):
    """Consolidated fun KPI endpoint — parallel queries."""
    (
        global_catch_rate,
        total_mb_used,
        longest_streak,
        rare_holders,
        escape_masters,
        night_owls,
        masterball_rich,
        pokeball_addicts,
        user_catch_rates,
        trade_kings,
        most_escaped,
        love_leaders,
    ) = await asyncio.gather(
        queries.get_global_catch_rate(),
        queries.get_total_master_balls_used(),
        queries.get_longest_streak_user(),
        queries.get_rare_pokemon_holders(20),
        queries.get_escape_masters(5),
        queries.get_night_owls(5),
        queries.get_masterball_rich(5),
        queries.get_pokeball_addicts(5),
        queries.get_user_catch_rates(10),
        queries.get_trade_kings(5),
        queries.get_most_escaped_pokemon(5),
        queries.get_love_leaders(5),
    )

    # Split catch rates into lucky (top) and unlucky (bottom)
    lucky_users = user_catch_rates[:5] if user_catch_rates else []
    unlucky_users = sorted(user_catch_rates, key=lambda x: x["catch_rate"])[:5] if user_catch_rates else []

    return pg_json_response({
        "global_catch_rate": global_catch_rate,
        "total_master_balls_used": total_mb_used,
        "longest_streak": longest_streak,
        "rare_holders": rare_holders,
        "escape_masters": escape_masters,
        "night_owls": night_owls,
        "masterball_rich": masterball_rich,
        "pokeball_addicts": pokeball_addicts,
        "lucky_users": lucky_users,
        "unlucky_users": unlucky_users,
        "trade_kings": trade_kings,
        "most_escaped": most_escaped,
        "love_leaders": love_leaders,
    })


# --- Battle APIs ---

async def api_battle_ranking(request):
    ranking = await bq.get_battle_ranking(20)
    return pg_json_response(ranking)


async def api_battle_tiers(request):
    """Build tier list data for epic+ pokemon."""
    from database.connection import get_db
    import config
    from utils.battle_calc import calc_battle_stats, EVO_STAGE_MAP
    from models.pokemon_skills import POKEMON_SKILLS

    pool = await get_db()
    rows = await pool.fetch("""
        SELECT id, name_ko, emoji, rarity, pokemon_type, stat_type
        FROM pokemon_master
        WHERE rarity IN ('epic', 'legendary')
        ORDER BY id
    """)

    scored = []
    for r in rows:
        evo_stage = EVO_STAGE_MAP.get(r["id"], 3)
        stats = calc_battle_stats(r["rarity"], r["stat_type"], 5, evo_stage=evo_stage)
        skill = POKEMON_SKILLS.get(r["id"], ("몸통박치기", 1.2))

        eff_atk = stats["atk"] * (1 + config.BATTLE_SKILL_RATE * skill[1])
        eff_tank = stats["hp"] * (1 + stats["def"] * 0.003)
        power = eff_atk * eff_tank / 1000

        type_emoji = config.TYPE_EMOJI.get(r["pokemon_type"], "")
        type_ko = config.TYPE_NAME_KO.get(r["pokemon_type"], r["pokemon_type"])
        stat_ko = {"offensive": "공격", "defensive": "방어", "balanced": "균형", "speedy": "속도"}.get(r["stat_type"], r["stat_type"])

        # Assign tier
        if r["rarity"] == "legendary":
            tier = "S+" if stats["atk"] >= 140 else "S"
        else:
            if stats["atk"] >= 110:
                tier = "A+"
            elif stats["atk"] >= 85:
                tier = "A"
            elif stats["atk"] >= 70:
                tier = "B+"
            else:
                tier = "B"

        scored.append({
            "id": r["id"], "name": r["name_ko"], "emoji": r["emoji"],
            "rarity": r["rarity"], "type_emoji": type_emoji, "type_ko": type_ko,
            "stat_ko": stat_ko, "power": round(power, 1), "tier": tier,
            "skill_name": skill[0], "skill_power": skill[1],
            "hp": stats["hp"], "atk": stats["atk"],
            "def_": stats["def"], "spd": stats["spd"],
        })

    scored.sort(key=lambda x: x["power"], reverse=True)
    return pg_json_response(scored)


# --- Dashboard KPI APIs ---

async def api_dashboard_kpi(request):
    """DAU, retention, economy health — single endpoint."""
    dau, dau_hist, retention, economy, top_channels = await asyncio.gather(
        queries.get_dau(),
        queries.get_dau_history(7),
        queries.get_retention_d1(),
        queries.get_economy_health(),
        queries.get_active_chat_rooms_top(5),
    )
    return pg_json_response({
        "dau": dau,
        "dau_history": dau_hist,
        "retention": retention,
        "economy": economy,
        "top_channels": top_channels,
    })


# --- Page Handler ---

async def index(request):
    html_path = TEMPLATE_DIR / "index.html"
    return web.FileResponse(html_path)


# --- Server Setup ---

def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/api/overview", api_overview)
    app.router.add_get("/api/chats", api_chats)
    app.router.add_get("/api/users", api_users)
    app.router.add_get("/api/spawns/recent", api_spawns_recent)
    app.router.add_get("/api/pokemon/stats", api_pokemon_stats)
    app.router.add_get("/api/events", api_events)
    app.router.add_get("/api/fun-kpis", api_fun_kpis)
    app.router.add_get("/api/battle/ranking", api_battle_ranking)
    app.router.add_get("/api/battle/tiers", api_battle_tiers)
    app.router.add_get("/api/dashboard-kpi", api_dashboard_kpi)
    return app


async def start_dashboard():
    """Start the dashboard web server in the background."""
    port = int(os.getenv("DASHBOARD_PORT", "8080"))
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Dashboard running at http://localhost:{port}")
    return runner
