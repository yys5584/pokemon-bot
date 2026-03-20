"""Dashboard web server using aiohttp."""

import asyncio
import hashlib
import hmac
import json
import logging
import math
import os
import secrets
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from aiohttp import web
from asyncpg import InterfaceError

import config

from database import queries, stats_queries
from database import battle_queries as bq


# ============================================================
# Rate Limiting (IP-based)
# ============================================================
from collections import defaultdict

_rate_buckets: dict[str, list[float]] = defaultdict(list)  # ip -> [timestamps]
_auth_buckets: dict[str, list[float]] = defaultdict(list)  # ip -> [timestamps]

# General API: 60 req/min per IP
RATE_LIMIT = 60
RATE_WINDOW = 60
# Auth endpoint: 5 req/min per IP
AUTH_RATE_LIMIT = 5
AUTH_RATE_WINDOW = 60
# Cleanup: every 5 minutes, purge old entries
_rate_last_cleanup = 0.0


def _check_rate(ip: str, bucket: dict, limit: int, window: int) -> bool:
    """Returns True if allowed, False if rate-limited."""
    now = time.time()
    timestamps = bucket[ip]
    # Remove old entries
    cutoff = now - window
    bucket[ip] = [t for t in timestamps if t > cutoff]
    if len(bucket[ip]) >= limit:
        return False
    bucket[ip].append(now)
    return True


def _cleanup_rate_buckets():
    """Periodically remove stale IPs from rate buckets."""
    global _rate_last_cleanup
    now = time.time()
    if now - _rate_last_cleanup < 300:
        return
    _rate_last_cleanup = now
    cutoff = now - max(RATE_WINDOW, AUTH_RATE_WINDOW)
    for bucket in (_rate_buckets, _auth_buckets):
        stale = [ip for ip, ts in bucket.items() if not ts or ts[-1] < cutoff]
        for ip in stale:
            del bucket[ip]


@web.middleware
async def rate_limit_middleware(request, handler):
    """Global rate limiter middleware."""
    _cleanup_rate_buckets()

    # Skip static files
    if request.path.startswith("/static"):
        return await handler(request)

    ip = request.headers.get("CF-Connecting-IP") or \
         request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or \
         request.remote or "unknown"

    # Stricter limit for auth endpoint
    if request.path == "/api/auth/telegram":
        if not _check_rate(ip, _auth_buckets, AUTH_RATE_LIMIT, AUTH_RATE_WINDOW):
            return web.json_response(
                {"error": "Too many requests. Try again later."}, status=429
            )

    # General API rate limit
    if request.path.startswith("/api/"):
        if not _check_rate(ip, _rate_buckets, RATE_LIMIT, RATE_WINDOW):
            return web.json_response(
                {"error": "Too many requests. Try again later."}, status=429
            )

    return await handler(request)


# ============================================================
# Session Management (DB-persisted)
# ============================================================
SESSION_MAX_AGE = 604800  # 7 days
MAX_SESSIONS = 1000  # prevent DB bloat

# LLM rate limiting: DB-persisted daily usage
LLM_DAILY_LIMIT = 3


async def _ensure_session_table():
    """Create dashboard_sessions table if not exists."""
    pool = await queries.get_db()
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_sessions (
            sid TEXT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            photo_url TEXT NOT NULL DEFAULT '',
            username TEXT NOT NULL DEFAULT '',
            created_at DOUBLE PRECISION NOT NULL
        )
    """)


async def _ensure_llm_usage_table():
    """Create llm_daily_usage table if not exists."""
    pool = await queries.get_db()
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS llm_daily_usage (
            user_id BIGINT NOT NULL,
            usage_date DATE NOT NULL DEFAULT CURRENT_DATE,
            count INT NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, usage_date)
        )
    """)


