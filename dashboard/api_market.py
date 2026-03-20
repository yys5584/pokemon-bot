"""Dashboard API — Marketplace listings, buy/sell/cancel, payment, donation."""

import hashlib
import hmac
import json
import logging
import os
import time
from datetime import timedelta, timezone

import aiohttp as _aiohttp
from aiohttp import web

import config
from database import queries, market_queries
from database import battle_queries as bq
from models.pokemon_base_stats import POKEMON_BASE_STATS
from services import market_service

logger = logging.getLogger(__name__)


# ============================================================
# Marketplace API (Web)
# ============================================================

async def api_market_listings(request):
    """Public: browse active market listings with filters."""
    from dashboard.server import pg_json_response
    q = request.query
    page = max(0, int(q.get("page", 0)))
    page_size = min(50, max(1, int(q.get("page_size", 20))))
    rarity = q.get("rarity") or None
    iv_grade = q.get("iv_grade") or None
    shiny_only = q.get("shiny") == "1"
    search = q.get("q") or None
    sort = q.get("sort", "newest")
    price_min = int(q["price_min"]) if q.get("price_min", "").isdigit() else None
    price_max = int(q["price_max"]) if q.get("price_max", "").isdigit() else None

    rows, total = await market_queries.get_active_listings_web(
        page=page, page_size=page_size,
        rarity=rarity, iv_grade=iv_grade,
        shiny_only=shiny_only, search=search,
        price_min=price_min, price_max=price_max,
        sort=sort,
    )

    now = config.get_kst_now()
    expire_days = config.MARKET_LISTING_EXPIRE_DAYS

    listings = []
    for r in rows:
        iv_hp = r.get("iv_hp") or 0
        iv_atk = r.get("iv_atk") or 0
        iv_def = r.get("iv_def") or 0
        iv_spa = r.get("iv_spa") or 0
        iv_spdef = r.get("iv_spdef") or 0
        iv_spd = r.get("iv_spd") or 0
        total_iv = iv_hp + iv_atk + iv_def + iv_spa + iv_spdef + iv_spd
        grade, _ = config.get_iv_grade(total_iv)

        # time remaining
        created = r["created_at"]
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        expires = created + timedelta(days=expire_days)
        remaining = expires - now
        if remaining.total_seconds() <= 0:
            time_remaining = "만료됨"
        elif remaining.days > 0:
            time_remaining = f"{remaining.days}일 {remaining.seconds // 3600}시간"
        else:
            time_remaining = f"{remaining.seconds // 3600}시간 {(remaining.seconds % 3600) // 60}분"

        # type2 from POKEMON_BASE_STATS
        pbs = POKEMON_BASE_STATS.get(r["pokemon_id"])
        type2 = None
        if pbs and len(pbs[-1]) > 1:
            type2 = pbs[-1][1]

        listings.append({
            "id": r["id"],
            "pokemon_name": r["pokemon_name"],
            "pokemon_id": r["pokemon_id"],
            "emoji": r["emoji"],
            "rarity": r["rarity"],
            "pokemon_type": r.get("pokemon_type", ""),
            "type2": type2,
            "is_shiny": bool(r.get("is_shiny")),
            "price_bp": r["price_bp"],
            "seller_name": r["seller_name"],
            "seller_id": r["seller_id"],
            "iv_hp": iv_hp, "iv_atk": iv_atk, "iv_def": iv_def,
            "iv_spa": iv_spa, "iv_spdef": iv_spdef, "iv_spd": iv_spd,
            "iv_total": total_iv,
            "iv_grade": grade,
            "friendship": r.get("friendship", 0),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else "",
            "time_remaining": time_remaining,
        })

    return web.json_response({
        "listings": listings, "total": total,
        "page": page, "page_size": page_size,
        "fee_rate": config.MARKET_FEE_RATE,
    })


