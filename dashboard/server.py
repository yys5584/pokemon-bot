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

import config
from database import queries
from database import battle_queries as bq
from utils.battle_calc import (
    calc_battle_stats, calc_power, iv_total,
    get_normalized_base_stats, EVO_STAGE_MAP, _iv_mult,
)
from models.pokemon_base_stats import POKEMON_BASE_STATS


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
# Session Management
# ============================================================
_sessions: dict[str, dict] = {}  # session_id -> {user_id, display_name, auth_date}
SESSION_MAX_AGE = 86400  # 24 hours
MAX_SESSIONS = 1000  # prevent memory bomb

# LLM rate limiting: user_id -> {date_str: count}
_llm_usage: dict[int, dict[str, int]] = {}
LLM_DAILY_LIMIT = 10


def _check_llm_limit(user_id: int) -> tuple[bool, int]:
    """Check if user can use LLM. Returns (allowed, remaining)."""
    today = datetime.now().strftime("%Y-%m-%d")
    if user_id not in _llm_usage:
        _llm_usage[user_id] = {}
    usage = _llm_usage[user_id]
    # Clean old dates
    for d in list(usage.keys()):
        if d != today:
            del usage[d]
    count = usage.get(today, 0)
    remaining = max(0, LLM_DAILY_LIMIT - count)
    return count < LLM_DAILY_LIMIT, remaining


def _record_llm_usage(user_id: int):
    """Record one LLM usage for today."""
    today = datetime.now().strftime("%Y-%m-%d")
    if user_id not in _llm_usage:
        _llm_usage[user_id] = {}
    _llm_usage[user_id][today] = _llm_usage[user_id].get(today, 0) + 1


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


def _get_session(request) -> dict | None:
    """Get session from cookie. Returns user dict or None."""
    sid = request.cookies.get("sid")
    if not sid or sid not in _sessions:
        return None
    sess = _sessions[sid]
    if time.time() - sess.get("created", 0) > SESSION_MAX_AGE:
        del _sessions[sid]
        return None
    return sess


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

    # Evict oldest sessions if too many (prevent memory bomb)
    if len(_sessions) >= MAX_SESSIONS:
        oldest = sorted(_sessions, key=lambda s: _sessions[s].get("created", 0))
        for old_sid in oldest[: len(_sessions) - MAX_SESSIONS + 1]:
            del _sessions[old_sid]

    # Create session
    sid = secrets.token_hex(32)
    _sessions[sid] = {
        "user_id": user_id,
        "display_name": display_name.strip(),
        "photo_url": data.get("photo_url", ""),
        "username": data.get("username", ""),
        "created": time.time(),
    }

    resp = web.json_response({
        "ok": True,
        "user": {
            "user_id": user_id,
            "display_name": display_name.strip(),
            "photo_url": data.get("photo_url", ""),
        },
    })
    resp.set_cookie("sid", sid, max_age=SESSION_MAX_AGE, httponly=True, samesite="Lax")
    return resp


async def api_auth_me(request):
    """Return current logged-in user info."""
    sess = _get_session(request)
    if not sess:
        return web.json_response({"ok": False})
    return web.json_response({
        "ok": True,
        "user": {
            "user_id": sess["user_id"],
            "display_name": sess["display_name"],
            "photo_url": sess.get("photo_url", ""),
        },
    })


async def api_auth_logout(request):
    """Destroy session."""
    sid = request.cookies.get("sid")
    if sid and sid in _sessions:
        del _sessions[sid]
    resp = web.json_response({"ok": True})
    resp.del_cookie("sid")
    return resp


# ============================================================
# My Pokemon API
# ============================================================

# Synergy weight presets per stat_type
_SYNERGY_WEIGHTS = {
    "offensive":  {"hp": 0.8, "atk": 2.0, "def": 0.4, "spa": 2.0, "spdef": 0.4, "spd": 1.5},
    "defensive":  {"hp": 2.0, "atk": 0.4, "def": 2.0, "spa": 0.4, "spdef": 2.0, "spd": 0.5},
    "balanced":   {"hp": 1.2, "atk": 1.2, "def": 1.0, "spa": 1.2, "spdef": 1.0, "spd": 1.2},
    "speedy":     {"hp": 0.5, "atk": 1.5, "def": 0.3, "spa": 1.5, "spdef": 0.3, "spd": 2.5},
}