async def _ensure_analytics_table():
    """Create web_analytics table if not exists."""
    pool = await queries.get_db()
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS web_analytics (
            id SERIAL PRIMARY KEY,
            event_type TEXT NOT NULL,
            user_id BIGINT,
            page TEXT,
            duration_sec INT DEFAULT 0,
            pages_viewed INT DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    await pool.execute("CREATE INDEX IF NOT EXISTS idx_wa_created ON web_analytics(created_at)")
    await pool.execute("CREATE INDEX IF NOT EXISTS idx_wa_type ON web_analytics(event_type)")


async def _check_llm_limit(user_id: int, cost: int = 1) -> tuple[bool, int, int]:
    """Check if user can use LLM. Returns (allowed, remaining_total, bonus_remaining)."""
    pool = await queries.get_db()
    today = config.get_kst_now().date()
    count = await pool.fetchval(
        "SELECT count FROM llm_daily_usage WHERE user_id = $1 AND usage_date = $2",
        user_id, today,
    )
    count = count or 0
    free_remaining = max(0, LLM_DAILY_LIMIT - count)
    bonus = await pool.fetchval(
        "SELECT llm_bonus_quota FROM users WHERE user_id = $1", user_id
    )
    bonus = bonus or 0
    total_remaining = free_remaining + bonus
    return total_remaining >= cost, total_remaining, bonus


async def _record_llm_usage(user_id: int, cost: int = 1):
    """Record LLM usage. Uses free quota first, then bonus."""
    pool = await queries.get_db()
    today = config.get_kst_now().date()
    count = await pool.fetchval(
        "SELECT count FROM llm_daily_usage WHERE user_id = $1 AND usage_date = $2",
        user_id, today,
    )
    count = count or 0
    for _ in range(cost):
        if count < LLM_DAILY_LIMIT:
            count += 1
        else:
            await pool.execute(
                "UPDATE users SET llm_bonus_quota = llm_bonus_quota - 1 "
                "WHERE user_id = $1 AND llm_bonus_quota > 0",
                user_id,
            )
    # Upsert daily usage count
    await pool.execute("""
        INSERT INTO llm_daily_usage (user_id, usage_date, count)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id, usage_date)
        DO UPDATE SET count = $3
    """, user_id, today, count)


async def _refund_llm_usage(user_id: int, cost: int = 1):
    """Refund LLM tokens on error. Reverses _record_llm_usage."""
    pool = await queries.get_db()
    today = config.get_kst_now().date()
    count = await pool.fetchval(
        "SELECT count FROM llm_daily_usage WHERE user_id = $1 AND usage_date = $2",
        user_id, today,
    )
    count = count or 0
    refunded = 0
    for _ in range(cost):
        if count > LLM_DAILY_LIMIT:
            # Was bonus usage — refund bonus
            await pool.execute(
                "UPDATE users SET llm_bonus_quota = llm_bonus_quota + 1 WHERE user_id = $1",
                user_id,
            )
            count -= 1
            refunded += 1
        elif count > 0:
            count -= 1
            refunded += 1
    if refunded:
        await pool.execute("""
            INSERT INTO llm_daily_usage (user_id, usage_date, count)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, usage_date)
            DO UPDATE SET count = $3
        """, user_id, today, count)
    logger.info(f"Refunded {refunded} LLM tokens for user {user_id}")


def _verify_telegram_auth(data: dict) -> bool:
    """Verify Telegram Login Widget HMAC-SHA256 hash."""
    bot_token = os.getenv("BOT_TOKEN", "")
    check_hash = data.get("hash", "")
    if not check_hash or not bot_token:
        return False
    # Build data-check-string (all fields except hash, sorted alphabetically)
    fields = {k: str(v) for k, v in data.items() if k != "hash"}
    data_check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    calculated = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, check_hash):
        return False
    # Check auth_date freshness (allow 5 minutes)
    auth_date = int(data.get("auth_date", 0))
    if abs(time.time() - auth_date) > 300:
        return False
    return True


