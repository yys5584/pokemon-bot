"""던전 랭킹 보상 스케줄러 job."""

import logging

import config
from database import dungeon_queries as dq, queries, item_queries
from database import camp_queries as cq

logger = logging.getLogger(__name__)


def _get_reward_for_rank(rank: int, reward_table: dict) -> dict | None:
    """순위에 해당하는 보상 딕셔너리 반환."""
    for key, rewards in reward_table.items():
        if isinstance(key, int):
            if rank == key:
                return rewards
        elif isinstance(key, tuple) and len(key) == 2:
            if key[0] <= rank <= key[1]:
                return rewards
    return None


async def dungeon_weekly_ranking_job(context):
    """월요일 00:20 KST — 지난 주 던전 랭킹 보상 자동 분배."""
    try:
        now = config.get_kst_now()
        if now.weekday() != 0:  # 월요일만
            return

        season_key = dq._previous_season_key()
        dist_key = f"{season_key}_weekly"

        if await dq.is_reward_distributed(dist_key):
            logger.info(f"Dungeon weekly rewards already distributed for {season_key}")
            return

        ranking = await dq.get_previous_week_ranking(limit=30)
        if not ranking:
            logger.info("No dungeon weekly ranking data")
            await dq.mark_reward_distributed(dist_key, "weekly")
            return

        logger.info(f"Distributing dungeon weekly rewards for {season_key}: {len(ranking)} users")

        for rank, entry in enumerate(ranking, 1):
            uid = entry["user_id"]
            rewards = _get_reward_for_rank(rank, config.DUNGEON_WEEKLY_RANKING_REWARDS)
            if not rewards:
                continue

            # 보상 지급
            try:
                if rewards.get("masterball"):
                    await queries.add_master_balls_bulk([uid])
                if rewards.get("crystals"):
                    await cq.add_crystals(uid, rewards["crystals"], 0)
                if rewards.get("tickets"):
                    await dq.add_dungeon_tickets(uid, rewards["tickets"])

                # DM 알림
                reward_lines = []
                if rewards.get("masterball"):
                    reward_lines.append(f"  🔴 마스터볼 ×{rewards['masterball']}")
                if rewards.get("crystals"):
                    reward_lines.append(f"  💎 결정 ×{rewards['crystals']}")
                if rewards.get("tickets"):
                    reward_lines.append(f"  🎫 던전 입장권 ×{rewards['tickets']}")
                if rewards.get("title"):
                    reward_lines.append(f"  👑 칭호: {rewards['title']}")

                dm_text = (
                    f"🏰 <b>던전 주간 랭킹 보상!</b>\n\n"
                    f"📅 시즌: {season_key}\n"
                    f"🏆 순위: {rank}위 ({entry['floor_reached']}층)\n\n"
                    + "\n".join(reward_lines)
                )
                try:
                    await context.bot.send_message(chat_id=uid, text=dm_text, parse_mode="HTML")
                except Exception:
                    pass  # DM 실패는 무시

            except Exception as e:
                logger.error(f"Dungeon weekly reward error for user {uid}: {e}")

        await dq.mark_reward_distributed(dist_key, "weekly")
        logger.info(f"Dungeon weekly rewards distributed for {season_key}")

    except Exception as e:
        logger.error(f"dungeon_weekly_ranking_job error: {e}", exc_info=True)


async def dungeon_daily_ranking_job(context):
    """매일 00:25 KST — 어제 던전 일일 랭킹 보상 분배."""
    try:
        import datetime as _dt

        now = config.get_kst_now()
        yesterday = (now - _dt.timedelta(days=1)).strftime("%Y-%m-%d")
        dist_key = f"daily_{yesterday}"

        if await dq.is_reward_distributed(dist_key):
            logger.info(f"Dungeon daily rewards already distributed for {yesterday}")
            return

        ranking = await dq.get_daily_ranking(yesterday, limit=10)
        if not ranking:
            logger.info(f"No dungeon daily ranking data for {yesterday}")
            await dq.mark_reward_distributed(dist_key, "daily")
            return

        logger.info(f"Distributing dungeon daily rewards for {yesterday}: {len(ranking)} users")

        for rank, entry in enumerate(ranking, 1):
            uid = entry["user_id"]
            rewards = _get_reward_for_rank(rank, config.DUNGEON_DAILY_RANKING_REWARDS)
            if not rewards:
                continue

            try:
                if rewards.get("iv_reroll_one"):
                    await item_queries.add_user_item(uid, "iv_reroll_one", rewards["iv_reroll_one"])
                if rewards.get("fragments"):
                    # 만능 조각으로 지급
                    from database.connection import get_db
                    pool = await get_db()
                    await pool.execute(
                        "UPDATE users SET universal_fragments = universal_fragments + $1 WHERE user_id = $2",
                        rewards["fragments"], uid,
                    )

                # DM 알림
                reward_lines = []
                if rewards.get("iv_reroll_one"):
                    reward_lines.append(f"  🎯 IV 선택 리롤 ×{rewards['iv_reroll_one']}")
                if rewards.get("fragments"):
                    reward_lines.append(f"  🧩 만능 조각 ×{rewards['fragments']}")

                dm_text = (
                    f"🏰 <b>던전 일일 랭킹 보상!</b>\n\n"
                    f"📅 {yesterday}\n"
                    f"🏆 순위: {rank}위 ({entry['floor_reached']}층)\n\n"
                    + "\n".join(reward_lines)
                )
                try:
                    await context.bot.send_message(chat_id=uid, text=dm_text, parse_mode="HTML")
                except Exception:
                    pass

            except Exception as e:
                logger.error(f"Dungeon daily reward error for user {uid}: {e}")

        await dq.mark_reward_distributed(dist_key, "daily")
        logger.info(f"Dungeon daily rewards distributed for {yesterday}")

    except Exception as e:
        logger.error(f"dungeon_daily_ranking_job error: {e}", exc_info=True)
