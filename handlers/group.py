"""Group chat handlers: catch (ㅊ), /랭킹, /로그, activity tracking."""

import asyncio
import logging
import random
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

import config
from database import queries
from services.catch_service import can_attempt_catch, record_attempt
from utils.helpers import time_ago, rarity_display, escape_html, get_decorated_name

logger = logging.getLogger(__name__)


async def close_message_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle ❌ button press — delete the bot message to reduce scroll clutter."""
    query = update.callback_query
    if not query:
        return
    try:
        await query.message.delete()
    except Exception:
        # If delete fails (permissions, too old, etc.), just dismiss the callback
        await query.answer("메시지를 삭제할 수 없습니다.")
        return
    await query.answer()


async def on_chat_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Track message activity for spawn eligibility. Runs for every group message."""
    if not update.effective_chat or not update.effective_message:
        return

    chat_id = update.effective_chat.id
    hour_bucket = datetime.now().strftime("%Y-%m-%d-%H")

    try:
        await queries.increment_activity(chat_id, hour_bucket)

        # Ensure chat room is registered
        await queries.ensure_chat_room(
            chat_id,
            title=update.effective_chat.title,
        )
    except Exception as e:
        logger.error(f"Activity tracking failed: {e}")


async def catch_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'ㅊ' message in group chat — attempt to catch a Pokemon."""
    if not update.effective_user or not update.effective_chat:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    display_name = update.effective_user.first_name or "트레이너"
    username = update.effective_user.username

    try:
        # Ensure user is registered
        await queries.ensure_user(user_id, display_name, username)

        # Update login streak for title tracking
        await queries.update_login_streak(user_id)

        # Check for active spawn
        session = await queries.get_active_spawn(chat_id)
        if session is None:
            logger.debug(f"ㅊ by {user_id} in {chat_id}: no active spawn")
            return  # No active spawn, silently ignore

        # Check if already attempted this session
        already = await queries.has_attempted_session(session["id"], user_id)
        if already:
            logger.debug(f"ㅊ by {user_id}: already attempted session {session['id']}")
            return  # Silently ignore duplicate

        # Check catch limits
        allowed, reason = await can_attempt_catch(user_id)
        if not allowed:
            logger.info(f"ㅊ by {user_id}: blocked - {reason}")
            await update.message.reply_text(reason)
            return

        # Record attempt
        await record_attempt(session["id"], user_id)
        logger.info(f"ㅊ by {user_id}: attempt recorded for session {session['id']}")

        # Show decorated name with title (HTML bold for titled users)
        user = await queries.get_user(user_id)
        decorated = get_decorated_name(
            display_name,
            user.get("title", "") if user else "",
            user.get("title_emoji", "") if user else "",
            username,
            html=True,
        )

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎯 {decorated} 도전!",
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"Catch handler error: {e}")


async def master_ball_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'ㅁ' message in group chat — use master ball for guaranteed catch."""
    if not update.effective_user or not update.effective_chat:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    display_name = update.effective_user.first_name or "트레이너"
    username = update.effective_user.username

    try:
        await queries.ensure_user(user_id, display_name, username)

        # Check for active spawn
        session = await queries.get_active_spawn(chat_id)
        if session is None:
            return

        # Check if already attempted
        already = await queries.has_attempted_session(session["id"], user_id)
        if already:
            return

        # Check if user has master balls
        balls = await queries.get_master_balls(user_id)
        if balls < 1:
            await update.message.reply_text("🟣 마스터볼이 없습니다!")
            return

        # Use master ball
        used = await queries.use_master_ball(user_id)
        if not used:
            return

        # Record attempt with master ball flag
        await queries.record_catch_attempt(session["id"], user_id, used_master_ball=True)

        remaining = balls - 1
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🟣 {display_name} 마스터볼 투척! (남은 마스터볼: {remaining}개)",
        )

    except Exception as e:
        logger.error(f"Master ball handler error: {e}")


_love_cooldown = {}  # user_id -> last_used timestamp

async def love_easter_egg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '포켓볼 충전' — grants +10 bonus catches for today."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    display_name = update.effective_user.first_name or "트레이너"
    now = datetime.now()

    # 30 second cooldown per user (anti-spam)
    last_used = _love_cooldown.get(user_id)
    if last_used and (now - last_used).total_seconds() < 30:
        return  # Silently ignore spam
    _love_cooldown[user_id] = now

    today = now.strftime("%Y-%m-%d")

    # Combine ensure_user + add_bonus in parallel where possible
    await queries.ensure_user(user_id, display_name, update.effective_user.username)

    # Check cap (max 100 bonus)
    bonus = await queries.get_bonus_catches(user_id, today)
    if bonus >= 100:
        await update.message.reply_text("🔴 오늘 포켓볼 충전 한도를 모두 사용했어요! (최대 100회)")
        return

    # Grant +10 bonus catches
    await queries.add_bonus_catches(user_id, today, 10)
    bonus = min(bonus + 10, 100)
    total = config.MAX_CATCH_ATTEMPTS_PER_DAY + bonus

    # Reply FIRST (fast response)
    await update.message.reply_text(
        f"🔴 포켓볼 충전 완료!\n"
        f"🎁 {display_name}의 오늘 잡기 횟수 +10! (총 {total}회)",
    )

    # Title tracking in background (non-blocking)
    async def _bg_title_check():
        try:
            await queries.increment_title_stat(user_id, "love_count")
            from utils.title_checker import check_and_unlock_titles
            new_titles = await check_and_unlock_titles(user_id)
            if new_titles:
                title_msg = "\n".join(f"🎉 새 칭호 해금! 「{temoji} {tname}」" for _, tname, temoji in new_titles)
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"🏷️ {display_name}의 {title_msg}",
                )
        except Exception:
            pass
    asyncio.create_task(_bg_title_check())