async def _get_session(request) -> dict | None:
    """Get session from cookie (DB-backed). Returns user dict or None."""
    sid = request.cookies.get("sid")
    if not sid:
        return None
    pool = await queries.get_db()
    row = await pool.fetchrow(
        "SELECT user_id, display_name, photo_url, username, created_at "
        "FROM dashboard_sessions WHERE sid = $1", sid,
    )
    if not row:
        return None
    if time.time() - row["created_at"] > SESSION_MAX_AGE:
        await pool.execute("DELETE FROM dashboard_sessions WHERE sid = $1", sid)
        return None
    return {
        "user_id": row["user_id"],
        "display_name": row["display_name"],
        "photo_url": row["photo_url"],
        "username": row["username"],
        "created": row["created_at"],
    }


# ============================================================
# Auth API Endpoints
# ============================================================

async def api_auth_telegram(request):
    """Verify Telegram Login Widget data, create session."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    if not _verify_telegram_auth(data):
        return web.json_response({"ok": False, "error": "Auth failed"}, status=401)

    user_id = int(data["id"])
    display_name = data.get("first_name", "") + (" " + data.get("last_name", "")).rstrip()

    pool = await queries.get_db()

    # Evict expired + oldest sessions if too many (prevent DB bloat)
    await pool.execute(
        "DELETE FROM dashboard_sessions WHERE created_at < $1",
        time.time() - SESSION_MAX_AGE,
    )
    cnt = await pool.fetchval("SELECT COUNT(*) FROM dashboard_sessions")
    if cnt >= MAX_SESSIONS:
        await pool.execute("""
            DELETE FROM dashboard_sessions WHERE sid IN (
                SELECT sid FROM dashboard_sessions
                ORDER BY created_at ASC LIMIT $1
            )
        """, cnt - MAX_SESSIONS + 1)

    # Create session
    sid = secrets.token_hex(32)
    await pool.execute(
        "INSERT INTO dashboard_sessions (sid, user_id, display_name, photo_url, username, created_at) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        sid, user_id, display_name.strip(),
        data.get("photo_url", ""), data.get("username", ""), time.time(),
    )

    resp = web.json_response({
        "ok": True,
        "user": {
            "user_id": user_id,
            "display_name": display_name.strip(),
            "photo_url": data.get("photo_url", ""),
        },
    })
    resp.set_cookie("sid", sid, max_age=SESSION_MAX_AGE, httponly=True, samesite="Lax", secure=True)
    return resp


async def api_auth_me(request):
    """Return current logged-in user info."""
    sess = await _get_session(request)
    if not sess:
        return web.json_response({"ok": False})
    return web.json_response({
        "ok": True,
        "user": {
            "user_id": sess["user_id"],
            "display_name": sess["display_name"],
            "photo_url": sess.get("photo_url", ""),
            "is_admin": sess["user_id"] in config.ADMIN_IDS,
        },
    })


async def api_auth_logout(request):
    """Destroy session."""
    sid = request.cookies.get("sid")
    if sid:
        pool = await queries.get_db()
        await pool.execute("DELETE FROM dashboard_sessions WHERE sid = $1", sid)
    resp = web.json_response({"ok": True})
    resp.del_cookie("sid")
    return resp


# ============================================================
# Web Emoji + JSON Encoding Utilities
# ============================================================

logger = logging.getLogger(__name__)

# Map Telegram custom emoji icon keys to unicode emoji for web display
_ICON_TO_UNICODE = {
    # UI icons
    "champion_first": "👑", "champion": "🏆",
    "crystal": "💎", "skull": "💀", "crown": "👑",
    # Pokemon character icons → unicode
    "caterpie": "🐛", "rattata": "🐭", "pikachu": "⚡",
    "charmander": "🔥", "bulbasaur": "🌿", "squirtle": "💧",
    "mew": "🌟", "chikorita": "🍃", "bellsprout": "🌱",
    "eevee": "🦊", "victini": "✌️", "dratini": "🐉",
    "mankey": "🐵", "zubat": "🦇", "venonat": "🌙",
    "meowth": "🐱", "jigglypuff": "🎤", "abra": "🔮",
    "articuno": "❄️", "snorlax": "😴", "moltres": "🔥",
    "psyduck": "🦆",
}


import re as _re

_TG_EMOJI_RE = _re.compile(r"<tg-emoji[^>]*>([^<]*)</tg-emoji>")


def _web_emoji(icon_key: str) -> str:
    """Convert icon key to unicode emoji for web.

    Handles three cases:
    1. Known icon key (e.g. "pikachu") → mapped unicode emoji
    2. Raw <tg-emoji> HTML tag → extract fallback text inside (supports multiple)
    3. Already a unicode emoji → return as-is
    """
    if not icon_key:
        return ""
    # Strip Telegram custom emoji HTML tags → use fallback text
    if "<tg-emoji" in icon_key:
        return _TG_EMOJI_RE.sub(r"\1", icon_key)
    return _ICON_TO_UNICODE.get(icon_key, icon_key)


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


# ============================================================
# Public API Handlers
# ============================================================

async def api_overview(request):
    total = await stats_queries.get_total_stats()
    today = await stats_queries.get_today_stats()
    return pg_json_response({**total, **today})


async def api_chats(request):
    rooms = await stats_queries.get_all_chat_rooms()
    # Hide private chats (no title) and small rooms (< 10 members)
    rooms = [r for r in rooms if r.get("chat_title") and r.get("member_count", 0) >= 10]
    return pg_json_response(rooms)


async def api_users(request):
    users = await stats_queries.get_user_rankings(20)
    for u in users:
        if u.get("title_emoji"):
            u["title_emoji"] = _web_emoji(u["title_emoji"])
        if u.get("display_name"):
            u["display_name"] = _web_emoji(u["display_name"])
    return pg_json_response(users)


async def api_spawns_recent(request):
    spawns = await stats_queries.get_recent_spawns_global(50)
    return pg_json_response(spawns)


async def api_pokemon_stats(request):
    stats = await stats_queries.get_top_pokemon_caught(20)
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
    ranking = await bq.get_battle_ranking_multi(100)
    for r in ranking:
        if r.get("title_emoji"):
            r["title_emoji"] = _web_emoji(r["title_emoji"])
    return pg_json_response(ranking)


async def api_ranked_season(request):
    """Get current ranked season info + ranking."""
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
    from database.connection import get_db
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


# ============================================================
# Board (Community) — 게시판
# ============================================================

async def _ensure_board_tables():
    """Create board tables if not exists."""
    pool = await queries.get_db()
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS board_posts (
            id SERIAL PRIMARY KEY,
            board_type TEXT NOT NULL DEFAULT 'community',
            user_id BIGINT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            tag TEXT DEFAULT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            image_filename TEXT DEFAULT NULL,
            view_count INTEGER NOT NULL DEFAULT 0,
            like_count INTEGER NOT NULL DEFAULT 0,
            comment_count INTEGER NOT NULL DEFAULT 0,
            is_pinned INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await pool.execute(
        "CREATE INDEX IF NOT EXISTS idx_board_posts_board "
        "ON board_posts(board_type, created_at DESC)"
    )
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS board_comments (
            id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL REFERENCES board_posts(id),
            user_id BIGINT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await pool.execute(
        "CREATE INDEX IF NOT EXISTS idx_board_comments_post "
        "ON board_comments(post_id)"
    )
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS board_likes (
            user_id BIGINT NOT NULL,
            post_id INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, post_id)
        )
    """)


