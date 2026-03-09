"""Admin handlers for event management and spawn settings."""

import asyncio
import logging
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import config
from database import queries
from services.spawn_service import schedule_spawns_for_chat
from services.event_service import invalidate_event_cache
from utils.helpers import schedule_delete, icon_emoji

logger = logging.getLogger(__name__)

# Per-chat lock to prevent concurrent force spawns (race condition)
_force_spawn_locks: dict[int, asyncio.Lock] = {}


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

    # Auto-delete the command message
    schedule_delete(update.message, config.AUTO_DEL_FORCE_SPAWN_CMD)

    # Check if in a group
    if update.effective_chat.type == "private":
        resp = await update.message.reply_text("그룹 채팅방에서만 사용 가능합니다.")
        schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
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

    # Acquire per-chat lock to prevent duplicate spawns from rapid button presses
    if chat_id not in _force_spawn_locks:
        _force_spawn_locks[chat_id] = asyncio.Lock()
    lock = _force_spawn_locks[chat_id]

    if lock.locked():
        return  # Another spawn is already in progress — silently ignore

    async with lock:
        # Check if there's already an active spawn
        active = await queries.get_active_spawn(chat_id)
        if active:
            resp = await update.message.reply_text(
                f"⚠️ 이미 스폰 중인 포켓몬이 있습니다!\n"
                f"{active['emoji']} {active['name_ko']}을(를) 먼저 잡아주세요."
            )
            schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            return

        # Check minimum members
        room = await queries.get_chat_room(chat_id)
        member_count = room["member_count"] if room else 0
        if member_count < config.SPAWN_MIN_MEMBERS:
            resp = await update.message.reply_text(
                f"🚫 멤버가 {config.SPAWN_MIN_MEMBERS}명 이상인 방에서만 사용 가능합니다. (현재 {member_count}명)"
            )
            schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            return

        # Check force spawn limit (50 per chat)
        count = await queries.get_force_spawn_count(chat_id)
        if count >= 50:
            resp = await update.message.reply_text("🚫 이 방의 강제스폰 횟수를 모두 사용했습니다! (50/50회)")
            schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            return

        logger.info(f"force_spawn: executing spawn in chat {chat_id} (count: {count}/50)")

        try:
            # Trigger spawn immediately (force=True skips activity check)
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

            fake_ctx = FakeContext(
                context.bot,
                context.application.job_queue,
                {"chat_id": chat_id, "force": True},
            )
            await execute_spawn(fake_ctx)

            # Increment count and show remaining
            await queries.increment_force_spawn(chat_id)
            used = count + 1
            try:
                resp = await context.bot.send_message(chat_id=chat_id, text=f"{icon_emoji('bolt')} 강제스폰! ({used}/50회)", parse_mode="HTML")
                schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            except Exception:
                pass
            logger.info(f"force_spawn: success in chat {chat_id} ({used}/50)")
        except Exception as e:
            logger.error(f"force_spawn FAILED in chat {chat_id}: {e}", exc_info=True)
            try:
                resp = await context.bot.send_message(chat_id=chat_id, text=f"❌ 강제스폰 실패: {e}")
                schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            except Exception:
                pass


async def ticket_force_spawn_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '강스권' command in group — use a force spawn reset ticket to reset 50-count."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Auto-delete the command message
    schedule_delete(update.message, config.AUTO_DEL_FORCE_SPAWN_CMD)

    if update.effective_chat.type == "private":
        resp = await update.message.reply_text("그룹 채팅방에서만 사용 가능합니다.")
        schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
        return

    # Use ticket (atomic)
    success = await queries.use_force_spawn_ticket(user_id)
    if not success:
        resp = await update.message.reply_text(f"{icon_emoji('bolt')} 강스권이 없습니다! DM에서 '상점'으로 구매하세요.", parse_mode="HTML")
        schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
        return

    # Reset force spawn count for this chat
    await queries.reset_force_spawn_for_chat(chat_id)

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
    chat_id = update.effective_chat.id

    # Allow bot admins + group admins (same as force_spawn)
    if not is_admin(user_id):
        if update.effective_chat.type == "private":
            return
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status not in ("creator", "administrator"):
                return
        except Exception:
            return

    await queries.reset_force_spawn_counts()
    await update.message.reply_text(f"{icon_emoji('check')} 모든 방의 강제스폰 횟수가 초기화되었습니다!", parse_mode="HTML")


