"""Newbie Journey System — catch-based progressive onboarding.

Phase 1: Every catch advances one step (6 steps total).
Phase 2: After graduation, daily tips for 7 days on first catch of the day.
"""

import logging

import config
from database import queries
from utils.helpers import ball_emoji, icon_emoji

logger = logging.getLogger(__name__)

# ── Phase 1: Journey Milestones (step 0~5 → 1~6) ──
# Each catch advances one step. No pokemon count check.
# (message, reward_type, reward_amount)
#   reward_type: "hyper_ball", "master_ball", "bp", "graduate"
JOURNEY_MILESTONES = [
    # step 0→1: 1st catch
    {
        "msg": "🎉 첫 포켓몬! DM에서 밥 피카츄 로 밥을 줘보세요!",
        "rewards": [("hyper_ball", 3)],
    },
    # step 1→2: 2nd catch
    {
        "msg": "📖 DM에서 도감 을 입력해 수집 현황을 확인해보세요!",
        "rewards": [("bp", 100)],
    },
    # step 2→3: 3rd catch
    {
        "msg": "⚔️ 채팅방에서 다른 트레이너에게 답글로 배틀 을 걸어보세요!",
        "rewards": [("master_ball", 1)],
    },
    # step 3→4: 4th catch
    {
        "msg": "🔄 채팅방에서 다른 트레이너에게 답글로 교환 피카츄 를 보내보세요!",
        "rewards": [("bp", 200)],
    },
    # step 4→5: 5th catch
    {
        "msg": "📋 DM에서 미션 을 입력해 매일 보상을 받을 수 있어요!",
        "rewards": [("master_ball", 1)],
    },
    # step 5→6: 6th catch (graduation)
    {
        "msg": "🎓 축하! 칭호 「🌟 신예 트레이너」 해금!",
        "rewards": [("master_ball", 2), ("bp", 500), ("title", "newbie_graduate")],
    },
]

# ── Phase 2: Daily Guide Tips (step 6~12 → 7~13) ──
GUIDE_TIPS = [
    "💡 DM에서 감정 피카츄 로 포켓몬의 IV를 상세하게 볼 수 있어요!",
    "💡 DM에서 상성 불꽃 으로 배틀 상성표를 확인해보세요!",
    "💡 DM에서 칭호 를 입력하면 멋진 칭호를 장착할 수 있어요!",
    "💡 채팅방에서 출석 을 매일 치면 하이퍼볼을 받을 수 있어요!",
    "💡 DM에서 파트너 피카츄 로 파트너를 설정하면 배틀에서 공격력 +5%!",
    "💡 DM에서 진화 피카츄 로 친밀도 MAX인 포켓몬을 진화시킬 수 있어요!",
    "💡 합성 팁: ⭐이로치 + 일반 합성 → 이로치 유지! ⭐+⭐ 합성 → 최소 A등급 보장!",
    f"💡 {config.DASHBOARD_URL} 대시보드에서 내 포켓몬을 한눈에 볼 수 있어요!",
]

JOURNEY_COMPLETE_STEP = 14  # step >= 14 means fully done (6 milestones + 8 tips)


async def check_journey(user_id: int) -> str | None:
    """Check and advance journey after a successful catch.

    Returns an inline message string to append to catch result, or None.
    """
    try:
        user = await queries.get_user(user_id)
        if not user:
            return None

        step = user.get("journey_step", 0) or 0

        # ── Already completed ──
        if step >= JOURNEY_COMPLETE_STEP:
            return None

        # ── Phase 1: Milestones (step 0~5) ──
        if step < len(JOURNEY_MILESTONES):
            milestone = JOURNEY_MILESTONES[step]
            reward_lines = []

            for reward_type, value in milestone["rewards"]:
                if reward_type == "hyper_ball":
                    await queries.add_hyper_ball(user_id, value)
                    reward_lines.append(f"{ball_emoji('hyperball')} 하이퍼볼 x{value}")
                elif reward_type == "master_ball":
                    await queries.add_master_ball(user_id, value)
                    reward_lines.append(f"{ball_emoji('masterball')} 마스터볼 x{value}")
                elif reward_type == "bp":
                    await queries.add_battle_points(user_id, value)
                    reward_lines.append(f"{icon_emoji('bolt')} BP +{value}")
                elif reward_type == "title":
                    await queries.unlock_title(user_id, value)

            # Advance step
            new_step = step + 1
            await queries.update_journey_step(user_id, new_step)

            msg = milestone["msg"]
            if reward_lines:
                msg += "\n🎁 보상: " + ", ".join(reward_lines)

            logger.info(f"Journey step {step}→{new_step} for user {user_id}")
            return msg

        # ── Phase 2: Daily Guide Tips (step 6~12) ──
        tip_index = step - len(JOURNEY_MILESTONES)  # 0~6
        if tip_index < len(GUIDE_TIPS):
            # Check if already shown today (KST)
            today_str = config.get_kst_today()
            last_tip = user.get("journey_last_tip_date")
            if last_tip is not None:
                last_tip_str = last_tip.isoformat() if hasattr(last_tip, 'isoformat') else str(last_tip)
                if last_tip_str == today_str:
                    return None  # Already shown today

            # Show tip and advance
            tip = GUIDE_TIPS[tip_index]
            await queries.update_journey_tip_date(user_id, today_str)

            logger.info(f"Journey guide tip {tip_index + 1}/7 for user {user_id}")
            return tip

        # ── Beyond all tips ──
        return None

    except Exception as e:
        logger.error(f"Journey check failed for user {user_id}: {e}")
        return None