BOARD_PAGE_SIZE = 20
BOARD_UPLOAD_DIR = Path(__file__).parent.parent / "uploads" / "board"


def _board_time_ago(dt) -> str:
    """Convert datetime to Korean relative time string."""
    now = config.get_kst_now()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=config.KST)
    diff = now - dt
    secs = int(diff.total_seconds())
    if secs < 60:
        return "방금 전"
    if secs < 3600:
        return f"{secs // 60}분 전"
    if secs < 86400:
        return f"{secs // 3600}시간 전"
    if secs < 604800:
        return f"{secs // 86400}일 전"
    return dt.strftime("%m.%d")


async def api_board_posts(request):
    """GET /api/board/posts — list posts."""
    board_type = request.query.get("board_type", "notice")
    tag = request.query.get("tag", "")
    page = max(1, int(request.query.get("page", "1")))
    offset = (page - 1) * BOARD_PAGE_SIZE

    pool = await queries.get_db()

    where = "WHERE is_active = 1 AND board_type = $1"
    params: list = [board_type]
    if tag:
        where += " AND tag = $2"
        params.append(tag)

    total = await pool.fetchval(
        f"SELECT COUNT(*) FROM board_posts {where}", *params
    )

    # pinned first, then newest
    idx = len(params) + 1
    rows = await pool.fetch(
        f"SELECT id, board_type, tag, title, display_name, image_filename, "
        f"view_count, like_count, comment_count, is_pinned, created_at "
        f"FROM board_posts {where} "
        f"ORDER BY is_pinned DESC, created_at DESC "
        f"LIMIT ${idx} OFFSET ${idx + 1}",
        *params, BOARD_PAGE_SIZE, offset,
    )

    posts = []
    for r in rows:
        posts.append({
            "id": r["id"],
            "board_type": r["board_type"],
            "tag": r["tag"],
            "title": r["title"],
            "display_name": r["display_name"],
            "has_image": bool(r["image_filename"]),
            "view_count": r["view_count"],
            "like_count": r["like_count"],
            "comment_count": r["comment_count"],
            "is_pinned": r["is_pinned"],
            "time_ago": _board_time_ago(r["created_at"]),
            "created_at": r["created_at"].isoformat(),
        })

    return web.json_response({
        "total": total, "page": page,
        "total_pages": math.ceil(total / BOARD_PAGE_SIZE) if total else 1,
        "posts": posts,
    })


