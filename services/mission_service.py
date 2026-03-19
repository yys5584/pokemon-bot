"""Daily mission service: generation, progress tracking, and rewards."""

import logging
import random

import config

from database import queries, mission_queries
from database import battle_queries as bq
from utils.helpers import ball_emoji

logger = logging.getLogger(__name__)


async def ensure_daily_missions(user_id: int) -> list[dict]:
    """Return today's missions; create them lazily if not yet generated."""
    date = config.get_kst_today()
    missions = await mission_queries.get_daily_missions(user_id, date)
    if missions:
        return missions

    # Pick MISSION_COUNT random missions from pool
    pool_items = list(config.MISSION_POOL.items())
    selected = random.sample(pool_items, min(config.MISSION_COUNT, len(pool_items)))
    mission_list = [{"key": k, "target": v["target"]} for k, v in selected]
    await mission_queries.create_daily_missions(user_id, date, mission_list)
    return await mission_queries.get_daily_missions(user_id, date)


async def check_mission_progress(user_id: int, mission_key: str) -> str | None:
    """Increment mission progress by 1.

    If a mission is completed by this increment, auto-claim reward and
    return a congratulation message string.  Returns None otherwise.
    """
    date = config.get_kst_today()
    # Lazily ensure missions exist for today before incrementing
    await ensure_daily_missions(user_id)
    result = await mission_queries.increment_mission_progress(user_id, date, mission_key)
    if not result:
        return None  # 해당 미션이 오늘 없거나 이미 완료됨
    if not result["completed_now"]:
        return None  # 아직 목표 미달

    # ── 개별 보상 자동 지급 ──
    # 구독자 미션 보상 배율 적용
    bp_reward = config.MISSION_REWARD_BP
    hyper_reward = config.MISSION_REWARD_HYPER
    try:
        from services.subscription_service import get_benefit_value
        mission_mult = await get_benefit_value(user_id, "mission_reward_multiplier", 1.0)
        if mission_mult > 1.0:
            bp_reward = int(bp_reward * mission_mult)
            hyper_reward = int(hyper_reward * mission_mult) or hyper_reward
    except Exception:
        pass

    await bq.add_bp(user_id, bp_reward, "mission")
    await queries.add_hyper_ball(user_id, hyper_reward)
    await mission_queries.claim_mission_reward(user_id, date, mission_key)

    label = config.MISSION_POOL.get(mission_key, {}).get("label", mission_key)
    msg = (
        f"🎯 미션 완료! {label}\n"
        f"{ball_emoji('hyperball')} 하이퍼볼 {hyper_reward}개 + {bp_reward} BP 획득!"
    )

    # ── 전체 완료 체크 ──
    if result["all_done"]:
        claimed = await mission_queries.claim_allclear_reward(user_id, date)
        if claimed:
            await queries.add_master_ball(user_id, config.MISSION_ALLCLEAR_MASTER)
            msg += (
                f"\n\n🌟 일일 미션 올클리어!\n"
                f"{ball_emoji('masterball')} 마스터볼 {config.MISSION_ALLCLEAR_MASTER}개 획득!"
            )

    return msg