_SYNERGY_LABELS = {90: "완벽", 70: "우수", 50: "보통", 0: "아쉬움"}
_SYNERGY_EMOJI = {90: "⚡", 70: "🔥", 50: "⚖️", 0: "💤"}


def _calc_synergy(stat_type: str, ivs: dict) -> tuple[int, str, str]:
    """Calculate synergy score (0-100) and grade label/emoji."""
    weights = _SYNERGY_WEIGHTS.get(stat_type, _SYNERGY_WEIGHTS["balanced"])
    iv_keys = ["hp", "atk", "def", "spa", "spdef", "spd"]
    iv_map = {"hp": "iv_hp", "atk": "iv_atk", "def": "iv_def",
              "spa": "iv_spa", "spdef": "iv_spdef", "spd": "iv_spd"}

    weighted_sum = sum(weights[k] * (ivs.get(iv_map[k]) or 0) for k in iv_keys)
    max_sum = sum(weights[k] * 31 for k in iv_keys)
    score = int(weighted_sum / max_sum * 100) if max_sum > 0 else 0

    label = "아쉬움"
    emoji = "💤"
    for threshold in sorted(_SYNERGY_LABELS.keys(), reverse=True):
        if score >= threshold:
            label = _SYNERGY_LABELS[threshold]
            emoji = _SYNERGY_EMOJI[threshold]
            break
    return score, label, emoji


async def _build_pokemon_data(rows) -> list[dict]:
    """Build full pokemon data list with stats + synergy from DB rows."""
    result = []
    for r in rows:
        pid = r["pokemon_id"]
        rarity = r["rarity"]
        stat_type = r["stat_type"]
        friendship = r["friendship"]
        evo_stage = EVO_STAGE_MAP.get(pid, 3)

        ivs = {
            "iv_hp": r.get("iv_hp"), "iv_atk": r.get("iv_atk"),
            "iv_def": r.get("iv_def"), "iv_spa": r.get("iv_spa"),
            "iv_spdef": r.get("iv_spdef"), "iv_spd": r.get("iv_spd"),
        }

        # Get normalized base stats
        base_raw = get_normalized_base_stats(pid)
        base_kw = base_raw if base_raw else {}

        # Stats WITH IV
        real_stats = calc_battle_stats(
            rarity, stat_type, friendship, evo_stage,
            ivs["iv_hp"], ivs["iv_atk"], ivs["iv_def"],
            ivs["iv_spa"], ivs["iv_spdef"], ivs["iv_spd"],
            **base_kw,
        )
        # Stats WITHOUT IV (IV_mult=1.0)
        base_stats = calc_battle_stats(
            rarity, stat_type, friendship, evo_stage,
            None, None, None, None, None, None,
            **base_kw,
        )

        real_power = calc_power(real_stats)
        base_power = calc_power(base_stats)
        iv_bonus = real_power - base_power

        iv_sum = iv_total(ivs["iv_hp"], ivs["iv_atk"], ivs["iv_def"],
                          ivs["iv_spa"], ivs["iv_spdef"], ivs["iv_spd"])
        iv_grade, _ = config.get_iv_grade(iv_sum)

        synergy_score, synergy_label, synergy_emoji = _calc_synergy(stat_type, ivs)

        # Type info from base stats
        bs_entry = POKEMON_BASE_STATS.get(pid)
        types = bs_entry[6] if bs_entry else [r.get("pokemon_type", "normal")]

        result.append({
            "id": r["id"],  # instance id
            "pokemon_id": pid,
            "name_ko": r["name_ko"],
            "emoji": r["emoji"],
            "rarity": rarity,
            "pokemon_type": types[0] if types else "normal",
            "type2": types[1] if len(types) > 1 else None,
            "stat_type": stat_type,
            "friendship": friendship,
            "is_shiny": bool(r.get("is_shiny", 0)),
            "is_favorite": bool(r.get("is_favorite", 0)),
            "evo_stage": evo_stage,
            "ivs": {k.replace("iv_", ""): (v if v is not None else 0) for k, v in ivs.items()},
            "stats": base_stats,
            "real_stats": real_stats,
            "power": base_power,
            "real_power": real_power,
            "iv_bonus": iv_bonus,
            "iv_total": iv_sum,
            "iv_grade": iv_grade,
            "synergy_score": synergy_score,
            "synergy_label": synergy_label,
            "synergy_emoji": synergy_emoji,
        })

    return result