async def api_board_post_detail(request):
    """GET /api/board/posts/{id} — post detail + comments."""
    post_id = int(request.match_info["id"])
    pool = await queries.get_db()

    row = await pool.fetchrow(
        "SELECT * FROM board_posts WHERE id = $1 AND is_active = 1", post_id
    )
    if not row:
        return web.json_response({"error": "Not found"}, status=404)

    # Increment view count
    await pool.execute(
        "UPDATE board_posts SET view_count = view_count + 1 WHERE id = $1", post_id
    )

    # Comments
    comments_rows = await pool.fetch(
        "SELECT id, user_id, display_name, content, created_at "
        "FROM board_comments WHERE post_id = $1 AND is_active = 1 "
        "ORDER BY created_at ASC", post_id
    )
    comments = [{
        "id": c["id"], "user_id": c["user_id"],
        "display_name": c["display_name"], "content": c["content"],
        "time_ago": _board_time_ago(c["created_at"]),
        "created_at": c["created_at"].isoformat(),
    } for c in comments_rows]

    # Check if current user liked
    liked = False
    sess = await _get_session(request)
    if sess:
        like_row = await pool.fetchval(
            "SELECT 1 FROM board_likes WHERE user_id = $1 AND post_id = $2",
            sess["user_id"], post_id,
        )
        liked = bool(like_row)

    post = {
        "id": row["id"], "board_type": row["board_type"],
        "tag": row["tag"], "title": row["title"],
        "user_id": row["user_id"], "display_name": row["display_name"],
        "content": row["content"],
        "image_filename": row["image_filename"],
        "view_count": row["view_count"] + 1,
        "like_count": row["like_count"],
        "comment_count": row["comment_count"],
        "is_pinned": row["is_pinned"],
        "time_ago": _board_time_ago(row["created_at"]),
        "created_at": row["created_at"].isoformat(),
    }

    return web.json_response({"post": post, "comments": comments, "liked": liked})