async def pokeball_reset_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '포켓볼초기화' command - reset all users' catch limits."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Allow bot admins + group admins
    if not is_admin(user_id):
        if update.effective_chat.type == "private":
            return
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status not in ("creator", "administrator"):
                return
        except Exception:
            return

    await queries.reset_catch_limits()
    await update.message.reply_text(f"{icon_emoji('check')} 모든 유저의 포켓볼(잡기 횟수)이 초기화되었습니다!", parse_mode="HTML")


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

    end_time = (config.get_kst_now() + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")

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

    # Count recently active users for DM broadcast option
    active_user_ids = await queries.get_recently_active_user_ids(minutes=180)
    active_count = len(active_user_ids)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"📢 {active_count}명에게 DM 발송",
                callback_data=f"evt_dm_{event_id}",
            ),
            InlineKeyboardButton("❌ 안 보냄", callback_data="evt_dm_skip"),
        ]
    ])

    await update.message.reply_text(
        f"🎉 이벤트 시작!\n\n"
        f"{template['description']}\n"
        f"기간: {hours}시간\n"
        f"ID: #{event_id}\n\n"
        f"최근 3시간 활성 유저 {active_count}명에게 DM을 보낼까요?",
        reply_markup=keyboard,
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

    lines = ["📋 진행 중인 이벤트\n"]

    # Config-level permanent events
    base_nat = 1 / 64
    base_arc = 1 / 512
    if config.SHINY_RATE_NATURAL > base_nat:
        nat_mult = round(config.SHINY_RATE_NATURAL / base_nat)
        lines.append(f"✨ 이로치 자연발생 {nat_mult}배 ({config.SHINY_RATE_NATURAL:.0%}) (상시)")
    if config.SHINY_RATE_ARCADE > base_arc:
        arc_mult = round(config.SHINY_RATE_ARCADE / base_arc)
        lines.append(f"✨ 이로치 아케이드 {arc_mult}배 ({config.SHINY_RATE_ARCADE:.1%}) (상시)")

    for e in events:
        lines.append(
            f"#{e['id']} {e['description']}\n"
            f"   종료: {e['end_time']}"
        )

    if len(lines) == 1:
        await update.message.reply_text("현재 진행 중인 이벤트가 없습니다.")
        return

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
    await update.message.reply_text(f"{icon_emoji('check')} 이벤트 #{event_id} 종료되었습니다.", parse_mode="HTML")


# ============================================================
# Event DM Broadcast Callback
# ============================================================

async def event_dm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle event DM broadcast confirmation buttons."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    user_id = query.from_user.id if query.from_user else 0
    if not is_admin(user_id):
        return

    if query.data == "evt_dm_skip":
        await query.edit_message_reply_markup(reply_markup=None)
        return

    # evt_dm_{event_id}
    try:
        event_id = int(query.data.split("_")[-1])
    except (ValueError, IndexError):
        return

    # Fetch event info for DM message
    events = await queries.get_active_events()
    event = next((e for e in events if e["id"] == event_id), None)
    if not event:
        await query.edit_message_text("이벤트를 찾을 수 없습니다. (이미 종료됨)")
        return

    # Remove buttons, show sending status
    await query.edit_message_reply_markup(reply_markup=None)

    active_user_ids = await queries.get_recently_active_user_ids(minutes=180)
    total = len(active_user_ids)

    # Build DM message
    desc = event["description"]
    end_time = event["end_time"]
    if hasattr(end_time, "strftime"):
        end_str = end_time.strftime("%m/%d %H:%M")
    else:
        end_str = str(end_time)[:16]

    dm_text = (
        f"📢 이벤트 알림!\n\n"
        f"{desc}\n"
        f"⏰ 종료: {end_str}\n\n"
        f"👉 https://t.me/tg_poke"
    )

    sent = 0
    for uid in active_user_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=dm_text)
            sent += 1
        except Exception:
            pass
        if sent % 25 == 0:
            await asyncio.sleep(1)

    await context.bot.send_message(
        chat_id=user_id,
        text=f"{icon_emoji('check')} 이벤트 DM 발송 완료: {sent}/{total}명",
        parse_mode="HTML",
    )


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
        f"🎯 총 포획: {total['total_catches']}회",
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


