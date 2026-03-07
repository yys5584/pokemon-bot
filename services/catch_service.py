"""Catch service: handles catch attempt validation and recording."""

import asyncio
import config
from database import queries


async def can_attempt_catch(user_id: int) -> tuple[bool, str]:
    """Check if a user can attempt to catch. Returns (allowed, reason)."""
    today = config.get_kst_today()

    # Parallel: get_catch_limit + get_bonus_catches
    limit, bonus = await asyncio.gather(
        queries.get_catch_limit(user_id, today),
        queries.get_bonus_catches(user_id, today),
    )

    max_today = config.MAX_CATCH_ATTEMPTS_PER_DAY + bonus
    if limit["attempt_count"] >= max_today:
        return False, f"오늘 잡기 횟수({max_today}회)를 모두 사용했습니다!"

    # Check consecutive catch cooldown
    if limit["consecutive_catches"] >= config.CONSECUTIVE_CATCH_COOLDOWN:
        await queries.reset_consecutive(user_id, today)
        return False, "연속 포획 쿨타임! 다음 출현에 도전하세요."

    return True, ""


async def record_attempt(session_id: int, user_id: int):
    """Record a catch attempt and increment daily count."""
    today = config.get_kst_today()
    # Parallel: record + increment are independent
    await asyncio.gather(
        queries.record_catch_attempt(session_id, user_id),
        queries.increment_attempt(user_id, today),
    )