async def api_board_post_create(request):
    """POST /api/board/posts — create a post."""
    from dashboard.api_admin import _admin_check
    sess = await _get_session(request)
    if not sess:
        return web.json_response({"error": "Login required"}, status=401)

    # Parse multipart form
    try:
        reader = await request.multipart()
    except Exception:
        return web.json_response({"error": "Invalid form data"}, status=400)

    board_type = "community"
    tag = None
    title = ""
    content = ""
    image_data = None
    image_ext = ""

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
        elif part.name == "image":
            if part.filename:
                image_ext = Path(part.filename).suffix.lower()
                if image_ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    return web.json_response(
                        {"error": "Image must be jpg/png/gif/webp"}, status=400
                    )
                image_data = await part.read(chunk_size=5 * 1024 * 1024 + 1)
                if len(image_data) > 5 * 1024 * 1024:
                    return web.json_response(
                        {"error": "Image too large (max 5MB)"}, status=400
                    )

    # Validate board_type
    if board_type not in ("notice", "community"):
        return web.json_response({"error": "Invalid board_type"}, status=400)

    # Notice: admin only
    if board_type == "notice":
        admin = await _admin_check(request)
        if not admin:
            return web.json_response({"error": "Admin only"}, status=403)

    # Validate lengths
    if len(title) < 2 or len(title) > 80:
        return web.json_response({"error": "제목은 2~80자"}, status=400)
    if len(content) < 5 or len(content) > 5000:
        return web.json_response({"error": "내용은 5~5000자"}, status=400)

    pool = await queries.get_db()

    # Insert post
    post_id = await pool.fetchval(
        "INSERT INTO board_posts (board_type, user_id, display_name, tag, title, content) "
        "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
        board_type, sess["user_id"], sess["display_name"], tag, title, content,
    )

    # Save image if provided
    image_filename = None
    if image_data:
        BOARD_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        image_filename = f"{post_id}_{ts}{image_ext}"
        filepath = BOARD_UPLOAD_DIR / image_filename

        # Try to resize with PIL, fallback to raw save
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(image_data))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            max_w = 1280
            if img.width > max_w:
                ratio = max_w / img.width
                img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            filepath = filepath.with_suffix(".jpg")
            image_filename = filepath.name
            with open(filepath, "wb") as f:
                f.write(buf.getvalue())
        except ImportError:
            # No PIL — save raw
            with open(filepath, "wb") as f:
                f.write(image_data)

        await pool.execute(
            "UPDATE board_posts SET image_filename = $1 WHERE id = $2",
            image_filename, post_id,
        )

    return web.json_response({"ok": True, "id": post_id})


async def api_board_post_delete(request):
    """DELETE /api/board/posts/{id}."""
    sess = await _get_session(request)
    if not sess:
        return web.json_response({"error": "Login required"}, status=401)

    post_id = int(request.match_info["id"])
    pool = await queries.get_db()

    row = await pool.fetchrow(
        "SELECT user_id FROM board_posts WHERE id = $1 AND is_active = 1", post_id
    )
    if not row:
        return web.json_response({"error": "Not found"}, status=404)

    # Owner or admin
    is_admin = sess["user_id"] in config.ADMIN_IDS
    if row["user_id"] != sess["user_id"] and not is_admin:
        return web.json_response({"error": "Permission denied"}, status=403)

    await pool.execute(
        "UPDATE board_posts SET is_active = 0 WHERE id = $1", post_id
    )
    return web.json_response({"ok": True})


async def api_board_post_pin(request):
    """POST /api/board/posts/{id}/pin — toggle pin (admin only)."""
    from dashboard.api_admin import _admin_check
    admin = await _admin_check(request)
    if not admin:
        return web.json_response({"error": "Admin only"}, status=403)

    post_id = int(request.match_info["id"])
    pool = await queries.get_db()

    current = await pool.fetchval(
        "SELECT is_pinned FROM board_posts WHERE id = $1 AND is_active = 1", post_id
    )
    if current is None:
        return web.json_response({"error": "Not found"}, status=404)

    new_val = 0 if current else 1
    await pool.execute(
        "UPDATE board_posts SET is_pinned = $1 WHERE id = $2", new_val, post_id
    )
    return web.json_response({"ok": True, "is_pinned": new_val})


