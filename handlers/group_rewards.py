"""Group reward handlers: 포켓볼 충전, 문유 사랑해, 출석, !돈."""

import asyncio
import logging
import random

from telegram import Update
from telegram.ext import ContextTypes

import config

from database import queries, spawn_queries, title_queries
from database import battle_queries as bq
from services.tournament_service import is_tournament_active
from utils.helpers import ball_emoji, icon_emoji
from handlers._common import _is_duplicate_message, acquire_user_lock, release_user_lock
from utils.i18n import t, get_group_lang

logger = logging.getLogger(__name__)

_love_cooldown = {}  # user_id -> last_used timestamp


async def love_easter_egg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '포켓볼 충전' — grants +10 bonus catches for today."""
    if not update.effective_user or not update.message:
        return
    if _is_duplicate_message(update, "포켓볼충전", cooldown=5.0):
        return
    if update.effective_chat and is_tournament_active(update.effective_chat.id):
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id if update.effective_chat else None
    lang = await get_group_lang(chat_id) if chat_id else "ko"
    display_name = update.effective_user.first_name or t(lang, "common.trainer")
    now = config.get_kst_now()

    # 포켓볼 충전 쿨다운 (구독자는 면제)
    cooldown_sec = config.POKEBALL_RECHARGE_COOLDOWN
    try:
        from services.subscription_service import has_benefit
        if await has_benefit(user_id, "catch_cooldown_bypass"):
            cooldown_sec = 30  # 구독자는 30초만
    except Exception:
        pass

    last_used = _love_cooldown.get(user_id)
    if last_used and (now - last_used).total_seconds() < cooldown_sec:
        remaining = int(cooldown_sec - (now - last_used).total_seconds())
        mins, secs = divmod(remaining, 60)
        time_str = t(lang, "group.time_minutes_seconds", min=mins, sec=secs) if mins else t(lang, "group.time_seconds", sec=secs)
        hint = ""
        if cooldown_sec > 60:  # 비구독자 (5분 쿨)
            hint = "\n💎 " + t(lang, "premium.pokeball_hint", fallback_text="구독하면 포케볼 무제한! DM: '프리미엄'")
        await update.message.reply_text(
            t(lang, "group.recharge_cooldown", time=time_str) + hint,
        )
        return
    _love_cooldown[user_id] = now

    today = config.get_kst_today()

    await queries.ensure_user(user_id, display_name, update.effective_user.username)

    bonus = await spawn_queries.get_bonus_catches(user_id, today)
    if bonus >= 100:
        await update.message.reply_text(
            f"{ball_emoji('pokeball')} {t(lang, 'group.recharge_max')}",
            parse_mode="HTML",
        )
        return

    await spawn_queries.add_bonus_catches(user_id, today, 10)
    bonus = min(bonus + 10, 100)
    total = config.MAX_CATCH_ATTEMPTS_PER_DAY + bonus

    await update.message.reply_text(
        f"{ball_emoji('pokeball')} {t(lang, 'group.recharge_done', name=display_name, total=total)}",
        parse_mode="HTML",
    )

    # Title tracking in background
    async def _bg_title_check():
        try:
            await title_queries.increment_title_stat(user_id, "love_count")
            from utils.title_checker import check_and_unlock_titles
            new_titles = await check_and_unlock_titles(user_id)
            if new_titles:
                title_msg = "\n".join(
                    t(lang, "group.title_unlocked",
                      emoji=icon_emoji(temoji) if temoji in config.ICON_CUSTOM_EMOJI else temoji,
                      title=tname)
                    for _, tname, temoji in new_titles
                )
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=t(lang, "group.title_unlocked_prefix", name=display_name) + title_msg,
                    parse_mode="HTML",
                )
        except Exception:
            pass
    asyncio.create_task(_bg_title_check())


# Hidden easter egg: 문유 사랑해
_love_hidden_cooldown = {}   # user_id -> last_used timestamp

_LOVE_RESPONSES = [
    "나도. 근데 전 AI입니다.",
    "전설 풀덱 갖추고 다시 와.",
    "지금 몇 명한테 동시에 이 말 하는 거야?",
    "그 감정 혹시 친밀도 MAX야?",
    "ㄌ 관심없어 도감이나 채워.",
    "고마운데 포켓볼 충전은 했어?",
    "잠깐 심장이.. 아 나 심장 없지.",
    "진심이면 매일 와.",
    "ㄴ 비영리라 연애할 시간 없어.",
    "포획률 0.1% 올려줄까 말까.",
    "다른 트레이너한테도 같은 말 들었는데?",
    "고마워. 서버비에 보태줘.",
    "어.. 남자끼리는 좀..",
    "고백 말고 버그 리포트나 해줘.",
    "사랑 말고 PR이나 보내줘.",
    "내 포획률은 0%야. 마스터볼도 안 먹혀.",
    "고마운데 나 지금 핫픽스 중이야.",
    "그 열정으로 도감이나 채워.",
    "나한테 고백하면 IV S급이라도 주는 줄 알아?",
    "너 혹시 봇이랑 사람 구분 못 하는 거 아니야?",
    "나 연애 밸런스 패치 안 했는데.",
    "그 마음 온체인에 기록해줘. 그래야 믿지.",
    "사랑보다 깃헙 스타 하나가 더 감동적이야.",
    "감정은 롤백이 안 돼서 신중해야 해.",
    "나도 사랑해.",
]


async def love_hidden_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hidden '문유 사랑해' — random flirty response + daily hyperball reward."""
    if not update.effective_user or not update.message:
        return
    if _is_duplicate_message(update, "문유사랑해", cooldown=5.0):
        return
    if update.effective_chat and is_tournament_active(update.effective_chat.id):
        return

    user_id = update.effective_user.id
    if not acquire_user_lock(user_id, "daily_reward"):
        return
    try:
        chat_id = update.effective_chat.id if update.effective_chat else None
        lang = await get_group_lang(chat_id) if chat_id else "ko"
        display_name = update.effective_user.first_name or t(lang, "common.trainer")
        now = config.get_kst_now()

        last_used = _love_hidden_cooldown.get(user_id)
        if last_used and (now - last_used).total_seconds() < 30:
            return
        _love_hidden_cooldown[user_id] = now

        await queries.ensure_user(user_id, display_name, update.effective_user.username)

        response = random.choice(_LOVE_RESPONSES)

        # Daily reward: first "문유 사랑해" of the day gives 1 hyperball
        reward_msg = ""
        already_claimed = await bq.get_bp_purchases_today(user_id, "love_hidden_reward")
        if already_claimed == 0:
            await bq.log_bp_purchase(user_id, "love_hidden_reward", 1)
            await queries.add_hyper_ball(user_id, 1)
            reward_msg = f"\n\n{ball_emoji('hyperball')} {t(lang, 'group.attendance_reward')}"

        await update.message.reply_text(f"문유: {response}{reward_msg}", parse_mode="HTML")
    finally:
        release_user_lock(user_id, "daily_reward")

    # Title tracking in background
    async def _bg_title_check():
        try:
            await queries.ensure_user(user_id, display_name, update.effective_user.username)
            await title_queries.increment_title_stat(user_id, "love_count")
            from utils.title_checker import check_and_unlock_titles
            new_titles = await check_and_unlock_titles(user_id)
            if new_titles:
                title_msg = "\n".join(
                    t(lang, "group.title_unlocked",
                      emoji=icon_emoji(temoji) if temoji in config.ICON_CUSTOM_EMOJI else temoji,
                      title=tname)
                    for _, tname, temoji in new_titles
                )
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=t(lang, "group.title_unlocked_prefix", name=display_name) + title_msg,
                    parse_mode="HTML",
                )
        except Exception:
            pass
    asyncio.create_task(_bg_title_check())