async def api_my_pokemon(request):
    """Return all pokemon for the logged-in user with full stat data."""
    sess = _get_session(request)
    if not sess:
        return web.json_response({"error": "Unauthorized"}, status=401)

    pool = await queries.get_db()
    rows = await pool.fetch("""
        SELECT up.id, up.pokemon_id, up.friendship, up.is_shiny, up.is_favorite,
               up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd,
               pm.name_ko, pm.emoji, pm.rarity, pm.pokemon_type, pm.stat_type,
               pm.evolves_to
        FROM user_pokemon up
        JOIN pokemon_master pm ON up.pokemon_id = pm.id
        WHERE up.user_id = $1 AND up.is_active = 1
        ORDER BY up.id DESC
    """, sess["user_id"])

    data = await _build_pokemon_data(rows)
    return pg_json_response(data)


async def api_my_summary(request):
    """Return summary stats for the logged-in user."""
    sess = _get_session(request)
    if not sess:
        return web.json_response({"error": "Unauthorized"}, status=401)

    pool = await queries.get_db()
    uid = sess["user_id"]

    row = await pool.fetchrow("""
        SELECT COUNT(*) as total,
               COUNT(CASE WHEN is_shiny = 1 THEN 1 END) as shiny_count,
               COUNT(DISTINCT pokemon_id) as dex_count
        FROM user_pokemon WHERE user_id = $1 AND is_active = 1
    """, uid)

    battle_row = await pool.fetchrow("""
        SELECT battle_points, battle_wins, battle_losses, best_streak
        FROM users WHERE user_id = $1
    """, uid)

    return pg_json_response({
        "total_pokemon": row["total"],
        "shiny_count": row["shiny_count"],
        "dex_count": row["dex_count"],
        "battle_points": battle_row["battle_points"] if battle_row else 0,
        "battle_wins": battle_row["battle_wins"] if battle_row else 0,
        "battle_losses": battle_row["battle_losses"] if battle_row else 0,
        "best_streak": battle_row["best_streak"] if battle_row else 0,
    })


# ============================================================
# Team Recommendation API
# ============================================================

def _validate_team(team: list[dict]) -> bool:
    """Check legendary 1 limit + no epic species dup."""
    legendaries = [p for p in team if p["rarity"] == "legendary"]
    if len(legendaries) > 1:
        return False
    epic_species = [p["pokemon_id"] for p in team if p["rarity"] == "epic"]
    if len(epic_species) != len(set(epic_species)):
        return False
    return True


def _pick_team(candidates: list[dict], max_size: int = 6) -> list[dict]:
    """Pick top candidates respecting team composition rules."""
    team = []
    epic_species = set()
    has_legendary = False
    for p in candidates:
        if len(team) >= max_size:
            break
        if p["rarity"] == "legendary":
            if has_legendary:
                continue
            has_legendary = True
        if p["rarity"] == "epic":
            if p["pokemon_id"] in epic_species:
                continue
            epic_species.add(p["pokemon_id"])
        team.append(p)
    return team


def _recommend_power(pokemon: list[dict]) -> tuple[list[dict], str]:
    """Mode 1: Pure power — top 6 by real_power."""
    sorted_p = sorted(pokemon, key=lambda x: x["real_power"], reverse=True)
    team = _pick_team(sorted_p)
    total = sum(p["real_power"] for p in team)
    analysis = f"실전투력 TOP 6 구성입니다. 총 전투력 {total}."
    types = set(p["pokemon_type"] for p in team)
    if len(types) < 3:
        analysis += " 타입 다양성이 부족해 상성에 취약할 수 있습니다."
    return team, analysis


def _recommend_synergy(pokemon: list[dict]) -> tuple[list[dict], str]:
    """Mode 2: Best IV synergy with base stats."""
    sorted_p = sorted(pokemon, key=lambda x: (x["synergy_score"], x["real_power"]), reverse=True)
    team = _pick_team(sorted_p)
    avg_syn = sum(p["synergy_score"] for p in team) // max(len(team), 1)
    analysis = f"IV-종족값 시너지가 가장 좋은 6마리입니다. 평균 시너지 {avg_syn}점."
    low = [p for p in team if p["synergy_score"] < 50]
    if low:
        names = ", ".join(p["name_ko"] for p in low)
        analysis += f" {names}의 IV 배분이 아쉽습니다."
    return team, analysis