async def api_board_post_like(request):
    """POST /api/board/posts/{id}/like — toggle like."""
    sess = await _get_session(request)
    if not sess:
        return web.json_response({"error": "Login required"}, status=401)

    post_id = int(request.match_info["id"])
    pool = await queries.get_db()

    exists = await pool.fetchval(
        "SELECT 1 FROM board_likes WHERE user_id = $1 AND post_id = $2",
        sess["user_id"], post_id,
    )

    if exists:
        await pool.execute(
            "DELETE FROM board_likes WHERE user_id = $1 AND post_id = $2",
            sess["user_id"], post_id,
        )
        await pool.execute(
            "UPDATE board_posts SET like_count = GREATEST(0, like_count - 1) WHERE id = $1",
            post_id,
        )
        liked = False
    else:
        await pool.execute(
            "INSERT INTO board_likes (user_id, post_id) VALUES ($1, $2) "
            "ON CONFLICT DO NOTHING",
            sess["user_id"], post_id,
        )
        await pool.execute(
            "UPDATE board_posts SET like_count = like_count + 1 WHERE id = $1",
            post_id,
        )
        liked = True

    new_count = await pool.fetchval(
        "SELECT like_count FROM board_posts WHERE id = $1", post_id
    )
    return web.json_response({"ok": True, "liked": liked, "like_count": new_count or 0})


async def api_board_comment_create(request):
    """POST /api/board/posts/{id}/comments — add comment."""
    sess = await _get_session(request)
    if not sess:
        return web.json_response({"error": "Login required"}, status=401)

    post_id = int(request.match_info["id"])
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    content = (body.get("content") or "").strip()
    if len(content) < 1 or len(content) > 500:
        return web.json_response({"error": "댓글은 1~500자"}, status=400)

    pool = await queries.get_db()

    # Check post exists
    post_exists = await pool.fetchval(
        "SELECT 1 FROM board_posts WHERE id = $1 AND is_active = 1", post_id
    )
    if not post_exists:
        return web.json_response({"error": "Post not found"}, status=404)

    comment_id = await pool.fetchval(
        "INSERT INTO board_comments (post_id, user_id, display_name, content) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        post_id, sess["user_id"], sess["display_name"], content,
    )
    await pool.execute(
        "UPDATE board_posts SET comment_count = comment_count + 1 WHERE id = $1",
        post_id,
    )

    return web.json_response({"ok": True, "id": comment_id})


async def api_board_comment_delete(request):
    """DELETE /api/board/comments/{id}."""
    sess = await _get_session(request)
    if not sess:
        return web.json_response({"error": "Login required"}, status=401)

    comment_id = int(request.match_info["id"])
    pool = await queries.get_db()

    row = await pool.fetchrow(
        "SELECT user_id, post_id FROM board_comments "
        "WHERE id = $1 AND is_active = 1", comment_id
    )
    if not row:
        return web.json_response({"error": "Not found"}, status=404)

    is_admin = sess["user_id"] in config.ADMIN_IDS
    if row["user_id"] != sess["user_id"] and not is_admin:
        return web.json_response({"error": "Permission denied"}, status=403)

    await pool.execute(
        "UPDATE board_comments SET is_active = 0 WHERE id = $1", comment_id
    )
    await pool.execute(
        "UPDATE board_posts SET comment_count = GREATEST(0, comment_count - 1) "
        "WHERE id = $1", row["post_id"],
    )
    return web.json_response({"ok": True})


async def api_board_image(request):
    """GET /uploads/board/{filename} — serve uploaded image."""
    filename = request.match_info["filename"]
    # Sanitize filename
    if "/" in filename or "\\" in filename or ".." in filename:
        return web.json_response({"error": "Invalid filename"}, status=400)
    filepath = BOARD_UPLOAD_DIR / filename
    if not filepath.exists():
        return web.json_response({"error": "Not found"}, status=404)
    return web.FileResponse(filepath)


# --- Page Handler ---

