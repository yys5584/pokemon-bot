"""Check Jun's camp settings."""
import asyncio
from database.connection import get_db, close_db


async def check():
    pool = await get_db()

    # Jun user search
    rows = await pool.fetch(
        "SELECT user_id, display_name, username FROM users "
        "WHERE username ILIKE '%jun%' OR display_name ILIKE '%jun%' LIMIT 10"
    )
    print("=== Jun candidates ===")
    for r in rows:
        print(f"  uid={r['user_id']} | {r['display_name']} | @{r['username']}")

    # All camp user settings
    settings = await pool.fetch("SELECT * FROM camp_user_settings")
    print(f"\n=== Camp settings ({len(settings)} users) ===")
    for s in settings:
        print(f"  uid={s['user_id']} home={s.get('home_chat_id')} home2={s.get('home_chat_id_2')}")

    # Available camps (same query as the bot uses)
    camps = await pool.fetch(
        """SELECT c.chat_id, c.level, cr.chat_title, cr.member_count, cr.invite_link, cr.is_active
           FROM camps c
           JOIN chat_rooms cr ON cr.chat_id = c.chat_id
           WHERE cr.is_active = 1
           ORDER BY cr.member_count DESC NULLS LAST
           LIMIT 50"""
    )
    print(f"\n=== Available camps ({len(camps)}) ===")
    for c in camps:
        print(f"  {c['chat_id']} | lv{c['level']} | {c['member_count']}명 | {c['chat_title']}")

    # Check minimum member count config
    print(f"\n=== CAMP_MIN_MEMBERS check ===")
    try:
        import config
        print(f"  CAMP_MIN_MEMBERS = {config.CAMP_MIN_MEMBERS}")
    except Exception as e:
        print(f"  Error: {e}")

    await close_db()


asyncio.run(check())
