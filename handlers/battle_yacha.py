"""Yacha (야차 - Betting Battle) handlers.

개편 v2: "야차" 답장 → 상대에게 [수락 100BP] [거절] → 즉시 배틀.
- 고정 100BP 베팅 (마볼 베팅 제거)
- 같은 상대 하루 3판 제한 (어뷰징 방지)
"""

import asyncio
import logging
import random
from datetime import datetime as dt, timedelta, timezone

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
# Yacha (야차 - Betting Battle) v2
# ============================================================


async def _get_yacha_pair_count_today(pool, user_a: int, user_b: int) -> int:
    """오늘 두 유저 간 야차 횟수 (양방향 합산)."""
    row = await pool.fetchrow(
        """SELECT COUNT(*) as cnt FROM battle_records
           WHERE battle_type = 'yacha'
             AND created_at >= (NOW() AT TIME ZONE 'Asia/Seoul')::date AT TIME ZONE 'Asia/Seoul'
             AND ((winner_id = $1 AND loser_id = $2) OR (winner_id = $2 AND loser_id = $1))""",
        user_a, user_b,
    )
    return row["cnt"] if row else 0


async def yacha_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '야차' command (group). 바로 상대에게 수락/거절 전송."""
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
    last_any = await bq.get_last_yacha_time_any(challenger_id)
    if last_any:
        last_time = dt.fromisoformat(last_any) if isinstance(last_any, str) else last_any
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

    # 같은 상대 하루 제한 체크
    from database.connection import get_db
    pool = await get_db()
    pair_count = await _get_yacha_pair_count_today(pool, challenger_id, defender_id)
    limit = config.YACHA_SAME_OPPONENT_DAILY_LIMIT
    if pair_count >= limit:
        await update.message.reply_text(
            f"🎰 오늘 이 상대와는 더 이상 야차를 할 수 없습니다 ({pair_count}/{limit})"
        )
        return

    # Check challenger BP
    bet_amount = config.YACHA_BET_AMOUNT
    balance = await bq.get_bp(challenger_id)
    if balance < bet_amount:
        await update.message.reply_text(
            f"❌ {t(lang, 'yacha.bp_insufficient', have=balance, need=bet_amount)}"
        )
        return

    # Create challenge & send accept/decline to defender
    expires = dt.now(timezone.utc) + timedelta(seconds=config.YACHA_CHALLENGE_TIMEOUT)
    challenge_id = await bq.create_challenge(
        challenger_id, defender_id, chat_id, expires,
        bet_type="bp", bet_amount=bet_amount,
    )

    c_user = await queries.get_user(challenger_id)
    d_user = await queries.get_user(defender_id)
    c_name = c_user["display_name"] if c_user else "???"
    d_name = d_user["display_name"] if d_user else "???"

    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            f"수락 {bet_amount}BP",
            callback_data=f"yacha_accept_{challenge_id}_{defender_id}",
        ),
        InlineKeyboardButton(
            "거절",
            callback_data=f"yacha_decline_{challenge_id}_{defender_id}",
        ),
    ]])

    await update.message.reply_text(
        f"🎰 <b>{c_name}</b>님이 <b>{d_name}</b>님에게 야차 대결! (💰 {bet_amount} BP)\n"
        f"⏰ {config.YACHA_CHALLENGE_TIMEOUT}초 내에 수락해주세요!",
        parse_mode="HTML",
        reply_markup=buttons,
    )


async def yacha_response_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle yacha accept/decline → deduct BP → run battle → payout."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data  # yacha_accept_{id}_{d} or yacha_decline_{id}_{d}
    parts = data.split("_")
    action = parts[1]  # accept or decline
    challenge_id = int(parts[2])
    expected_defender = int(parts[3])
    # Only defender can respond
    if query.from_user.id != expected_defender:
        lang = await get_user_lang(query.from_user.id)
        await query.answer(t(lang, "error.not_your_button"), show_alert=True)
        return

    await query.answer()
    lang = await get_user_lang(query.from_user.id)

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

    if action == "decline":
        await bq.update_challenge_status(challenge_id, "declined")
        try:
            await query.edit_message_text(t(lang, "yacha.declined"))
        except Exception:
            pass
        return

    # === ACCEPT ===
    challenger_id = challenge["challenger_id"]
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
            await query.edit_message_text(
                f"❌ {t(lang, 'yacha.defender_incomplete', count=len(d_team), required=config.RANKED_TEAM_SIZE)}"
            )
        except Exception:
            pass
        return
    d_cost = sum(config.RANKED_COST.get(p.get("rarity", ""), 0) for p in d_team)
    if d_cost > config.RANKED_COST_LIMIT:
        try:
            await query.edit_message_text(
                f"❌ {t(lang, 'yacha.defender_cost_over', cost=d_cost, limit=config.RANKED_COST_LIMIT)}"
            )
        except Exception:
            pass
        return

    c_team = await bq.get_battle_team(challenger_id)
    if not c_team or len(c_team) < config.RANKED_TEAM_SIZE:
        try:
            await query.edit_message_text(f"🎰 {t(lang, 'yacha.challenger_no_team')}")
        except Exception:
            pass
        return
    c_cost = sum(config.RANKED_COST.get(p.get("rarity", ""), 0) for p in c_team)
    if c_cost > config.RANKED_COST_LIMIT:
        try:
            await query.edit_message_text(
                f"❌ {t(lang, 'yacha.challenger_cost_over', cost=c_cost, limit=config.RANKED_COST_LIMIT)}"
            )
        except Exception:
            pass
        return

    # Deduct BP from BOTH sides
    c_ok = await bq.spend_bp(challenger_id, bet_amount)
    if not c_ok:
        await bq.update_challenge_status(challenge_id, "expired")
        try:
            await query.edit_message_text(f"❌ {t(lang, 'yacha.challenger_bp_fail')}")
        except Exception:
            pass
        return

    d_ok = await bq.spend_bp(expected_defender, bet_amount)
    if not d_ok:
        await bq.add_bp(challenger_id, bet_amount, "bet_refund")
        await bq.update_challenge_status(challenge_id, "expired")
        try:
            await query.edit_message_text(f"❌ {t(lang, 'yacha.defender_bp_fail')}")
        except Exception:
            pass
        return

    await bq.update_challenge_status(challenge_id, "accepted")

    # Run the battle
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
    await bq.add_bp(winner_id, bet_amount * 2, "bet_win")

    # Display result
    c_user = await queries.get_user(challenger_id)
    d_user = await queries.get_user(expected_defender)
    c_name = c_user["display_name"] if c_user else "???"
    d_name = d_user["display_name"] if d_user else "???"
    winner_name = c_name if winner_id == challenger_id else d_name

    vs = icon_emoji('battle')
    trophy = icon_emoji('crown')
    loser_id = result["loser_id"]
    cache_key = result["cache_key"]

    full_text = "\n".join([
        t(lang, "yacha.result_title"),
        f"{rarity_badge('red')} {c_name}  {vs}  {d_name} {rarity_badge('blue')}",
        t(lang, "yacha.bet_label", bet=f"💰 {bet_amount} BP"),
        "━━━━━━━━━━━━━━━",
        f"{trophy} {t(lang, 'yacha.winner_msg', name=winner_name)}",
        f"💰 +{bet_amount * 2} BP 획득!",
    ])

    battle_buttons = InlineKeyboardMarkup([[
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
    ]])

    try:
        await query.edit_message_text(
            full_text, parse_mode="HTML", reply_markup=battle_buttons,
        )
    except Exception:
        try:
            await context.bot.send_message(
                chat_id=challenge["chat_id"],
                text=full_text, parse_mode="HTML", reply_markup=battle_buttons,
            )
        except Exception:
            pass


async def yacha_result_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle yacha teabag button."""
    query = update.callback_query
    if not query or not query.data:
        return

    if _is_duplicate_callback(query):
        await query.answer()
        return
    lang = await get_user_lang(query.from_user.id)

    data = query.data  # yres_tbag_{w}_{l}
    parts = data.split("_")
    try:
        action = parts[1]
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

        w_honorific = _get_honorific(w_tier)
        if w_honorific == "supreme":
            pool = config.TEABAG_MESSAGES_SUPREME
        elif w_honorific == "polite":
            pool = config.TEABAG_MESSAGES_POLITE
        else:
            pool = config.YACHA_TEABAG_MESSAGES

        await query.answer()

        # Remove teabag button
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

        msg = random.choice(pool).format(winner=w_name, loser=l_name)
        msg = msg.replace("님님", "님")
        msg = msg.replace("💀", icon_emoji("skull"))
        try:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=msg, parse_mode="HTML",
            )
        except Exception:
            pass