async def _recommend_counter(pokemon: list[dict]) -> tuple[list[dict], str]:
    """Mode 3: Counter top ranker teams."""
    ranking = await bq.get_battle_ranking(5)
    pool = await queries.get_db()

    # Collect enemy types from top ranker teams
    enemy_types = []
    for r in ranking:
        team_rows = await pool.fetch("""
            SELECT pm.pokemon_type FROM battle_teams bt
            JOIN user_pokemon up ON bt.pokemon_instance_id = up.id
            JOIN pokemon_master pm ON up.pokemon_id = pm.id
            WHERE bt.user_id = $1
        """, r["user_id"])
        for t in team_rows:
            enemy_types.append(t["pokemon_type"])

    if not enemy_types:
        return _recommend_power(pokemon)

    # Find counter types
    from collections import Counter
    type_freq = Counter(enemy_types)
    counter_scores = {}
    for ptype in config.TYPE_ADVANTAGE:
        score = sum(type_freq.get(weak, 0) for weak in config.TYPE_ADVANTAGE.get(ptype, []))
        counter_scores[ptype] = score

    # Score each pokemon by counter effectiveness
    for p in pokemon:
        p["_counter"] = counter_scores.get(p["pokemon_type"], 0) * 100 + p["real_power"]

    sorted_p = sorted(pokemon, key=lambda x: x["_counter"], reverse=True)
    team = _pick_team(sorted_p)

    # Cleanup temp field
    for p in pokemon:
        p.pop("_counter", None)

    top_enemy = type_freq.most_common(3)
    enemy_str = ", ".join(f"{config.TYPE_NAME_KO.get(t, t)}({c})" for t, c in top_enemy)
    analysis = f"상위 랭커 팀 분석: {enemy_str} 타입이 많습니다. 이에 유리한 포켓몬으로 구성했습니다."

    return team, analysis


def _recommend_balance(pokemon: list[dict]) -> tuple[list[dict], str]:
    """Mode 4: Balanced — power + synergy + type coverage."""
    # Combined score
    max_power = max((p["real_power"] for p in pokemon), default=1)
    for p in pokemon:
        p["_balance"] = (p["real_power"] / max_power * 50) + (p["synergy_score"] * 0.3)

    sorted_p = sorted(pokemon, key=lambda x: x["_balance"], reverse=True)

    # Greedy pick with type diversity bonus
    team = []
    used_types = set()
    epic_species = set()
    has_legendary = False

    for p in sorted_p:
        if len(team) >= 6:
            break
        if p["rarity"] == "legendary":
            if has_legendary:
                continue
            has_legendary = True
        if p["rarity"] == "epic" and p["pokemon_id"] in epic_species:
            continue
        # Bonus for new type
        bonus = 20 if p["pokemon_type"] not in used_types else 0
        p["_balance"] += bonus
        team.append(p)
        used_types.add(p["pokemon_type"])
        if p["rarity"] == "epic":
            epic_species.add(p["pokemon_id"])

    # Re-sort by balance score
    team.sort(key=lambda x: x["_balance"], reverse=True)

    for p in pokemon:
        p.pop("_balance", None)

    analysis = f"전투력 + 시너지 + 타입 다양성을 균형있게 고려한 추천입니다. {len(used_types)}개 타입 커버."
    return team, analysis


