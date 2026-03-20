"""Yacha (야차 - Betting Battle) handlers."""

import asyncio
import logging
import random
from datetime import timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config

from database import queries
from database import battle_queries as bq
from handlers._common import _is_duplicate_callback
from utils.helpers import icon_emoji, rarity_badge
from utils.i18n import t, get_user_lang

logger = logging.getLogger(__name__)


# ============================================================
# Yacha (야차 - Betting Battle)
# ============================================================


async def yacha_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '야차' command (group). Start a betting battle challenge."""
    if not update.effective_user or not update.message:
        return

    chat_id = update.effective_chat.id
    challenger_id = update.effective_user.id
    lang = await get_user_lang(challenger_id)
    challenger_name = update.effective_user.first_name or t(lang, "common.trainer")

    # Must reply to someone
    reply = update.message.reply_to_message
    if not reply or not reply.from_user:
        await update.message.reply_text(f"🎰 {t(lang, 'yacha.reply_hint')}")
        return

    defender_id = reply.from_user.id
    defender_name = reply.from_user.first_name or t(lang, "common.trainer")

    if challenger_id == defender_id:
        await update.message.reply_text(t(lang, "yacha.cannot_self"))
        return

    if reply.from_user.is_bot:
        await update.message.reply_text(t(lang, "yacha.cannot_bot"))
        return

    await queries.ensure_user(challenger_id, challenger_name, update.effective_user.username)
    await queries.ensure_user(defender_id, defender_name, reply.from_user.username)

    # Yacha cooldown (global 10min)
    from datetime import datetime as dt
    last_any = await bq.get_last_yacha_time_any(challenger_id)
    if last_any:
        last_time = dt.fromisoformat(last_any)
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=timezone.utc)
        cooldown = timedelta(seconds=config.YACHA_COOLDOWN)
        if dt.now(timezone.utc) - last_time < cooldown:
            remaining = cooldown - (dt.now(timezone.utc) - last_time)
            mins = int(remaining.total_seconds() // 60)
            secs = int(remaining.total_seconds() % 60)
            await update.message.reply_text(
                t(lang, "yacha.cooldown_msg", min=mins, sec=secs)
            )
            return

    # Check challenger has a team
    c_team = await bq.get_battle_team(challenger_id)
    if not c_team:
        await update.message.reply_text(f"🎰 {t(lang, 'yacha.no_team')}")
        return
    if len(c_team) < config.RANKED_TEAM_SIZE:
        await update.message.reply_text(
            f"❌ {t(lang, 'yacha.team_incomplete', count=len(c_team), required=config.RANKED_TEAM_SIZE)}"
        )
        return
    c_cost = sum(config.RANKED_COST.get(p.get("rarity", ""), 0) for p in c_team)
    if c_cost > config.RANKED_COST_LIMIT:
        await update.message.reply_text(
            f"❌ {t(lang, 'yacha.cost_over', cost=c_cost, limit=config.RANKED_COST_LIMIT)}"
        )
        return

    # Check for existing pending yacha
    existing = await bq.get_pending_challenge(challenger_id, defender_id)
    if existing:
        await update.message.reply_text(t(lang, "battle.already_pending"))
        return

    # Show bet type selection
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                t(lang, "yacha.btn_bp_bet"),
                callback_data=f"yc_bp_{challenger_id}_{defender_id}",
            ),
            InlineKeyboardButton(
                t(lang, "yacha.btn_mb_bet"),
                callback_data=f"yc_mb_{challenger_id}_{defender_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                t(lang, "battle.decline_btn"),
                callback_data=f"yc_cancel_{challenger_id}_{defender_id}",
            ),
        ],
    ])

    await update.message.reply_text(
        f"🎰 {t(lang, 'yacha.challenge_msg', challenger=challenger_name, defender=defender_name)}",
        reply_markup=buttons,
    )


async def yacha_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle yacha bet type selection (BP / Masterball / Cancel)."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data  # yc_bp_{c}_{d}, yc_mb_{c}_{d}, yc_cancel_{c}_{d}
    parts = data.split("_")
    bet_type = parts[1]  # bp, mb, cancel
    challenger_id = int(parts[2])
    defender_id = int(parts[3])
    lang = await get_user_lang(query.from_user.id)

    # Only challenger can select
    if query.from_user.id != challenger_id:
        await query.answer(t(lang, "battle.challenger_only"), show_alert=True)
        return

    await query.answer()

    if bet_type == "cancel":
        try:
            await query.edit_message_text(t(lang, "yacha.cancelled"))
        except Exception:
            pass
        return

    if bet_type == "bp":
        # Show BP amount options
        bp_buttons = []
        for amount in config.YACHA_BP_OPTIONS:
            bp_buttons.append(
                InlineKeyboardButton(
                    f"💰 {amount} BP",
                    callback_data=f"ya_bp_{amount}_{challenger_id}_{defender_id}",
                )
            )
        buttons = InlineKeyboardMarkup([
            bp_buttons,
            [InlineKeyboardButton(t(lang, "battle.decline_btn"), callback_data=f"yc_cancel_{challenger_id}_{defender_id}")],
        ])
        try:
            await query.edit_message_text(
                f"💰 {t(lang, 'yacha.bp_amount_prompt')}",
                reply_markup=buttons,
            )
        except Exception:
            pass

    elif bet_type == "mb":
        # Show masterball count options
        mb_buttons = []
        for count in config.YACHA_MASTERBALL_OPTIONS:
            mb_buttons.append(
                InlineKeyboardButton(
                    f"🔮 {count}개",
                    callback_data=f"ya_mb_{count}_{challenger_id}_{defender_id}",
                )
            )
        buttons = InlineKeyboardMarkup([
            mb_buttons,
            [InlineKeyboardButton(t(lang, "battle.decline_btn"), callback_data=f"yc_cancel_{challenger_id}_{defender_id}")],
        ])
        try:
            await query.edit_message_text(
                f"🔮 {t(lang, 'yacha.mb_amount_prompt')}",
                reply_markup=buttons,
            )
        except Exception:
            pass


async def yacha_amount_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle yacha amount selection → verify balance → create challenge."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data  # ya_bp_{amt}_{c}_{d} or ya_mb_{cnt}_{c}_{d}
    parts = data.split("_")
    bet_type_code = parts[1]  # bp or mb
    amount = int(parts[2])
    challenger_id = int(parts[3])
    defender_id = int(parts[4])
    lang = await get_user_lang(query.from_user.id)

    # Only challenger can select
    if query.from_user.id != challenger_id:
        await query.answer(t(lang, "battle.challenger_only"), show_alert=True)
        return

    await query.answer()

    bet_type = "bp" if bet_type_code == "bp" else "masterball"

    # Verify challenger has enough
    if bet_type == "bp":
        balance = await bq.get_bp(challenger_id)
        if balance < amount:
            try:
                await query.edit_message_text(
                    f"❌ {t(lang, 'yacha.bp_insufficient', have=balance, need=amount)}"
                )
            except Exception:
                pass
            return
        bet_display = f"💰 {amount} BP"
    else:  # masterball
        mb_count = await queries.get_master_balls(challenger_id)
        if mb_count < amount:
            try:
                await query.edit_message_text(
                    f"❌ {t(lang, 'yacha.mb_insufficient', have=mb_count, need=amount)}"
                )
            except Exception:
                pass
            return
        bet_display = f"🔮 {amount} {t(lang, 'item.masterball')}"

    # Create the challenge
    from datetime import datetime as dt
    expires = dt.now(timezone.utc) + timedelta(seconds=config.YACHA_CHALLENGE_TIMEOUT)

    challenge_id = await bq.create_challenge(
        challenger_id, defender_id, update.effective_chat.id, expires,
        bet_type=bet_type, bet_amount=amount,
    )

    # Get names
    c_user = await queries.get_user(challenger_id)
    d_user = await queries.get_user(defender_id)
    c_name = c_user["display_name"] if c_user else "???"
    d_name = d_user["display_name"] if d_user else "???"

    # Challenge message to defender
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                t(lang, "battle.accept_btn"),
                callback_data=f"yacha_accept_{challenge_id}_{defender_id}",
            ),
            InlineKeyboardButton(
                t(lang, "battle.decline_btn"),
                callback_data=f"yacha_decline_{challenge_id}_{defender_id}",
            ),
        ]
    ])

    try:
        await query.edit_message_text(
            t(lang, "yacha.bet_msg", challenger=c_name, defender=d_name, bet=bet_display, timeout=config.YACHA_CHALLENGE_TIMEOUT),
            reply_markup=buttons,
        )
    except Exception:
        pass


async def yacha_response_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle yacha accept/decline → deduct resources → run battle → payout."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data  # yacha_accept_{id}_{d} or yacha_decline_{id}_{d}
    parts = data.split("_")
    action = parts[1]  # accept or decline
    challenge_id = int(parts[2])
    expected_defender = int(parts[3])
    lang = await get_user_lang(query.from_user.id)

    # Only defender can respond
    if query.from_user.id != expected_defender:
        await query.answer(t(lang, "error.not_your_button"), show_alert=True)
        return

    challenge = await bq.get_challenge_by_id(challenge_id)
    if not challenge:
        try:
            await query.edit_message_text(t(lang, "yacha.challenge_not_found"))
        except Exception:
            pass
        return

    if challenge["status"] != "pending":
        try:
            await query.edit_message_text(t(lang, "yacha.already_processed"))
        except Exception:
            pass
        return

    # Check expiry
    from datetime import datetime as dt
    expires = challenge["expires_at"]
    if hasattr(expires, 'tzinfo') and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if dt.now(timezone.utc) > expires:
        await bq.update_challenge_status(challenge_id, "expired")
        try:
            await query.edit_message_text(f"⏰ {t(lang, 'yacha.expired_msg')}")
        except Exception:
            pass
        return

    await query.answer()

    if action == "decline":
        await bq.update_challenge_status(challenge_id, "declined")
        try:
            await query.edit_message_text(t(lang, "yacha.declined"))
        except Exception:
            pass
        return

    # === ACCEPT ===
    challenger_id = challenge["challenger_id"]
    bet_type = challenge["bet_type"]
    bet_amount = challenge["bet_amount"]

    # Validate teams
    d_team = await bq.get_battle_team(expected_defender)
    if not d_team:
        try:
            await query.edit_message_text(f"🎰 {t(lang, 'yacha.defender_no_team')}")
        except Exception:
            pass
        return
    if len(d_team) < config.RANKED_TEAM_SIZE:
        try:
            await query.edit_message_text(f"❌ {t(lang, 'yacha.defender_incomplete', count=len(d_team), required=config.RANKED_TEAM_SIZE)}")
        except Exception:
            pass
        return
    d_cost = sum(config.RANKED_COST.get(p.get("rarity", ""), 0) for p in d_team)
    if d_cost > config.RANKED_COST_LIMIT:
        try:
            await query.edit_message_text(f"❌ {t(lang, 'yacha.defender_cost_over', cost=d_cost, limit=config.RANKED_COST_LIMIT)}")
        except Exception:
            pass
        return

    c_team = await bq.get_battle_team(challenger_id)
    if not c_team:
        try:
            await query.edit_message_text(f"🎰 {t(lang, 'yacha.challenger_no_team')}")
        except Exception:
            pass
        return
    if len(c_team) < config.RANKED_TEAM_SIZE:
        try:
            await query.edit_message_text(f"❌ {t(lang, 'yacha.challenger_incomplete', count=len(c_team), required=config.RANKED_TEAM_SIZE)}")
        except Exception:
            pass
        return
    c_cost = sum(config.RANKED_COST.get(p.get("rarity", ""), 0) for p in c_team)
    if c_cost > config.RANKED_COST_LIMIT:
        try:
            await query.edit_message_text(f"❌ {t(lang, 'yacha.challenger_cost_over', cost=c_cost, limit=config.RANKED_COST_LIMIT)}")
        except Exception:
            pass
        return

    # Deduct resources from BOTH sides
    if bet_type == "bp":
        c_ok = await bq.spend_bp(challenger_id, bet_amount)
        if not c_ok:
            await bq.update_challenge_status(challenge_id, "expired")
            try:
                await query.edit_message_text(
                    f"❌ {t(lang, 'yacha.challenger_bp_fail')}"
                )
            except Exception:
                pass
            return
        d_ok = await bq.spend_bp(expected_defender, bet_amount)
        if not d_ok:
            # Refund challenger
            await bq.add_bp(challenger_id, bet_amount, "bet_refund")
            await bq.update_challenge_status(challenge_id, "expired")
            try:
                await query.edit_message_text(
                    f"❌ {t(lang, 'yacha.defender_bp_fail')}"
                )
            except Exception:
                pass
            return
        bet_display = f"💰 {bet_amount} BP"
        win_display = f"💰 +{bet_amount * 2} BP 획득! (베팅 {bet_amount} BP × 2)"
    else:  # masterball
        c_ok = await bq.use_master_balls(challenger_id, bet_amount)
        if not c_ok:
            await bq.update_challenge_status(challenge_id, "expired")
            try:
                await query.edit_message_text(
                    f"❌ {t(lang, 'yacha.challenger_mb_fail')}"
                )
            except Exception:
                pass
            return
        d_ok = await bq.use_master_balls(expected_defender, bet_amount)
        if not d_ok:
            # Refund challenger
            await queries.add_master_ball(challenger_id, bet_amount)
            await bq.update_challenge_status(challenge_id, "expired")
            try:
                await query.edit_message_text(
                    f"❌ {t(lang, 'yacha.defender_mb_fail')}"
                )
            except Exception:
                pass
            return
        bet_display = f"🔮 마스터볼 {bet_amount}개"
        win_display = f"🔮 마스터볼 {bet_amount * 2}개 획득! (베팅 {bet_amount}개 × 2)"

    await bq.update_challenge_status(challenge_id, "accepted")

    # Run the battle (skip_bp=True: yacha handles its own payout)
    from services.battle_service import execute_battle
    result = await execute_battle(
        challenger_id=challenger_id,
        defender_id=expected_defender,
        challenger_team=c_team,
        defender_team=d_team,
        challenge_id=challenge_id,
        chat_id=challenge["chat_id"],
        skip_bp=True,
        bot=context.bot,
    )

    # Pay the winner
    winner_id = result["winner_id"]
    if bet_type == "bp":
        await bq.add_bp(winner_id, bet_amount * 2, "bet_win")
    else:
        await queries.add_master_ball(winner_id, bet_amount * 2)

    # Get names for display
    c_user = await queries.get_user(challenger_id)
    d_user = await queries.get_user(expected_defender)
    c_name = c_user["display_name"] if c_user else "???"
    d_name = d_user["display_name"] if d_user else "???"
    winner_name = c_name if result["winner_id"] == challenger_id else d_name

    # Build yacha result message (simplified)
    vs = icon_emoji('battle')
    trophy = icon_emoji('crown')
    loser_id = result["loser_id"]
    cache_key = result["cache_key"]

    full_text = "\n".join([
        t(lang, "yacha.result_title"),
        f"{rarity_badge('red')} {c_name}  {vs}  {d_name} {rarity_badge('blue')}",
        t(lang, "yacha.bet_label", bet=bet_display),
        "━━━━━━━━━━━━━━━",
        f"{trophy} {t(lang, 'yacha.winner_msg', name=winner_name)}",
        win_display,
    ])

    # Detail / Skip / Teabag buttons
    battle_buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                t(lang, "battle.btn_detail"),
                callback_data=f"bdetail_{cache_key}_{winner_id}_{loser_id}",
            ),
            InlineKeyboardButton(
                t(lang, "battle.btn_skip"),
                callback_data=f"bskip_{winner_id}_{loser_id}",
            ),
            InlineKeyboardButton(
                t(lang, "battle.btn_teabag"),
                callback_data=f"yres_tbag_{winner_id}_{loser_id}",
            ),
        ]
    ])

    try:
        await query.edit_message_text(
            full_text,
            parse_mode="HTML",
            reply_markup=battle_buttons,
        )
    except Exception:
        try:
            await context.bot.send_message(
                chat_id=challenge["chat_id"],
                text=full_text,
                parse_mode="HTML",
                reply_markup=battle_buttons,
            )
        except Exception:
            pass


async def yacha_result_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle yacha result buttons (teabag only — detail/skip handled by battle_result_callback_handler)."""
    query = update.callback_query
    if not query or not query.data:
        return

    # 중복 클릭 방지
    if _is_duplicate_callback(query):
        await query.answer()
        return
    lang = await get_user_lang(query.from_user.id)

    data = query.data  # yres_tbag_{w}_{l}
    parts = data.split("_")
    try:
        action = parts[1]  # tbag
        winner_id = int(parts[2])
        loser_id = int(parts[3])
    except (IndexError, ValueError):
        await query.answer()
        return

    if action == "tbag":
        if query.from_user.id != winner_id:
            await query.answer(t(lang, "battle.winner_only"), show_alert=True)
            return

        from utils.honorific import honorific_name as _hon_name, _get_honorific
        from services.subscription_service import get_user_tier
        winner_user, loser_user, w_tier, l_tier = await asyncio.gather(
            queries.get_user(winner_id),
            queries.get_user(loser_id),
            get_user_tier(winner_id),
            get_user_tier(loser_id),
        )
        w_name = winner_user["display_name"] if winner_user else "???"
        l_name = loser_user["display_name"] if loser_user else "???"
        l_name = _hon_name(l_name, l_tier)

        # 승자 구독 티어에 따라 멘트풀 분기
        w_honorific = _get_honorific(w_tier)
        if w_honorific == "supreme":
            pool = config.TEABAG_MESSAGES_SUPREME
        elif w_honorific == "polite":
            pool = config.TEABAG_MESSAGES_POLITE
        else:
            pool = config.YACHA_TEABAG_MESSAGES

        await query.answer()

        # Remove only the teabag button, keep detail/skip
        try:
            old_kb = query.message.reply_markup
            if old_kb:
                new_rows = []
                for row in old_kb.inline_keyboard:
                    new_btns = [b for b in row if not (b.callback_data and b.callback_data.startswith("yres_tbag"))]
                    if new_btns:
                        new_rows.append(new_btns)
                await query.edit_message_reply_markup(
                    reply_markup=InlineKeyboardMarkup(new_rows) if new_rows else None
                )
        except Exception:
            pass

        # Send random yacha teabag message
        msg = random.choice(pool).format(
            winner=w_name, loser=l_name,
        )
        msg = msg.replace("님님", "님")
        msg = msg.replace("💀", icon_emoji("skull"))
        try:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=msg,
                parse_mode="HTML",
            )
        except Exception:
            pass
