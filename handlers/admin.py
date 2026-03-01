"""Admin handlers for event management and spawn settings."""

import logging
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import ContextTypes

import config
from database import queries
from services.spawn_service import schedule_spawns_for_chat
from services.event_service import invalidate_event_cache

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


# ============================================================
# Spawn Multiplier (group command by admin)
# ============================================================

async def spawn_rate_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '스폰배율 [배율]' command in group chat."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Check admin
    if not is_admin(user_id):
        # Also allow group admins
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

    # Reschedule spawns with new multiplier
    room = await queries.get_chat_room(chat_id)
    if room:
        await schedule_spawns_for_chat(context.application, chat_id, room["member_count"])

    await update.message.reply_text(f"✅ 스폰 배율이 {multiplier}x로 설정되었습니다!")


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

    # Check if in a group
    if update.effective_chat.type == "private":
        await update.message.reply_text("그룹 채팅방에서만 사용 가능합니다.")
        return

    # Allow bot admins + group admins
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

    # Check minimum members
    room = await queries.get_chat_room(chat_id)
    member_count = room["member_count"] if room else 0
    if member_count < config.SPAWN_MIN_MEMBERS:
        await update.message.reply_text(
            f"🚫 멤버가 {config.SPAWN_MIN_MEMBERS}명 이상인 방에서만 사용 가능합니다. (현재 {member_count}명)"
        )
        return

    # Check force spawn limit (50 per chat)
    count = await queries.get_force_spawn_count(chat_id)
    if count >= 50:
        await update.message.reply_text("🚫 이 방의 강제스폰 횟수를 모두 사용했습니다! (50/50회)")
        return

    logger.info(f"force_spawn: executing spawn in chat {chat_id} (count: {count}/50)")

    try:
        # Trigger spawn immediately (force=True skips activity check)
        from services.spawn_service import execute_spawn

        class FakeJob:
            def __init__(self, data):
                self.data = data

        class FakeContext:
            def __init__(self, bot, job_queue, data):
                self.bot = bot
                self.job_queue = job_queue
                self.job = FakeJob(data)

        fake_ctx = FakeContext(
            context.bot,
            context.application.job_queue,
            {"chat_id": chat_id, "force": True},
        )
        await execute_spawn(fake_ctx)

        # Increment count and show remaining
        await queries.increment_force_spawn(chat_id)
        used = count + 1
        await update.message.reply_text(f"⚡ 강제스폰! ({used}/50회)")
        logger.info(f"force_spawn: success in chat {chat_id} ({used}/50)")
    except Exception as e:
        logger.error(f"force_spawn FAILED in chat {chat_id}: {e}", exc_info=True)
        await update.message.reply_text(f"❌ 강제스폰 실패: {e}")


async def force_spawn_reset_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '강제스폰초기화' command - reset force spawn counts for all chats."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    await queries.reset_force_spawn_counts()
    await update.message.reply_text("✅ 모든 방의 강제스폰 횟수가 초기화되었습니다!")


# ============================================================
# Event Management (DM only, bot admin only)
# ============================================================