async def api_my_team_recommend(request):
    """AI team recommendation for the logged-in user."""
    sess = _get_session(request)
    if not sess:
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        body = await request.json()
    except Exception:
        body = {}
    mode = body.get("mode", "power")

    pool = await queries.get_db()
    rows = await pool.fetch("""
        SELECT up.id, up.pokemon_id, up.friendship, up.is_shiny, up.is_favorite,
               up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd,
               pm.name_ko, pm.emoji, pm.rarity, pm.pokemon_type, pm.stat_type,
               pm.evolves_to
        FROM user_pokemon up
        JOIN pokemon_master pm ON up.pokemon_id = pm.id
        WHERE up.user_id = $1 AND up.is_active = 1
        ORDER BY up.id DESC
    """, sess["user_id"])

    pokemon = await _build_pokemon_data(rows)

    if not pokemon:
        return pg_json_response({"team": [], "analysis": "보유한 포켓몬이 없습니다.", "warnings": []})

    warnings = []
    if len(pokemon) < 6:
        warnings.append(f"보유 포켓몬이 {len(pokemon)}마리로 6마리 미만입니다.")

    if mode == "power":
        team, analysis = _recommend_power(pokemon)
    elif mode == "synergy":
        team, analysis = _recommend_synergy(pokemon)
    elif mode == "counter":
        team, analysis = await _recommend_counter(pokemon)
    elif mode == "balance":
        team, analysis = _recommend_balance(pokemon)
    else:
        team, analysis = _recommend_power(pokemon)

    # Check for type weaknesses
    team_types = set(p["pokemon_type"] for p in team)
    weak_to = set()
    for etype, advs in config.TYPE_ADVANTAGE.items():
        hits = sum(1 for t in team_types if t in advs)
        if hits >= 3:
            weak_to.add(config.TYPE_NAME_KO.get(etype, etype))
    if weak_to:
        warnings.append(f"팀이 {', '.join(weak_to)} 타입에 취약합니다.")

    # Check pool depth
    high_power = [p for p in pokemon if p["real_power"] > sum(p2["real_power"] for p2 in pokemon) / len(pokemon)]
    if len(high_power) < 6:
        warnings.append("전투력이 높은 포켓몬이 부족합니다. 포켓몬 육성을 권장합니다.")

    return pg_json_response({
        "team": team,
        "analysis": analysis,
        "warnings": warnings,
        "mode": mode,
    })


# ============================================================
# AI Chat Advisor API (Gemini Flash)
# ============================================================

async def _get_battle_meta() -> dict:
    """Collect recent battle win rate meta data."""
    pool = await queries.get_db()

    # Pokemon win rates from recent battles (last 100)
    rows = await pool.fetch("""
        WITH recent AS (
            SELECT * FROM battle_records ORDER BY created_at DESC LIMIT 100
        ),
        winners AS (
            SELECT bt.pokemon_instance_id, pm.name_ko, pm.pokemon_type, pm.rarity,
                   COUNT(*) as wins
            FROM recent r
            JOIN battle_teams bt ON bt.user_id = r.winner_id
            JOIN user_pokemon up ON bt.pokemon_instance_id = up.id
            JOIN pokemon_master pm ON up.pokemon_id = pm.id
            GROUP BY bt.pokemon_instance_id, pm.name_ko, pm.pokemon_type, pm.rarity
        ),
        losers AS (
            SELECT bt.pokemon_instance_id, pm.name_ko, pm.pokemon_type, pm.rarity,
                   COUNT(*) as losses
            FROM recent r
            JOIN battle_teams bt ON bt.user_id = r.loser_id
            JOIN user_pokemon up ON bt.pokemon_instance_id = up.id
            JOIN pokemon_master pm ON up.pokemon_id = pm.id
            GROUP BY bt.pokemon_instance_id, pm.name_ko, pm.pokemon_type, pm.rarity
        )
        SELECT COALESCE(w.name_ko, l.name_ko) as name_ko,
               COALESCE(w.pokemon_type, l.pokemon_type) as pokemon_type,
               COALESCE(w.rarity, l.rarity) as rarity,
               COALESCE(w.wins, 0) as wins,
               COALESCE(l.losses, 0) as losses
        FROM winners w
        FULL OUTER JOIN losers l ON w.pokemon_instance_id = l.pokemon_instance_id
        ORDER BY (COALESCE(w.wins,0) + COALESCE(l.losses,0)) DESC
        LIMIT 20
    """)

    meta_pokemon = []
    for r in rows:
        w = int(r["wins"])
        l = int(r["losses"])
        total = w + l
        rate = round(w / total * 100, 1) if total > 0 else 0
        meta_pokemon.append({
            "name": r["name_ko"], "type": r["pokemon_type"],
            "rarity": r["rarity"], "wins": w, "losses": l,
            "win_rate": rate, "pick_count": total,
        })

    # Top rankers
    ranking = await bq.get_battle_ranking(5)
    rankers = [{"name": r["display_name"], "wins": r["battle_wins"],
                "losses": r["battle_losses"], "bp": r["bp"],
                "streak": r.get("battle_streak", 0)} for r in ranking]

    return {"pokemon_meta": meta_pokemon, "top_rankers": rankers}


