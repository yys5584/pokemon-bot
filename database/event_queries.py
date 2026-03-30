"""매일 이벤트 (퀴즈) DB 쿼리."""

from __future__ import annotations

import json
from datetime import date

from database.connection import get_db


# ── 이벤트 채널 등록 ──

async def register_event_channel(owner_id: int, invite_link: str) -> bool:
    """채널 등록 (1인 1채널). 이미 있으면 False."""
    pool = await get_db()
    try:
        await pool.execute(
            """INSERT INTO event_channels (owner_id, invite_link)
               VALUES ($1, $2)
               ON CONFLICT (owner_id) DO NOTHING""",
            owner_id, invite_link,
        )
        return True
    except Exception:
        return False


async def update_event_channel_link(owner_id: int, invite_link: str) -> bool:
    """초대링크 수정."""
    pool = await get_db()
    row = await pool.fetchrow(
        "UPDATE event_channels SET invite_link = $2 WHERE owner_id = $1 AND is_active = 1 RETURNING id",
        owner_id, invite_link,
    )
    return row is not None


async def unregister_event_channel(owner_id: int) -> bool:
    """채널 해제."""
    pool = await get_db()
    row = await pool.fetchrow(
        "UPDATE event_channels SET is_active = 0 WHERE owner_id = $1 AND is_active = 1 RETURNING id",
        owner_id,
    )
    return row is not None


async def get_event_channel_by_owner(owner_id: int) -> dict | None:
    """내 등록 채널 조회."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT * FROM event_channels WHERE owner_id = $1 AND is_active = 1",
        owner_id,
    )
    return dict(row) if row else None


async def get_active_event_channels() -> list[dict]:
    """활성 이벤트 채널 목록."""
    pool = await get_db()
    rows = await pool.fetch(
        "SELECT * FROM event_channels WHERE is_active = 1",
    )
    return [dict(r) for r in rows]


# ── 일일 이벤트 ──

async def create_daily_event(
    event_date: date,
    chat_id: int,
    quiz_data: list[dict],
    event_type: str = "quiz",
) -> int:
    """일일 이벤트 생성. 반환: event_id."""
    pool = await get_db()
    row = await pool.fetchrow(
        """INSERT INTO daily_events (event_date, event_type, chat_id, quiz_data, status)
           VALUES ($1, $2, $3, $4, 'pending')
           RETURNING id""",
        event_date, event_type, chat_id, json.dumps(quiz_data, ensure_ascii=False),
    )
    return row["id"]


async def update_event_status(event_id: int, status: str):
    """이벤트 상태 업데이트."""
    pool = await get_db()
    if status == "active":
        await pool.execute(
            "UPDATE daily_events SET status = $2, started_at = NOW() WHERE id = $1",
            event_id, status,
        )
    elif status == "ended":
        await pool.execute(
            "UPDATE daily_events SET status = $2, ended_at = NOW() WHERE id = $1",
            event_id, status,
        )
    else:
        await pool.execute(
            "UPDATE daily_events SET status = $2 WHERE id = $1",
            event_id, status,
        )


async def get_today_event(event_date: date) -> dict | None:
    """오늘 이벤트 조회."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT * FROM daily_events WHERE event_date = $1 ORDER BY id DESC LIMIT 1",
        event_date,
    )
    return dict(row) if row else None


# ── 퀴즈 참가자 ──

async def record_quiz_answer(
    event_id: int,
    user_id: int,
    question_num: int,
    rank_in_question: int,
) -> bool:
    """정답 기록. 중복이면 False."""
    pool = await get_db()
    try:
        await pool.execute(
            """INSERT INTO event_participants (event_id, user_id, question_num, rank_in_question)
               VALUES ($1, $2, $3, $4)""",
            event_id, user_id, question_num, rank_in_question,
        )
        return True
    except Exception:
        return False


async def get_event_results(event_id: int) -> list[dict]:
    """이벤트 결과 집계 — 유저별 정답 수, 총 등수합."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT user_id,
                  COUNT(*) AS correct_count,
                  SUM(CASE WHEN rank_in_question = 1 THEN 1 ELSE 0 END) AS first_count,
                  SUM(rank_in_question) AS rank_sum,
                  MIN(answered_at) AS first_answer_at
           FROM event_participants
           WHERE event_id = $1
           GROUP BY user_id
           ORDER BY correct_count DESC, first_count DESC, rank_sum ASC""",
        event_id,
    )
    return [dict(r) for r in rows]


async def get_event_participant_ids(event_id: int) -> set[int]:
    """이벤트에 참가한 모든 유저 ID (정답 맞춘 적 있는)."""
    pool = await get_db()
    rows = await pool.fetch(
        "SELECT DISTINCT user_id FROM event_participants WHERE event_id = $1",
        event_id,
    )
    return {r["user_id"] for r in rows}
