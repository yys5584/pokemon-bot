"""Dashboard API — Public endpoints (overview, rankings, KPI, type chart, etc.)."""

import asyncio
import logging

from aiohttp import web

import config
from database import queries, stats_queries
from database import battle_queries as bq

logger = logging.getLogger(__name__)


async def api_overview(request):
    total = await stats_queries.get_total_stats()
    today = await stats_queries.get_today_stats()
    from dashboard.server import pg_json_response
    return pg_json_response({**total, **today})


async def api_chats(request):
    rooms = await stats_queries.get_all_chat_rooms()
    # Hide private chats (no title) and small rooms (< 10 members)
    rooms = [r for r in rooms if r.get("chat_title") and r.get("member_count", 0) >= 10]
    from dashboard.server import pg_json_response
    return pg_json_response(rooms)


async def api_users(request):
    from dashboard.server import pg_json_response, _web_emoji
    users = await stats_queries.get_user_rankings(20)
    for u in users:
        if u.get("title_emoji"):
            u["title_emoji"] = _web_emoji(u["title_emoji"])
        if u.get("display_name"):
            u["display_name"] = _web_emoji(u["display_name"])
    return pg_json_response(users)


async def api_spawns_recent(request):
    spawns = await stats_queries.get_recent_spawns_global(50)
    from dashboard.server import pg_json_response
    return pg_json_response(spawns)


async def api_pokemon_stats(request):
    stats = await stats_queries.get_top_pokemon_caught(20)
    from dashboard.server import pg_json_response
    return pg_json_response(stats)


async def api_events(request):
    await queries.cleanup_expired_events()
    events = await queries.get_active_events()
    from dashboard.server import pg_json_response
    return pg_json_response(events)


async def api_fun_kpis(request):
    """Consolidated fun KPI endpoint — parallel queries."""
    from dashboard.server import pg_json_response, _web_emoji
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
        stats_queries.get_global_catch_rate(),
        stats_queries.get_total_master_balls_used(),
        stats_queries.get_longest_streak_user(),
        stats_queries.get_rare_pokemon_holders(20),
        stats_queries.get_escape_masters(5),
        stats_queries.get_night_owls(5),
        stats_queries.get_masterball_rich(5),
        stats_queries.get_pokeball_addicts(5),
        stats_queries.get_user_catch_rates(10),
        stats_queries.get_trade_kings(5),
        stats_queries.get_most_escaped_pokemon(5),
        stats_queries.get_love_leaders(5),
        stats_queries.get_shiny_holders(20),
    )

    # Split catch rates into lucky (top) and unlucky (bottom)
    lucky_users = user_catch_rates[:5] if user_catch_rates else []
    unlucky_users = sorted(user_catch_rates, key=lambda x: x["catch_rate"])[:5] if user_catch_rates else []

    # Strip <tg-emoji> from all display_name fields in KPI lists
    for lst in (shiny_holders, rare_holders, escape_masters, night_owls,
                masterball_rich, pokeball_addicts, lucky_users, unlucky_users,
                trade_kings, love_leaders):
        if lst:
            for item in lst:
                if item.get("display_name"):
                    item["display_name"] = _web_emoji(item["display_name"])

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


async def api_iv_ranking(request):
    """Top 10 users by highest single-pokemon IV total."""
    from dashboard.server import pg_json_response, _web_emoji
    import config
    pool = await queries.get_db()
    rows = await pool.fetch("""
        SELECT up.user_id, u.display_name,
               pm.name_ko, pm.emoji, up.is_shiny,
               (COALESCE(up.iv_hp,0) + COALESCE(up.iv_atk,0) + COALESCE(up.iv_def,0)
                + COALESCE(up.iv_spa,0) + COALESCE(up.iv_spdef,0) + COALESCE(up.iv_spd,0)) as iv_total
        FROM user_pokemon up
        JOIN users u ON up.user_id = u.user_id
        JOIN pokemon_master pm ON up.pokemon_id = pm.id
        WHERE up.iv_hp IS NOT NULL AND up.is_active = 1
        ORDER BY iv_total DESC
        LIMIT 10
    """)
    result = [dict(r) for r in rows]
    # Add grade + strip tg-emoji from display fields
    for r in result:
        grade, _ = config.get_iv_grade(r["iv_total"])
        r["iv_grade"] = grade
        if r.get("display_name"):
            r["display_name"] = _web_emoji(r["display_name"])
        if r.get("emoji"):
            r["emoji"] = _web_emoji(r["emoji"])
    return pg_json_response(result)


# --- Battle APIs ---

async def api_battle_ranking(request):
    from dashboard.server import pg_json_response, _web_emoji
    ranking = await bq.get_battle_ranking_multi(100)
    for r in ranking:
        if r.get("title_emoji"):
            r["title_emoji"] = _web_emoji(r["title_emoji"])
    return pg_json_response(ranking)


