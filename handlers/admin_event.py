"""Admin event handlers: 이벤트 시작/목록/종료/DM 브로드캐스트."""

import asyncio
import logging
from datetime import timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import config

from database import queries
from handlers.admin import is_admin
from services.event_service import invalidate_event_cache
from utils.helpers import icon_emoji

logger = logging.getLogger(__name__)


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

    try:
        event_id = int(query.data.split("_")[-1])
    except (ValueError, IndexError):
        return

    events = await queries.get_active_events()
    event = next((e for e in events if e["id"] == event_id), None)
    if not event:
        await query.edit_message_text("이벤트를 찾을 수 없습니다. (이미 종료됨)")
        return

    await query.edit_message_reply_markup(reply_markup=None)

    active_user_ids = await queries.get_recently_active_user_ids(minutes=180)
    total = len(active_user_ids)

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
