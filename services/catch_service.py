"""Catch service: handles catch attempt validation and recording."""

import asyncio
import config
from database import queries


async def can_attempt_catch(user_id: int) -> tuple[bool, str]:
    """Check if a user can attempt to catch. Returns (allowed, reason)."""
    # 구독자 혜택 체크
    try:
        from services.subscription_service import has_benefit
        pokeball_unlimited = await has_benefit(user_id, "pokeball_unlimited")
    except Exception:
        pokeball_unlimited = False

    # 포케볼 무제한 구독자는 횟수 제한 스킵
    if not pokeball_unlimited:
        today = config.get_kst_today()
        limit, bonus = await asyncio.gather(
            queries.get_catch_limit(user_id, today),
            queries.get_bonus_catches(user_id, today),
        )
        max_today = config.MAX_CATCH_ATTEMPTS_PER_DAY + bonus
        if limit["attempt_count"] >= max_today:
            if bonus >= 100:
                return False, (
                    f"오늘 잡기 횟수({max_today}회)를 모두 사용했습니다!\n"
                    f"💡 DM 상점에서 '구매 포켓볼초기화'로 리셋할 수 있어요!"
                )
            return False, f"오늘 잡기 횟수({max_today}회)를 모두 사용했습니다!\n💡 채팅방에서 '포켓볼 충전'으로 +10회 충전하세요!"

    return True, ""


async def record_attempt(session_id: int, user_id: int):
    """Record a catch attempt and increment daily count."""
    today = config.get_kst_today()
    # Parallel: record + increment are independent
    await asyncio.gather(
        queries.record_catch_attempt(session_id, user_id),
        queries.increment_attempt(user_id, today),
    )