async def api_market_stats(request):
    """Public: marketplace summary stats."""
    pool = await queries.get_db()
    row = await pool.fetchrow("""
        SELECT
            (SELECT COUNT(*) FROM market_listings
             WHERE status='active' AND created_at > NOW()-INTERVAL '7 days') AS active,
            (SELECT COUNT(*) FROM market_listings
             WHERE status='sold' AND sold_at > NOW()-INTERVAL '1 day') AS sold_24h,
            (SELECT COALESCE(AVG(price_bp),0) FROM market_listings
             WHERE status='active' AND created_at > NOW()-INTERVAL '7 days') AS avg_price,
            (SELECT COALESCE(SUM(price_bp),0) FROM market_listings
             WHERE status='sold' AND sold_at > NOW()-INTERVAL '1 day') AS volume_24h
    """)
    return web.json_response({
        "total_active": int(row["active"]),
        "total_sold_24h": int(row["sold_24h"]),
        "avg_price": int(row["avg_price"]),
        "volume_24h": int(row["volume_24h"]),
    })


async def api_market_my_listings(request):
    """Auth: get user's own active listings."""
    from dashboard.server import _get_session
    sess = await _get_session(request)
    if not sess:
        return web.json_response({"error": "Unauthorized"}, status=401)

    rows = await market_queries.get_user_active_listings(sess["user_id"])
    listings = []
    for r in rows:
        iv_hp = r.get("iv_hp") or 0
        iv_atk = r.get("iv_atk") or 0
        iv_def = r.get("iv_def") or 0
        iv_spa = r.get("iv_spa") or 0
        iv_spdef = r.get("iv_spdef") or 0
        iv_spd = r.get("iv_spd") or 0
        total_iv = iv_hp + iv_atk + iv_def + iv_spa + iv_spdef + iv_spd
        grade, _ = config.get_iv_grade(total_iv)
        listings.append({
            "id": r["id"], "pokemon_name": r["pokemon_name"],
            "pokemon_id": r.get("pokemon_id"), "emoji": r.get("emoji", ""),
            "rarity": r.get("rarity", ""),
            "is_shiny": bool(r.get("is_shiny")),
            "price_bp": r["price_bp"],
            "iv_total": total_iv, "iv_grade": grade,
            "created_at": r["created_at"].isoformat() if r.get("created_at") else "",
        })
    return web.json_response(listings)


async def api_market_my_balance(request):
    """Auth: get user's BP balance."""
    from dashboard.server import _get_session
    sess = await _get_session(request)
    if not sess:
        return web.json_response({"error": "Unauthorized"}, status=401)
    bp = await bq.get_bp(sess["user_id"])
    return web.json_response({"bp": bp})


async def api_market_my_sellable(request):
    """Auth: get user's pokemon available for selling."""
    from dashboard.server import _get_session
    sess = await _get_session(request)
    if not sess:
        return web.json_response({"error": "Unauthorized"}, status=401)

    user_id = sess["user_id"]
    pool = await queries.get_db()

    search = request.query.get("q", "").strip()
    search_clause = ""
    params = [user_id]
    if search:
        params.append(f"%{search}%")
        search_clause = f"AND pm.name_ko ILIKE ${len(params)}"

    rows = await pool.fetch(f"""
        SELECT up.id, up.pokemon_id, up.friendship, up.is_shiny, up.is_favorite,
               up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd,
               pm.name_ko, pm.emoji, pm.rarity, pm.pokemon_type,
               bt.slot AS team_slot
        FROM user_pokemon up
        JOIN pokemon_master pm ON up.pokemon_id = pm.id
        LEFT JOIN battle_teams bt ON bt.pokemon_instance_id = up.id
        WHERE up.user_id = $1 AND up.is_active = 1
          AND bt.slot IS NULL
          AND up.id NOT IN (
              SELECT offer_pokemon_instance_id FROM trades
              WHERE status = 'pending'
          )
          AND up.id NOT IN (
              SELECT pokemon_instance_id FROM market_listings
              WHERE status = 'active'
          )
          {search_clause}
        ORDER BY up.id DESC
    """, *params)

    result = []
    for r in rows:
        iv_hp = r.get("iv_hp") or 0
        iv_atk = r.get("iv_atk") or 0
        iv_def = r.get("iv_def") or 0
        iv_spa = r.get("iv_spa") or 0
        iv_spdef = r.get("iv_spdef") or 0
        iv_spd = r.get("iv_spd") or 0
        total_iv = iv_hp + iv_atk + iv_def + iv_spa + iv_spdef + iv_spd
        grade, _ = config.get_iv_grade(total_iv)
        pbs = POKEMON_BASE_STATS.get(r["pokemon_id"])
        type2 = pbs[-1][1] if pbs and len(pbs[-1]) > 1 else None
        result.append({
            "id": r["id"], "pokemon_id": r["pokemon_id"],
            "name_ko": r["name_ko"], "emoji": r["emoji"],
            "rarity": r["rarity"], "pokemon_type": r.get("pokemon_type", ""),
            "type2": type2,
            "is_shiny": bool(r["is_shiny"]),
            "friendship": r["friendship"],
            "iv_total": total_iv, "iv_grade": grade,
        })
    return web.json_response(result)


