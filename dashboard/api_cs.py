"""Dashboard API — CS 문의 시스템."""

import logging
import math
import time
from pathlib import Path

from aiohttp import web

import config
from database import cs_queries as csq

CS_UPLOAD_DIR = Path(__file__).parent.parent / "uploads" / "cs"

logger = logging.getLogger(__name__)

CS_PAGE_SIZE = 20

CATEGORY_LABELS = {
    "bug": "버그신고",
    "suggestion": "개선제안",
    "premium": "프리미엄",
    "other": "기타",
}

STATUS_LABELS = {
    "open": "대기중",
    "in_progress": "처리중",
    "resolved": "완료",
    "closed": "종료",
}


def _is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


def _time_ago(dt) -> str:
    if dt is None:
        return ""
    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc)
    diff = (now - dt).total_seconds()
    if diff < 60:
        return "방금"
    if diff < 3600:
        return f"{int(diff // 60)}분 전"
    if diff < 86400:
        return f"{int(diff // 3600)}시간 전"
    if diff < 604800:
        return f"{int(diff // 86400)}일 전"
    kst = dt + _dt.timedelta(hours=9)
    return kst.strftime("%m/%d")


# ──────────────────────────────────────────────
# Session helper (import from server)
# ──────────────────────────────────────────────
async def _get_session(request):
    from dashboard.server import _get_session as gs
    return await gs(request)


# ──────────────────────────────────────────────
# API endpoints
# ──────────────────────────────────────────────

async def api_cs_list(request: web.Request) -> web.Response:
    """GET /api/cs/inquiries — 문의 목록.
    view=public: 공개 문의 (비로그인도 가능)
    view=mine: 내 문의 (로그인 필요)
    view=admin: 전체 (관리자만)
    """
    session = await _get_session(request)
    view = request.query.get("view", "public")
    status_filter = request.query.get("status")
    page = int(request.query.get("page", 1))

    user_id = session["user_id"] if session else None
    is_admin = _is_admin(user_id) if user_id else False

    if view == "mine":
        if not session:
            return web.json_response({"error": "login_required"}, status=401)
        rows, total = await csq.get_inquiries(
            user_id=user_id, status=status_filter, page=page, page_size=CS_PAGE_SIZE
        )
    elif view == "admin" and is_admin:
        rows, total = await csq.get_inquiries(
            status=status_filter, page=page, page_size=CS_PAGE_SIZE
        )
    else:
        # public view — 공개 문의만
        rows, total = await csq.get_inquiries(
            public_only=True, status=status_filter, page=page, page_size=CS_PAGE_SIZE
        )

    for r in rows:
        r["category_label"] = CATEGORY_LABELS.get(r["category"], r["category"])
        r["status_label"] = STATUS_LABELS.get(r["status"], r["status"])
        r["time_ago"] = _time_ago(r["created_at"])
        r["created_at"] = r["created_at"].isoformat() if r["created_at"] else None
        r["replied_at"] = r["replied_at"].isoformat() if r.get("replied_at") else None

    return web.json_response({
        "items": rows,
        "total": total,
        "page": page,
        "pages": max(1, math.ceil(total / CS_PAGE_SIZE)),
        "is_admin": is_admin,
        "logged_in": bool(session),
    })


async def api_cs_detail(request: web.Request) -> web.Response:
    """GET /api/cs/inquiries/{id} — 문의 상세."""
    session = await _get_session(request)

    inquiry_id = int(request.match_info["id"])
    row = await csq.get_inquiry(inquiry_id)
    if not row:
        return web.json_response({"error": "not_found"}, status=404)

    user_id = session["user_id"] if session else None
    is_admin = _is_admin(user_id) if user_id else False

    # 비공개 문의: 본인 또는 관리자만
    if not row.get("is_public"):
        if not session:
            return web.json_response({"error": "login_required"}, status=401)
        if row["user_id"] != user_id and not is_admin:
            return web.json_response({"error": "forbidden"}, status=403)

    row["category_label"] = CATEGORY_LABELS.get(row["category"], row["category"])
    row["status_label"] = STATUS_LABELS.get(row["status"], row["status"])
    row["time_ago"] = _time_ago(row["created_at"])
    row["created_at"] = row["created_at"].isoformat() if row["created_at"] else None
    row["replied_at"] = row["replied_at"].isoformat() if row.get("replied_at") else None
    row["is_admin"] = is_admin
    row["has_liked"] = await csq.has_liked(user_id, inquiry_id) if user_id else False

    return web.json_response(row)


