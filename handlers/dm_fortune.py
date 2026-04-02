"""DM 타로 리딩 핸들러 — 창백피카츄의 타로."""

from __future__ import annotations

import logging
from datetime import date, datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import queries
from services.fortune_service import (
    generate_reading, format_reading_message,
    get_zodiac, SPREADS, TOPIC_EMOJIS,
)

_log = logging.getLogger(__name__)


# ── DM: "타로" 명령 ──

async def tarot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """DM에서 '타로' 입력 시 주제 선택 메뉴."""
    user_id = update.effective_user.id

    # 하루 1회 제한 체크
    today = __import__("config").get_kst_now().date()
    last_reading = context.user_data.get("last_tarot_date")
    if last_reading == today.isoformat():
        await update.message.reply_text(
            "🔮 오늘은 이미 리딩을 받았어요.\n"
            "...카드는 하루에 한 번만 답해줘요.\n"
            "내일 다시 와줄래요? 기다리고 있을게.",
            parse_mode="HTML",
        )
        return

    buttons = [
        [
            InlineKeyboardButton("💕 연애", callback_data=f"tarot_topic_{user_id}_연애"),
            InlineKeyboardButton("💼 직장", callback_data=f"tarot_topic_{user_id}_직장"),
        ],
        [
            InlineKeyboardButton("💰 재물", callback_data=f"tarot_topic_{user_id}_재물"),
            InlineKeyboardButton("📈 투자", callback_data=f"tarot_topic_{user_id}_투자"),
        ],
        [
            InlineKeyboardButton("🤝 인간관계", callback_data=f"tarot_topic_{user_id}_인간관계"),
            InlineKeyboardButton("🌟 종합", callback_data=f"tarot_topic_{user_id}_종합"),
        ],
    ]

    await update.message.reply_text(
        "🔮 <b>창백피카츄의 타로</b>\n\n"
        "...어서 와요. 기다리고 있었어요.\n"
        "오늘은 어떤 이야기가 듣고 싶나요?\n",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def tarot_topic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """주제 선택 후 스프레드 선택 또는 바로 리딩."""
    query = update.callback_query
    await query.answer()

    data = query.data  # tarot_topic_{user_id}_{topic}
    parts = data.split("_")
    if len(parts) < 4:
        return

    user_id = int(parts[2])
    topic = parts[3]

    if query.from_user.id != user_id:
        await query.answer("다른 사람의 타로예요!", show_alert=True)
        return

    # 투자 주제면 투자 전용 스프레드, 연애면 연애 전용 스프레드 옵션 제공
    if topic == "투자":
        buttons = [
            [InlineKeyboardButton("🃏 쓰리카드 (과거/현재/미래)", callback_data=f"tarot_read_{user_id}_{topic}_three_card")],
            [InlineKeyboardButton("📊 투자 스프레드 (4장)", callback_data=f"tarot_read_{user_id}_{topic}_investment")],
        ]
    elif topic == "연애":
        buttons = [
            [InlineKeyboardButton("🃏 쓰리카드 (과거/현재/미래)", callback_data=f"tarot_read_{user_id}_{topic}_three_card")],
            [InlineKeyboardButton("💕 연애 스프레드 (5장)", callback_data=f"tarot_read_{user_id}_{topic}_love")],
        ]
    else:
        # 나머지 주제는 바로 쓰리카드
        await _do_reading(query, context, user_id, topic, "three_card")
        return

    await query.edit_message_text(
        f"🔮 {TOPIC_EMOJIS.get(topic, '🔮')} <b>{topic}</b> 리딩\n\n"
        "...어떤 배치로 볼까요?\n",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def tarot_read_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """스프레드 선택 후 실제 리딩."""
    query = update.callback_query
    await query.answer()

    data = query.data  # tarot_read_{user_id}_{topic}_{spread}
    parts = data.split("_")
    if len(parts) < 5:
        return

    user_id = int(parts[2])
    topic = parts[3]
    spread_type = "_".join(parts[4:])

    if query.from_user.id != user_id:
        await query.answer("다른 사람의 타로예요!", show_alert=True)
        return

    await _do_reading(query, context, user_id, topic, spread_type)


async def _do_reading(query, context, user_id: int, topic: str, spread_type: str):
    """실제 리딩 수행 + 메시지 전송."""
    # 생년월일 조회 (DB)
    birth_date = None
    try:
        from database.connection import get_db
        pool = await get_db()
        row = await pool.fetchrow(
            "SELECT birth_date FROM users WHERE user_id = $1", user_id
        )
        if row and row.get("birth_date"):
            birth_date = row["birth_date"]
            if isinstance(birth_date, datetime):
                birth_date = birth_date.date()
    except Exception:
        pass

    # 리딩 생성
    reading = generate_reading(
        topic=topic,
        spread_type=spread_type,
        birth_date=birth_date,
        user_id=user_id,
    )

    # 메시지 포맷
    msg = format_reading_message(reading)

    # 오늘 리딩 기록
    today = __import__("config").get_kst_now().date()
    context.user_data["last_tarot_date"] = today.isoformat()

    # DB에 리딩 기록 (통계용)
    try:
        from database.connection import get_db
        pool = await get_db()
        await pool.execute(
            """INSERT INTO tarot_readings (user_id, topic, spread_type, cards_json, reading_date)
               VALUES ($1, $2, $3, $4, $5)""",
            user_id, topic, spread_type,
            __import__("json").dumps(
                [{"card": c["card_name_en"], "reversed": c["reversed"], "position": c["position"]}
                 for c in reading["cards"]],
                ensure_ascii=False,
            ),
            today,
        )
    except Exception as e:
        _log.warning(f"Failed to log tarot reading: {e}")

    # 전송
    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔮 다른 주제로 보기", callback_data=f"tarot_again_{user_id}"),
    ]])

    await query.edit_message_text(
        msg,
        parse_mode="HTML",
        reply_markup=buttons,
    )


async def tarot_again_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """다시 보기 — 하루 1회 이미 사용했으면 안내."""
    query = update.callback_query
    await query.answer("오늘은 이미 리딩을 받았어요 🔮", show_alert=True)