async def api_market_sell(request):
    """Auth: create a market listing."""
    from dashboard.server import _get_session
    sess = await _get_session(request)
    if not sess:
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    instance_id = body.get("instance_id")
    price_bp = body.get("price_bp")
    if not instance_id or not price_bp:
        return web.json_response({"error": "instance_id, price_bp 필요"}, status=400)

    price_bp = int(price_bp)
    if price_bp < config.MARKET_MIN_PRICE:
        return web.json_response({"error": f"최소 가격: {config.MARKET_MIN_PRICE} BP"}, status=400)

    success, message, listing_id, _ = await market_service.create_listing(
        sess["user_id"], "", price_bp, instance_id=int(instance_id),
    )
    if not success:
        return web.json_response({"error": message}, status=400)

    fee = market_service.calc_fee(price_bp)
    return web.json_response({
        "ok": True, "listing_id": listing_id,
        "fee": fee, "seller_gets": price_bp - fee,
        "message": message,
    })


async def api_market_buy(request):
    """Auth: purchase a market listing."""
    from dashboard.server import _get_session
    from dashboard.api_admin import _admin_send_dm, _send_dm_with_markup
    sess = await _get_session(request)
    if not sess:
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    listing_id = body.get("listing_id")
    if not listing_id:
        return web.json_response({"error": "listing_id 필요"}, status=400)

    success, message, trade_info = await market_service.buy_listing(
        sess["user_id"], int(listing_id),
    )
    if not success:
        return web.json_response({"error": message}, status=400)

    new_bp = await bq.get_bp(sess["user_id"])

    # Notify seller via Telegram DM
    if trade_info:
        try:
            seller_id = trade_info.get("seller_id")
            pokemon_name = trade_info.get("pokemon_name", "")
            seller_gets = trade_info.get("seller_gets", 0)
            fee = trade_info.get("fee", 0)
            await _admin_send_dm(
                seller_id,
                f"💰 거래소 판매 알림!\n\n"
                f"{pokemon_name}이(가) 웹 거래소에서 판매되었습니다.\n"
                f"💵 수익: {seller_gets:,} BP (수수료 {fee:,} BP)",
            )
        except Exception:
            pass

        # Send trade evolution choice DM to buyer via Telegram
        if trade_info.get("pending_evo"):
            try:
                evo = trade_info["pending_evo"]
                source = await queries.get_pokemon(evo["source_id"])
                target = await queries.get_pokemon(evo["target_id"])
                if source and target:
                    evo_text = (
                        f"✨ 교환 진화 가능!\n\n"
                        f"{source['emoji']} {source['name_ko']}을(를)\n"
                        f"{target['emoji']} {target['name_ko']}(으)로 진화시킬 수 있습니다!\n\n"
                        f"진화하시겠습니까?"
                    )
                    reply_markup = {
                        "inline_keyboard": [[
                            {"text": "✨ 진화시키기", "callback_data": f"tevo_yes_{evo['instance_id']}"},
                            {"text": "❌ 그대로 유지", "callback_data": f"tevo_no_{evo['instance_id']}"},
                        ]]
                    }
                    await _send_dm_with_markup(sess["user_id"], evo_text, reply_markup)
            except Exception:
                pass

    has_pending_evo = bool(trade_info.get("pending_evo")) if trade_info else False
    return web.json_response({
        "ok": True, "message": message,
        "pokemon_name": trade_info.get("pokemon_name", "") if trade_info else "",
        "price": trade_info.get("price", 0) if trade_info else 0,
        "new_bp": new_bp,
        "pending_evo": has_pending_evo,
    })


