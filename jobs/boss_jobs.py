"""Weekly Boss scheduled jobs."""

import logging
from datetime import datetime, timedelta, timezone

from telegram.ext import ContextTypes

import config
from services.boss_service import (
    create_weekly_boss, distribute_weekly_rewards, current_week_key,
)

logger = logging.getLogger(__name__)

_KST = timezone(timedelta(hours=9))


async def boss_weekly_reset_job(context: ContextTypes.DEFAULT_TYPE):
    """Monday 00:10 KST — distribute last week's rewards + create new boss."""
    now = datetime.now(_KST)

    # Only on Monday
    if now.weekday() != 0:
        return

    # Previous week key
    prev = now - timedelta(days=7)
    prev_wk = f"W{prev.isocalendar()[0]}-{prev.isocalendar()[1]:02d}"

    # Distribute rewards
    try:
        rewarded = await distribute_weekly_rewards(prev_wk)
        logger.info(f"Boss weekly rewards: {rewarded} users rewarded (week={prev_wk})")
    except Exception as e:
        logger.error(f"Boss weekly reward distribution failed: {e}", exc_info=True)

    # Create new boss
    try:
        boss = await create_weekly_boss()
        if boss:
            logger.info(f"New weekly boss: {boss['pokemon_name']} (HP={boss['max_hp']:,})")
    except Exception as e:
        logger.error(f"Boss creation failed: {e}", exc_info=True)
