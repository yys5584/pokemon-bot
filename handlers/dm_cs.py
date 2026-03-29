"""DM 문의 핸들러 — '문의' 명령어로 CS 접수."""

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from database import cs_queries as csq

logger = logging.getLogger(__name__)

CATEGORIES = [
    ("bug", "🐛 버그신고"),
    ("suggestion", "💡 개선제안"),
    ("premium", "💎 프리미엄"),
    ("other", "📋 기타"),
]
CAT_LABELS = dict(CATEGORIES)


async def dm_cs_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """'문의' 명령어 → 카테고리 선택."""
    keyboard = [
        [InlineKeyboardButton(label, callback_data=f"cs_cat_{key}")]
        for key, label in CATEGORIES
    ]
    keyboard.append([InlineKeyboardButton("❌ 취소", callback_data="cs_cancel")])
    await update.message.reply_text(
        "📩 CS 문의\n\n분류를 선택해주세요:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """콜백 처리: 카테고리 선택, 취소."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cs_cancel":
        context.user_data.pop("cs_state", None)
        await query.edit_message_text("문의가 취소되었습니다.")
        return

    if data.startswith("cs_cat_"):
        cat = data[7:]  # e.g. "bug"
        context.user_data["cs_state"] = {"step": "title", "category": cat}
        cat_label = CAT_LABELS.get(cat, cat)
        await query.edit_message_text(
            f"📩 분류: {cat_label}\n\n"
            "제목을 입력해주세요 (100자 이내):\n"
            "(취소: '취소' 입력)"
        )
        return


async def cs_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """텍스트 입력 처리: 제목 → 내용 → 접수."""
    state = context.user_data.get("cs_state")
    if not state:
        return False  # not in CS flow

    text = (update.message.text or "").strip()
    if text == "취소":
        context.user_data.pop("cs_state", None)
        await update.message.reply_text("문의가 취소되었습니다.")
        return True

    step = state.get("step")

    if step == "title":
        if len(text) > 100:
            await update.message.reply_text("제목은 100자 이내로 입력해주세요.")
            return True
        if len(text) < 2:
            await update.message.reply_text("제목을 2글자 이상 입력해주세요.")
            return True
        state["title"] = text
        state["step"] = "content"
        await update.message.reply_text(
            f"제목: {text}\n\n"
            "내용을 입력해주세요 (2000자 이내):\n"
            "(취소: '취소' 입력)"
        )
        return True

    if step == "content":
        if len(text) > 2000:
            await update.message.reply_text("내용은 2000자 이내로 입력해주세요.")
            return True
        if len(text) < 2:
            await update.message.reply_text("내용을 2글자 이상 입력해주세요.")
            return True

        user = update.effective_user
        user_id = user.id
        display_name = user.first_name or user.username or str(user_id)
        category = state["category"]
        title = state["title"]

        inquiry_id = await csq.create_inquiry(
            user_id, display_name, category, title, text
        )

        context.user_data.pop("cs_state", None)
        cat_label = CAT_LABELS.get(category, category)
        await update.message.reply_text(
            f"✅ 문의 #{inquiry_id} 접수 완료!\n\n"
            f"분류: {cat_label}\n"
            f"제목: {title}\n\n"
            "답변이 등록되면 DM으로 알려드립니다."
        )

        # 관리자 알림
        try:
            for admin_id in config.ADMIN_IDS:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=(
                        f"📩 새 CS 문의 #{inquiry_id}\n"
                        f"분류: {cat_label}\n"
                        f"제목: {title}\n"
                        f"작성자: {display_name}\n\n"
                        "대시보드에서 확인해주세요."
                    ),
                )
        except Exception as e:
            logger.warning(f"CS admin notify failed: {e}")

        return True

    return False