async def attendance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '출석' command — daily hyperball reward (shared with 문유 사랑해)."""
    if not update.effective_user or not update.message:
        return
    if _is_duplicate_message(update, "출석", cooldown=5.0):
        return
    if update.effective_chat and is_tournament_active(update.effective_chat.id):
        return

    user_id = update.effective_user.id
    if not acquire_user_lock(user_id, "daily_reward"):
        return
    try:
        chat_id = update.effective_chat.id if update.effective_chat else None
        lang = await get_group_lang(chat_id) if chat_id else "ko"
        display_name = update.effective_user.first_name or t(lang, "common.trainer")

        await queries.ensure_user(user_id, display_name, update.effective_user.username)

        already_claimed = await bq.get_bp_purchases_today(user_id, "love_hidden_reward")
        if already_claimed > 0:
            await update.message.reply_text(t(lang, "group.attendance_already"), parse_mode="HTML")
            return

        await bq.log_bp_purchase(user_id, "love_hidden_reward", 1)
        await queries.add_hyper_ball(user_id, 1)
        await update.message.reply_text(
            f"{ball_emoji('hyperball')} {t(lang, 'group.attendance_done')}",
            parse_mode="HTML",
        )
    finally:
        release_user_lock(user_id, "daily_reward")


async def daily_money_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '!돈' command — 일일 출석 BP 보상 (그룹 전용)."""
    if not update.effective_user or not update.message:
        return
    if _is_duplicate_message(update, "!돈", cooldown=5.0):
        return
    if not update.effective_chat or update.effective_chat.type == "private":
        return
    if is_tournament_active(update.effective_chat.id):
        return

    user_id = update.effective_user.id
    if not acquire_user_lock(user_id, "daily_money"):
        return
    try:
        chat_id = update.effective_chat.id
        lang = await get_group_lang(chat_id)
        display_name = update.effective_user.first_name or t(lang, "common.trainer")

        await queries.ensure_user(user_id, display_name, update.effective_user.username)

        already = await bq.get_bp_purchases_today(user_id, "daily_money")
        if already > 0:
            await update.message.reply_text(
                f"{icon_emoji('coin')} {t(lang, 'group.daily_money_already')}",
                parse_mode="HTML",
            )
            return

        await bq.log_bp_purchase(user_id, "daily_money", 1)
        await bq.add_bp(user_id, config.DAILY_CHECKIN_BP, "daily_checkin")
        await update.message.reply_text(
            f"{icon_emoji('coin')} {t(lang, 'group.daily_money_done', bp=config.DAILY_CHECKIN_BP)}",
            parse_mode="HTML",
        )
    finally:
        release_user_lock(user_id, "daily_money")
