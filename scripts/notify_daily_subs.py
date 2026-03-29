"""Send DM notification for daily subscription benefits (already granted)."""
import asyncio
import config
from database.connection import get_db, close_db
from database import subscription_queries as sq
from telegram import Bot


BOT_TOKEN = None


async def notify():
    # load token from .env
    import os
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("BOT_TOKEN not set")
        return

    bot = Bot(token=token)
    pool = await get_db()
    subs = await sq.get_all_active_subscriptions()
    print(f"Sending DM to {len(subs)} subscribers...")

    for sub in subs:
        uid = sub["user_id"]
        tier_cfg = config.SUBSCRIPTION_TIERS.get(sub["tier"], {})
        benefits = tier_cfg.get("benefits", {})
        tier_name = tier_cfg.get("name", "프리미엄")

        reward_lines = []
        daily_master = benefits.get("daily_masterball", 0)
        if daily_master:
            reward_lines.append(f"🔴 마스터볼 +{daily_master}")
        daily_hyper = benefits.get("daily_hyperball", 0)
        if daily_hyper:
            reward_lines.append(f"🔵 하이퍼볼 +{daily_hyper}")
        daily_arcade = benefits.get("daily_free_arcade_pass", 0)
        if daily_arcade:
            reward_lines.append(f"🎰 아케이드 이용권 +{daily_arcade}")
        daily_shiny = benefits.get("daily_shiny_ticket", 0)
        if daily_shiny:
            reward_lines.append(f"✨ 이로치 강스권 +{daily_shiny}")

        if reward_lines:
            text = (
                f"💎 <b>{tier_name}</b> 일일 혜택 지급!\n"
                "━━━━━━━━━━━━━━━\n"
                + "\n".join(reward_lines)
            )
            try:
                await bot.send_message(chat_id=uid, text=text, parse_mode="HTML")
                print(f"  DM sent to uid={uid}")
            except Exception as e:
                print(f"  DM failed uid={uid}: {e}")

    await close_db()
    print("Done!")

asyncio.run(notify())
