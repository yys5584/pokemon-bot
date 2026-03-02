"""Check and unlock titles based on user activity."""

import logging
from database import queries
import config

logger = logging.getLogger(__name__)


async def check_and_unlock_titles(user_id: int) -> list[tuple[str, str, str]]:
    """Check all title conditions and unlock any new titles.

    Returns list of newly unlocked (title_id, name, emoji).
    """
    newly_unlocked = []
    stats = await queries.get_title_stats(user_id)
    pokedex_count = await queries.count_pokedex(user_id)
    legendary_count = await queries.count_legendary_caught(user_id)

    for title_id, (name, emoji, desc, check_type, threshold) in config.UNLOCKABLE_TITLES.items():
        # Skip if already unlocked
        if await queries.has_title(user_id, title_id):
            continue

        unlocked = False

        if check_type == "pokedex" or check_type == "pokedex_gen1":
            gen1_count = await queries.count_pokedex_gen1(user_id)
            unlocked = gen1_count >= threshold
        elif check_type == "pokedex_gen2":
            gen2_count = await queries.count_pokedex_gen2(user_id)
            unlocked = gen2_count >= threshold
        elif check_type == "pokedex_all":
            unlocked = pokedex_count >= threshold
        elif check_type == "legendary":
            unlocked = legendary_count >= threshold
        elif check_type == "first_catch":
            unlocked = pokedex_count >= 1
        elif check_type == "total_catch":
            total = await queries.count_total_catches(user_id)
            unlocked = total >= threshold
        elif check_type == "catch_fail":
            unlocked = stats.get("catch_fail_count", 0) >= threshold
        elif check_type == "midnight_catch":
            unlocked = stats.get("midnight_catch_count", 0) >= threshold
        elif check_type == "master_ball_own":
            balls = await queries.get_master_balls(user_id)
            unlocked = balls >= threshold
        elif check_type == "master_ball_use":
            unlocked = stats.get("master_ball_used", 0) >= threshold
        elif check_type == "love_count":
            unlocked = stats.get("love_count", 0) >= threshold
        elif check_type == "trade":
            trades = await queries.count_completed_trades(user_id)
            unlocked = trades >= threshold
        elif check_type == "common_catch":
            common = await queries.count_common_catches(user_id)
            unlocked = common >= threshold
        elif check_type == "rare_catch":
            rare = await queries.count_rare_epic_legendary(user_id)
            unlocked = rare >= threshold
        elif check_type == "streak":
            unlocked = stats.get("login_streak", 0) >= threshold
        # Battle titles (checked here for 칭호목록, also checked in battle_service)
        elif check_type in ("battle_total", "battle_wins", "battle_streak", "battle_sweep", "partner_set"):
            try:
                from database import battle_queries as bq
                battle_stats = await bq.get_battle_stats(user_id)
                total_battles = battle_stats["battle_wins"] + battle_stats["battle_losses"]
                if check_type == "battle_total":
                    unlocked = total_battles >= threshold
                elif check_type == "battle_wins":
                    unlocked = battle_stats["battle_wins"] >= threshold
                elif check_type == "battle_streak":
                    unlocked = battle_stats["best_streak"] >= threshold
                elif check_type == "partner_set":
                    partner = await bq.get_partner(user_id)
                    unlocked = partner is not None
                # battle_sweep is only checked in battle_service.py
            except Exception:
                pass

        if unlocked:
            was_new = await queries.unlock_title(user_id, title_id)
            if was_new:
                newly_unlocked.append((title_id, name, emoji))
                logger.info(f"Title unlocked: {name} for user {user_id}")

    return newly_unlocked