async def api_ranked_season(request):
    """Get current ranked season info + ranking."""
    from dashboard.server import pg_json_response, _web_emoji
    from database import ranked_queries as rq
    pool = await queries.get_db()

    season = await rq.get_current_season()
    if not season:
        return pg_json_response({"season": None, "ranking": []})

    season_id = season["season_id"]

    from services.ranked_service import tier_display, tier_display_full

    rule_info = config.WEEKLY_RULES.get(season["weekly_rule"], {})

    ranking = await rq.get_ranked_ranking(season_id, limit=100)
    for r in ranking:
        r["tier_display"] = tier_display(r["tier"])
        if r.get("title_emoji"):
            r["title_emoji"] = _web_emoji(r["title_emoji"])

        # 디비전 정보 추가
        placement_done = r.get("placement_done", True)
        if not placement_done:
            r["division_display"] = f"🎯 배치중 ({r.get('placement_games', 0)}/5)"
        else:
            div = config.get_division_info(r["rp"])
            r["division_display"] = config.tier_division_display(
                div[0], div[1], div[2],
                placement_done=True, total_rp=r["rp"])
            r["division"] = div[1]
            r["division_rp"] = div[2]

        # MMR 포함 (대시보드에서는 표시)
        r["mmr"] = r.get("mmr", 1200)

    # --- Tier distribution ---
    try:
        all_recs = await pool.fetch("""
            SELECT rp, placement_done, placement_games
            FROM season_records WHERE season_id = $1
        """, season_id)
    except Exception:
        all_recs = []

    tier_distribution = {}
    total_players = len(all_recs)
    for rec in all_recs:
        pd = rec.get("placement_done", True)
        if not pd:
            pg = rec.get("placement_games", 0)
            key = "placement" if pg and pg > 0 else "unranked"
        else:
            div_info = config.get_division_info(rec["rp"])
            key = div_info[0]
        tier_distribution[key] = tier_distribution.get(key, 0) + 1

    # Challenger: top N masters
    master_count = tier_distribution.get("master", 0)
    if master_count > 0:
        challenger_n = min(master_count, config.CHALLENGER_TOP_N)
        # Count how many in ranking have tier="challenger"
        ch_count = sum(1 for r in ranking if r.get("tier") == "challenger")
        if ch_count > 0:
            tier_distribution["challenger"] = ch_count
            tier_distribution["master"] = max(0, master_count - ch_count)

    return pg_json_response({
        "season": {
            "season_id": season_id,
            "weekly_rule": season["weekly_rule"],
            "weekly_rule_name": rule_info.get("name", ""),
            "weekly_rule_desc": rule_info.get("desc", ""),
            "starts_at": str(season["starts_at"]),
            "ends_at": str(season["ends_at"]),
        },
        "ranking": ranking,
        "tier_distribution": tier_distribution,
        "total_players": total_players,
    })


async def api_battle_recent(request):
    """Get recent battle records."""
    from dashboard.server import pg_json_response
    pool = await queries.get_db()
    rows = await pool.fetch("""
        SELECT br.id, br.winner_id, br.loser_id, br.winner_remaining,
               br.total_rounds, br.bp_earned, br.created_at,
               w.display_name as winner_name, l.display_name as loser_name
        FROM battle_records br
        JOIN users w ON br.winner_id = w.user_id
        JOIN users l ON br.loser_id = l.user_id
        ORDER BY br.created_at DESC LIMIT 15
    """)
    return pg_json_response([dict(r) for r in rows])