async def index(request):
    html_path = TEMPLATE_DIR / "index.html"
    return web.FileResponse(html_path)


async def serve_markdown_doc(request):
    """Serve a markdown file from docs/ as rendered HTML."""
    name = request.match_info["name"]
    # Sanitize: only allow alphanumeric, dash, underscore
    import re as _re
    if not _re.match(r'^[\w-]+$', name):
        return web.Response(text="Not found", status=404)
    doc_path = Path(__file__).parent.parent / "docs" / f"{name}.md"
    if not doc_path.exists():
        return web.Response(text="Not found", status=404)
    content = doc_path.read_text(encoding="utf-8")
    # Escape for safe JS embedding
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


# --- Server Setup ---

def create_app() -> web.Application:
    app = web.Application(middlewares=[rate_limit_middleware])
    app.router.add_get("/", index)
    # Static files (type icons etc.)
    static_dir = TEMPLATE_DIR.parent / "static"
    if static_dir.exists():
        app.router.add_static("/static", static_dir, show_index=False)
    # Pokemon sprites
    sprite_dir = Path(__file__).resolve().parent.parent / "assets" / "pokemon"
    if sprite_dir.exists():
        app.router.add_static("/sprites", sprite_dir, show_index=False)
    # Camp assets (map images etc.)
    camp_dir = Path(__file__).resolve().parent.parent / "assets" / "camp"
    if camp_dir.exists():
        app.router.add_static("/camp-assets", camp_dir, show_index=False)
    # Auth
    app.router.add_post("/api/auth/telegram", api_auth_telegram)
    app.router.add_get("/api/auth/me", api_auth_me)
    app.router.add_post("/api/auth/logout", api_auth_logout)

    # --- Register domain-specific route modules ---
    from dashboard.api_my import setup_routes as setup_my_routes
    from dashboard.api_advisor import setup_routes as setup_advisor_routes
    from dashboard.api_admin import setup_routes as setup_admin_routes
    from dashboard.api_analytics import setup_routes as setup_analytics_routes
    from dashboard.api_market import setup_routes as setup_market_routes

    setup_my_routes(app)
    setup_advisor_routes(app)
    setup_admin_routes(app)
    setup_analytics_routes(app)
    setup_market_routes(app)

    # Public APIs
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
    # Board (Community)
    app.router.add_get("/api/board/posts", api_board_posts)
    app.router.add_get("/api/board/posts/{id}", api_board_post_detail)
    app.router.add_post("/api/board/posts", api_board_post_create)
    app.router.add_delete("/api/board/posts/{id}", api_board_post_delete)
    app.router.add_post("/api/board/posts/{id}/pin", api_board_post_pin)
    app.router.add_post("/api/board/posts/{id}/like", api_board_post_like)
    app.router.add_post("/api/board/posts/{id}/comments", api_board_comment_create)
    app.router.add_delete("/api/board/comments/{id}", api_board_comment_delete)
    app.router.add_get("/uploads/board/{filename}", api_board_image)
    # Markdown doc viewer
    app.router.add_get("/docs/{name}", serve_markdown_doc)
    # SPA catch-all: serve index.html for all non-API, non-static paths
    SPA_PAGES = {"/channels", "/patchnotes", "/board", "/battle", "/tier", "/types", "/guide", "/stats", "/mypokemon", "/pokedex", "/ai", "/admin", "/market", "/camp"}
    for p in SPA_PAGES:
        app.router.add_get(p, index)
    # Board deep-link sub-routes
    app.router.add_get("/board/post/{id}", index)
    app.router.add_get("/board/{sub}", index)
    # Admin deep-link sub-routes
    app.router.add_get("/admin/{sub}", index)
    return app


async def start_dashboard():
    """Start the dashboard web server in the background."""
    await _ensure_session_table()
    await _ensure_llm_usage_table()
    await _ensure_analytics_table()
    await _ensure_board_tables()
    port = int(os.getenv("DASHBOARD_PORT", "8080"))
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Dashboard running at http://localhost:{port}")
    return runner
