"""Shared utilities for battle-related handlers."""

import time

# ── 콜백 버튼 중복 클릭 방지 ──
_callback_dedup: dict[str, float] = {}  # "msg_id:callback_data" -> timestamp


def _is_duplicate_callback(query) -> bool:
    """Return True if this exact callback was already handled (rapid double-click guard).
    Single-threaded asyncio → no race condition on dict access."""
    key = f"{query.message.message_id}:{query.data}:{query.from_user.id}"
    now = time.monotonic()
    # 60초 지난 항목 정리 (200개 넘으면)
    if len(_callback_dedup) > 200:
        cutoff = now - 60
        stale = [k for k, v in _callback_dedup.items() if v < cutoff]
        for k in stale:
            del _callback_dedup[k]
    if key in _callback_dedup:
        return True
    _callback_dedup[key] = now
    return False


# ── 텍스트 메시지 명령어 중복 실행 방지 ──
_msg_dedup: dict[str, float] = {}  # "user_id:command" -> timestamp


def _is_duplicate_message(update, command: str, cooldown: float = 3.0) -> bool:
    """Return True if the same user already triggered this command within cooldown seconds.
    Prevents rapid-fire text command abuse (출석, !돈, 랭전, 포켓볼 충전 등).
    Single-threaded asyncio → no race condition on dict access."""
    if not update.effective_user:
        return False
    key = f"{update.effective_user.id}:{command}"
    now = time.monotonic()
    # 정리 (500개 넘으면)
    if len(_msg_dedup) > 500:
        cutoff = now - 10
        stale = [k for k, v in _msg_dedup.items() if v < cutoff]
        for k in stale:
            del _msg_dedup[k]
    last = _msg_dedup.get(key)
    if last and (now - last) < cooldown:
        return True
    _msg_dedup[key] = now
    return False