# Hidden easter egg: 문유 사랑해 → random master ball (max 3/day GLOBAL)
_love_hidden_cooldown = {}   # user_id -> last_used timestamp
_love_hidden_global = {}     # date_str -> master ball count today (global)

async def love_hidden_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hidden '문유 사랑해' — random master ball drop, max 3 per day globally."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    display_name = update.effective_user.first_name or "트레이너"
    now = datetime.now()

    # 30 second cooldown (prevent spam from blocking bot)
    last_used = _love_hidden_cooldown.get(user_id)
    if last_used and (now - last_used).total_seconds() < 30:
        return
    _love_hidden_cooldown[user_id] = now

    today = now.strftime("%Y-%m-%d")

    # Check GLOBAL daily master ball limit FIRST (no DB needed)
    got_today = _love_hidden_global.get(today, 0)

    # Random chance (33%) + global limit check
    if got_today < 3 and random.random() < 0.33:
        await queries.ensure_user(user_id, display_name, update.effective_user.username)
        await queries.add_master_ball(user_id)
        _love_hidden_global[today] = got_today + 1
        remaining = 3 - got_today - 1
        await update.message.reply_text(
            f"💕 문유가 감동받았다!\n"
            f"🟣 {display_name}에게 마스터볼 1개를 선물! (오늘 남은: {remaining}회)",
        )
    else:
        # No DB query needed for simple response
        await update.message.reply_text(f"💕 문유: 고마워요~!")

    # Title tracking in background (non-blocking)
    async def _bg_title_check():
        try:
            await queries.ensure_user(user_id, display_name, update.effective_user.username)
            await queries.increment_title_stat(user_id, "love_count")
            from utils.title_checker import check_and_unlock_titles
            new_titles = await check_and_unlock_titles(user_id)
            if new_titles:
                title_msg = "\n".join(f"🎉 새 칭호 해금! 「{temoji} {tname}」" for _, tname, temoji in new_titles)
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"🏷️ {display_name}의 {title_msg}",
                )
        except Exception:
            pass
    asyncio.create_task(_bg_title_check())


async def ranking_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /랭킹 command in group chat."""
    if not update.effective_chat:
        return

    try:
        rankings = await queries.get_rankings(limit=5)

        if not rankings:
            await update.message.reply_text("아직 포켓몬을 잡은 트레이너가 없습니다!")
            return

        medals = ["🥇", "🥈", "🥉", "4.", "5."]
        lines = ["🏅 <b>도감왕</b>"]
        for i, r in enumerate(rankings):
            medal = medals[i] if i < len(medals) else f"{i+1}."
            decorated = get_decorated_name(
                r["display_name"],
                r.get("title", ""),
                r.get("title_emoji", ""),
                r.get("username"),
                html=True,
            )
            lines.append(
                f"{medal} {decorated} — {r['caught_count']}/251"
            )

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ranking handler error: {e}")
        await update.message.reply_text("랭킹을 불러올 수 없습니다.")


async def log_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /로그 command in group chat."""
    if not update.effective_chat:
        return

    try:
        logs = await queries.get_recent_logs(update.effective_chat.id, limit=10)

        if not logs:
            await update.message.reply_text("아직 출현 기록이 없습니다!")
            return

        lines = ["📋 최근 출현 기록"]
        for log in logs:
            ago = time_ago(log["spawned_at"])
            if log["caught_by_name"]:
                result = f"→ {log['caught_by_name']} 포획"
            else:
                result = "→ 도망"
            lines.append(
                f"{ago} {log['pokemon_emoji']} {log['pokemon_name']} {result}"
            )

        await update.message.reply_text("\n".join(lines))

    except Exception as e:
        logger.error(f"Log handler error: {e}")
        await update.message.reply_text("기록을 불러올 수 없습니다.")


async def dashboard_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '대시보드' command — show dashboard link."""
    await update.message.reply_text(
        "📊 <b>포켓몬 봇 대시보드</b>\n\n"
        "🔗 <a href='https://court-astrology-minds-bernard.trycloudflare.com'>court-astrology-minds-bernard.trycloudflare.com</a>\n\n"
        "에픽/전설 보유자 랭킹, 도망 장인, 행운아/불행아,\n"
        "교환왕, 올빼미족 등 재미있는 통계를 확인하세요!",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