# ============================================================
# Master Ball Grant (DM, bot admin only)
# ============================================================

async def grant_masterball_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '마볼지급 [개수]' command.
    - 그룹: 상대 메시지에 답장 + '마볼지급 [개수]'
    - DM: '마볼지급 [유저ID] [개수]'
    """
    if not update.effective_user or not update.message:
        return
    if not is_admin(update.effective_user.id):
        return

    text = (update.message.text or "").strip()
    parts = text.split()
    is_group = update.effective_chat.type in ("group", "supergroup")

    target_user_id = None
    count = 1

    if is_group:
        # 그룹: 답장으로 대상 지정
        reply = update.message.reply_to_message
        if not reply or not reply.from_user:
            await update.message.reply_text("대상의 메시지에 답장으로 '마볼지급 [개수]' 를 입력하세요.")
            return
        target_user_id = reply.from_user.id
        # 개수 파싱 (마볼지급 2 → 2개)
        if len(parts) >= 2:
            try:
                count = int(parts[1])
                if count < 1 or count > 99:
                    await update.message.reply_text("개수는 1~99 사이로 입력해주세요.")
                    return
            except ValueError:
                pass
    else:
        # DM: 유저ID로 대상 지정
        if len(parts) < 2:
            await update.message.reply_text(
                "사용법: 마볼지급 [유저ID] [개수]\n"
                "예: 마볼지급 123456789 1\n"
                "그룹에서는 답장으로 사용 가능"
            )
            return
        try:
            target_user_id = int(parts[1])
        except ValueError:
            await update.message.reply_text("유저 ID를 숫자로 입력해주세요.")
            return
        if len(parts) >= 3:
            try:
                count = int(parts[2])
                if count < 1 or count > 99:
                    await update.message.reply_text("개수는 1~99 사이로 입력해주세요.")
                    return
            except ValueError:
                pass

    # Ensure user exists in DB
    user = await queries.get_user(target_user_id)
    if not user:
        await update.message.reply_text(f"유저를 찾을 수 없습니다. (봇 미등록)")
        return

    await queries.add_master_ball(target_user_id, count)
    new_total = await queries.get_master_balls(target_user_id)

    await update.message.reply_text(
        f"{icon_emoji('check')} 마스터볼 지급 완료!\n"
        f"대상: {user['display_name']}\n"
        f"지급: {count}개\n"
        f"현재 보유: {new_total}개",
        parse_mode="HTML",
    )

    # 대상 유저에게 DM 알림
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"🎁 마스터볼 {count}개를 지급받았습니다!\n현재 보유: {new_total}개",
        )
    except Exception:
        pass  # DM 실패 시 무시 (봇 차단 등)

    logger.info(f"Admin granted {count} master ball(s) to user {target_user_id}")


# ============================================================
# Arcade Channel Management
# ============================================================

async def arcade_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '아케이드' command in a group chat.
    - Admin: '아케이드 등록/해제' → permanent arcade toggle
    - User with ticket: '아케이드 등록' → 1-hour temporary arcade
    """
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    text = (update.message.text or "").strip()
    parts = text.split()
    chat_id = update.effective_chat.id

    if len(parts) < 2:
        # Check active temp pass
        active_pass = await queries.get_active_arcade_pass(chat_id)
        if chat_id in config.ARCADE_CHAT_IDS:
            status = f"{icon_emoji('check')} 영구 등록"
        elif active_pass:
            from datetime import datetime, timezone
            expires = active_pass["expires_at"]
            if hasattr(expires, 'tzinfo') and expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            remaining = max(0, int((expires - datetime.now(timezone.utc)).total_seconds()))
            status = f"⏱ 임시 등록 ({remaining // 60}분 남음)"
        else:
            status = "❌ 미등록"

        tickets = await queries.get_arcade_tickets(user_id)
        await update.message.reply_text(
            f"🕹️ 아케이드 채널 ({status})\n\n"
            f"'아케이드 등록' — 아케이드 활성화\n"
            f"'아케이드 해제' — 아케이드 비활성화\n\n"
            f"🎮 내 아케이드 티켓: {tickets}개",
            parse_mode="HTML",
        )
        return

    action = parts[1]

    if action == "등록":
        # Already an arcade channel?
        if chat_id in config.ARCADE_CHAT_IDS:
            await update.message.reply_text("🕹️ 이미 영구 아케이드 채널입니다!")
            return

        # Already has active temp pass?
        active_pass = await queries.get_active_arcade_pass(chat_id)
        if active_pass:
            await update.message.reply_text("🕹️ 이미 아케이드가 활성화되어 있습니다!")
            return

        # Ticket takes priority (even for admins)
        used = await queries.use_arcade_ticket(user_id)
        if used:
            await queries.create_arcade_pass(chat_id, user_id, config.ARCADE_PASS_DURATION)

            from services.spawn_service import start_temp_arcade
            start_temp_arcade(context.application, chat_id, config.ARCADE_PASS_DURATION, interval=config.ARCADE_TICKET_SPAWN_INTERVAL)

            display_name = update.effective_user.first_name or "트레이너"
            remaining_tickets = await queries.get_arcade_tickets(user_id)
            await update.message.reply_text(
                f"🕹️ {display_name}이(가) 아케이드 활성화!\n"
                f"⏱️ {config.ARCADE_PASS_DURATION // 60}분간 {config.ARCADE_TICKET_SPAWN_INTERVAL}초마다 스폰\n"
                f"🎮 남은 티켓: {remaining_tickets}개"
            )
            logger.info(f"Temp arcade activated by {user_id} (ticket) in chat {chat_id}")
            return

        # No ticket — admin: permanent registration
        if is_admin(user_id):
            config.ARCADE_CHAT_IDS.add(chat_id)
            await queries.set_arcade(chat_id, True)
            from services.spawn_service import schedule_arcade_spawns
            schedule_arcade_spawns(context.application)
            await update.message.reply_text(
                f"🕹️ 아케이드 채널 영구 등록 완료!\n"
                f"⏱️ {config.ARCADE_SPAWN_INTERVAL}초마다 포켓몬이 출현합니다."
            )
            logger.info(f"Arcade channel registered (permanent): {chat_id}")
            return

        # No ticket, not admin
        await update.message.reply_text(
            "🎮 아케이드 티켓이 없습니다!\nDM 상점에서 '구매 아케이드'로 구매하세요."
        )

    elif action == "해제":
        if chat_id in config.ARCADE_CHAT_IDS:
            # Only admin can remove permanent arcade
            if not is_admin(user_id):
                await update.message.reply_text("🚫 영구 아케이드 해제는 관리자만 가능합니다.")
                return
            config.ARCADE_CHAT_IDS.discard(chat_id)
            await queries.set_arcade(chat_id, False)

        # Remove arcade jobs
        from services.spawn_service import stop_arcade_for_chat
        stop_arcade_for_chat(context.application, chat_id)

        # Deactivate any active pass
        from database.connection import get_db
        pool = await get_db()
        await pool.execute(
            "UPDATE arcade_passes SET is_active = 0 WHERE chat_id = $1 AND is_active = 1",
            chat_id,
        )

        await update.message.reply_text("🕹️ 아케이드 해제됨. 일반 스폰으로 복구됩니다.")
        logger.info(f"Arcade channel unregistered: {chat_id}")


async def force_tournament_reg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: 대회시작 — manually trigger tournament registration."""
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    from services.tournament_service import start_registration
    await start_registration(context)
    await update.message.reply_text("✅ 대회 등록 수동 시작!")


async def force_tournament_run_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: 대회진행 — manually trigger tournament execution."""
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    from services.tournament_service import start_tournament
    await update.message.reply_text("⚔️ 대회 진행 시작!")
    await start_tournament(context)