async def api_market_cancel(request):
    """Auth: cancel own market listing."""
    from dashboard.server import _get_session
    sess = await _get_session(request)
    if not sess:
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    listing_id = body.get("listing_id")
    if not listing_id:
        return web.json_response({"error": "listing_id 필요"}, status=400)

    success, message = await market_service.cancel_listing_for_user(
        sess["user_id"], int(listing_id),
    )
    if not success:
        return web.json_response({"error": message}, status=400)

    return web.json_response({"ok": True, "message": message})


# --- NOWPayments Integration ---

NOWPAYMENTS_API_KEY = os.getenv("NOWPAYMENTS_API_KEY", "")
NOWPAYMENTS_IPN_SECRET = os.getenv("NOWPAYMENTS_IPN_SECRET", "")
NOWPAYMENTS_API = "https://api.nowpayments.io/v1"

# Tier configuration: {tier_id: {price_usd, llm_quota, master_balls, label}}
PAYMENT_TIERS = {
    1: {"price_usd": 3, "llm_quota": 20, "master_balls": 1, "label": "$3 - 20크레딧 + 마볼 1개"},
    2: {"price_usd": 7, "llm_quota": 50, "master_balls": 3, "label": "$7 - 50크레딧 + 마볼 3개"},
    3: {"price_usd": 15, "llm_quota": 100, "master_balls": 7, "label": "$15 - 100크레딧 + 마볼 7개"},
}


async def api_payment_create(request):
    """Create NOWPayments invoice for a donation tier."""
    from dashboard.server import _get_session
    sess = await _get_session(request)
    if not sess:
        return web.json_response({"error": "로그인이 필요합니다."}, status=401)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    tier_id = body.get("tier")
    custom_amount = body.get("custom_amount")

    if custom_amount and isinstance(custom_amount, (int, float)) and custom_amount >= 10:
        price_usd = float(custom_amount)
        llm_quota = int(price_usd / 7 * 50)
        master_balls = max(1, int(price_usd / 3))
        label = f"${price_usd:.0f} - {llm_quota}크레딧 + 마볼 {master_balls}개"
    elif tier_id in PAYMENT_TIERS:
        tier = PAYMENT_TIERS[tier_id]
        price_usd = tier["price_usd"]
        llm_quota = tier["llm_quota"]
        master_balls = tier["master_balls"]
        label = tier["label"]
    else:
        return web.json_response({"error": "Invalid tier"}, status=400)

    if not NOWPAYMENTS_API_KEY:
        return web.json_response({"error": "Payment not configured"}, status=500)

    user_id = sess["user_id"]
    order_id = f"tgpoke_{user_id}_{int(time.time())}_{tier_id or 'c'}"

    # Store order info for webhook fulfillment
    pool = await queries.get_db()
    await pool.execute(
        """INSERT INTO bot_settings (key, value) VALUES ($1, $2)
           ON CONFLICT (key) DO UPDATE SET value = $2""",
        f"order_{order_id}",
        json.dumps({"user_id": user_id, "llm_quota": llm_quota,
                     "master_balls": master_balls, "price_usd": price_usd}),
    )

    # Create NOWPayments invoice
    # Force HTTPS — Cloudflare Tunnel redirects HTTP→HTTPS, which drops POST body
    base_url = str(request.url.origin()).replace("http://", "https://")
    payload = {
        "price_amount": price_usd,
        "price_currency": "usd",
        "order_id": order_id,
        "order_description": label,
        "ipn_callback_url": base_url + "/api/payment/webhook",
        "success_url": base_url + "/?payment=success",
        "cancel_url": base_url + "/?payment=cancel",
    }
    headers = {"x-api-key": NOWPAYMENTS_API_KEY, "Content-Type": "application/json"}

    try:
        async with _aiohttp.ClientSession() as cs:
            async with cs.post(f"{NOWPAYMENTS_API}/invoice", json=payload, headers=headers) as resp:
                data = await resp.json()
                if resp.status != 200:
                    logger.error(f"NOWPayments invoice error: {data}")
                    return web.json_response({"error": "결제 생성 실패"}, status=500)
                return web.json_response({
                    "ok": True,
                    "invoice_url": data.get("invoice_url"),
                    "invoice_id": data.get("id"),
                })
    except Exception as e:
        logger.error(f"NOWPayments request failed: {e}")
        return web.json_response({"error": "결제 서비스 연결 실패"}, status=500)


