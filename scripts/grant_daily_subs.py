"""Manually grant daily subscription benefits."""
import asyncio
import config
from database.connection import get_db, close_db
from database import queries, subscription_queries as sq

from database import item_queries
async def grant():
    pool = await get_db()
    subs = await sq.get_all_active_subscriptions()
    print(f"Granting to {len(subs)} subscribers...")

    for sub in subs:
        uid = sub["user_id"]
        tier_cfg = config.SUBSCRIPTION_TIERS.get(sub["tier"], {})
        benefits = tier_cfg.get("benefits", {})
        tier_name = tier_cfg.get("name", "?")

        rewards = []

        daily_master = benefits.get("daily_masterball", 0)
        if daily_master:
            await queries.add_master_ball(uid, daily_master)
            rewards.append(f"마스터볼+{daily_master}")

        daily_hyper = benefits.get("daily_hyperball", 0)
        if daily_hyper:
            await queries.add_hyper_ball(uid, daily_hyper)
            rewards.append(f"하이퍼볼+{daily_hyper}")

        daily_arcade = benefits.get("daily_free_arcade_pass", 0)
        if daily_arcade:
            await queries.add_arcade_ticket(uid, daily_arcade)
            rewards.append(f"아케이드+{daily_arcade}")

        daily_shiny = benefits.get("daily_shiny_ticket", 0)
        if daily_shiny:
            await item_queries.add_shiny_spawn_ticket(uid, daily_shiny)
            rewards.append(f"이로치강스+{daily_shiny}")

        print(f"  uid={uid} tier={tier_name}: {', '.join(rewards) if rewards else 'no benefits'}")

    await close_db()
    print("Done!")

asyncio.run(grant())
