"""매일 이벤트 스케줄러 — 20:30~21:00 KST 사이 랜덤 퀴즈 스폰."""

from __future__ import annotations

import logging
import random

from telegram.ext import ContextTypes

import config
from database import event_queries as eq
from database import queries
from services.quiz_service import start_quiz

_log = logging.getLogger(__name__)


async def schedule_daily_quiz(context: ContextTypes.DEFAULT_TYPE):
    """매일 20:30 KST에 호출 → 0~30분 랜덤 딜레이 후 퀴즈 트리거."""
    delay_seconds = random.randint(0, 30) * 60  # 0~30분
    _log.info(f"Daily quiz scheduled: delay={delay_seconds}s ({delay_seconds // 60}min)")
    context.job_queue.run_once(
        _trigger_daily_quiz,
        when=delay_seconds,
        name="daily_quiz_trigger",
    )


async def _trigger_daily_quiz(context: ContextTypes.DEFAULT_TYPE):
    """실제 퀴즈 시작 — 등록 채널 중 랜덤 1개 선택."""
    channels = await eq.get_active_event_channels()
    if not channels:
        _log.info("No event channels registered, skipping daily quiz")
        return

    chosen = random.choice(channels)
    invite_link = chosen["invite_link"]
    _log.info(f"Daily quiz triggering in channel: invite_link={invite_link}")

    # 채널 초대링크에서 chat_id를 찾아야 함
    # invite_link로 직접 chat_id를 알 수 없으므로, 봇이 참여 중인 채팅방 중 매칭
    # → 등록 시 chat_id를 저장하거나, 봇이 참여 중인 방 목록에서 찾기
    # 일단 invite_link 기반으로 chat_rooms 테이블에서 매칭
    from database.connection import get_db
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT chat_id FROM chat_rooms WHERE invite_link = $1 AND is_active = 1 LIMIT 1",
        invite_link,
    )

    if not row:
        _log.warning(f"No active chat room found for invite_link={invite_link}")
        return

    chat_id = row["chat_id"]

    # 퀴즈 시작
    ok = await start_quiz(context, chat_id)
    if not ok:
        _log.warning(f"Failed to start quiz in chat_id={chat_id}")
        return

    # DM 알림 발송 (최근 3시간 활동 유저)
    await _send_quiz_alerts(context, chat_id, invite_link)


async def _send_quiz_alerts(context: ContextTypes.DEFAULT_TYPE, chat_id: int, invite_link: str):
    """최근 3시간 활동 유저에게 DM 알림."""
    try:
        user_ids = await queries.get_recently_active_user_ids(minutes=180)
    except Exception as e:
        _log.error(f"Failed to get active users for quiz alert: {e}")
        return

    alert_text = (
        "🧠 <b>오늘의 포켓몬은 뭘까요?</b>\n\n"
        "5문제 x 30초, 선착순 5명 <b>IV선택리롤</b> 지급!\n"
        "참가만 해도 BP 지급!\n\n"
        f"👉 지금 참여하기: {invite_link}"
    )

    sent = 0
    for uid in user_ids:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=alert_text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            sent += 1
        except Exception:
            pass  # 봇 차단 등

    _log.info(f"Quiz DM alerts sent: {sent}/{len(user_ids)}")
