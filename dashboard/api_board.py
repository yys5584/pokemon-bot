"""Dashboard API — Board (Community) 게시판 CRUD."""

import logging
import math
import time
from pathlib import Path

from aiohttp import web

import config
from database import queries

logger = logging.getLogger(__name__)

BOARD_PAGE_SIZE = 20
BOARD_UPLOAD_DIR = Path(__file__).parent.parent / "uploads" / "board"


async def ensure_board_tables():
    """Create board tables if not exists."""
    pool = await queries.get_db()
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS board_posts (
            id SERIAL PRIMARY KEY,
            board_type TEXT NOT NULL DEFAULT 'community',
            user_id BIGINT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            tag TEXT DEFAULT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            image_filename TEXT DEFAULT NULL,
            view_count INTEGER NOT NULL DEFAULT 0,
            like_count INTEGER NOT NULL DEFAULT 0,
            comment_count INTEGER NOT NULL DEFAULT 0,
            is_pinned INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await pool.execute(
        "CREATE INDEX IF NOT EXISTS idx_board_posts_board "
        "ON board_posts(board_type, created_at DESC)"
    )
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS board_comments (
            id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL REFERENCES board_posts(id),
            user_id BIGINT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await pool.execute(
        "CREATE INDEX IF NOT EXISTS idx_board_comments_post "
        "ON board_comments(post_id)"
    )
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS board_likes (
            user_id BIGINT NOT NULL,
            post_id INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, post_id)
        )
    """)


def _board_time_ago(dt) -> str:
    """Convert datetime to Korean relative time string."""
    now = config.get_kst_now()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=config.KST)
    diff = now - dt
    secs = int(diff.total_seconds())
    if secs < 60:
        return "방금 전"
    if secs < 3600:
        return f"{secs // 60}분 전"
    if secs < 86400:
        return f"{secs // 3600}시간 전"
    if secs < 604800:
        return f"{secs // 86400}일 전"
    return dt.strftime("%m.%d")


async def api_board_posts(request):
    """GET /api/board/posts — list posts."""
    board_type = request.query.get("board_type", "notice")
    tag = request.query.get("tag", "")
    page = max(1, int(request.query.get("page", "1")))
    offset = (page - 1) * BOARD_PAGE_SIZE

    pool = await queries.get_db()

    where = "WHERE is_active = 1 AND board_type = $1"
    params: list = [board_type]
    if tag:
        where += " AND tag = $2"
        params.append(tag)

    total = await pool.fetchval(
        f"SELECT COUNT(*) FROM board_posts {where}", *params
    )

    # pinned first, then newest
    idx = len(params) + 1
    rows = await pool.fetch(
        f"SELECT id, board_type, tag, title, display_name, image_filename, "
        f"view_count, like_count, comment_count, is_pinned, created_at "
        f"FROM board_posts {where} "
        f"ORDER BY is_pinned DESC, created_at DESC "
        f"LIMIT ${idx} OFFSET ${idx + 1}",
        *params, BOARD_PAGE_SIZE, offset,
    )

    posts = []
    for r in rows:
        posts.append({
            "id": r["id"],
            "board_type": r["board_type"],
            "tag": r["tag"],
            "title": r["title"],
            "display_name": r["display_name"],
            "has_image": bool(r["image_filename"]),
            "view_count": r["view_count"],
            "like_count": r["like_count"],
            "comment_count": r["comment_count"],
            "is_pinned": r["is_pinned"],
            "time_ago": _board_time_ago(r["created_at"]),
            "created_at": r["created_at"].isoformat(),
        })

    return web.json_response({
        "total": total, "page": page,
        "total_pages": math.ceil(total / BOARD_PAGE_SIZE) if total else 1,
        "posts": posts,
    })


async def api_board_post_detail(request):
    """GET /api/board/posts/{id} — post detail + comments."""
    from dashboard.server import _get_session

    post_id = int(request.match_info["id"])
    pool = await queries.get_db()

    row = await pool.fetchrow(
        "SELECT * FROM board_posts WHERE id = $1 AND is_active = 1", post_id
    )
    if not row:
        return web.json_response({"error": "Not found"}, status=404)

    # Increment view count
    await pool.execute(
        "UPDATE board_posts SET view_count = view_count + 1 WHERE id = $1", post_id
    )

    # Comments
    comments_rows = await pool.fetch(
        "SELECT id, user_id, display_name, content, created_at "
        "FROM board_comments WHERE post_id = $1 AND is_active = 1 "
        "ORDER BY created_at ASC", post_id
    )
    comments = [{
        "id": c["id"], "user_id": c["user_id"],
        "display_name": c["display_name"], "content": c["content"],
        "time_ago": _board_time_ago(c["created_at"]),
        "created_at": c["created_at"].isoformat(),
    } for c in comments_rows]

    # Check if current user liked
    liked = False
    sess = await _get_session(request)
    if sess:
        like_row = await pool.fetchval(
            "SELECT 1 FROM board_likes WHERE user_id = $1 AND post_id = $2",
            sess["user_id"], post_id,
        )
        liked = bool(like_row)

    post = {
        "id": row["id"], "board_type": row["board_type"],
        "tag": row["tag"], "title": row["title"],
        "user_id": row["user_id"], "display_name": row["display_name"],
        "content": row["content"],
        "image_filename": row["image_filename"],
        "view_count": row["view_count"] + 1,
        "like_count": row["like_count"],
        "comment_count": row["comment_count"],
        "is_pinned": row["is_pinned"],
        "time_ago": _board_time_ago(row["created_at"]),
        "created_at": row["created_at"].isoformat(),
    }

    return web.json_response({"post": post, "comments": comments, "liked": liked})


async def api_board_post_create(request):
    """POST /api/board/posts — create a post."""
    from dashboard.server import _get_session
    from dashboard.api_admin import _admin_check

    sess = await _get_session(request)
    if not sess:
        return web.json_response({"error": "Login required"}, status=401)

    # Parse multipart form
    try:
        reader = await request.multipart()
    except Exception:
        return web.json_response({"error": "Invalid form data"}, status=400)

    board_type = "community"
    tag = None
    title = ""
    content = ""
    image_data = None
    image_ext = ""

    while True:
        part = await reader.next()
        if part is None:
            break
        if part.name == "board_type":
            board_type = (await part.text()).strip()
        elif part.name == "tag":
            tag = (await part.text()).strip() or None
        elif part.name == "title":
            title = (await part.text()).strip()
        elif part.name == "content":
            content = (await part.text()).strip()
        elif part.name == "image":
            if part.filename:
                image_ext = Path(part.filename).suffix.lower()
                if image_ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    return web.json_response(
                        {"error": "Image must be jpg/png/gif/webp"}, status=400
                    )
                image_data = await part.read(chunk_size=5 * 1024 * 1024 + 1)
                if len(image_data) > 5 * 1024 * 1024:
                    return web.json_response(
                        {"error": "Image too large (max 5MB)"}, status=400
                    )

    # Validate board_type
    if board_type not in ("notice", "community"):
        return web.json_response({"error": "Invalid board_type"}, status=400)

    # Notice: admin only
    if board_type == "notice":
        admin = await _admin_check(request)
        if not admin:
            return web.json_response({"error": "Admin only"}, status=403)

    # Validate lengths
    if len(title) < 2 or len(title) > 80:
        return web.json_response({"error": "제목은 2~80자"}, status=400)
    if len(content) < 5 or len(content) > 5000:
        return web.json_response({"error": "내용은 5~5000자"}, status=400)

    pool = await queries.get_db()

    # Insert post
    post_id = await pool.fetchval(
        "INSERT INTO board_posts (board_type, user_id, display_name, tag, title, content) "
        "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
        board_type, sess["user_id"], sess["display_name"], tag, title, content,
    )

    # Save image if provided
    image_filename = None
    if image_data:
        BOARD_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        image_filename = f"{post_id}_{ts}{image_ext}"
        filepath = BOARD_UPLOAD_DIR / image_filename

        # Try to resize with PIL, fallback to raw save
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
            # No PIL — save raw
            with open(filepath, "wb") as f:
                f.write(image_data)

        await pool.execute(
            "UPDATE board_posts SET image_filename = $1 WHERE id = $2",
            image_filename, post_id,
        )

    return web.json_response({"ok": True, "id": post_id})


async def api_board_post_delete(request):
    """DELETE /api/board/posts/{id}."""
    from dashboard.server import _get_session

    sess = await _get_session(request)
    if not sess:
        return web.json_response({"error": "Login required"}, status=401)

    post_id = int(request.match_info["id"])
    pool = await queries.get_db()

    row = await pool.fetchrow(
        "SELECT user_id FROM board_posts WHERE id = $1 AND is_active = 1", post_id
    )
    if not row:
        return web.json_response({"error": "Not found"}, status=404)

    # Owner or admin
    is_admin = sess["user_id"] in config.ADMIN_IDS
    if row["user_id"] != sess["user_id"] and not is_admin:
        return web.json_response({"error": "Permission denied"}, status=403)

    await pool.execute(
        "UPDATE board_posts SET is_active = 0 WHERE id = $1", post_id
    )
    return web.json_response({"ok": True})


async def api_board_post_pin(request):
    """POST /api/board/posts/{id}/pin — toggle pin (admin only)."""
    from dashboard.api_admin import _admin_check

    admin = await _admin_check(request)
    if not admin:
        return web.json_response({"error": "Admin only"}, status=403)

    post_id = int(request.match_info["id"])
    pool = await queries.get_db()

    current = await pool.fetchval(
        "SELECT is_pinned FROM board_posts WHERE id = $1 AND is_active = 1", post_id
    )
    if current is None:
        return web.json_response({"error": "Not found"}, status=404)

    new_val = 0 if current else 1
    await pool.execute(
        "UPDATE board_posts SET is_pinned = $1 WHERE id = $2", new_val, post_id
    )
    return web.json_response({"ok": True, "is_pinned": new_val})


async def api_board_post_like(request):
    """POST /api/board/posts/{id}/like — toggle like."""
    from dashboard.server import _get_session

    sess = await _get_session(request)
    if not sess:
        return web.json_response({"error": "Login required"}, status=401)

    post_id = int(request.match_info["id"])
    pool = await queries.get_db()

    exists = await pool.fetchval(
        "SELECT 1 FROM board_likes WHERE user_id = $1 AND post_id = $2",
        sess["user_id"], post_id,
    )

    if exists:
        await pool.execute(
            "DELETE FROM board_likes WHERE user_id = $1 AND post_id = $2",
            sess["user_id"], post_id,
        )
        await pool.execute(
            "UPDATE board_posts SET like_count = GREATEST(0, like_count - 1) WHERE id = $1",
            post_id,
        )
        liked = False
    else:
        await pool.execute(
            "INSERT INTO board_likes (user_id, post_id) VALUES ($1, $2) "
            "ON CONFLICT DO NOTHING",
            sess["user_id"], post_id,
        )
        await pool.execute(
            "UPDATE board_posts SET like_count = like_count + 1 WHERE id = $1",
            post_id,
        )
        liked = True

    new_count = await pool.fetchval(
        "SELECT like_count FROM board_posts WHERE id = $1", post_id
    )
    return web.json_response({"ok": True, "liked": liked, "like_count": new_count or 0})


async def api_board_comment_create(request):
    """POST /api/board/posts/{id}/comments — add comment."""
    from dashboard.server import _get_session

    sess = await _get_session(request)
    if not sess:
        return web.json_response({"error": "Login required"}, status=401)

    post_id = int(request.match_info["id"])
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    content = (body.get("content") or "").strip()
    if len(content) < 1 or len(content) > 500:
        return web.json_response({"error": "댓글은 1~500자"}, status=400)

    pool = await queries.get_db()

    # Check post exists
    post_exists = await pool.fetchval(
        "SELECT 1 FROM board_posts WHERE id = $1 AND is_active = 1", post_id
    )
    if not post_exists:
        return web.json_response({"error": "Post not found"}, status=404)

    comment_id = await pool.fetchval(
        "INSERT INTO board_comments (post_id, user_id, display_name, content) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        post_id, sess["user_id"], sess["display_name"], content,
    )
    await pool.execute(
        "UPDATE board_posts SET comment_count = comment_count + 1 WHERE id = $1",
        post_id,
    )

    return web.json_response({"ok": True, "id": comment_id})


async def api_board_comment_delete(request):
    """DELETE /api/board/comments/{id}."""
    from dashboard.server import _get_session

    sess = await _get_session(request)
    if not sess:
        return web.json_response({"error": "Login required"}, status=401)

    comment_id = int(request.match_info["id"])
    pool = await queries.get_db()

    row = await pool.fetchrow(
        "SELECT user_id, post_id FROM board_comments "
        "WHERE id = $1 AND is_active = 1", comment_id
    )
    if not row:
        return web.json_response({"error": "Not found"}, status=404)

    is_admin = sess["user_id"] in config.ADMIN_IDS
    if row["user_id"] != sess["user_id"] and not is_admin:
        return web.json_response({"error": "Permission denied"}, status=403)

    await pool.execute(
        "UPDATE board_comments SET is_active = 0 WHERE id = $1", comment_id
    )
    await pool.execute(
        "UPDATE board_posts SET comment_count = GREATEST(0, comment_count - 1) "
        "WHERE id = $1", row["post_id"],
    )
    return web.json_response({"ok": True})


async def api_board_image(request):
    """GET /uploads/board/{filename} — serve uploaded image."""
    filename = request.match_info["filename"]
    # Sanitize filename
    if "/" in filename or "\\" in filename or ".." in filename:
        return web.json_response({"error": "Invalid filename"}, status=400)
    filepath = BOARD_UPLOAD_DIR / filename
    if not filepath.exists():
        return web.json_response({"error": "Not found"}, status=404)
    return web.FileResponse(filepath)


def setup_routes(app):
    """Register Board (Community) routes."""
    app.router.add_get("/api/board/posts", api_board_posts)
    app.router.add_get("/api/board/posts/{id}", api_board_post_detail)
    app.router.add_post("/api/board/posts", api_board_post_create)
    app.router.add_delete("/api/board/posts/{id}", api_board_post_delete)
    app.router.add_post("/api/board/posts/{id}/pin", api_board_post_pin)
    app.router.add_post("/api/board/posts/{id}/like", api_board_post_like)
    app.router.add_post("/api/board/posts/{id}/comments", api_board_comment_create)
    app.router.add_delete("/api/board/comments/{id}", api_board_comment_delete)
    app.router.add_get("/uploads/board/{filename}", api_board_image)
