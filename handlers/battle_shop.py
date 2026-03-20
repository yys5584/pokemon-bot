"""Battle shop handlers: BP balance, shop, purchases, tier list, battle stats."""

import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config

from database import queries, spawn_queries, market_queries
from database import battle_queries as bq
from utils.battle_calc import calc_battle_stats, EVO_STAGE_MAP, get_normalized_base_stats
from utils.helpers import escape_html, rarity_badge, type_badge, icon_emoji, ball_emoji
from utils.i18n import t, get_user_lang, poke_name

logger = logging.getLogger(__name__)


# ============================================================
# Battle Stats (/배틀전적, /BP)
# ============================================================

async def battle_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 배틀전적 command (DM). Show user's battle record + ranked info."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    stats = await bq.get_battle_stats(user_id)

    wins = stats["battle_wins"]
    losses = stats["battle_losses"]
    total = wins + losses
    win_rate = round(wins / total * 100, 1) if total > 0 else 0

    lines = [
        f"{icon_emoji('battle')} <b>{t(lang, 'battle.my_record_title')}</b>\n",
        f"🏆 {t(lang, 'battle.wins_losses', wins=wins, losses=losses, rate=win_rate)}",
        f"🔥 {t(lang, 'battle.current_streak', n=stats['battle_streak'])}",
        f"💫 {t(lang, 'battle.best_streak_label', n=stats['best_streak'])}",
        f"{icon_emoji('coin')} {t(lang, 'battle.bp_balance', bp=stats['battle_points'])}",
    ]

    # Season ranked info
    try:
        from services import ranked_service as rs
        from database import ranked_queries as rq
        season = await rq.get_current_season()
        if season:
            rec = await rq.get_season_record(user_id, season["season_id"])
            if rec:
                tier_full = rs.tier_display_full(rec)
                r_total = rec["ranked_wins"] + rec["ranked_losses"]
                r_wr = round(rec["ranked_wins"] / r_total * 100, 1) if r_total > 0 else 0
                lines.extend([
                    "",
                    f"🏟️ {t(lang, 'ranked.season_title', id=season['season_id'])}",
                    f"{tier_full}",
                    f"{t(lang, 'battle.wins_losses', wins=rec['ranked_wins'], losses=rec['ranked_losses'], rate=r_wr)}",
                ])
                mmr_rec = await rq.get_user_mmr(user_id)
                lines.append(f"📊 MMR: {mmr_rec['mmr']}")
    except Exception:
        pass

    lines.append(f"\n💡 {t(lang, 'battle.ranked_hint')}")

    buttons = [[InlineKeyboardButton(t(lang, "battle.ranked_challenge_btn"), callback_data=f"ranked_auto_{user_id}")]]
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
    )


async def bp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle BP command (DM). Show BP balance."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    bp = await bq.get_bp(user_id)
    await update.message.reply_text(f"{icon_emoji('coin')} {t(lang, 'battle.bp_balance', bp=bp)}\n\n{t(lang, 'battle.bp_exchange_hint')}", parse_mode="HTML")


def _masterball_price(bought_today: int) -> int:
    """Progressive master ball pricing."""
    prices = config.BP_MASTERBALL_PRICES
    if bought_today >= len(prices):
        return 0  # sold out
    return prices[bought_today]