async def api_battle_tiers(request):
    """Build tier list data for ALL pokemon (final evolution only)."""
    from dashboard.server import pg_json_response
    from database.connection import get_db
    import config
    from utils.battle_calc import calc_battle_stats, EVO_STAGE_MAP, get_normalized_base_stats
    from models.pokemon_skills import POKEMON_SKILLS, SKILL_EFFECTS, get_skill_display, get_max_skill_power
    from models.pokemon_base_stats import POKEMON_BASE_STATS

    pool = await queries.get_db()
    rows = await pool.fetch("""
        SELECT id, name_ko, emoji, rarity, pokemon_type, stat_type, evolves_to
        FROM pokemon_master
        ORDER BY id
    """)

    scored = []
    for r in rows:
        base = get_normalized_base_stats(r["id"])
        evo_stage = 3 if base else EVO_STAGE_MAP.get(r["id"], 3)
        stats = calc_battle_stats(
            r["rarity"], r["stat_type"], 5,
            evo_stage=evo_stage,
            **(base or {}),
        )
        from models.pokemon_skills import get_max_skill_power
        _skill_pow = get_max_skill_power(r["id"])

        # Best offensive stat (physical or special)
        best_atk = max(stats["atk"], stats["spa"])
        # Best defensive stat (average of physical + special)
        eff_def = (stats["def"] + stats["spdef"]) / 2

        eff_atk = best_atk * (1 + config.BATTLE_SKILL_RATE * _skill_pow)
        eff_tank = stats["hp"] * (1 + eff_def * 0.003)
        power = eff_atk * eff_tank / 1000

        # Dual type from base stats data
        bs_entry = POKEMON_BASE_STATS.get(r["id"])
        types = bs_entry[6] if bs_entry else [r["pokemon_type"]]
        type1 = types[0] if types else r["pokemon_type"]
        type2 = types[1] if len(types) > 1 else None

        stat_ko = {"offensive": "공격", "defensive": "방어", "balanced": "균형", "speedy": "속도"}.get(r["stat_type"], r["stat_type"])

        # Skill effect info for tooltip
        raw_skills = POKEMON_SKILLS.get(r["id"])
        skill_effects_list = []
        if raw_skills:
            sk_list = [raw_skills] if isinstance(raw_skills, tuple) else raw_skills
            for sn, sp in sk_list:
                eff = SKILL_EFFECTS.get(sn)
                if eff:
                    skill_effects_list.append({"name": sn, "power": sp, **eff})
                else:
                    skill_effects_list.append({"name": sn, "power": sp, "type": "normal"})

        # 격턴 스킵 (나태/슬로우스타트)
        is_truant = r["id"] in config.TRUANT_POKEMON
        if is_truant:
            skill_effects_list.append({"name": "슬로우스타트", "power": 0, "type": "truant"})

        scored.append({
            "id": r["id"], "name": r["name_ko"], "emoji": r["emoji"],
            "rarity": r["rarity"], "evo_stage": evo_stage,
            "type1": type1, "type2": type2,
            "stat_ko": stat_ko, "power": round(power, 1),
            "skill_name": get_skill_display(r["id"]), "skill_power": _skill_pow,
            "skill_effects": skill_effects_list,
            "truant": is_truant,
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
    from dashboard.server import pg_json_response
    pool = await queries.get_db()
    now = config.get_kst_now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    one_hour_ago = now - __import__('datetime').timedelta(hours=1)

    dau, dau_hist, retention, economy, top_channels, new_today, active_1h = await asyncio.gather(
        stats_queries.get_dau(),
        stats_queries.get_dau_history(7),
        stats_queries.get_retention_d1(),
        stats_queries.get_economy_health(),
        stats_queries.get_active_chat_rooms_top(5),
        pool.fetchrow("SELECT COUNT(*) as cnt FROM users WHERE registered_at >= $1", today),
        pool.fetchrow("SELECT COUNT(*) as cnt FROM users WHERE last_active_at >= $1", one_hour_ago),
    )
    return pg_json_response({
        "dau": dau,
        "dau_history": dau_hist,
        "retention": retention,
        "economy": economy,
        "top_channels": top_channels,
        "new_today": new_today["cnt"] if new_today else 0,
        "active_1h": active_1h["cnt"] if active_1h else 0,
    })


async def api_type_chart(request):
    """Return the full 18-type effectiveness chart data."""
    from dashboard.server import pg_json_response
    import config
    types = list(config.TYPE_ADVANTAGE.keys())
    chart = {}
    for atk_type in types:
        row = {}
        for def_type in types:
            immunities = config.TYPE_IMMUNITY.get(atk_type, [])
            advantages = config.TYPE_ADVANTAGE.get(atk_type, [])
            resistances = config.TYPE_RESISTANCE.get(atk_type, [])
            if def_type in immunities:
                row[def_type] = 0
            elif def_type in advantages:
                row[def_type] = 2  # super effective
            elif def_type in resistances:
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


async def api_tournament_winners(request):
    """Get tournament winners grouped by user, with battle team."""
    from dashboard.server import pg_json_response, _web_emoji
    pool = await queries.get_db()
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
            "title_emoji": _web_emoji(title_info[1]),
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


def setup_routes(app):
    """Register public API routes."""
    app.router.add_get("/api/overview", api_overview)
    app.router.add_get("/api/chats", api_chats)
    app.router.add_get("/api/users", api_users)
    app.router.add_get("/api/spawns/recent", api_spawns_recent)
    app.router.add_get("/api/pokemon/stats", api_pokemon_stats)
    app.router.add_get("/api/events", api_events)
    app.router.add_get("/api/fun-kpis", api_fun_kpis)
    app.router.add_get("/api/iv-ranking", api_iv_ranking)
    app.router.add_get("/api/battle/ranking", api_battle_ranking)
    app.router.add_get("/api/battle/recent", api_battle_recent)
    app.router.add_get("/api/battle/tiers", api_battle_tiers)
    app.router.add_get("/api/ranked/season", api_ranked_season)
    app.router.add_get("/api/tournament/winners", api_tournament_winners)
    app.router.add_get("/api/dashboard-kpi", api_dashboard_kpi)
    app.router.add_get("/api/type-chart", api_type_chart)
