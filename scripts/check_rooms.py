"""Check room spawn stats."""
import asyncio
from database.connection import get_db, close_db


async def check():
    pool = await get_db()

    rows = await pool.fetch("""
        SELECT s.chat_id, c.chat_title, c.member_count, c.is_arcade,
               c.force_spawn_count,
               COUNT(*) as spawn_count,
               COUNT(CASE WHEN s.is_resolved = 1 AND s.caught_by_user_id IS NOT NULL THEN 1 END) as caught,
               COUNT(CASE WHEN s.is_resolved = 1 AND s.caught_by_user_id IS NULL THEN 1 END) as escaped,
               COUNT(DISTINCT s.caught_by_user_id) FILTER (WHERE s.caught_by_user_id IS NOT NULL) as unique_catchers
        FROM spawn_sessions s
        LEFT JOIN chat_rooms c ON s.chat_id = c.chat_id
        WHERE s.spawned_at > NOW() - interval '24 hours'
        GROUP BY s.chat_id, c.chat_title, c.member_count, c.is_arcade, c.force_spawn_count
        ORDER BY spawn_count DESC
        LIMIT 30
    """)

    header = f"{'chat_id':<16} {'title':<25} {'mem':>4} {'arc':>4} {'fs':>3} {'spawn':>6} {'catch':>6} {'esc':>6} {'ppl':>4}"
    print(header)
    print("-" * len(header))
    for r in rows:
        title = (r["chat_title"] or "?")[:24]
        arc = "Y" if r["is_arcade"] else "N"
        fs = r["force_spawn_count"] or 0
        print(
            f"{r['chat_id']:<16} {title:<25} {r['member_count'] or 0:>4} {arc:>4} {fs:>3} "
            f"{r['spawn_count']:>6} {r['caught']:>6} {r['escaped']:>6} {r['unique_catchers']:>4}"
        )

    # Rooms with chat_title that is just a number or very short
    print("\n\n=== Suspicious rooms (no real title, < 5 members, or only 1 catcher) ===")
    sus = await pool.fetch("""
        SELECT s.chat_id, c.chat_title, c.member_count, c.is_arcade,
               COUNT(*) as spawn_count,
               COUNT(CASE WHEN s.caught_by_user_id IS NOT NULL THEN 1 END) as caught,
               COUNT(DISTINCT s.caught_by_user_id) FILTER (WHERE s.caught_by_user_id IS NOT NULL) as unique_catchers,
               array_agg(DISTINCT u.display_name) FILTER (WHERE u.display_name IS NOT NULL) as catcher_names
        FROM spawn_sessions s
        LEFT JOIN chat_rooms c ON s.chat_id = c.chat_id
        LEFT JOIN users u ON s.caught_by_user_id = u.user_id
        WHERE s.spawned_at > NOW() - interval '24 hours'
        GROUP BY s.chat_id, c.chat_title, c.member_count, c.is_arcade
        HAVING COUNT(DISTINCT s.caught_by_user_id) FILTER (WHERE s.caught_by_user_id IS NOT NULL) <= 2
           AND COUNT(*) >= 5
        ORDER BY spawn_count DESC
    """)
    for r in sus:
        title = (r["chat_title"] or "?")[:24]
        names = r["catcher_names"] or []
        arc = "Y" if r["is_arcade"] else "N"
        print(
            f"  {r['chat_id']:<16} {title:<25} mem={r['member_count'] or 0:>3} arc={arc} "
            f"spawn={r['spawn_count']:>4} catch={r['caught']:>4} catchers={r['unique_catchers']} "
            f"names={', '.join(str(n) for n in names[:3])}"
        )

    await close_db()


asyncio.run(check())
