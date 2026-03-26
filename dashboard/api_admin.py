"""Dashboard API — Admin panel, DB browser, user management."""

import asyncio
import json
import logging
import os

import aiohttp as _aiohttp
from aiohttp import web

import config
from database import queries

logger = logging.getLogger(__name__)

_RARITY_LABEL = {"common": "일반", "rare": "레어", "epic": "에픽", "legendary": "전설", "ultra_legendary": "초전설"}


async def _admin_check(request):
    """Return session if admin, else None."""
    from dashboard.server import _get_session
    sess = await _get_session(request)
    if not sess or sess["user_id"] not in config.ADMIN_IDS:
        return None
    return sess


async def _admin_send_dm(user_id: int, text: str, parse_mode: str = "HTML") -> bool:
    """Send Telegram DM to a user via Bot API (form-data for VM compatibility)."""
    bot_token = os.getenv("BOT_TOKEN", "")
    if not bot_token:
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": str(user_id), "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        async with _aiohttp.ClientSession() as cs:
            async with cs.post(url, data=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(f"Telegram DM failed ({resp.status}): {body}")
                return resp.status == 200
    except Exception as e:
        logger.warning(f"Telegram DM exception: {e}")
        return False


async def _send_dm_with_markup(user_id: int, text: str, reply_markup: dict) -> bool:
    """Send Telegram DM with inline keyboard via Bot API (form-data, reply_markup as JSON string)."""
    import json as _json
    bot_token = os.getenv("BOT_TOKEN", "")
    if not bot_token:
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": str(user_id),
        "text": text,
        "reply_markup": _json.dumps(reply_markup),
    }
    try:
        async with _aiohttp.ClientSession() as cs:
            async with cs.post(url, data=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(f"Telegram DM with markup failed ({resp.status}): {body}")
                return resp.status == 200
    except Exception as e:
        logger.warning(f"Telegram DM with markup exception: {e}")
        return False


def _iv_grade(total: int) -> str:
    """IV total → grade letter."""
    grade, _ = config.get_iv_grade(total)
    return grade


# --- Admin: Add LLM Bonus Quota ---

async def api_admin_add_quota(request):
    """Admin: add LLM bonus quota to a user after donation verification."""
    from dashboard.server import _get_session
    sess = await _get_session(request)
    if not sess or sess["user_id"] not in config.ADMIN_IDS:
        return web.json_response({"error": "Unauthorized"}, status=403)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    target_user_id = body.get("user_id")
    amount = body.get("amount", 0)
    if not target_user_id or not isinstance(amount, int) or amount <= 0:
        return web.json_response({"error": "user_id and positive amount required"}, status=400)
    pool = await queries.get_db()
    new_quota = await pool.fetchval(
        "UPDATE users SET llm_bonus_quota = llm_bonus_quota + $2 "
        "WHERE user_id = $1 RETURNING llm_bonus_quota",
        target_user_id, amount,
    )
    if new_quota is None:
        return web.json_response({"error": "User not found"}, status=404)
    return web.json_response({"ok": True, "user_id": target_user_id, "new_quota": new_quota})


async def api_admin_users(request):
    """Admin: list all users with search/pagination."""
    if not await _admin_check(request):
        return web.json_response({"error": "Unauthorized"}, status=403)
    pool = await queries.get_db()
    search = request.query.get("q", "").strip()[:100]
    try:
        page = max(1, int(request.query.get("page", "1")))
    except (ValueError, TypeError):
        page = 1
    per_page = 50
    offset = (page - 1) * per_page

    if search:
        like = f"%{search}%"
        total = await pool.fetchval(
            "SELECT COUNT(*) FROM users WHERE display_name ILIKE $1 OR username ILIKE $1 OR CAST(user_id AS TEXT) LIKE $1",
            like,
        )
        rows = await pool.fetch(
            "SELECT user_id, username, display_name, master_balls, battle_points, "
            "llm_bonus_quota, registered_at, last_active_at "
            "FROM users WHERE display_name ILIKE $1 OR username ILIKE $1 OR CAST(user_id AS TEXT) LIKE $1 "
            "ORDER BY last_active_at DESC LIMIT $2 OFFSET $3",
            like, per_page, offset,
        )
    else:
        total = await pool.fetchval("SELECT COUNT(*) FROM users")
        rows = await pool.fetch(
            "SELECT user_id, username, display_name, master_balls, battle_points, "
            "llm_bonus_quota, registered_at, last_active_at "
            "FROM users ORDER BY last_active_at DESC LIMIT $1 OFFSET $2",
            per_page, offset,
        )

    users = []
    for r in rows:
        users.append({
            "user_id": r["user_id"],
            "username": r["username"] or "",
            "display_name": r["display_name"],
            "master_balls": r["master_balls"],
            "bp": r["battle_points"],
            "credits": r["llm_bonus_quota"],
            "registered_at": r["registered_at"].isoformat() if r["registered_at"] else "",
            "last_active": r["last_active_at"].isoformat() if r["last_active_at"] else "",
        })
    return web.json_response({"total": total, "page": page, "per_page": per_page, "users": users})


async def api_admin_orders(request):
    """Admin: list all payment orders."""
    if not await _admin_check(request):
        return web.json_response({"error": "Unauthorized"}, status=403)
    pool = await queries.get_db()
    rows = await pool.fetch(
        "SELECT key, value FROM bot_settings WHERE key LIKE 'order_%' ORDER BY key DESC"
    )
    orders = []
    for r in rows:
        try:
            data = json.loads(r["value"])
        except Exception:
            continue
        orders.append({
            "order_key": r["key"],
            "user_id": data.get("user_id"),
            "price_usd": data.get("price_usd", 0),
            "llm_quota": data.get("llm_quota", 0),
            "master_balls": data.get("master_balls", 0),
            "fulfilled": data.get("fulfilled", False),
            "fulfilled_at": data.get("fulfilled_at", ""),
        })
    return web.json_response({"orders": orders})


async def api_admin_grant_credit(request):
    """Admin: grant credits + send DM."""
    sess = await _admin_check(request)
    if not sess:
        return web.json_response({"error": "Unauthorized"}, status=403)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    try:
        target = int(body.get("user_id", 0))
        amount = int(body.get("amount", 0))
    except (ValueError, TypeError):
        return web.json_response({"error": "Invalid parameters"}, status=400)
    if target <= 0 or amount <= 0 or amount > 10000:
        return web.json_response({"error": "user_id must be positive, amount 1-10000"}, status=400)
    pool = await queries.get_db()
    new_quota = await pool.fetchval(
        "UPDATE users SET llm_bonus_quota = llm_bonus_quota + $2 "
        "WHERE user_id = $1 RETURNING llm_bonus_quota",
        target, amount,
    )
    if new_quota is None:
        return web.json_response({"error": "User not found"}, status=404)
    _coin = '<tg-emoji emoji-id="6143083713354801765">💰</tg-emoji>'
    dm_ok = await _admin_send_dm(target, f"{_coin} 관리자가 크레딧 {amount}개를 지급했습니다!")
    logger.info(f"ADMIN_GRANT_CREDIT: admin={sess['user_id']} target={target} amount={amount} new={new_quota} dm={dm_ok}")
    return web.json_response({"ok": True, "new_credits": new_quota, "dm_sent": dm_ok})


async def api_admin_grant_bp(request):
    """Admin: grant BP + send DM."""
    sess = await _admin_check(request)
    if not sess:
        return web.json_response({"error": "Unauthorized"}, status=403)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    try:
        target = int(body.get("user_id", 0))
        amount = int(body.get("amount", 0))
    except (ValueError, TypeError):
        return web.json_response({"error": "Invalid parameters"}, status=400)
    if target <= 0 or amount <= 0 or amount > 100000:
        return web.json_response({"error": "user_id must be positive, amount 1-100000"}, status=400)
    pool = await queries.get_db()
    new_bp = await pool.fetchval(
        "UPDATE users SET battle_points = battle_points + $2 "
        "WHERE user_id = $1 RETURNING battle_points",
        target, amount,
    )
    if new_bp is None:
        return web.json_response({"error": "User not found"}, status=404)
    dm_ok = await _admin_send_dm(target, f"⚔️ 관리자가 BP {amount}를 지급했습니다! (잔여: {new_bp})")
    logger.info(f"ADMIN_GRANT_BP: admin={sess['user_id']} target={target} amount={amount} new={new_bp} dm={dm_ok}")
    return web.json_response({"ok": True, "new_bp": new_bp, "dm_sent": dm_ok})


async def api_admin_grant_masterball(request):
    """Admin: grant master balls + send DM."""
    sess = await _admin_check(request)
    if not sess:
        return web.json_response({"error": "Unauthorized"}, status=403)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    try:
        target = int(body.get("user_id", 0))
        amount = int(body.get("amount", 0))
    except (ValueError, TypeError):
        return web.json_response({"error": "Invalid parameters"}, status=400)
    if target <= 0 or amount <= 0 or amount > 1000:
        return web.json_response({"error": "user_id must be positive, amount 1-1000"}, status=400)
    pool = await queries.get_db()
    new_count = await pool.fetchval(
        "UPDATE users SET master_balls = master_balls + $2 "
        "WHERE user_id = $1 RETURNING master_balls",
        target, amount,
    )
    if new_count is None:
        return web.json_response({"error": "User not found"}, status=404)
    _mb = '<tg-emoji emoji-id="6143130859210807699">🟣</tg-emoji>'
    dm_ok = await _admin_send_dm(target, f"{_mb} 관리자가 마스터볼 {amount}개를 지급했습니다!")
    logger.info(f"ADMIN_GRANT_MASTERBALL: admin={sess['user_id']} target={target} amount={amount} new={new_count} dm={dm_ok}")
    return web.json_response({"ok": True, "new_master_balls": new_count, "dm_sent": dm_ok})


async def api_admin_fulfill_order(request):
    """Admin: manually fulfill an unfulfilled order."""
    sess = await _admin_check(request)
    if not sess:
        return web.json_response({"error": "Unauthorized"}, status=403)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    order_key = body.get("order_key", "")
    if not order_key.startswith("order_") or len(order_key) > 200 or not all(c.isalnum() or c in "_-." for c in order_key):
        return web.json_response({"error": "Invalid order_key"}, status=400)

    pool = await queries.get_db()
    order_data = await pool.fetchval(
        "SELECT value FROM bot_settings WHERE key = $1", order_key
    )
    if not order_data:
        return web.json_response({"error": "Order not found"}, status=404)

    order = json.loads(order_data)
    if order.get("fulfilled"):
        return web.json_response({"error": "Already fulfilled"}, status=400)

    user_id = order["user_id"]
    llm_quota = order.get("llm_quota", 0)
    master_balls = order.get("master_balls", 0)
    price_usd = order.get("price_usd", 0)

    # Grant rewards
    await pool.execute(
        "UPDATE users SET llm_bonus_quota = llm_bonus_quota + $2, "
        "master_balls = master_balls + $3 WHERE user_id = $1",
        user_id, llm_quota, master_balls,
    )
    # Mark fulfilled
    await pool.execute(
        "UPDATE bot_settings SET value = $2 WHERE key = $1",
        order_key,
        json.dumps({**order, "fulfilled": True, "fulfilled_at": config.get_kst_now().isoformat()}),
    )
    # DM
    dm_ok = await _admin_send_dm(
        user_id,
        f'<tg-emoji emoji-id="6143083713354801765">💰</tg-emoji> 결제가 확인되었습니다! 크레딧 {llm_quota}개 + 마스터볼 {master_balls}개 지급 완료'
    )
    logger.info(f"ADMIN_FULFILL_ORDER: admin={sess['user_id']} order={order_key} user={user_id} llm=+{llm_quota} mb=+{master_balls}")
    return web.json_response({"ok": True, "dm_sent": dm_ok})


async def api_admin_send_dm(request):
    """Admin: send custom DM to a user."""
    sess = await _admin_check(request)
    if not sess:
        return web.json_response({"error": "Unauthorized"}, status=403)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    try:
        target = int(body.get("user_id", 0))
    except (ValueError, TypeError):
        return web.json_response({"error": "Invalid user_id"}, status=400)
    message = body.get("message", "").strip()
    if target <= 0 or not message or len(message) > 4000:
        return web.json_response({"error": "user_id required, message 1-4000 chars"}, status=400)
    dm_ok = await _admin_send_dm(target, message)
    logger.info(f"Admin DM: admin={sess['user_id']} target={target} len={len(message)} ok={dm_ok}")
    return web.json_response({"ok": True, "dm_sent": dm_ok})


# --- Admin DB Browser APIs ---

async def api_admin_db_overview(request):
    """Admin DB: server overview stats."""
    if not await _admin_check(request):
        return web.json_response({"error": "Unauthorized"}, status=403)
    pool = await queries.get_db()
    rows = await asyncio.gather(
        pool.fetchval("SELECT COUNT(*) FROM users"),
        pool.fetchval("SELECT COUNT(*) FROM user_pokemon WHERE is_active = 1"),
        pool.fetchval("SELECT COUNT(*) FROM user_pokemon WHERE is_active = 1 AND is_shiny = 1"),
        pool.fetchval("SELECT COALESCE(SUM(master_balls),0) FROM users"),
        pool.fetchval("SELECT COALESCE(SUM(hyper_balls),0) FROM users"),
        pool.fetchval("SELECT COUNT(*) FROM spawn_log WHERE spawned_at >= CURRENT_DATE"),
        pool.fetchval("SELECT COUNT(*) FROM spawn_log WHERE spawned_at >= CURRENT_DATE AND caught_by_user_id IS NOT NULL"),
        pool.fetchval("SELECT COUNT(*) FROM spawn_log WHERE is_shiny = 1"),
        pool.fetchval("SELECT COUNT(*) FROM spawn_log WHERE is_shiny = 1 AND caught_by_user_id IS NOT NULL"),
        pool.fetchval("SELECT COUNT(*) FROM spawn_log"),
    )
    total_spawns_today = rows[5] or 0
    caught_today = rows[6] or 0
    return web.json_response({
        "total_users": rows[0] or 0,
        "total_pokemon": rows[1] or 0,
        "total_shiny": rows[2] or 0,
        "total_masterballs": rows[3] or 0,
        "total_hyperballs": rows[4] or 0,
        "spawns_today": total_spawns_today,
        "caught_today": caught_today,
        "catch_rate_today": round(caught_today / total_spawns_today * 100, 1) if total_spawns_today else 0,
        "shiny_spawned": rows[7] or 0,
        "shiny_caught": rows[8] or 0,
        "total_spawns": rows[9] or 0,
    })


async def api_admin_db_shiny(request):
    """Admin DB: shiny spawn log with IVs."""
    if not await _admin_check(request):
        return web.json_response({"error": "Unauthorized"}, status=403)
    pool = await queries.get_db()
    days = min(int(request.query.get("days", "0")), 365)
    rarity = request.query.get("rarity", "")
    page = max(1, int(request.query.get("page", "1")))
    per_page = 50

    where = ["sl.is_shiny = 1"]
    params = []
    idx = 1
    if days > 0:
        where.append(f"sl.spawned_at >= NOW() - INTERVAL '{days} days'")
    if rarity in ("common", "rare", "epic", "legendary"):
        where.append(f"sl.rarity = ${idx}")
        params.append(rarity)
        idx += 1

    where_sql = " AND ".join(where)

    total = await pool.fetchval(f"SELECT COUNT(*) FROM spawn_log sl WHERE {where_sql}", *params)

    rows = await pool.fetch(f"""
        SELECT sl.id, sl.pokemon_name, sl.rarity, sl.spawned_at,
               sl.caught_by_user_id, sl.caught_by_name,
               cr.chat_title,
               up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd
        FROM spawn_log sl
        LEFT JOIN chat_rooms cr ON sl.chat_id = cr.chat_id
        LEFT JOIN user_pokemon up ON (
            up.user_id = sl.caught_by_user_id
            AND up.pokemon_id = sl.pokemon_id
            AND up.is_shiny = 1
            AND up.caught_at BETWEEN sl.spawned_at - INTERVAL '5 minutes' AND sl.spawned_at + INTERVAL '5 minutes'
        )
        WHERE {where_sql}
        ORDER BY sl.spawned_at DESC
        LIMIT {per_page} OFFSET {(page - 1) * per_page}
    """, *params)

    # Summary counts
    summary = await pool.fetchrow(f"""
        SELECT COUNT(*) as total,
               COUNT(caught_by_user_id) as caught,
               COUNT(*) - COUNT(caught_by_user_id) as escaped
        FROM spawn_log sl WHERE {where_sql}
    """, *params)

    items = []
    for r in rows:
        iv_total = None
        iv_grade_val = None
        ivs = None
        if r["iv_hp"] is not None:
            iv_total = r["iv_hp"] + r["iv_atk"] + r["iv_def"] + r["iv_spa"] + r["iv_spdef"] + r["iv_spd"]
            iv_grade_val = _iv_grade(iv_total)
            ivs = {"hp": r["iv_hp"], "atk": r["iv_atk"], "def": r["iv_def"],
                    "spa": r["iv_spa"], "spdef": r["iv_spdef"], "spd": r["iv_spd"]}
        items.append({
            "pokemon": r["pokemon_name"],
            "rarity": r["rarity"],
            "rarity_label": _RARITY_LABEL.get(r["rarity"], r["rarity"]),
            "chat": r["chat_title"] or "?",
            "caught_by": r["caught_by_name"],
            "caught_uid": r["caught_by_user_id"],
            "time": r["spawned_at"].isoformat() if r["spawned_at"] else None,
            "iv_grade": iv_grade_val,
            "iv_total": iv_total,
            "ivs": ivs,
        })
    return web.json_response({
        "items": items, "total": total, "page": page, "pages": max(1, -(-total // per_page)),
        "summary": {"total": summary["total"], "caught": summary["caught"], "escaped": summary["escaped"]},
    })


async def api_admin_db_spawns(request):
    """Admin DB: spawn log with filters."""
    if not await _admin_check(request):
        return web.json_response({"error": "Unauthorized"}, status=403)
    pool = await queries.get_db()
    days = min(int(request.query.get("days", "1")), 365)
    rarity = request.query.get("rarity", "")
    shiny_only = request.query.get("shiny", "") == "1"
    caught_filter = request.query.get("caught", "")  # "yes", "no", or ""
    page = max(1, int(request.query.get("page", "1")))
    per_page = 50

    where = []
    params = []
    idx = 1
    if days > 0:
        where.append(f"sl.spawned_at >= NOW() - INTERVAL '{days} days'")
    if rarity in ("common", "rare", "epic", "legendary"):
        where.append(f"sl.rarity = ${idx}")
        params.append(rarity)
        idx += 1
    if shiny_only:
        where.append("sl.is_shiny = 1")
    if caught_filter == "yes":
        where.append("sl.caught_by_user_id IS NOT NULL")
    elif caught_filter == "no":
        where.append("sl.caught_by_user_id IS NULL")

    where_sql = " AND ".join(where) if where else "1=1"

    total = await pool.fetchval(f"SELECT COUNT(*) FROM spawn_log sl WHERE {where_sql}", *params)

    rows = await pool.fetch(f"""
        SELECT sl.pokemon_name, sl.rarity, sl.is_shiny, sl.spawned_at,
               sl.caught_by_name, sl.participants, cr.chat_title
        FROM spawn_log sl
        LEFT JOIN chat_rooms cr ON sl.chat_id = cr.chat_id
        WHERE {where_sql}
        ORDER BY sl.spawned_at DESC
        LIMIT {per_page} OFFSET {(page - 1) * per_page}
    """, *params)

    items = [{
        "pokemon": r["pokemon_name"],
        "rarity": r["rarity"],
        "rarity_label": _RARITY_LABEL.get(r["rarity"], r["rarity"]),
        "shiny": bool(r["is_shiny"]),
        "chat": r["chat_title"] or "?",
        "caught_by": r["caught_by_name"],
        "participants": r["participants"] or 0,
        "time": r["spawned_at"].isoformat() if r["spawned_at"] else None,
    } for r in rows]
    return web.json_response({
        "items": items, "total": total, "page": page, "pages": max(1, -(-total // per_page)),
    })


async def api_admin_db_user_pokemon(request):
    """Admin DB: browse a user's pokemon collection."""
    if not await _admin_check(request):
        return web.json_response({"error": "Unauthorized"}, status=403)
    pool = await queries.get_db()

    q = request.query.get("q", "").strip()[:100]
    if not q:
        return web.json_response({"error": "q (user_id or name) required"}, status=400)

    rarity = request.query.get("rarity", "")
    shiny_only = request.query.get("shiny", "") == "1"
    iv_filter = request.query.get("iv", "")  # S, A, B, C, D

    # Find user
    try:
        uid = int(q)
        user = await pool.fetchrow("SELECT user_id, display_name, username FROM users WHERE user_id = $1", uid)
    except ValueError:
        user = await pool.fetchrow(
            "SELECT user_id, display_name, username FROM users WHERE display_name ILIKE $1 LIMIT 1", f"%{q}%"
        )
    if not user:
        return web.json_response({"error": "User not found", "items": [], "summary": {}})

    uid = user["user_id"]

    where = ["up.user_id = $1"]
    params = [uid]
    idx = 2
    if rarity in ("common", "rare", "epic", "legendary"):
        where.append(f"pm.rarity = ${idx}")
        params.append(rarity)
        idx += 1
    if shiny_only:
        where.append("up.is_shiny = 1")

    where_sql = " AND ".join(where)

    rows = await pool.fetch(f"""
        SELECT up.id, pm.name_ko, pm.rarity, up.is_shiny, up.is_active, up.caught_at,
               up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd
        FROM user_pokemon up
        JOIN pokemon_master pm ON up.pokemon_id = pm.id
        WHERE {where_sql}
        ORDER BY up.id DESC
    """, *params)

    items = []
    for r in rows:
        iv_total = (r["iv_hp"] or 0) + (r["iv_atk"] or 0) + (r["iv_def"] or 0) + \
                   (r["iv_spa"] or 0) + (r["iv_spdef"] or 0) + (r["iv_spd"] or 0)
        grade = _iv_grade(iv_total)
        if iv_filter and grade != iv_filter:
            continue
        items.append({
            "id": r["id"],
            "name": r["name_ko"],
            "rarity": r["rarity"],
            "rarity_label": _RARITY_LABEL.get(r["rarity"], r["rarity"]),
            "shiny": bool(r["is_shiny"]),
            "active": bool(r["is_active"]),
            "time": r["caught_at"].isoformat() if r["caught_at"] else None,
            "iv_grade": grade,
            "iv_total": iv_total,
            "ivs": {"hp": r["iv_hp"], "atk": r["iv_atk"], "def": r["iv_def"],
                    "spa": r["iv_spa"], "spdef": r["iv_spdef"], "spd": r["iv_spd"]},
        })

    # Summary
    summary_rows = await pool.fetch("""
        SELECT pm.rarity, COUNT(*) as cnt, SUM(CASE WHEN up.is_shiny=1 THEN 1 ELSE 0 END) as shiny_cnt
        FROM user_pokemon up JOIN pokemon_master pm ON up.pokemon_id = pm.id
        WHERE up.user_id = $1 AND up.is_active = 1
        GROUP BY pm.rarity
    """, uid)
    summary = {r["rarity"]: {"count": r["cnt"], "shiny": r["shiny_cnt"]} for r in summary_rows}
    total_active = sum(r["cnt"] for r in summary_rows)
    total_shiny = sum(r["shiny_cnt"] for r in summary_rows)

    return web.json_response({
        "user": {"id": uid, "name": user["display_name"], "username": user["username"]},
        "items": items, "total": len(items),
        "summary": {"total": total_active, "shiny": total_shiny, "by_rarity": summary},
    })


async def api_admin_db_economy(request):
    """Admin DB: economy rankings (top holders)."""
    if not await _admin_check(request):
        return web.json_response({"error": "Unauthorized"}, status=403)
    pool = await queries.get_db()
    limit = min(int(request.query.get("limit", "20")), 50)

    mb, hb, bp, cr = await asyncio.gather(
        pool.fetch(f"SELECT user_id, display_name, master_balls as val FROM users WHERE master_balls > 0 ORDER BY master_balls DESC LIMIT {limit}"),
        pool.fetch(f"SELECT user_id, display_name, hyper_balls as val FROM users WHERE hyper_balls > 0 ORDER BY hyper_balls DESC LIMIT {limit}"),
        pool.fetch(f"SELECT user_id, display_name, battle_points as val FROM users WHERE battle_points > 0 ORDER BY battle_points DESC LIMIT {limit}"),
        pool.fetch(f"SELECT user_id, display_name, llm_bonus_quota as val FROM users WHERE llm_bonus_quota > 0 ORDER BY llm_bonus_quota DESC LIMIT {limit}"),
    )

    def to_list(rows):
        return [{"uid": r["user_id"], "name": r["display_name"], "val": r["val"]} for r in rows]

    return web.json_response({
        "masterballs": to_list(mb),
        "hyperballs": to_list(hb),
        "bp": to_list(bp),
        "credits": to_list(cr),
    })


async def api_admin_db_dungeon(request):
    """Admin DB: dungeon analytics."""
    if not await _admin_check(request):
        return web.json_response({"ok": False, "error": "forbidden"}, status=403)
    pool = await queries.get_db()

    # 기본 통계
    stats = await pool.fetchrow(
        "SELECT COUNT(*) as total_runs, "
        "COALESCE(AVG(floor_reached)::numeric(5,1), 0) as avg_floor, "
        "COALESCE(MAX(floor_reached), 0) as max_floor, "
        "COUNT(CASE WHEN started_at >= (NOW() AT TIME ZONE 'Asia/Seoul')::date THEN 1 END) as today_runs "
        "FROM dungeon_runs WHERE status = 'completed'"
    )

    # 층별 분포
    floor_dist = await pool.fetch(
        "SELECT floor_reached as floor, COUNT(*) as cnt FROM dungeon_runs "
        "WHERE status = 'completed' GROUP BY floor_reached ORDER BY floor_reached"
    )

    # 희귀도별
    rarity_stats = await pool.fetch(
        "SELECT rarity, COUNT(*) as cnt, AVG(floor_reached)::numeric(5,1) as avg, "
        "MAX(floor_reached) as max_f FROM dungeon_runs "
        "WHERE status = 'completed' AND rarity IS NOT NULL "
        "GROUP BY rarity ORDER BY avg DESC"
    )

    # 사망 원인 Top10
    death_top = await pool.fetch(
        "SELECT death_enemy as name, death_enemy_rarity as rarity, COUNT(*) as cnt "
        "FROM dungeon_runs WHERE status = 'completed' AND death_enemy IS NOT NULL "
        "GROUP BY death_enemy, death_enemy_rarity ORDER BY cnt DESC LIMIT 10"
    )

    # 런 로그 (페이지네이션)
    page = max(1, int(request.query.get("page", "1")))
    per_page = 30
    total_runs_count = stats["total_runs"]

    recent_runs = await pool.fetch(
        "SELECT dr.pokemon_name as pokemon, dr.rarity, dr.is_shiny as shiny, "
        "dr.floor_reached as floor, dr.bp_earned as bp, dr.ended_at, "
        "COALESCE(u.display_name, u.user_id::text) as name "
        "FROM dungeon_runs dr LEFT JOIN users u ON dr.user_id = u.user_id "
        "WHERE dr.status = 'completed' ORDER BY dr.ended_at DESC "
        f"LIMIT {per_page} OFFSET {(page - 1) * per_page}"
    )

    total_pages = max(1, (total_runs_count + per_page - 1) // per_page)

    # 액션 로그 통계 (자동배틀 롤백으로 비활성)
    action_counts = {"normal": 0, "skill1": 0, "skill2": 0, "defend": 0}
    total_actions = 0
    action_pct = {}

    # 인기 빌드 Top10 (버프 조합별 평균 도달 층)
    import json as _json
    buff_rows = await pool.fetch(
        "SELECT buffs_json, floor_reached FROM dungeon_runs "
        "WHERE status = 'completed' AND buffs_json IS NOT NULL AND floor_reached >= 10 "
        "ORDER BY floor_reached DESC LIMIT 200"
    )
    buff_freq = {}
    for br in buff_rows:
        try:
            buffs = br["buffs_json"] if isinstance(br["buffs_json"], list) else _json.loads(br["buffs_json"])
            key = "+".join(sorted(b.get("id", "") for b in buffs if not b.get("id", "").startswith("_")))
            if key:
                if key not in buff_freq:
                    buff_freq[key] = {"combo": key, "cnt": 0, "total_floor": 0}
                buff_freq[key]["cnt"] += 1
                buff_freq[key]["total_floor"] += br["floor_reached"]
        except Exception:
            pass
    top_builds = []
    for v in buff_freq.values():
        v["avg_floor"] = round(v["total_floor"] / v["cnt"], 1) if v["cnt"] > 0 else 0
        del v["total_floor"]
        top_builds.append(v)
    top_builds.sort(key=lambda x: -x["avg_floor"])
    top_builds = top_builds[:10]

    return web.json_response({
        "ok": True,
        "stats": {
            "total_runs": total_runs_count,
            "avg_floor": float(stats["avg_floor"]),
            "max_floor": stats["max_floor"],
            "today_runs": stats["today_runs"],
        },
        "floor_dist": [{"floor": r["floor"], "cnt": r["cnt"]} for r in floor_dist],
        "rarity_stats": [{"rarity": r["rarity"], "cnt": r["cnt"], "avg": float(r["avg"]), "max_f": r["max_f"]} for r in rarity_stats],
        "death_top": [{"name": r["name"], "rarity": r["rarity"], "cnt": r["cnt"]} for r in death_top],
        "action_stats": {"counts": action_counts, "pct": action_pct, "total": total_actions},
        "top_builds": top_builds,
        "recent_runs": [{"pokemon": r["pokemon"], "rarity": r["rarity"], "shiny": r["shiny"], "floor": r["floor"], "bp": r["bp"], "ended_at": r["ended_at"].isoformat() if r["ended_at"] else None, "name": r["name"]} for r in recent_runs],
        "page": page,
        "pages": total_pages,
    })


async def api_admin_db_optout(request):
    """Admin DB: list users who opted out of patch notes."""
    if not await _admin_check(request):
        return web.json_response({"error": "Unauthorized"}, status=403)
    pool = await queries.get_db()
    rows = await pool.fetch(
        """SELECT user_id, display_name, username, last_active_at
           FROM users WHERE patch_optout = TRUE
           ORDER BY last_active_at DESC"""
    )
    users = [
        {
            "uid": r["user_id"],
            "name": r["display_name"],
            "username": r["username"],
            "last_active": r["last_active_at"].isoformat() if r["last_active_at"] else None,
        }
        for r in rows
    ]
    return web.json_response({"total": len(users), "users": users})


async def api_admin_db_optout_remove(request):
    """Admin: remove patch_optout for a user."""
    if not await _admin_check(request):
        return web.json_response({"error": "Unauthorized"}, status=403)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    uid = int(body.get("user_id", 0))
    if uid <= 0:
        return web.json_response({"error": "Invalid user_id"}, status=400)
    pool = await queries.get_db()
    await pool.execute(
        "UPDATE users SET patch_optout = FALSE WHERE user_id = $1", uid
    )
    logger.info(f"ADMIN_OPTOUT_REMOVE: user_id={uid}")
    return web.json_response({"ok": True})


def setup_routes(app):
    """Register admin routes."""
    app.router.add_post("/api/admin/add-quota", api_admin_add_quota)
    app.router.add_get("/api/admin/users", api_admin_users)
    app.router.add_get("/api/admin/orders", api_admin_orders)
    app.router.add_post("/api/admin/grant-credit", api_admin_grant_credit)
    app.router.add_post("/api/admin/grant-bp", api_admin_grant_bp)
    app.router.add_post("/api/admin/grant-masterball", api_admin_grant_masterball)
    app.router.add_post("/api/admin/fulfill-order", api_admin_fulfill_order)
    app.router.add_post("/api/admin/send-dm", api_admin_send_dm)
    # Admin DB Browser
    app.router.add_get("/api/admin/db/overview", api_admin_db_overview)
    app.router.add_get("/api/admin/db/shiny", api_admin_db_shiny)
    app.router.add_get("/api/admin/db/spawns", api_admin_db_spawns)
    app.router.add_get("/api/admin/db/user-pokemon", api_admin_db_user_pokemon)
    app.router.add_get("/api/admin/db/economy", api_admin_db_economy)
    app.router.add_get("/api/admin/db/dungeon", api_admin_db_dungeon)
    app.router.add_get("/api/admin/db/optout", api_admin_db_optout)
    app.router.add_post("/api/admin/db/optout-remove", api_admin_db_optout_remove)