async def api_cs_create(request: web.Request) -> web.Response:
    """POST /api/cs/inquiries — 문의 작성 (multipart/form-data)."""
    session = await _get_session(request)
    if not session:
        return web.json_response({"error": "login_required"}, status=401)

    # Parse multipart
    try:
        reader = await request.multipart()
    except Exception:
        return web.json_response({"error": "Invalid form data"}, status=400)

    category = "other"
    title = ""
    content = ""
    is_public = True
    image_data = None
    image_ext = ""

    while True:
        part = await reader.next()
        if part is None:
            break
        if part.name == "category":
            category = (await part.text()).strip()
        elif part.name == "title":
            title = (await part.text()).strip()
        elif part.name == "content":
            content = (await part.text()).strip()
        elif part.name == "is_public":
            is_public = (await part.text()).strip() == "true"
        elif part.name == "image":
            if part.filename:
                image_ext = Path(part.filename).suffix.lower()
                if image_ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    return web.json_response(
                        {"error": "이미지는 jpg/png/gif/webp만 가능합니다."}, status=400
                    )
                image_data = await part.read(chunk_size=5 * 1024 * 1024 + 1)
                if len(image_data) > 5 * 1024 * 1024:
                    return web.json_response(
                        {"error": "이미지는 5MB 이하만 가능합니다."}, status=400
                    )

    if not title or not content:
        return web.json_response({"error": "제목과 내용을 입력해주세요."}, status=400)
    if len(title) > 100:
        return web.json_response({"error": "제목은 100자 이내로 입력해주세요."}, status=400)
    if len(content) > 2000:
        return web.json_response({"error": "내용은 2000자 이내로 입력해주세요."}, status=400)
    if category not in CATEGORY_LABELS:
        category = "other"

    user_id = session["user_id"]
    display_name = session.get("display_name", "")

    inquiry_id = await csq.create_inquiry(user_id, display_name, category, title, content, is_public=is_public)

    # Save image if provided
    image_filename = None
    if image_data:
        CS_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        image_filename = f"cs_{inquiry_id}_{ts}{image_ext}"
        filepath = CS_UPLOAD_DIR / image_filename
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(image_data))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            max_w = 1280
            if img.width > max_w:
                ratio = max_w / img.width
                img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            filepath = filepath.with_suffix(".jpg")
            image_filename = filepath.name
            with open(filepath, "wb") as f:
                f.write(buf.getvalue())
        except ImportError:
            with open(filepath, "wb") as f:
                f.write(image_data)

        from database.connection import get_db
        pool = await get_db()
        await pool.execute(
            "UPDATE cs_inquiries SET image_filename = $1 WHERE id = $2",
            image_filename, inquiry_id,
        )

    # 관리자 DM 알림
    cat_label = CATEGORY_LABELS.get(category, category)
    await _notify_admin_new_inquiry(inquiry_id, cat_label, title, display_name)

    return web.json_response({"id": inquiry_id, "ok": True})


async def api_cs_update(request: web.Request) -> web.Response:
    """PUT /api/cs/inquiries/{id} — 답변/상태 변경 (관리자)."""
    session = await _get_session(request)
    if not session:
        return web.json_response({"error": "login_required"}, status=401)
    if not _is_admin(session["user_id"]):
        return web.json_response({"error": "forbidden"}, status=403)

    inquiry_id = int(request.match_info["id"])
    data = await request.json()

    status = data.get("status")
    admin_reply = data.get("admin_reply")

    ok = await csq.update_inquiry(inquiry_id, status=status, admin_reply=admin_reply)
    if not ok:
        return web.json_response({"error": "not_found"}, status=404)

    # 답변 시 유저에게 DM 알림
    if admin_reply:
        inquiry = await csq.get_inquiry(inquiry_id)
        if inquiry:
            await _notify_user_reply(inquiry)

    return web.json_response({"ok": True})


async def api_cs_stats(request: web.Request) -> web.Response:
    """GET /api/cs/inquiries/stats — 미해결 건수."""
    session = await _get_session(request)
    if not session or not _is_admin(session["user_id"]):
        return web.json_response({"count": 0})
    count = await csq.get_open_count()
    return web.json_response({"count": count})


# ──────────────────────────────────────────────
# 알림 헬퍼
# ──────────────────────────────────────────────

async def _notify_admin_new_inquiry(inquiry_id, cat_label, title, display_name):
    """새 문의 접수 → 관리자 DM."""
    try:
        from main import application
        bot = application.bot
        for admin_id in config.ADMIN_IDS:
            await bot.send_message(
                chat_id=admin_id,
                text=(
                    f"📩 새 CS 문의 #{inquiry_id}\n"
                    f"분류: {cat_label}\n"
                    f"제목: {title}\n"
                    f"작성자: {display_name}\n\n"
                    f"대시보드에서 확인해주세요."
                ),
            )
    except Exception as e:
        logger.warning(f"CS admin notify failed: {e}")


async def _notify_user_reply(inquiry: dict):
    """관리자 답변 → 유저 DM."""
    try:
        from main import application
        bot = application.bot
        reply_preview = (inquiry["admin_reply"] or "")[:200]
        await bot.send_message(
            chat_id=inquiry["user_id"],
            text=(
                f"💬 문의 #{inquiry['id']} 답변 안내\n\n"
                f"제목: {inquiry['title']}\n"
                f"답변: {reply_preview}\n\n"
                f"대시보드에서 전체 내용을 확인하세요."
            ),
        )
    except Exception as e:
        logger.warning(f"CS user notify failed: {e}")


async def api_cs_like(request: web.Request) -> web.Response:
    """POST /api/cs/inquiries/{id}/like — 좋아요 토글."""
    session = await _get_session(request)
    if not session:
        return web.json_response({"error": "login_required"}, status=401)
    inquiry_id = int(request.match_info["id"])
    liked, count = await csq.toggle_like(session["user_id"], inquiry_id)
    return web.json_response({"liked": liked, "like_count": count})


async def api_cs_image(request: web.Request) -> web.Response:
    """GET /uploads/cs/{filename} — CS 첨부 이미지 서빙."""
    filename = request.match_info["filename"]
    filepath = CS_UPLOAD_DIR / filename
    if not filepath.exists():
        return web.Response(status=404)
    return web.FileResponse(filepath)


def setup_routes(app):
    """Register CS inquiry routes."""
    app.router.add_get("/api/cs/inquiries", api_cs_list)
    app.router.add_get("/api/cs/inquiries/stats", api_cs_stats)
    app.router.add_get("/api/cs/inquiries/{id}", api_cs_detail)
    app.router.add_post("/api/cs/inquiries", api_cs_create)
    app.router.add_put("/api/cs/inquiries/{id}", api_cs_update)
    app.router.add_post("/api/cs/inquiries/{id}/like", api_cs_like)
    app.router.add_get("/uploads/cs/{filename}", api_cs_image)
