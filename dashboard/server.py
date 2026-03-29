"""Dashboard web server using aiohttp."""

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from aiohttp import web
from asyncpg import InterfaceError

import config

from database import queries


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
LLM_DAILY_LIMIT = 999999  # 무제한


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
    from dashboard.api_board import setup_routes as setup_board_routes
    from dashboard.api_public import setup_routes as setup_public_routes
    from dashboard.api_cs import setup_routes as setup_cs_routes

    setup_my_routes(app)
    setup_advisor_routes(app)
    setup_admin_routes(app)
    setup_analytics_routes(app)
    setup_market_routes(app)
    setup_board_routes(app)
    setup_public_routes(app)
    setup_cs_routes(app)
    # Markdown doc viewer
    app.router.add_get("/docs/{name}", serve_markdown_doc)
    # SPA catch-all: serve index.html for all non-API, non-static paths
    SPA_PAGES = {"/channels", "/patchnotes", "/board", "/battle", "/tier", "/types", "/guide", "/stats", "/mypokemon", "/pokedex", "/ai", "/admin", "/market", "/camp", "/cs"}
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
    from dashboard.api_board import ensure_board_tables
    await ensure_board_tables()
    port = int(os.getenv("DASHBOARD_PORT", "8080"))
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Dashboard running at http://localhost:{port}")
    return runner