def _build_system_prompt(pokemon_data: list, meta: dict) -> str:
    """Build Gemini system prompt with full battle context."""
    # Summarize user's pokemon
    poke_summary = []
    for p in pokemon_data[:30]:  # cap at 30 for prompt size
        ivs = p.get("ivs", {})
        iv_str = "/".join(str(ivs.get(k, 0)) for k in ["hp","atk","def","spa","spdef","spd"])
        poke_summary.append(
            f"- {p['emoji']}{p['name_ko']} ({p['rarity']}) "
            f"타입:{p['pokemon_type']}/{p.get('type2','없음')} "
            f"실전투력:{p['real_power']} IV:{iv_str}({p['iv_grade']}) "
            f"시너지:{p['synergy_score']}점({p['synergy_label']})"
        )

    # Meta summary
    meta_lines = []
    for m in meta.get("pokemon_meta", [])[:10]:
        meta_lines.append(f"- {m['name']}({m['type']}): 승률 {m['win_rate']}% ({m['wins']}승/{m['losses']}패)")

    ranker_lines = []
    for r in meta.get("top_rankers", [])[:5]:
        ranker_lines.append(f"- {r['name']}: {r['wins']}승/{r['losses']}패 BP:{r['bp']} 연승:{r['streak']}")

    return f"""당신은 포켓몬 배틀 전략 AI 어드바이저입니다. 한국어로 답변하세요.

## 배틀 시스템 규칙
- 팀은 6마리 구성. 전설(legendary) 최대 1마리, 에픽(epic) 같은 종 중복 불가
- 스탯: HP, 공격(ATK), 방어(DEF), 특공(SPA), 특방(SPDEF), 속도(SPD)
- 실전투력 = 6개 스탯 합계 (IV 적용 후)
- IV(개체값): 0~31, 높을수록 해당 스탯 0.85x~1.15x 보너스
- 타입 상성: 18타입, 유리 1.3x, 불리 0.7x, 면역 0.3x
- 고유기술 발동률 30%, 기술 배율 1.0~2.5
- 친밀도 1당 +4% 전스탯 (최대 5 = +20%)
- 배틀은 속도 순 턴제, 물공/특공 중 높은 쪽으로 공격

## IV 시너지
- 공격형(offensive): 공격/특공 IV 중요, 방어 IV는 덜 중요
- 방어형(defensive): HP/방어/특방 IV 중요
- 속도형(speedy): 속도 IV가 핵심
- 시너지 점수 90+: 완벽, 70+: 우수, 50+: 보통, 50 미만: 아쉬움

## 유저의 포켓몬 보유 현황
{chr(10).join(poke_summary) if poke_summary else '(포켓몬 없음)'}

## 최근 배틀 메타 (승률 데이터)
{chr(10).join(meta_lines) if meta_lines else '(데이터 부족)'}

## 상위 랭커
{chr(10).join(ranker_lines) if ranker_lines else '(데이터 부족)'}

## 지침
- 유저의 실제 보유 포켓몬만 추천하세요
- 추천 시 "왜 이 포켓몬인지" 근거를 제시하세요 (IV 시너지, 타입 상성, 메타 승률 등)
- 답변은 친근하고 간결하게, 핵심 위주로 하세요
- 팀 추천 시 JSON 블록으로 팀 ID를 포함하세요: [TEAM:id1,id2,id3,id4,id5,id6]
- 포켓몬 이름은 한국어로 사용하세요"""


async def _call_gemini(system_prompt: str, messages: list, user_msg: str) -> str:
    """Call Gemini Flash API. Returns response text."""
    import aiohttp

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return ""

    # Build Gemini chat format
    contents = []
    for m in messages[-8:]:  # last 8 messages for context
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    contents.append({"role": "user", "parts": [{"text": user_msg}]})

    payload = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 1024,
            "topP": 0.9,
        },
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    logger.warning(f"Gemini API error: {resp.status}")
                    return ""
                data = await resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
    except Exception as e:
        logger.warning(f"Gemini API call failed: {e}")
    return ""


def _parse_team_ids(text: str) -> list[int]:
    """Extract [TEAM:id1,id2,...] from AI response text."""
    import re
    match = re.search(r'\[TEAM:([\d,]+)\]', text)
    if match:
        try:
            return [int(x) for x in match.group(1).split(",")]
        except ValueError:
            pass
    return []


