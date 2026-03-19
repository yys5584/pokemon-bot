"""Admin handlers for event management and spawn settings."""

import asyncio
import logging
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import config

from database import queries, spawn_queries, stats_queries
from services.spawn_service import schedule_spawns_for_chat
from services.event_service import invalidate_event_cache
from services.abuse_service import get_flagged_users, get_user_abuse_detail, admin_reset_score
from utils.helpers import schedule_delete, icon_emoji, type_badge

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
        # Check if arcade is active — block force spawn
        from services.spawn_service import get_arcade_state
        is_permanent_arcade = chat_id in config.ARCADE_CHAT_IDS
        arcade_state = get_arcade_state(context.application, chat_id)
        if is_permanent_arcade or (arcade_state and arcade_state.get("active")):
            resp = await update.message.reply_text("🎰 아케이드가 활성화되어 있어 강스를 사용할 수 없습니다.")
            schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            return

        # Check if there's already an active spawn
        active = await spawn_queries.get_active_spawn(chat_id)
        if active:
            resp = await update.message.reply_text(
                f"⚠️ 이미 스폰 중인 포켓몬이 있습니다!\n"
                f"{type_badge(active['pokemon_id'])} {active['name_ko']}을(를) 먼저 잡아주세요.",
                parse_mode="HTML",
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

        # Check force spawn ban (24h lockout)
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

        # 강스 10회 이상 AND 24시간 고유 포획자 2명 이하 → 24시간 차단
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

        # Check force spawn limit (50 per chat) — 구독자 무제한 체크
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
    chat_id = update.effective_chat.id

    # Bot admins only (global reset affects ALL chats)
    if not is_admin(user_id):
        return

    await spawn_queries.reset_force_spawn_counts()
    await update.message.reply_text(f"{icon_emoji('check')} 모든 방의 강제스폰 횟수가 초기화되었습니다!", parse_mode="HTML")


async def pokeball_reset_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '포켓볼초기화' command - reset all users' catch limits."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Bot admins only (global reset affects ALL users)
    if not is_admin(user_id):
        return

    await spawn_queries.reset_catch_limits()
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
        f"👉 {config.BOT_CHANNEL_URL}"
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

    total = await stats_queries.get_total_stats()
    today = await stats_queries.get_today_stats()
    top_users = await stats_queries.get_rankings(3)
    top_pokemon = await stats_queries.get_top_pokemon_caught(5)

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

    rooms = await stats_queries.get_all_chat_rooms()

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
# BP 지급 (관리자)
# ============================================================

async def grant_bp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'BP지급 [금액]' command.
    - 그룹: 답장 + 'BP지급 [금액]'
    - DM: 'BP지급 [유저ID] [금액]'
    """
    if not update.effective_user or not update.message:
        return
    if not is_admin(update.effective_user.id):
        return

    from database import battle_queries as bq

    text = (update.message.text or "").strip()
    parts = text.split()
    is_group = update.effective_chat.type in ("group", "supergroup")

    target_user_id = None
    amount = 0

    if is_group:
        reply = update.message.reply_to_message
        if not reply or not reply.from_user:
            await update.message.reply_text("대상의 메시지에 답장으로 'BP지급 [금액]' 을 입력하세요.")
            return
        target_user_id = reply.from_user.id
        if len(parts) >= 2:
            try:
                amount = int(parts[1])
            except ValueError:
                await update.message.reply_text("금액을 숫자로 입력해주세요.")
                return
        else:
            await update.message.reply_text("사용법: BP지급 [금액]")
            return
    else:
        if len(parts) < 3:
            await update.message.reply_text(
                "사용법: BP지급 [유저ID] [금액]\n"
                "예: BP지급 123456789 500\n"
                "그룹에서는 답장으로 사용 가능"
            )
            return
        try:
            target_user_id = int(parts[1])
        except ValueError:
            await update.message.reply_text("유저 ID를 숫자로 입력해주세요.")
            return
        try:
            amount = int(parts[2])
        except ValueError:
            await update.message.reply_text("금액을 숫자로 입력해주세요.")
            return

    if amount <= 0 or amount > 99999:
        await update.message.reply_text("금액은 1~99999 사이로 입력해주세요.")
        return

    user = await queries.get_user(target_user_id)
    if not user:
        await update.message.reply_text("유저를 찾을 수 없습니다. (봇 미등록)")
        return

    await bq.add_bp(target_user_id, amount, "admin")
    new_bp = await bq.get_bp(target_user_id)

    await update.message.reply_text(
        f"{icon_emoji('check')} BP 지급 완료!\n"
        f"대상: {user['display_name']}\n"
        f"지급: {amount} BP\n"
        f"현재 보유: {new_bp} BP",
        parse_mode="HTML",
    )

    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"🎁 BP {amount}을(를) 지급받았습니다!\n현재 보유: {new_bp} BP",
        )
    except Exception:
        pass

    logger.info(f"Admin granted {amount} BP to user {target_user_id}")


# ============================================================
# 구독권 지급 (관리자)
# ============================================================

async def grant_subscription_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '구독권지급 [티어] [일수]' command.
    - 그룹: 답장 + '구독권지급 [티어] [일수]'
    - DM: '구독권지급 [유저ID] [티어] [일수]'
    티어: basic / channel_owner (또는 베이직 / 채널장)
    일수 생략 시 30일
    """
    if not update.effective_user or not update.message:
        return
    if not is_admin(update.effective_user.id):
        return

    from database import subscription_queries as sq
    from datetime import datetime, timedelta

    text = (update.message.text or "").strip()
    parts = text.split()
    is_group = update.effective_chat.type in ("group", "supergroup")

    target_user_id = None
    tier = "basic"
    days = 30

    _TIER_MAP = {"베이직": "basic", "basic": "basic", "채널장": "channel_owner", "channel_owner": "channel_owner"}

    if is_group:
        reply = update.message.reply_to_message
        if not reply or not reply.from_user:
            await update.message.reply_text("대상의 메시지에 답장으로 '구독권지급 [티어] [일수]' 를 입력하세요.")
            return
        target_user_id = reply.from_user.id
        if len(parts) >= 2:
            tier = _TIER_MAP.get(parts[1], parts[1])
        if len(parts) >= 3:
            try:
                days = int(parts[2])
            except ValueError:
                pass
    else:
        if len(parts) < 2:
            await update.message.reply_text(
                "사용법: 구독권지급 [유저ID] [티어] [일수]\n"
                "예: 구독권지급 123456789 채널장 30\n"
                "티어: 베이직 / 채널장\n"
                "일수 생략 시 30일"
            )
            return
        try:
            target_user_id = int(parts[1])
        except ValueError:
            await update.message.reply_text("유저 ID를 숫자로 입력해주세요.")
            return
        if len(parts) >= 3:
            tier = _TIER_MAP.get(parts[2], parts[2])
        if len(parts) >= 4:
            try:
                days = int(parts[3])
            except ValueError:
                pass

    if tier not in config.SUBSCRIPTION_TIERS:
        await update.message.reply_text(f"유효하지 않은 티어입니다. (베이직 / 채널장)")
        return

    if days < 1 or days > 365:
        await update.message.reply_text("일수는 1~365 사이로 입력해주세요.")
        return

    user = await queries.get_user(target_user_id)
    if not user:
        await update.message.reply_text("유저를 찾을 수 없습니다. (봇 미등록)")
        return

    # 기존 구독이 있으면 만료일 연장, 없으면 새로 생성
    existing = await sq.get_active_subscription(target_user_id)
    if existing and existing["tier"] == tier:
        new_expires = existing["expires_at"] + timedelta(days=days)
    else:
        new_expires = datetime.utcnow() + timedelta(days=days)

    await sq.create_subscription(target_user_id, tier, new_expires, payment_id=None)

    tier_name = config.SUBSCRIPTION_TIERS[tier]["name"]
    exp_kst = (new_expires + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M")

    await update.message.reply_text(
        f"{icon_emoji('check')} 구독권 지급 완료!\n"
        f"대상: {user['display_name']}\n"
        f"티어: {tier_name}\n"
        f"기간: {days}일\n"
        f"만료: {exp_kst} (KST)",
        parse_mode="HTML",
    )

    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"🎁 {tier_name} 구독권 {days}일이 지급되었습니다!\n만료: {exp_kst} (KST)",
        )
    except Exception:
        pass

    logger.info(f"Admin granted {tier} subscription ({days}d) to user {target_user_id}")


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
        # 최소 멤버 수 체크 (관리자 제외)
        if not is_admin(user_id):
            room = await queries.get_chat_room(chat_id)
            member_count = room["member_count"] if room else 0
            if member_count < config.SPAWN_MIN_MEMBERS:
                await update.message.reply_text(
                    f"🚫 멤버가 {config.SPAWN_MIN_MEMBERS}명 이상인 방에서만 아케이드를 사용할 수 있습니다. (현재 {member_count}명)"
                )
                return

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


async def tournament_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: '대회방등록' / '대회방해제' — set tournament chat independently from arcade."""
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    text = (update.message.text or "").strip()
    chat_id = update.effective_chat.id

    if "해제" in text:
        await queries.set_tournament_chat_id(None)
        config.TOURNAMENT_CHAT_ID = None
        await update.message.reply_text("🏟️ 대회방 해제 완료.")
    else:
        await queries.set_tournament_chat_id(chat_id)
        config.TOURNAMENT_CHAT_ID = chat_id
        await update.message.reply_text(f"🏟️ 대회방 등록 완료!\n채팅방 ID: {chat_id}")


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


# ============================================================
# 구독 수동 승인 (admin DM command)
# ============================================================

async def manual_subscription_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: 구독승인 {user_id} {tier} — RPC 장애 시 수동 승인."""
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    text = (update.message.text or "").strip()
    parts = text.split()
    # 구독승인 {user_id} {tier?}
    if len(parts) < 2:
        await update.message.reply_text(
            "사용법: 구독승인 {user_id} {tier}\n"
            "tier: basic / channel_owner (기본: basic)"
        )
        return

    try:
        target_uid = int(parts[1])
    except ValueError:
        await update.message.reply_text("❌ user_id는 숫자여야 합니다.")
        return

    tier = parts[2] if len(parts) >= 3 else "basic"
    if tier not in config.SUBSCRIPTION_TIERS:
        await update.message.reply_text(f"❌ 알 수 없는 티어: {tier}\n사용 가능: {', '.join(config.SUBSCRIPTION_TIERS.keys())}")
        return

    from datetime import timezone
    from database import subscription_queries as sq

    tier_cfg = config.SUBSCRIPTION_TIERS[tier]
    duration = tier_cfg.get("duration_days", 30)

    # 기존 구독이 있으면 만료일부터 연장
    existing = await sq.get_active_subscription(target_uid)
    if existing and existing["tier"] == tier:
        base_date = existing["expires_at"]
    else:
        base_date = config.get_kst_now()

    expires_at = base_date + timedelta(days=duration)

    # pending payment 없으면 더미 생성
    pending = await sq.get_user_pending(target_uid)
    if pending:
        payment_id = pending["id"]
        await sq.confirm_payment(payment_id, f"manual_{int(config.get_kst_now().timestamp())}", "admin")
    else:
        payment_id = await sq.create_pending_payment(
            target_uid, tier, 0, 0.0, "MANUAL", expires_at,
        )
        await sq.confirm_payment(payment_id, f"manual_{int(config.get_kst_now().timestamp())}", "admin")

    await sq.create_subscription(target_uid, tier, expires_at, payment_id)

    tier_name = tier_cfg.get("name", tier)
    exp_kst = expires_at.astimezone(config.KST).strftime("%Y-%m-%d %H:%M")

    await update.message.reply_text(
        f"✅ 구독 수동 승인 완료!\n\n"
        f"유저: {target_uid}\n"
        f"티어: {tier_name}\n"
        f"만료: {exp_kst} (KST)"
    )

    # 유저에게 DM 알림
    try:
        await context.bot.send_message(
            chat_id=target_uid,
            text=(
                f"✅ <b>구독이 활성화되었습니다!</b>\n\n"
                f"💎 티어: {tier_name}\n"
                f"📅 만료: {exp_kst} (KST)\n\n"
                f"DM에서 '구독정보'로 혜택을 확인하세요!"
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass


# ─── 어뷰징 관리 명령어 ───────────────────────────────
async def abuse_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """관리자 명령 '어뷰징' — 의심 유저 목록."""
    if not update.effective_user or update.effective_user.id not in config.ADMIN_IDS:
        return
    flagged = await get_flagged_users(20)
    if not flagged:
        await update.message.reply_text("✅ 현재 의심 유저가 없습니다.")
        return

    lines = ["🚨 <b>봇 의심 유저 목록</b>\n"]
    for u in flagged:
        name = u.get("display_name", "???")
        uname = f"@{u['username']}" if u.get("username") else ""
        score = u.get("bot_score", 0)
        total = u.get("total_challenges", 0)
        fails = u.get("challenge_fails", 0)
        lines.append(
            f"• {name} {uname} — 점수: <b>{score:.2f}</b> "
            f"(챌린지 {total}회, 실패 {fails}회)\n"
            f"  <code>/어뷰징상세 {u['user_id']}</code>"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def abuse_detail_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """관리자 명령 '어뷰징상세 ID' — 특정 유저 상세."""
    if not update.effective_user or update.effective_user.id not in config.ADMIN_IDS:
        return
    text = update.message.text.strip()
    parts = text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await update.message.reply_text("사용법: 어뷰징상세 <유저ID>")
        return

    target_id = int(parts[1])
    detail = await get_user_abuse_detail(target_id)
    if not detail or not detail.get("score"):
        await update.message.reply_text(f"유저 {target_id}의 어뷰징 기록이 없습니다.")
        return

    s = detail["score"]
    lines = [
        f"🔍 <b>어뷰징 상세</b> — <code>{target_id}</code>\n",
        f"봇 점수: <b>{s.get('bot_score', 0):.3f}</b>",
        f"챌린지: 총 {s.get('total_challenges', 0)}회 | 통과 {s.get('challenge_passes', 0)} | 실패 {s.get('challenge_fails', 0)}",
        f"마지막 챌린지: {s.get('last_challenge_at', '-')}",
        f"마지막 플래그: {s.get('last_flagged_at', '-')}",
    ]

    # 최근 반응시간
    reactions = detail.get("reactions", [])
    if reactions:
        ms_list = [r["reaction_ms"] for r in reactions if r.get("reaction_ms")]
        if ms_list:
            avg_ms = sum(ms_list) / len(ms_list)
            min_ms = min(ms_list)
            max_ms = max(ms_list)
            lines.append(f"\n📊 최근 반응시간 ({len(ms_list)}회):")
            lines.append(f"  평균: {avg_ms:.0f}ms | 최소: {min_ms}ms | 최대: {max_ms}ms")
            lines.append(f"  상세: {', '.join(f'{m}ms' for m in ms_list[:10])}")

    # 최근 챌린지
    challenges = detail.get("challenges", [])
    if challenges:
        lines.append(f"\n📋 최근 챌린지:")
        for c in challenges[:5]:
            status = "✅" if c.get("passed") else "❌"
            ans = c.get("given_answer", "무응답") or "무응답"
            lines.append(f"  {status} 정답: {c.get('expected_answer')} | 입력: {ans}")

    lines.append(f"\n점수 초기화: <code>어뷰징초기화 {target_id}</code>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def abuse_reset_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """관리자 명령 '어뷰징초기화 ID' — 점수 리셋."""
    if not update.effective_user or update.effective_user.id not in config.ADMIN_IDS:
        return
    text = update.message.text.strip()
    parts = text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await update.message.reply_text("사용법: 어뷰징초기화 <유저ID>")
        return

    target_id = int(parts[1])
    await admin_reset_score(target_id)
    await update.message.reply_text(f"✅ 유저 {target_id}의 봇 의심 점수가 초기화되었습니다.")


async def report_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '!리포트 MMDD' — 특정 날짜 일일 리포트 수동 트리거."""
    if not update.effective_user or not update.message:
        return
    if not is_admin(update.effective_user.id):
        return
    text = update.message.text.strip()
    parts = text.split()
    if len(parts) < 2 or len(parts[1]) != 4 or not parts[1].isdigit():
        await update.message.reply_text("사용법: !리포트 0316 (MMDD)")
        return

    from main import _send_daily_kpi_report
    mm, dd = int(parts[1][:2]), int(parts[1][2:])
    now = config.get_kst_now()
    target = now.replace(month=mm, day=dd, hour=0, minute=0, second=0, microsecond=0)
    await update.message.reply_text(f"📊 {mm}/{dd} 리포트 생성 중...")
    await _send_daily_kpi_report(context, target_date=target)
