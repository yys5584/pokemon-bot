"""Check active subscriptions and grant daily benefits."""
import asyncio
from database.connection import get_db, close_db
from database import subscription_queries as sq


async def check():
    pool = await get_db()
    subs = await sq.get_all_active_subscriptions()
    print(f"Active subscriptions: {len(subs)}")
    for s in subs:
        uid = s["user_id"]
        tier = s["tier"]
        expires = s.get("expires_at", "?")
        print(f"  uid={uid} tier={tier} expires={expires}")
    await close_db()

asyncio.run(check())
