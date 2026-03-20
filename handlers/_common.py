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
