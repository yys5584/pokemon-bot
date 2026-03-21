"""CS 문의 시스템 쿼리."""

import logging
from database.connection import get_db

logger = logging.getLogger(__name__)

CATEGORIES = {
    "bug": "버그신고",
    "suggestion": "개선제안",
    "premium": "프리미엄",
    "other": "기타",
}


async def create_inquiry(
    user_id: int, display_name: str, category: str, title: str, content: str
) -> int:
    """문의 생성. 생성된 id 반환."""
    pool = await get_db()
    row = await pool.fetchrow(
        """INSERT INTO cs_inquiries (user_id, display_name, category, title, content)
           VALUES ($1, $2, $3, $4, $5) RETURNING id""",
        user_id, display_name, category, title, content,
    )
    return row["id"]


async def get_inquiries(
    user_id: int | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    """문의 목록 조회. (rows, total_count) 반환.
    user_id=None이면 전체(관리자용), 지정하면 해당 유저만."""
    pool = await get_db()
    conditions = []
    params = []
    idx = 1

    if user_id is not None:
        conditions.append(f"user_id = ${idx}")
        params.append(user_id)
        idx += 1
    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    total = await pool.fetchval(
        f"SELECT count(*) FROM cs_inquiries {where}", *params
    )

    offset = (page - 1) * page_size
    rows = await pool.fetch(
        f"""SELECT id, user_id, display_name, category, title, status, created_at,
                   replied_at
            FROM cs_inquiries {where}
            ORDER BY created_at DESC
            LIMIT {page_size} OFFSET {offset}""",
        *params,
    )
    return [dict(r) for r in rows], total


async def get_inquiry(inquiry_id: int) -> dict | None:
    """문의 상세 조회."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT id, user_id, display_name, category, title, content,
                  status, admin_reply, replied_at, created_at
           FROM cs_inquiries WHERE id = $1""",
        inquiry_id,
    )
    return dict(row) if row else None


async def update_inquiry(
    inquiry_id: int, status: str | None = None, admin_reply: str | None = None
) -> bool:
    """관리자 답변/상태 변경."""
    pool = await get_db()
    sets = []
    params = []
    idx = 1

    if status:
        sets.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    if admin_reply is not None:
        sets.append(f"admin_reply = ${idx}")
        params.append(admin_reply)
        idx += 1
        sets.append(f"replied_at = NOW()")

    if not sets:
        return False

    params.append(inquiry_id)
    result = await pool.execute(
        f"UPDATE cs_inquiries SET {', '.join(sets)} WHERE id = ${idx}",
        *params,
    )
    return result.endswith("1")


async def get_open_count() -> int:
    """미해결 문의 건수."""
    pool = await get_db()
    return await pool.fetchval(
        "SELECT count(*) FROM cs_inquiries WHERE status IN ('open', 'in_progress')"
    )
