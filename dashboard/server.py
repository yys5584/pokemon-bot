"""Dashboard web server using aiohttp."""

import asyncio
import json
import logging
import math
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
    # Hide private chats (no title) and small rooms (< 10 members)
    rooms = [r for r in rooms if r.get("chat_title") and r.get("member_count", 0) >= 10]
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
        shiny_holders,
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
        queries.get_shiny_holders(20),
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
        "shiny_holders": shiny_holders,
    })


# --- Battle APIs ---

async def api_battle_ranking(request):
    ranking = await bq.get_battle_ranking(20)
    return pg_json_response(ranking)


async def api_battle_ranking_teams(request):
    """Get battle teams + partner info for top 10 rankers."""
    ranking = await bq.get_battle_ranking(10)
    result = {}
    for r in ranking:
        uid = r["user_id"]
        team_task = bq.get_battle_team(uid)
        partner_task = bq.get_partner(uid)
        team, partner = await asyncio.gather(team_task, partner_task)
        partner_iid = partner["instance_id"] if partner else None
        result[str(uid)] = [
            {
                "emoji": p["emoji"],
                "name_ko": p["name_ko"],
                "is_partner": p["pokemon_instance_id"] == partner_iid,
                "is_shiny": bool(p.get("is_shiny", 0)),
            }
            for p in team
        ]
    return pg_json_response(result)


async def api_battle_tiers(request):
    """Build tier list data for ALL pokemon (final evolution only)."""
    from database.connection import get_db
    import config
    from utils.battle_calc import calc_battle_stats, EVO_STAGE_MAP, get_normalized_base_stats
    from models.pokemon_skills import POKEMON_SKILLS
    from models.pokemon_base_stats import POKEMON_BASE_STATS

    pool = await get_db()
    rows = await pool.fetch("""
        SELECT id, name_ko, emoji, rarity, pokemon_type, stat_type, evolves_to
        FROM pokemon_master
        ORDER BY id
    """)

    # Only final evolutions (evolves_to IS NULL or evo_stage == 3)
    final_evos = [r for r in rows if r["evolves_to"] is None]

    scored = []
    for r in final_evos:
        base = get_normalized_base_stats(r["id"])
        stats = calc_battle_stats(
            r["rarity"], r["stat_type"], 5,
            evo_stage=3 if base else EVO_STAGE_MAP.get(r["id"], 3),
            **(base or {}),
        )
        skill = POKEMON_SKILLS.get(r["id"], ("몸통박치기", 1.2))

        # Best offensive stat (physical or special)
        best_atk = max(stats["atk"], stats["spa"])
        # Best defensive stat (average of physical + special)
        eff_def = (stats["def"] + stats["spdef"]) / 2

        eff_atk = best_atk * (1 + config.BATTLE_SKILL_RATE * skill[1])
        eff_tank = stats["hp"] * (1 + eff_def * 0.003)
        power = eff_atk * eff_tank / 1000

        # Dual type from base stats data
        bs_entry = POKEMON_BASE_STATS.get(r["id"])
        types = bs_entry[6] if bs_entry else [r["pokemon_type"]]
        type1 = types[0] if types else r["pokemon_type"]
        type2 = types[1] if len(types) > 1 else None

        stat_ko = {"offensive": "공격", "defensive": "방어", "balanced": "균형", "speedy": "속도"}.get(r["stat_type"], r["stat_type"])

        scored.append({
            "id": r["id"], "name": r["name_ko"], "emoji": r["emoji"],
            "rarity": r["rarity"],
            "type1": type1, "type2": type2,
            "stat_ko": stat_ko, "power": round(power, 1),
            "skill_name": skill[0], "skill_power": skill[1],
            "hp": stats["hp"], "atk": stats["atk"],
            "def_": stats["def"], "spa": stats["spa"],
            "spdef": stats["spdef"], "spd": stats["spd"],
        })

    # Sort by power descending
    scored.sort(key=lambda x: -x["power"])
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


async def api_type_chart(request):
    """Return the full 18-type effectiveness chart data."""
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
                row[def_type] = 2  # super effective
            elif atk_type in disadvantages:
                row[def_type] = 0.5  # not very effective
            else:
                row[def_type] = 1
        chart[atk_type] = row
    return pg_json_response({
        "types": types,
        "type_names": config.TYPE_NAME_KO,
        "type_emoji": config.TYPE_EMOJI,
        "chart": chart,
    })


# --- Page Handler ---

async def index(request):
    html_path = TEMPLATE_DIR / "index.html"
    return web.FileResponse(html_path)


# --- Server Setup ---

def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    # Static files (type icons etc.)
    static_dir = TEMPLATE_DIR.parent / "static"
    if static_dir.exists():
        app.router.add_static("/static", static_dir, show_index=False)
    app.router.add_get("/api/overview", api_overview)
    app.router.add_get("/api/chats", api_chats)
    app.router.add_get("/api/users", api_users)
    app.router.add_get("/api/spawns/recent", api_spawns_recent)
    app.router.add_get("/api/pokemon/stats", api_pokemon_stats)
    app.router.add_get("/api/events", api_events)
    app.router.add_get("/api/fun-kpis", api_fun_kpis)
    app.router.add_get("/api/battle/ranking", api_battle_ranking)
    app.router.add_get("/api/battle/ranking-teams", api_battle_ranking_teams)
    app.router.add_get("/api/battle/tiers", api_battle_tiers)
    app.router.add_get("/api/tournament/winners", api_tournament_winners)
    app.router.add_get("/api/dashboard-kpi", api_dashboard_kpi)
    app.router.add_get("/api/type-chart", api_type_chart)
    return app



async def api_tournament_winners(request):
    """Get tournament winners grouped by user, with battle team."""
    from database.connection import get_db
    pool = await get_db()
    import config

    # Get all tournament titles
    rows = await pool.fetch("""
        SELECT ut.title_id, ut.unlocked_at, ut.user_id,
               u.display_name, u.username
        FROM user_titles ut
        JOIN users u ON ut.user_id = u.user_id
        WHERE ut.title_id LIKE 'tournament%'
        ORDER BY ut.unlocked_at DESC
    """)

    # Group by user
    seen = {}
    for r in rows:
        uid = r["user_id"]
        title_info = config.TOURNAMENT_TITLES.get(r["title_id"])
        if not title_info:
            continue
        title_entry = {
            "title_id": r["title_id"],
            "title_name": title_info[0],
            "title_emoji": title_info[1],
            "title_desc": title_info[2],
            "unlocked_at": r["unlocked_at"].isoformat() if r["unlocked_at"] else None,
        }
        if uid not in seen:
            seen[uid] = {
                "user_id": uid,
                "display_name": r["display_name"],
                "username": r["username"],
                "titles": [],
                "team": [],
            }
        seen[uid]["titles"].append(title_entry)

    # Fetch battle teams for each winner
    for uid, data in seen.items():
        team_rows = await pool.fetch("""
            SELECT bt.slot, pm.name_ko, pm.emoji, up.is_shiny
            FROM battle_teams bt
            JOIN user_pokemon up ON bt.pokemon_instance_id = up.id
            JOIN pokemon_master pm ON up.pokemon_id = pm.id
            WHERE bt.user_id = $1
            ORDER BY bt.slot
        """, uid)
        data["team"] = [{"slot": t["slot"], "name": t["name_ko"], "emoji": t["emoji"], "shiny": bool(t["is_shiny"])} for t in team_rows]

    return pg_json_response(list(seen.values()))

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
