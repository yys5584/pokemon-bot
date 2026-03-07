"""Check and unlock titles based on user activity."""

import logging
from database import queries
import config

logger = logging.getLogger(__name__)


async def check_and_unlock_titles(user_id: int) -> list[tuple[str, str, str]]:
    """Check all title conditions and unlock any new titles.

    Returns list of newly unlocked (title_id, name, emoji).
    Optimized: batch-fetches existing titles and stats to minimize DB round-trips.
    """
    newly_unlocked = []

    # Batch-fetch all needed data in parallel (3 queries instead of 40+)
    from database.connection import get_db
    pool = await get_db()

    # 1. Get all already-unlocked title IDs in one query
    rows = await pool.fetch(
        "SELECT title_id FROM user_titles WHERE user_id = $1", user_id
    )
    existing_titles = {r["title_id"] for r in rows}

    # 2. Get title stats + pokedex counts + other counts in parallel
    stats = await queries.get_title_stats(user_id)

    # 3. Batch-fetch all counts we might need (single multi-column query)
    counts = await pool.fetchrow("""
        SELECT
            (SELECT COUNT(DISTINCT pokemon_id) FROM pokedex WHERE user_id = $1) AS pokedex_all,
            (SELECT COUNT(DISTINCT pokemon_id) FROM pokedex WHERE user_id = $1 AND pokemon_id <= 151) AS pokedex_gen1,
            (SELECT COUNT(DISTINCT pokemon_id) FROM pokedex WHERE user_id = $1 AND pokemon_id BETWEEN 152 AND 251) AS pokedex_gen2,
            (SELECT COUNT(DISTINCT pokemon_id) FROM pokedex WHERE user_id = $1 AND pokemon_id BETWEEN 252 AND 386) AS pokedex_gen3,
            (SELECT COUNT(*) FROM pokedex p JOIN pokemon_master pm ON p.pokemon_id = pm.id
                WHERE p.user_id = $1 AND pm.rarity IN ('legendary', 'ultra_legendary')) AS legendary_count,
            (SELECT COUNT(*) FROM user_pokemon WHERE user_id = $1) AS total_catches,
            (SELECT master_balls FROM users WHERE user_id = $1) AS master_balls,
            (SELECT COUNT(*) FROM trades WHERE (from_user_id = $1 OR to_user_id = $1) AND status = 'accepted') AS trade_count,
            (SELECT COUNT(*) FROM user_pokemon up JOIN pokemon_master pm ON up.pokemon_id = pm.id
                WHERE up.user_id = $1 AND pm.rarity = 'common') AS common_catches,
            (SELECT COUNT(*) FROM user_pokemon up JOIN pokemon_master pm ON up.pokemon_id = pm.id
                WHERE up.user_id = $1 AND pm.rarity IN ('epic', 'legendary', 'ultra_legendary')) AS rare_catches,
            (SELECT COUNT(*) FROM user_pokemon
                WHERE user_id = $1 AND is_shiny = 1 AND is_active = 1) AS shiny_catches,
            (SELECT COUNT(*) FROM user_pokemon up JOIN pokemon_master pm ON up.pokemon_id = pm.id
                WHERE up.user_id = $1 AND up.is_shiny = 1 AND pm.rarity IN ('legendary', 'ultra_legendary') AND up.is_active = 1) AS shiny_legendary
    """, user_id)

    # 4. Get battle stats once (if any battle titles remain)
    battle_stats = None
    partner = None
    battle_titles_to_check = [
        tid for tid, (_, _, _, ct, _) in config.UNLOCKABLE_TITLES.items()
        if ct in ("battle_total", "battle_wins", "battle_streak", "battle_sweep", "partner_set")
        and tid not in existing_titles
    ]
    if battle_titles_to_check:
        try:
            from database import battle_queries as bq
            battle_stats = await bq.get_battle_stats(user_id)
            # Only fetch partner if partner_set title is not yet unlocked
            if "partner_set" not in existing_titles:
                partner = await bq.get_partner(user_id)
        except Exception:
            pass

    for title_id, (name, emoji, desc, check_type, threshold) in config.UNLOCKABLE_TITLES.items():
        # Skip if already unlocked (checked from in-memory set, no DB query)
        if title_id in existing_titles:
            continue

        unlocked = False

        if check_type == "pokedex" or check_type == "pokedex_gen1":
            unlocked = counts["pokedex_gen1"] >= threshold
        elif check_type == "pokedex_gen2":
            unlocked = counts["pokedex_gen2"] >= threshold
        elif check_type == "pokedex_gen3":
            unlocked = counts["pokedex_gen3"] >= threshold
        elif check_type == "pokedex_all":
            unlocked = counts["pokedex_all"] >= threshold
        elif check_type == "legendary":
            unlocked = counts["legendary_count"] >= threshold
        elif check_type == "first_catch":
            unlocked = counts["pokedex_all"] >= 1
        elif check_type == "total_catch":
            unlocked = counts["total_catches"] >= threshold
        elif check_type == "catch_fail":
            unlocked = stats.get("catch_fail_count", 0) >= threshold
        elif check_type == "midnight_catch":
            unlocked = stats.get("midnight_catch_count", 0) >= threshold
        elif check_type == "master_ball_own":
            unlocked = (counts["master_balls"] or 0) >= threshold
        elif check_type == "master_ball_use":
            unlocked = stats.get("master_ball_used", 0) >= threshold
        elif check_type == "love_count":
            unlocked = stats.get("love_count", 0) >= threshold
        elif check_type == "trade":
            unlocked = counts["trade_count"] >= threshold
        elif check_type == "common_catch":
            unlocked = counts["common_catches"] >= threshold
        elif check_type == "rare_catch":
            unlocked = counts["rare_catches"] >= threshold
        elif check_type == "streak":
            unlocked = stats.get("login_streak", 0) >= threshold
        elif check_type == "shiny_catch":
            unlocked = counts["shiny_catches"] >= threshold
        elif check_type == "shiny_legendary":
            unlocked = counts["shiny_legendary"] >= threshold
        elif check_type in ("battle_total", "battle_wins", "battle_streak", "battle_sweep", "partner_set"):
            if battle_stats:
                total_battles = battle_stats["battle_wins"] + battle_stats["battle_losses"]
                if check_type == "battle_total":
                    unlocked = total_battles >= threshold
                elif check_type == "battle_wins":
                    unlocked = battle_stats["battle_wins"] >= threshold
                elif check_type == "battle_streak":
                    unlocked = battle_stats["best_streak"] >= threshold
                elif check_type == "partner_set":
                    unlocked = partner is not None
                # battle_sweep is only checked in battle_service.py
        elif check_type == "tournament_win":
            unlocked = stats.get("tournament_wins", 0) >= threshold
        elif check_type == "tutorial_complete":
            pass  # 튜토리얼 졸업 시 tutorial.py에서 직접 해금
        elif check_type == "journey_graduate":
            pass  # 뉴비 여정 졸업 시 journey_service.py에서 직접 해금
        elif check_type == "tournament_first":
            # Only unlockable if no one else has this title yet (world-first)
            if stats.get("tournament_wins", 0) >= threshold:
                first_exists = await pool.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM user_titles WHERE title_id = 'tournament_first')"
                )
                unlocked = not first_exists
        elif check_type == "inaugural_champ":
            # 초대 챔피언 — 최초 공식 토너먼트 우승자 (단 1명)
            if stats.get("tournament_wins", 0) >= threshold:
                first_exists = await pool.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM user_titles WHERE title_id = 'inaugural_champ')"
                )
                unlocked = not first_exists

        if unlocked:
            was_new = await queries.unlock_title(user_id, title_id)
            if was_new:
                newly_unlocked.append((title_id, name, emoji))
                logger.info(f"Title unlocked: {name} for user {user_id}")

    return newly_unlocked
