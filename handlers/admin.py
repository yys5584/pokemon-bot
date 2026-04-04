"""Admin handlers: hub module with re-exports + spawn control (force spawn, reset, multiplier)."""

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

import config

from database import queries, spawn_queries
from services.spawn_service import schedule_spawns_for_chat
from utils.helpers import schedule_delete, icon_emoji, type_badge
from handlers._common import _is_duplicate_message

logger = logging.getLogger(__name__)

# Per-chat lock to prevent concurrent force spawns (race condition)
_force_spawn_locks: dict[int, asyncio.Lock] = {}


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


# ── Re-exports for backward compatibility ──────────────────────
from handlers.admin_event import (  # noqa: F401
    event_start_handler, event_list_handler, event_end_handler, event_dm_callback,
)
from handlers.admin_grant import (  # noqa: F401
    grant_masterball_handler, grant_bp_handler,
    grant_subscription_handler, manual_subscription_handler,
)
from handlers.admin_manage import (  # noqa: F401
    stats_handler, channel_list_handler,
    arcade_handler, tournament_chat_handler,
    force_tournament_reg_handler, force_tournament_run_handler,
    mock_tournament_reg_handler, mock_tournament_run_handler,
    resume_tournament_handler, co_champion_handler,
    abuse_list_handler, abuse_detail_handler, abuse_reset_handler,
    report_handler,
    event_tournament_reg_handler, event_tournament_run_handler,
)


# ============================================================
# Spawn Multiplier (group command by admin)
# ============================================================

async def spawn_rate_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '스폰배율 [배율]' command in group chat."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_admin(user_id):
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status not in ("creator", "administrator"):
                return
        except Exception:
            return

    text = (update.message.text or "").strip()
    parts = text.split()

    if len(parts) < 2:
        room = await queries.get_chat_room(chat_id)
        current = room["spawn_multiplier"] if room else 1.0
        await update.message.reply_text(
            f"현재 스폰 배율: {current}x\n"
            f"사용법: 스폰배율 [숫자]\n예: 스폰배율 2"
        )
        return

    try:
        multiplier = float(parts[1])
        if multiplier < 0.5 or multiplier > 5.0:
            await update.message.reply_text("배율은 0.5~5.0 사이로 설정해주세요.")
            return
    except ValueError:
        await update.message.reply_text("숫자를 입력해주세요. 예: 스폰배율 2")
        return

    await queries.set_spawn_multiplier(chat_id, multiplier)

    room = await queries.get_chat_room(chat_id)
    if room:
        await schedule_spawns_for_chat(context.application, chat_id, room["member_count"])

    await update.message.reply_text(f"{icon_emoji('check')} 스폰 배율이 {multiplier}x로 설정되었습니다!", parse_mode="HTML")


# ============================================================
# Force Spawn (admin only)
# ============================================================