async def bp_shop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle BP상점/상점 command (DM). Show BP shop."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    bp, bought_today, tickets, hyper_balls, arcade_tickets = await asyncio.gather(
        bq.get_bp(user_id),
        bq.get_bp_purchases_today(user_id, "masterball"),
        queries.get_force_spawn_tickets(user_id),
        queries.get_hyper_balls(user_id),
        queries.get_arcade_tickets(user_id),
    )

    remaining = config.BP_MASTERBALL_DAILY_LIMIT - bought_today
    next_price = _masterball_price(bought_today)
    price_str = f"{next_price} BP" if next_price else t(lang, "shop.sold_out")

    fst_label = t(lang, "shop.free_label") if config.BP_FORCE_SPAWN_TICKET_COST == 0 else f"{config.BP_FORCE_SPAWN_TICKET_COST} BP"
    pb_label = t(lang, "shop.free_label") if config.BP_POKEBALL_RESET_COST == 0 else f"{config.BP_POKEBALL_RESET_COST} BP"

    lines = [
        f"{icon_emoji('shopping-bag')} {t(lang, 'shop.shop_header')}\n",
        f"{icon_emoji('coin')} {t(lang, 'shop.bp_owned', bp=bp)}\n",
        f"{ball_emoji('masterball')} {t(lang, 'shop.masterball_item', price=price_str, remaining=remaining, limit=config.BP_MASTERBALL_DAILY_LIMIT)}",
        f"{icon_emoji('bolt')} {t(lang, 'shop.forcespawn_item', price=fst_label, count=tickets)}",
        f"{ball_emoji('pokeball')} {t(lang, 'shop.pokeball_reset_item', price=pb_label)}",
        f"{ball_emoji('hyperball')} {t(lang, 'shop.hyperball_item', price=config.BP_HYPER_BALL_COST * 3, count=hyper_balls)}",
        f"🎮 {t(lang, 'shop.arcade_item', price=config.ARCADE_PASS_COST, count=arcade_tickets)}",
    ]

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t(lang, "shop.btn_masterball", price=price_str), callback_data="shop_masterball"),
            InlineKeyboardButton(t(lang, "shop.btn_forcespawn"), callback_data="shop_forcespawn"),
        ],
        [
            InlineKeyboardButton(t(lang, "shop.btn_pokeball_reset"), callback_data="shop_pokeball"),
            InlineKeyboardButton(t(lang, "shop.btn_hyperball3", price=config.BP_HYPER_BALL_COST * 3), callback_data="shop_hyperball3"),
        ],
        [
            InlineKeyboardButton(t(lang, "shop.btn_arcade"), callback_data="shop_arcade"),
        ],
        [
            InlineKeyboardButton(t(lang, "shop.btn_market"), callback_data="shop_market"),
        ],
    ])

    await update.message.reply_text("\n".join(lines), reply_markup=buttons, parse_mode="HTML")


async def bp_buy_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 구매/BP구매 command (DM). Purchase from BP shop."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    text = (update.message.text or "").strip()
    parts = text.split()

    if len(parts) < 2:
        await update.message.reply_text(t(lang, "shop.buy_usage"))
        return

    item = parts[1]
    if item in ("마스터볼", "마볼"):
        bought_today = await bq.get_bp_purchases_today(user_id, "masterball")
        if bought_today >= config.BP_MASTERBALL_DAILY_LIMIT:
            await update.message.reply_text(
                f"🚫 {t(lang, 'shop.buy_masterball_limit', limit=config.BP_MASTERBALL_DAILY_LIMIT)}"
            )
            return

        cost = _masterball_price(bought_today)
        success = await bq.spend_bp(user_id, cost)
        if not success:
            bp = await bq.get_bp(user_id)
            await update.message.reply_text(
                t(lang, "shop.bp_insufficient", have=bp, need=cost)
            )
            return

        await queries.add_master_ball(user_id, 1)
        await bq.log_bp_purchase(user_id, "masterball", 1)
        remaining = config.BP_MASTERBALL_DAILY_LIMIT - bought_today - 1
        bp = await bq.get_bp(user_id)
        next_price = _masterball_price(bought_today + 1)
        next_str = t(lang, "shop.buy_masterball_next", price=next_price) if next_price else ""
        await update.message.reply_text(
            f"{ball_emoji('masterball')} {t(lang, 'shop.buy_masterball_ok', cost=cost, bp=bp, remaining=remaining, next=next_str)}",
            parse_mode="HTML",
        )

    elif item in ("강제스폰", "강스", "강제스폰권", "강스권"):
        cost = config.BP_FORCE_SPAWN_TICKET_COST
        success = await bq.spend_bp(user_id, cost)
        if not success:
            bp = await bq.get_bp(user_id)
            await update.message.reply_text(
                t(lang, "shop.bp_insufficient", have=bp, need=cost)
            )
            return

        await queries.add_force_spawn_ticket(user_id)
        await bq.log_bp_purchase(user_id, "force_spawn_ticket", 1)
        bp = await bq.get_bp(user_id)
        tickets = await queries.get_force_spawn_tickets(user_id)
        await update.message.reply_text(
            f"{icon_emoji('bolt')} {t(lang, 'shop.buy_forcespawn_ok', bp=bp, count=tickets)}",
            parse_mode="HTML",
        )

    elif item in ("포켓볼", "볼"):
        cost = config.BP_POKEBALL_RESET_COST
        success = await bq.spend_bp(user_id, cost)
        if not success:
            bp = await bq.get_bp(user_id)
            await update.message.reply_text(
                t(lang, "shop.bp_insufficient", have=bp, need=cost)
            )
            return

        today = config.get_kst_today()
        await spawn_queries.reset_bonus_catches(user_id, today)
        await bq.log_bp_purchase(user_id, "pokeball_reset", 1)
        bp = await bq.get_bp(user_id)
        await update.message.reply_text(
            f"{ball_emoji('pokeball')} {t(lang, 'shop.buy_pokeball_ok', bp=bp)}",
            parse_mode="HTML"
        )

    elif item in ("하이퍼볼", "하이퍼", "ㅎ"):
        # Support quantity: 구매 하이퍼볼 5
        qty = 1
        if len(parts) >= 3:
            try:
                qty = max(1, int(parts[2]))
            except ValueError:
                qty = 1

        cost = config.BP_HYPER_BALL_COST * qty
        success = await bq.spend_bp(user_id, cost)
        if not success:
            bp = await bq.get_bp(user_id)
            await update.message.reply_text(
                t(lang, "shop.bp_insufficient", have=bp, need=cost)
            )
            return

        await queries.add_hyper_ball(user_id, qty)
        await bq.log_bp_purchase(user_id, "hyper_ball", qty)
        bp = await bq.get_bp(user_id)
        hyper_balls = await queries.get_hyper_balls(user_id)
        await update.message.reply_text(
            f"{ball_emoji('hyperball')} {t(lang, 'shop.buy_hyperball_ok', qty=qty, cost=cost, bp=bp, count=hyper_balls)}",
            parse_mode="HTML",
        )

    elif item in ("아케이드", "이용권", "아케이드이용권", "아케이드티켓", "티켓"):
        # Buy arcade ticket (inventory item, use in group with '아케이드 등록')
        cost = config.ARCADE_PASS_COST
        success = await bq.spend_bp(user_id, cost)
        if not success:
            bp = await bq.get_bp(user_id)
            await update.message.reply_text(
                t(lang, "shop.bp_insufficient", have=bp, need=cost)
            )
            return

        await queries.add_arcade_ticket(user_id)
        await bq.log_bp_purchase(user_id, "arcade_ticket", 1)
        bp = await bq.get_bp(user_id)
        tickets = await queries.get_arcade_tickets(user_id)
        await update.message.reply_text(
            f"🎮 {t(lang, 'shop.buy_arcade_ok', cost=cost, bp=bp, count=tickets, minutes=config.ARCADE_PASS_DURATION // 60)}",
            parse_mode="HTML",
        )

    else:
        await update.message.reply_text(t(lang, "shop.unknown_item"))


