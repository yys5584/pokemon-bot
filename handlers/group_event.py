"""매일 이벤트 — 퀴즈 정답 감지 + 채널 등록 DM 핸들러."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from database import event_queries as eq
from database import subscription_queries as sq
from services.quiz_service import get_active_quiz, handle_answer

_log = logging.getLogger(__name__)


# ── 그룹: 퀴즈 정답 감지 ──

async def quiz_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """그룹 채팅에서 퀴즈 정답 감지.

    퀴즈가 활성 상태인 채팅방에서만 동작.
    비활성이면 즉시 return (무응답 — 그룹 보호).
    """
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id

    # 퀴즈 비활성 → 즉시 무시 (그룹 보호)
    if get_active_quiz(chat_id) is None:
        return

    user = update.effective_user
    text = update.message.text.strip()
    display_name = user.first_name or user.username or str(user.id)

    await handle_answer(context, chat_id, user.id, text, display_name)


# ── DM: 채널 등록/수정/해제 ──

async def channel_register_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """DM에서 '채널등록' → 초대링크 입력 안내."""
    user_id = update.effective_user.id

    # 구독 확인
    sub = await sq.get_active_subscription(user_id)
    if not sub or sub["tier"] != "channel_owner":
        await update.message.reply_text(
            "❌ 채널장 구독권 보유자만 등록할 수 있습니다.",
            parse_mode="HTML",
        )
        return

    # 이미 등록 확인
    existing = await eq.get_event_channel_by_owner(user_id)
    if existing:
        await update.message.reply_text(
            f"이미 등록된 채널이 있습니다.\n"
            f"🔗 {existing['invite_link']}\n\n"
            f"링크 변경: <b>채널수정</b>\n"
            f"해제: <b>채널해제</b>",
            parse_mode="HTML",
        )
        return

    # 링크 입력 대기 상태 저장
    context.user_data["awaiting_channel_link"] = True
    await update.message.reply_text(
        "📢 매일 퀴즈 이벤트에 참여할 채널의 <b>초대링크</b>를 입력해주세요.\n\n"
        "예: <code>https://t.me/mychannel</code>\n"
        "취소: <b>취소</b>",
        parse_mode="HTML",
    )


async def channel_link_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """DM에서 채널 초대링크 입력 처리."""
    if not context.user_data.get("awaiting_channel_link") and \
       not context.user_data.get("awaiting_channel_modify"):
        return

    user_id = update.effective_user.id
    text = update.message.text.strip()

    if text in ("취소", "ㅊㅅ"):
        context.user_data.pop("awaiting_channel_link", None)
        context.user_data.pop("awaiting_channel_modify", None)
        await update.message.reply_text("취소되었습니다.")
        return

    # 간단한 링크 검증
    if not text.startswith("https://t.me/") and not text.startswith("t.me/"):
        await update.message.reply_text(
            "❌ 올바른 텔레그램 초대링크를 입력해주세요.\n"
            "예: <code>https://t.me/mychannel</code>",
            parse_mode="HTML",
        )
        return

    if not text.startswith("https://"):
        text = "https://" + text

    if context.user_data.get("awaiting_channel_link"):
        context.user_data.pop("awaiting_channel_link", None)
        ok = await eq.register_event_channel(user_id, text)
        if ok:
            await update.message.reply_text(
                f"✅ 채널 등록 완료!\n🔗 {text}\n\n"
                f"매일 저녁 퀴즈 이벤트가 이 채널에서 열릴 수 있습니다.",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text("❌ 등록 실패. 다시 시도해주세요.")

    elif context.user_data.get("awaiting_channel_modify"):
        context.user_data.pop("awaiting_channel_modify", None)
        ok = await eq.update_event_channel_link(user_id, text)
        if ok:
            await update.message.reply_text(
                f"✅ 채널 링크 수정 완료!\n🔗 {text}",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text("❌ 등록된 채널이 없습니다. 먼저 <b>채널등록</b>을 해주세요.", parse_mode="HTML")


async def channel_modify_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """DM에서 '채널수정' → 새 링크 입력."""
    user_id = update.effective_user.id
    existing = await eq.get_event_channel_by_owner(user_id)
    if not existing:
        await update.message.reply_text(
            "등록된 채널이 없습니다. 먼저 <b>채널등록</b>을 해주세요.",
            parse_mode="HTML",
        )
        return

    context.user_data["awaiting_channel_modify"] = True
    await update.message.reply_text(
        f"현재 등록: {existing['invite_link']}\n\n"
        f"새 <b>초대링크</b>를 입력해주세요.\n취소: <b>취소</b>",
        parse_mode="HTML",
    )


async def channel_unregister_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """DM에서 '채널해제'."""
    user_id = update.effective_user.id
    ok = await eq.unregister_event_channel(user_id)
    if ok:
        await update.message.reply_text("✅ 채널 등록이 해제되었습니다.")
    else:
        await update.message.reply_text("등록된 채널이 없습니다.")


# ── 관리자: 강제 퀴즈 트리거 ──

async def admin_force_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """관리자 전용: 현재 채팅방에서 즉시 퀴즈 시작."""
    from services.quiz_service import start_quiz
    import config as cfg

    user_id = update.effective_user.id
    if user_id != 1832746512:  # 관리자 ID
        return

    chat_id = update.effective_chat.id
    ok = await start_quiz(context, chat_id, test_mode=True)
    if not ok:
        await update.message.reply_text("퀴즈가 이미 진행 중입니다.")