async def event_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '이벤트시작 [이름] [시간]' command."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("관리자만 사용할 수 있습니다.")
        return

    text = (update.message.text or "").strip()
    parts = text.split()

    # "이벤트시작 포획2배 24"
    if len(parts) < 3:
        template_list = "\n".join(
            f"  {name} — {t['description']}"
            for name, t in config.EVENT_TEMPLATES.items()
        )
        await update.message.reply_text(
            f"사용법: 이벤트시작 [이름] [시간(h)]\n\n"
            f"📋 사용 가능한 이벤트:\n{template_list}\n\n"
            f"예: 이벤트시작 포획2배 24"
        )
        return

    event_name = parts[1]
    try:
        hours = float(parts[2])
        if hours < 0.5 or hours > 168:
            await update.message.reply_text("시간은 0.5~168 사이로 설정해주세요.")
            return
    except ValueError:
        await update.message.reply_text("시간을 숫자로 입력해주세요.")
        return

    template = config.EVENT_TEMPLATES.get(event_name)
    if not template:
        await update.message.reply_text(
            f"'{event_name}' 이벤트를 찾을 수 없습니다.\n"
            f"이벤트시작 으로 목록을 확인하세요."
        )
        return

    end_time = (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")

    event_id = await queries.create_event(
        name=event_name,
        event_type=template["event_type"],
        multiplier=template["multiplier"],
        target=template["target"],
        description=template["description"],
        end_time=end_time,
        created_by=user_id,
    )
    invalidate_event_cache()

    await update.message.reply_text(
        f"🎉 이벤트 시작!\n\n"
        f"{template['description']}\n"
        f"기간: {hours}시간\n"
        f"ID: #{event_id}"
    )


async def event_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '이벤트목록' command."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("관리자만 사용할 수 있습니다.")
        return

    await queries.cleanup_expired_events()
    events = await queries.get_active_events()

    if not events:
        await update.message.reply_text("현재 진행 중인 이벤트가 없습니다.")
        return

    lines = ["📋 진행 중인 이벤트\n"]
    for e in events:
        lines.append(
            f"#{e['id']} {e['description']}\n"
            f"   종료: {e['end_time']}"
        )

    lines.append("\n이벤트종료 [번호] 로 종료할 수 있습니다.")
    await update.message.reply_text("\n".join(lines))


async def event_end_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '이벤트종료 [번호]' command."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("관리자만 사용할 수 있습니다.")
        return

    text = (update.message.text or "").strip()
    parts = text.split()

    if len(parts) < 2:
        await update.message.reply_text("사용법: 이벤트종료 [번호]\n예: 이벤트종료 1")
        return

    try:
        event_id = int(parts[1])
    except ValueError:
        await update.message.reply_text("번호를 숫자로 입력해주세요.")
        return

    await queries.end_event(event_id)
    invalidate_event_cache()
    await update.message.reply_text(f"✅ 이벤트 #{event_id} 종료되었습니다.")


# ============================================================
# Stats & Channel List (DM, bot admin only)
# ============================================================

async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '통계' command — show overall bot statistics."""
    if not update.effective_user or not update.message:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("관리자만 사용할 수 있습니다.")
        return

    total = await queries.get_total_stats()
    today = await queries.get_today_stats()
    top_users = await queries.get_rankings(3)
    top_pokemon = await queries.get_top_pokemon_caught(5)

    lines = [
        "📊 봇 전체 통계\n",
        f"👥 총 유저: {total['total_users']}명",
        f"💬 활성 채팅방: {total['total_chats']}개",
        f"🌿 총 스폰: {total['total_spawns']}회",
        f"✨ 총 포획: {total['total_catches']}회",
        f"🔄 총 교환: {total['total_trades']}회",
        "",
        f"📅 오늘 스폰: {today['today_spawns']}회",
        f"📅 오늘 포획: {today['today_catches']}회",
    ]

    if top_users:
        lines.append("\n🏆 도감 TOP 3")
        for i, u in enumerate(top_users, 1):
            medal = ["🥇", "🥈", "🥉"][i - 1]
            lines.append(f"{medal} {u['display_name']} — {u['caught_count']}/151")

    if top_pokemon:
        lines.append("\n🔥 가장 많이 잡힌 포켓몬")
        for p in top_pokemon:
            lines.append(f"  {p['pokemon_emoji']} {p['pokemon_name']} — {p['catch_count']}회")

    await update.message.reply_text("\n".join(lines))


async def channel_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '채널목록' command — list all chat rooms."""
    if not update.effective_user or not update.message:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("관리자만 사용할 수 있습니다.")
        return

    rooms = await queries.get_all_chat_rooms()

    if not rooms:
        await update.message.reply_text("등록된 채팅방이 없습니다.")
        return

    active = [r for r in rooms if r["is_active"]]
    inactive = [r for r in rooms if not r["is_active"]]

    lines = [f"💬 채팅방 목록 (총 {len(rooms)}개)\n"]

    if active:
        lines.append(f"🟢 활성 ({len(active)}개)")
        for r in active:
            title = r["chat_title"] or "(제목 없음)"
            members = r["member_count"]
            joined = (r["joined_at"] or "")[:10]
            last_spawn = (r["last_spawn_at"] or "-")[:16]
            lines.append(f"  {title}")
            lines.append(f"    인원: {members} | 가입: {joined}")
            lines.append(f"    최근스폰: {last_spawn}")

    if inactive:
        lines.append(f"\n🔴 비활성 ({len(inactive)}개)")
        for r in inactive:
            title = r["chat_title"] or "(제목 없음)"
            lines.append(f"  {title}")

    await update.message.reply_text("\n".join(lines))