async def api_payment_webhook(request):
    """NOWPayments IPN webhook — auto-fulfill rewards on payment."""
    try:
        raw_body = await request.read()
        body = json.loads(raw_body)
    except Exception:
        return web.Response(status=400)

    # Verify HMAC signature using sorted JSON (NOWPayments spec)
    sig = request.headers.get("x-nowpayments-sig", "")
    if NOWPAYMENTS_IPN_SECRET and sig:
        sorted_body = json.dumps(body, sort_keys=True, separators=(',', ':'))
        expected = hmac.new(
            NOWPAYMENTS_IPN_SECRET.encode(),
            sorted_body.encode(),
            hashlib.sha512,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            logger.warning(f"NOWPayments webhook: signature mismatch (expected={expected[:16]}... got={sig[:16]}...)")
            return web.json_response({"error": "Invalid signature"}, status=403)

    payment_status = body.get("payment_status")
    order_id = body.get("order_id", "")

    logger.info(f"NOWPayments webhook: order={order_id} status={payment_status}")

    # Only fulfill on "finished" status
    if payment_status != "finished":
        return web.json_response({"ok": True})

    # Look up order
    pool = await queries.get_db()
    order_data = await pool.fetchval(
        "SELECT value FROM bot_settings WHERE key = $1", f"order_{order_id}"
    )
    if not order_data:
        logger.warning(f"NOWPayments webhook: unknown order {order_id}")
        return web.json_response({"ok": True})

    order = json.loads(order_data)
    user_id = order["user_id"]
    llm_quota = order["llm_quota"]
    master_balls_count = order["master_balls"]
    price_usd = order.get("price_usd", 0)

    # Fulfill rewards
    await pool.execute(
        "UPDATE users SET llm_bonus_quota = llm_bonus_quota + $2, "
        "master_balls = master_balls + $3 WHERE user_id = $1",
        user_id, llm_quota, master_balls_count,
    )

    # Update donation total
    await pool.execute(
        """INSERT INTO bot_settings (key, value) VALUES ('donation_current', $1::text)
           ON CONFLICT (key) DO UPDATE SET value = (COALESCE(bot_settings.value::int, 0) + $1)::text""",
        int(price_usd),
    )

    # Mark order as fulfilled
    await pool.execute(
        "UPDATE bot_settings SET value = $2 WHERE key = $1",
        f"order_{order_id}",
        json.dumps({**order, "fulfilled": True, "fulfilled_at": config.get_kst_now().isoformat()}),
    )

    logger.info(f"Payment fulfilled: user={user_id} llm=+{llm_quota} masterball=+{master_balls_count} ${price_usd}")
    return web.json_response({"ok": True})


# --- Donation Progress ---

DONATION_GOAL = 200  # USD

async def api_donation(request):
    """Return donation progress — sum of fulfilled order price_usd."""
    import json as _json
    pool = await queries.get_db()
    rows = await pool.fetch(
        "SELECT value FROM bot_settings WHERE key LIKE 'order_%'"
    )
    current = 0
    for r in rows:
        try:
            data = _json.loads(r["value"])
            if data.get("fulfilled"):
                current += int(data.get("price_usd", 0))
        except Exception:
            pass
    return web.json_response({"current": current, "goal": DONATION_GOAL})


def setup_routes(app):
    """Register marketplace routes."""
    app.router.add_get("/api/market/listings", api_market_listings)
    app.router.add_get("/api/market/stats", api_market_stats)
    app.router.add_get("/api/market/my-listings", api_market_my_listings)
    app.router.add_get("/api/market/my-balance", api_market_my_balance)
    app.router.add_get("/api/market/my-sellable", api_market_my_sellable)
    app.router.add_post("/api/market/sell", api_market_sell)
    app.router.add_post("/api/market/buy", api_market_buy)
    app.router.add_post("/api/market/cancel", api_market_cancel)
    # Payment & donation
    app.router.add_get("/api/donation", api_donation)
    app.router.add_post("/api/payment/create", api_payment_create)
    app.router.add_post("/api/payment/webhook", api_payment_webhook)