async def shop_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle shop inline button purchases."""
    query = update.callback_query
    if not query or not query.data:
        return

    user_id = query.from_user.id
    lang = await get_user_lang(user_id)
    item_key = query.data.replace("shop_", "")

    # Map callback to item name for bp_buy logic
    item_map = {
        "masterball": "마스터볼",
        "forcespawn": "강제스폰",
        "pokeball": "포켓볼",
        "hyperball": "하이퍼볼",
        "hyperball3": "하이퍼볼3",
        "arcade": "아케이드",
    }
    # 거래소 바로가기
    if item_key == "market":
        await query.answer()
        from handlers.dm_market import _build_listing_page
        listings, total = await market_queries.get_active_listings(page=0, page_size=config.MARKET_PAGE_SIZE)
        text_msg, markup = _build_listing_page(listings, total, 0, config.MARKET_PAGE_SIZE)
        await query.message.reply_text(text_msg, reply_markup=markup, parse_mode="HTML")
        return

    item = item_map.get(item_key)
    if not item:
        await query.answer(t(lang, "shop.unknown_item"), show_alert=True)
        return

    # --- Purchase logic (same as bp_buy_handler) ---
    if item == "마스터볼":
        bought_today = await bq.get_bp_purchases_today(user_id, "masterball")
        if bought_today >= config.BP_MASTERBALL_DAILY_LIMIT:
            await query.answer(t(lang, "shop.popup_masterball_limit", limit=config.BP_MASTERBALL_DAILY_LIMIT), show_alert=True)
            return
        cost = _masterball_price(bought_today)
        success = await bq.spend_bp(user_id, cost)
        if not success:
            bp = await bq.get_bp(user_id)
            await query.answer(t(lang, "shop.popup_bp_insufficient", have=bp, need=cost), show_alert=True)
            return
        await queries.add_master_ball(user_id, 1)
        await bq.log_bp_purchase(user_id, "masterball", 1)
        remaining = config.BP_MASTERBALL_DAILY_LIMIT - bought_today - 1
        bp = await bq.get_bp(user_id)
        await query.answer(t(lang, "shop.popup_masterball_ok", cost=cost, bp=bp), show_alert=True)

    elif item == "강제스폰":
        cost = config.BP_FORCE_SPAWN_TICKET_COST
        success = await bq.spend_bp(user_id, cost)
        if not success:
            bp = await bq.get_bp(user_id)
            await query.answer(t(lang, "shop.popup_bp_insufficient", have=bp, need=cost), show_alert=True)
            return
        await queries.add_force_spawn_ticket(user_id)
        await bq.log_bp_purchase(user_id, "force_spawn_ticket", 1)
        bp = await bq.get_bp(user_id)
        await query.answer(t(lang, "shop.popup_forcespawn_ok", bp=bp), show_alert=True)

    elif item == "포켓볼":
        cost = config.BP_POKEBALL_RESET_COST
        success = await bq.spend_bp(user_id, cost)
        if not success:
            bp = await bq.get_bp(user_id)
            await query.answer(t(lang, "shop.popup_bp_insufficient", have=bp, need=cost), show_alert=True)
            return
        today = config.get_kst_today()
        await spawn_queries.reset_bonus_catches(user_id, today)
        await bq.log_bp_purchase(user_id, "pokeball_reset", 1)
        bp = await bq.get_bp(user_id)
        await query.answer(t(lang, "shop.popup_pokeball_ok", bp=bp), show_alert=True)

    elif item in ("하이퍼볼", "하이퍼볼3"):
        qty = 3 if item == "하이퍼볼3" else 1
        cost = config.BP_HYPER_BALL_COST * qty
        success = await bq.spend_bp(user_id, cost)
        if not success:
            bp = await bq.get_bp(user_id)
            await query.answer(t(lang, "shop.popup_bp_insufficient", have=bp, need=cost), show_alert=True)
            return
        await queries.add_hyper_ball(user_id, qty)
        await bq.log_bp_purchase(user_id, "hyper_ball", qty)
        bp = await bq.get_bp(user_id)
        hyper_balls = await queries.get_hyper_balls(user_id)
        await query.answer(t(lang, "shop.popup_hyperball_ok", qty=qty, count=hyper_balls, bp=bp), show_alert=True)

    elif item == "아케이드":
        cost = config.ARCADE_PASS_COST
        success = await bq.spend_bp(user_id, cost)
        if not success:
            bp = await bq.get_bp(user_id)
            await query.answer(t(lang, "shop.popup_bp_insufficient", have=bp, need=cost), show_alert=True)
            return
        await asyncio.gather(
            queries.add_arcade_ticket(user_id),
            bq.log_bp_purchase(user_id, "arcade_ticket", 1),
        )
        bp, tickets = await asyncio.gather(bq.get_bp(user_id), queries.get_arcade_tickets(user_id))
        await query.answer(t(lang, "shop.popup_arcade_ok", count=tickets, bp=bp), show_alert=True)

    # Refresh shop display after purchase
    try:
        bought_today, bp, tickets, hyper_balls, arcade_tickets = await asyncio.gather(
            bq.get_bp_purchases_today(user_id, "masterball"),
            bq.get_bp(user_id),
            queries.get_force_spawn_tickets(user_id),
            queries.get_hyper_balls(user_id),
            queries.get_arcade_tickets(user_id),
        )
        remaining = config.BP_MASTERBALL_DAILY_LIMIT - bought_today
        next_price = _masterball_price(bought_today)
        price_str = f"{next_price} BP" if next_price else t(lang, "shop.sold_out")
        fst_label = t(lang, "shop.free_label") if config.BP_FORCE_SPAWN_TICKET_COST == 0 else f"{config.BP_FORCE_SPAWN_TICKET_COST} BP"
        pb_label = t(lang, "shop.free_label") if config.BP_POKEBALL_RESET_COST == 0 else f"{config.BP_POKEBALL_RESET_COST} BP"

        lines = [
            f"{icon_emoji('shopping-bag')} {t(lang, 'shop.shop_header')}\n",
            f"{icon_emoji('coin')} {t(lang, 'shop.bp_owned', bp=bp)}\n",
            f"{ball_emoji('masterball')} {t(lang, 'shop.masterball_item', price=price_str, remaining=remaining, limit=config.BP_MASTERBALL_DAILY_LIMIT)}",
            f"{icon_emoji('bolt')} {t(lang, 'shop.forcespawn_item', price=fst_label, count=tickets)}",
            f"{ball_emoji('pokeball')} {t(lang, 'shop.pokeball_reset_item', price=pb_label)}",
            f"{ball_emoji('hyperball')} {t(lang, 'shop.hyperball_item', price=config.BP_HYPER_BALL_COST * 3, count=hyper_balls)}",
            f"{icon_emoji('game')} {t(lang, 'shop.arcade_item', price=config.ARCADE_PASS_COST, count=arcade_tickets)}",
        ]

        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(t(lang, "shop.btn_masterball", price=price_str), callback_data="shop_masterball"),
                InlineKeyboardButton(t(lang, "shop.btn_forcespawn"), callback_data="shop_forcespawn"),
            ],
            [
                InlineKeyboardButton(t(lang, "shop.btn_pokeball_reset"), callback_data="shop_pokeball"),
                InlineKeyboardButton(t(lang, "shop.btn_hyperball3", price=config.BP_HYPER_BALL_COST * 3), callback_data="shop_hyperball3"),
            ],
            [
                InlineKeyboardButton(t(lang, "shop.btn_arcade"), callback_data="shop_arcade"),
            ],
        ])

        await query.edit_message_text("\n".join(lines), reply_markup=buttons, parse_mode="HTML")
    except Exception:
        pass


# ============================================================
# Battle Tier List
# ============================================================

# Cache tier list (computed once, cleared on restart)
_tier_cache: str | None = None


async def tier_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '티어' command (DM). Show battle tier list for epic+ pokemon."""
    global _tier_cache

    if _tier_cache:
        await update.message.reply_text(_tier_cache, parse_mode="HTML")
        return

    # Fetch all pokemon — final evolution only (same logic as dashboard)
    from database.connection import get_db
    from models.pokemon_skills import POKEMON_SKILLS

    pool = await get_db()
    rows = await pool.fetch("""
        SELECT id, name_ko, emoji, rarity, pokemon_type, stat_type, evolves_to
        FROM pokemon_master ORDER BY id
    """)

    final_evos = [r for r in rows if r["evolves_to"] is None]

    scored = []
    for r in final_evos:
        base = get_normalized_base_stats(r["id"])
        stats = calc_battle_stats(
            r["rarity"], r["stat_type"], 5,
            evo_stage=3 if base else EVO_STAGE_MAP.get(r["id"], 3),
            **(base or {}),
        )
        from models.pokemon_skills import get_max_skill_power
        _skill_pow = get_max_skill_power(r["id"])

        best_atk = max(stats["atk"], stats["spa"])
        eff_def = (stats["def"] + stats["spdef"]) / 2
        eff_atk = best_atk * (1 + config.BATTLE_SKILL_RATE * _skill_pow)
        eff_tank = stats["hp"] * (1 + eff_def * 0.003)
        power = round(eff_atk * eff_tank / 1000, 1)

        tb = type_badge(r["id"], r["pokemon_type"])
        scored.append({
            "name": r["name_ko"], "rarity": r["rarity"],
            "type_emoji": tb, "power": power,
            "hp": stats["hp"], "atk": stats["atk"],
            "def": stats["def"], "spd": stats["spd"],
        })

    scored.sort(key=lambda x: -x["power"])
    top20 = scored[:20]

    lang = await get_user_lang(update.effective_user.id) if update.effective_user else "ko"
    lines = [f"{icon_emoji('battle')} <b>{t(lang, 'battle.tier_title')}</b> ({t(lang, 'battle.tier_top')})"]
    lines.append("━━━━━━━━━━━━━━━━━━━━\n")

    for rank, p in enumerate(top20, 1):
        rb = rarity_badge(p["rarity"])
        trap = f" {t(lang, 'battle.tier_trap')}" if p["atk"] < 40 else ""
        lines.append(
            f"{rank}. {rb}{p['type_emoji']}<b>{p['name']}</b>{trap}  "
            f"{t(lang, 'battle.tier_stat_hp')}{p['hp']} {t(lang, 'battle.tier_stat_atk')}{p['atk']} {t(lang, 'battle.tier_stat_def')}{p['def']} {t(lang, 'battle.tier_stat_spd')}{p['spd']}  "
            f"{icon_emoji('bolt')}{p['power']}"
        )

    lines.append("\n─────────────────")
    lines.append(f"💡 {t(lang, 'battle.tier_note_base')}")
    lines.append(f"💡 {t(lang, 'battle.tier_note_matchup')}")

    _tier_cache = "\n".join(lines)
    await update.message.reply_text(_tier_cache, parse_mode="HTML")