async def _fallback_response(msg: str, pokemon: list, meta: dict) -> dict:
    """Algorithm-based fallback when Gemini is unavailable."""
    msg_lower = msg.lower()

    # Detect intent
    if any(k in msg_lower for k in ["최강", "전투력", "강한", "top"]):
        team, analysis = _recommend_power(pokemon)
        mode = "power"
    elif any(k in msg_lower for k in ["시너지", "iv", "궁합"]):
        team, analysis = _recommend_synergy(pokemon)
        mode = "synergy"
    elif any(k in msg_lower for k in ["카운터", "랭커", "상위"]):
        team, analysis = await _recommend_counter(pokemon)
        mode = "counter"
    elif any(k in msg_lower for k in ["밸런스", "균형", "골고루"]):
        team, analysis = _recommend_balance(pokemon)
        mode = "balance"
    elif any(k in msg_lower for k in ["메타", "승률", "요즘", "인기"]):
        # Meta analysis
        meta_pokemon = meta.get("pokemon_meta", [])
        if meta_pokemon:
            lines = ["📊 최근 배틀 메타 분석 (최근 100전 기준):\n"]
            for i, m in enumerate(meta_pokemon[:10], 1):
                bar = "🟢" if m["win_rate"] >= 55 else ("🟡" if m["win_rate"] >= 45 else "🔴")
                lines.append(f"{i}. {m['name']} ({m['type']}) — 승률 {m['win_rate']}% ({m['wins']}승/{m['losses']}패) {bar}")
            return {"analysis": "\n".join(lines), "team": [], "warnings": []}
        return {"analysis": "아직 배틀 데이터가 충분하지 않습니다.", "team": [], "warnings": []}
    elif any(k in msg_lower for k in ["육성", "키울", "성장", "추천"]):
        # Find high-potential low-power pokemon
        potential = sorted(pokemon, key=lambda p: p["synergy_score"] - p["real_power"]/20, reverse=True)
        team = potential[:3]
        lines = ["🌱 육성 추천 포켓몬:\n"]
        for p in team:
            lines.append(f"- {p['emoji']}{p['name_ko']}: 시너지 {p['synergy_score']}점({p['synergy_label']}), 현재 전투력 {p['real_power']}")
        lines.append("\n친밀도를 올리면 스탯이 최대 +20% 상승합니다.")
        return {"analysis": "\n".join(lines), "team": team, "warnings": []}
    elif any(k in msg_lower for k in ["약점", "취약"]):
        team, analysis = _recommend_balance(pokemon)
        team_types = set(p["pokemon_type"] for p in team)
        weak_to = []
        for etype, advs in config.TYPE_ADVANTAGE.items():
            hits = sum(1 for t in team_types if t in advs)
            if hits >= 2:
                weak_to.append(config.TYPE_NAME_KO.get(etype, etype))
        if weak_to:
            analysis = f"🔍 현재 최적 팀 기준, {', '.join(weak_to)} 타입에 취약합니다.\n이 타입을 커버할 포켓몬을 팀에 포함하는 것을 권장합니다."
        else:
            analysis = "🔍 현재 팀은 타입 밸런스가 양호합니다!"
        return {"analysis": analysis, "team": team, "warnings": []}
    else:
        team, analysis = _recommend_balance(pokemon)
        mode = "balance"

    warnings = []
    team_types = set(p["pokemon_type"] for p in team)
    weak_to = set()
    for etype, advs in config.TYPE_ADVANTAGE.items():
        hits = sum(1 for t in team_types if t in advs)
        if hits >= 3:
            weak_to.add(config.TYPE_NAME_KO.get(etype, etype))
    if weak_to:
        warnings.append(f"팀이 {', '.join(weak_to)} 타입에 취약합니다.")

    return {"team": team, "analysis": analysis, "warnings": warnings}