async def force_spawn_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '강제스폰' command - immediately spawn a Pokemon."""
    logger.info(f"force_spawn_handler triggered by {update.effective_user.id if update.effective_user else 'unknown'}")
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    schedule_delete(update.message, config.AUTO_DEL_FORCE_SPAWN_CMD)

    if update.effective_chat.type == "private":
        resp = await update.message.reply_text("그룹 채팅방에서만 사용 가능합니다.")
        schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
        return

    if not is_admin(user_id):
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status not in ("creator", "administrator"):
                logger.info(f"force_spawn denied: user {user_id} is not admin in chat {chat_id}")
                return
        except Exception as e:
            logger.warning(f"force_spawn admin check error: {e}")
            return

    logger.info(f"force_spawn: admin check passed for user {user_id} in chat {chat_id}")

    if chat_id not in _force_spawn_locks:
        _force_spawn_locks[chat_id] = asyncio.Lock()
    lock = _force_spawn_locks[chat_id]

    if lock.locked():
        return

    async with lock:
        from services.spawn_service import get_arcade_state
        from services.quiz_service import get_active_quiz

        if get_active_quiz(chat_id):
            resp = await update.message.reply_text("❓ 퀴즈 진행 중에는 강스를 사용할 수 없습니다.")
            schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            return

        is_permanent_arcade = chat_id in config.ARCADE_CHAT_IDS
        arcade_state = get_arcade_state(context.application, chat_id)
        if is_permanent_arcade or (arcade_state and arcade_state.get("active")):
            resp = await update.message.reply_text("🎰 아케이드가 활성화되어 있어 강스를 사용할 수 없습니다.")
            schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            return

        active = await spawn_queries.get_active_spawn(chat_id)
        if active:
            resp = await update.message.reply_text(
                f"⚠️ 이미 스폰 중인 포켓몬이 있습니다!\n"
                f"{type_badge(active['pokemon_id'])} {active['name_ko']}을(를) 먼저 잡아주세요.",
                parse_mode="HTML",
            )
            schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            return

        room = await queries.get_chat_room(chat_id)
        member_count = room["member_count"] if room else 0
        if member_count < config.SPAWN_MIN_MEMBERS:
            resp = await update.message.reply_text(
                f"🚫 멤버가 {config.SPAWN_MIN_MEMBERS}명 이상인 방에서만 사용 가능합니다. (현재 {member_count}명)"
            )
            schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            return

        from database.connection import get_db as _get_db
        _pool = await _get_db()
        fs_ban = await _pool.fetchval(
            """SELECT banned_until FROM force_spawn_bans
               WHERE chat_id = $1 AND banned_until > NOW()""",
            chat_id,
        )
        if fs_ban:
            from datetime import timezone as _tz
            now_utc = config.get_kst_now().astimezone(_tz.utc)
            ban_utc = fs_ban.astimezone(_tz.utc) if fs_ban.tzinfo else fs_ban.replace(tzinfo=_tz.utc)
            remaining_sec = max(0, int((ban_utc - now_utc).total_seconds()))
            if remaining_sec >= 3600:
                time_str = f"{remaining_sec // 3600}시간 {(remaining_sec % 3600) // 60}분"
            else:
                time_str = f"{remaining_sec // 60}분"
            resp = await update.message.reply_text(
                f"🚫 이 방은 현재 강스가 제한되어 있습니다.\n"
                f"해제까지 약 {time_str} 남았습니다.",
            )
            schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            return

        unique_catchers = await _pool.fetchval(
            """SELECT COUNT(DISTINCT caught_by_user_id)
               FROM spawn_sessions
               WHERE chat_id = $1
                 AND spawned_at > NOW() - interval '24 hours'
                 AND caught_by_user_id IS NOT NULL""",
            chat_id,
        )
        fs_count_now = await spawn_queries.get_force_spawn_count(chat_id)
        if (unique_catchers or 0) <= 2 and fs_count_now >= 50:
            await _pool.execute(
                """INSERT INTO force_spawn_bans (chat_id, banned_until, reason)
                   VALUES ($1, NOW() + interval '24 hours', $2)
                   ON CONFLICT (chat_id) DO UPDATE
                   SET banned_until = NOW() + interval '24 hours', reason = $2""",
                chat_id, f"unique_catchers={unique_catchers},fs_count={fs_count_now}",
            )
            resp = await update.message.reply_text(
                "🚫 이 방의 강스가 24시간 제한됩니다.",
            )
            schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            logger.warning(f"Force spawn banned chat={chat_id} catchers={unique_catchers} fs={fs_count_now}")
            return

        count = await spawn_queries.get_force_spawn_count(chat_id)
        force_spawn_unlimited = False
        try:
            from services.subscription_service import has_benefit
            force_spawn_unlimited = await has_benefit(user_id, "force_spawn_unlimited")
        except Exception:
            pass

        if not force_spawn_unlimited and count >= 50:
            resp = await update.message.reply_text("🚫 이 방의 강제스폰 횟수를 모두 사용했습니다! (50/50회)")
            schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            return

        logger.info(f"force_spawn: executing spawn in chat {chat_id} (count: {count}/50, unlimited={force_spawn_unlimited})")

        try:
            from services.spawn_service import execute_spawn

            class FakeJob:
                def __init__(self, data):
                    self.data = data
                    self.name = None

            class FakeContext:
                def __init__(self, bot, job_queue, data):
                    self.bot = bot
                    self.job_queue = job_queue
                    self.job = FakeJob(data)

            # 관리자 전용: 포켓몬 ID 지정 + 이로치 옵션
            spawn_data = {"chat_id": chat_id, "force": True}
            if is_admin(user_id) and context.args:
                text_args = update.message.text.split()[1:]  # 강스 뒤의 인자들
                for arg in text_args:
                    if arg.isdigit():
                        spawn_data["force_pokemon_id"] = int(arg)
                    elif arg in ("이로치", "shiny"):
                        spawn_data["force_shiny"] = True

            fake_ctx = FakeContext(
                context.bot,
                context.application.job_queue,
                spawn_data,
            )
            await execute_spawn(fake_ctx)

            await spawn_queries.increment_force_spawn(chat_id)
            used = count + 1
            try:
                count_txt = f"({used}/∞)" if force_spawn_unlimited else f"({used}/50회)"
                resp = await context.bot.send_message(chat_id=chat_id, text=f"{icon_emoji('bolt')} 강제스폰! {count_txt}", parse_mode="HTML")
                schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            except Exception:
                pass
            logger.info(f"force_spawn: success in chat {chat_id} ({used}/50)")
        except Exception as e:
            logger.error(f"force_spawn FAILED in chat {chat_id}: {e}", exc_info=True)
            try:
                resp = await context.bot.send_message(chat_id=chat_id, text="❌ 강제스폰 실패. 로그를 확인하세요.")
                schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            except Exception:
                pass


async def ticket_force_spawn_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '강스권' command in group — use a force spawn reset ticket to reset 50-count."""
    if not update.effective_user or not update.message:
        return
    if _is_duplicate_message(update, "강스권", cooldown=3.0):
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    schedule_delete(update.message, config.AUTO_DEL_FORCE_SPAWN_CMD)

    if update.effective_chat.type == "private":
        resp = await update.message.reply_text("그룹 채팅방에서만 사용 가능합니다.")
        schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
        return

    success = await queries.use_force_spawn_ticket(user_id)
    if not success:
        resp = await update.message.reply_text(f"{icon_emoji('bolt')} 강스권이 없습니다! DM에서 '상점'으로 구매하세요.", parse_mode="HTML")
        schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
        return

    await spawn_queries.reset_force_spawn_for_chat(chat_id)

    remaining = await queries.get_force_spawn_tickets(user_id)
    display_name = update.effective_user.first_name or "트레이너"
    room = await queries.get_chat_room(chat_id)
    chat_title = room["chat_title"] if room else "이 채팅방"
    resp = await update.message.reply_text(
        f"{icon_emoji('bolt')} {display_name}이(가) 강스권을 사용했습니다!\n"
        f"{icon_emoji('check')} [{chat_title}]의 강제스폰 횟수가 초기화되었습니다. (0/50)\n"
        f"{icon_emoji('container')} 남은 강스권: {remaining}개",
        parse_mode="HTML",
    )
    schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)


async def force_spawn_reset_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '강제스폰초기화' command - reset force spawn counts for all chats."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    await spawn_queries.reset_force_spawn_counts()
    await update.message.reply_text(f"{icon_emoji('check')} 모든 방의 강제스폰 횟수가 초기화되었습니다!", parse_mode="HTML")


async def pokeball_reset_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '포켓볼초기화' command - reset all users' catch limits."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    await spawn_queries.reset_catch_limits()
    await update.message.reply_text(f"{icon_emoji('check')} 모든 유저의 포켓볼(잡기 횟수)이 초기화되었습니다!", parse_mode="HTML")
