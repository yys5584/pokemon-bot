"""Dashboard web server using aiohttp."""

import asyncio
import logging
import os
from pathlib import Path

from aiohttp import web

from database import queries

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"


# --- API Handlers ---

async def api_overview(request):
    total = await queries.get_total_stats()
    today = await queries.get_today_stats()
    return web.json_response({**total, **today})


async def api_chats(request):
    rooms = await queries.get_all_chat_rooms()
    return web.json_response(rooms)


async def api_users(request):
    users = await queries.get_user_rankings(20)
    return web.json_response(users)


async def api_spawns_recent(request):
    spawns = await queries.get_recent_spawns_global(50)
    return web.json_response(spawns)


async def api_pokemon_stats(request):
    stats = await queries.get_top_pokemon_caught(20)
    return web.json_response(stats)


async def api_events(request):
    await queries.cleanup_expired_events()
    events = await queries.get_active_events()
    return web.json_response(events)


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

    return web.json_response({
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