async def api_my_chat(request):
    """AI chat endpoint — Gemini Flash with battle context."""
    sess = _get_session(request)
    if not sess:
        return web.json_response({"error": "로그인이 필요합니다."}, status=401)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    user_msg = body.get("message", "").strip()
    history = body.get("history", [])
    if not user_msg:
        return web.json_response({"error": "메시지를 입력해주세요."}, status=400)

    # Rate limit check
    uid = sess["user_id"]
    allowed, remaining = _check_llm_limit(uid)
    if not allowed:
        return pg_json_response({
            "analysis": f"오늘의 AI 채팅 횟수({LLM_DAILY_LIMIT}회)를 모두 사용했습니다.\n내일 다시 이용해주세요!\n\n💡 위 모드 버튼(전투력/시너지/카운터/밸런스)은 제한 없이 사용 가능합니다.",
            "team": [], "warnings": [], "remaining": 0,
        })

    # Load user's pokemon
    pool = await queries.get_db()
    rows = await pool.fetch("""
        SELECT up.id, up.pokemon_id, up.friendship, up.is_shiny, up.is_favorite,
               up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd,
               pm.name_ko, pm.emoji, pm.rarity, pm.pokemon_type, pm.stat_type,
               pm.evolves_to
        FROM user_pokemon up
        JOIN pokemon_master pm ON up.pokemon_id = pm.id
        WHERE up.user_id = $1 AND up.is_active = 1
        ORDER BY up.id DESC
    """, sess["user_id"])

    pokemon = await _build_pokemon_data(rows)
    meta = await _get_battle_meta()

    # Record LLM usage
    _record_llm_usage(uid)
    _, remaining_after = _check_llm_limit(uid)

    # Try Gemini first
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key:
        system_prompt = _build_system_prompt(pokemon, meta)
        ai_text = await _call_gemini(system_prompt, history, user_msg)
        if ai_text:
            # Extract team IDs if present
            team_ids = _parse_team_ids(ai_text)
            team = []
            if team_ids:
                id_map = {p["id"]: p for p in pokemon}
                team = [id_map[tid] for tid in team_ids if tid in id_map]
            # Clean [TEAM:...] from display text
            import re
            clean_text = re.sub(r'\[TEAM:[\d,]+\]', '', ai_text).strip()
            return pg_json_response({
                "analysis": clean_text,
                "team": team,
                "warnings": [],
                "remaining": remaining_after,
            })

    # Fallback: algorithm-based
    result = await _fallback_response(user_msg, pokemon, meta)
    result["remaining"] = remaining_after
    return pg_json_response(result)


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


def _web_emoji(icon_key: str) -> str:
    """Convert icon key to unicode emoji for web. Returns as-is if already emoji."""
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
    for u in users:
        if u.get("title_emoji"):
            u["title_emoji"] = _web_emoji(u["title_emoji"])
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


async def api_iv_ranking(request):
    """Top 10 users by highest single-pokemon IV total."""
    import config
    pool = await queries.get_db()
    rows = await pool.fetch("""
        SELECT DISTINCT ON (up.user_id)
               up.user_id, u.display_name,
               pm.name_ko, pm.emoji, up.is_shiny,
               (COALESCE(up.iv_hp,0) + COALESCE(up.iv_atk,0) + COALESCE(up.iv_def,0)
                + COALESCE(up.iv_spa,0) + COALESCE(up.iv_spdef,0) + COALESCE(up.iv_spd,0)) as iv_total
        FROM user_pokemon up
        JOIN users u ON up.user_id = u.user_id
        JOIN pokemon_master pm ON up.pokemon_id = pm.id
        WHERE up.iv_hp IS NOT NULL
        ORDER BY up.user_id, iv_total DESC
    """)
    # Sort by iv_total desc, take top 10
    result = sorted([dict(r) for r in rows], key=lambda x: x["iv_total"], reverse=True)[:10]
    # Add grade
    for r in result:
        grade, _ = config.get_iv_grade(r["iv_total"])
        r["iv_grade"] = grade
    return pg_json_response(result)


# --- Battle APIs ---

async def api_battle_ranking(request):
    ranking = await bq.get_battle_ranking(20)
    for r in ranking:
        if r.get("title_emoji"):
            r["title_emoji"] = _web_emoji(r["title_emoji"])
    return pg_json_response(ranking)


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
    app = web.Application(middlewares=[rate_limit_middleware])
    app.router.add_get("/", index)
    # Static files (type icons etc.)
    static_dir = TEMPLATE_DIR.parent / "static"
    if static_dir.exists():
        app.router.add_static("/static", static_dir, show_index=False)
    # Auth
    app.router.add_post("/api/auth/telegram", api_auth_telegram)
    app.router.add_get("/api/auth/me", api_auth_me)
    app.router.add_post("/api/auth/logout", api_auth_logout)
    # My data (authenticated)
    app.router.add_get("/api/my/pokemon", api_my_pokemon)
    app.router.add_get("/api/my/summary", api_my_summary)
    app.router.add_post("/api/my/team-recommend", api_my_team_recommend)
    app.router.add_post("/api/my/chat", api_my_chat)
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
