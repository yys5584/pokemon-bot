"""Spawn system: coordinator module with shared state and re-exports.

Sub-modules:
  spawn_schedule.py  — scheduling + arcade management
  spawn_execute.py   — spawn execution
  spawn_resolve.py   — resolution + catch processing
"""

import asyncio
import logging
import time as _time

from telegram.ext import ContextTypes

import config

from database import queries
from utils.i18n import t, get_group_lang

logger = logging.getLogger(__name__)

# ── Shared state ──────────────────────────────────────────────────────────

# 채팅방별 스폰 락: 포획 메시지 전송 완료 전 다음 스폰 방지
_chat_spawn_locks: dict[int, asyncio.Lock] = {}


def _get_chat_lock(chat_id: int) -> asyncio.Lock:
    if chat_id not in _chat_spawn_locks:
        _chat_spawn_locks[chat_id] = asyncio.Lock()
    return _chat_spawn_locks[chat_id]


async def _add_cxp_bg(context, chat_id: int, amount: int, action: str, user_id: int | None = None):
    """Background: award CXP to a chat room and announce level-ups."""
    try:
        # 구독자 채널 CXP 배율 적용
        if user_id:
            try:
                from services.subscription_service import get_benefit_value
                cxp_mult = await get_benefit_value(user_id, "channel_cxp_multiplier", 1.0)
                if cxp_mult > 1.0:
                    amount = int(amount * cxp_mult)
            except Exception:
                pass

        new_level = await queries.add_chat_cxp(chat_id, amount, action, user_id)
        if new_level:
            lang = await get_group_lang(chat_id)
            info = config.get_chat_level_info(0)  # just for display
            # Re-fetch actual info for the new level
            row = await queries.get_chat_level(chat_id)
            info = config.get_chat_level_info(row["cxp"])
            bonus_txt = t(lang, "spawn_msg.level_spawn_bonus", count=info["spawn_bonus"]) if info["spawn_bonus"] else ""
            shiny_txt = t(lang, "spawn_msg.level_shiny_boost", pct=f"{info['shiny_boost_pct']:.1f}") if info["shiny_boost_pct"] else ""
            parts = [p for p in [bonus_txt, shiny_txt] if p]
            perks = f" ({', '.join(parts)})" if parts else ""
            special = ""
            if "daily_shiny" in info["specials"]:
                special = t(lang, "spawn_msg.level_daily_shiny")
            if "auto_arcade" in info["specials"]:
                special = t(lang, "spawn_msg.level_auto_arcade")
            await context.bot.send_message(
                chat_id=chat_id,
                text=t(lang, "spawn_msg.level_up", level=new_level, perks=perks, special=special),
                parse_mode="HTML",
            )
    except Exception as e:
        logger.error(f"CXP add failed for chat {chat_id}: {e}")


# Track attempt messages for cleanup when spawn resolves
# {session_id: (timestamp, [(chat_id, message_id), ...])}
_attempt_messages: dict[int, tuple[float, list[tuple[int, int]]]] = {}


def track_attempt_message(session_id: int, chat_id: int, message_id: int):
    """Store an attempt message for later deletion."""
    if session_id not in _attempt_messages:
        _attempt_messages[session_id] = (_time.time(), [])
    _attempt_messages[session_id][1].append((chat_id, message_id))


def cleanup_old_attempt_messages():
    """Remove _attempt_messages entries older than 1 hour to prevent memory leaks."""
    cutoff = _time.time() - 3600
    expired = [sid for sid, (ts, _) in _attempt_messages.items() if ts < cutoff]
    for sid in expired:
        _attempt_messages.pop(sid, None)
    if expired:
        logger.info(f"Cleaned up {len(expired)} stale attempt_message entries")


async def _delete_attempt_messages(bot, session_id: int):
    """Delete all tracked attempt messages for a resolved spawn."""
    entry = _attempt_messages.pop(session_id, None)
    messages = entry[1] if entry else []
    for cid, mid in messages:
        try:
            await bot.delete_message(chat_id=cid, message_id=mid)
        except Exception:
            pass


# ── Re-exports (all existing imports continue to work) ────────────────────

from services.spawn_schedule import (  # noqa: E402, F401
    calculate_daily_spawns,
    roll_rarity,
    is_midnight_bonus,
    pick_random_pokemon,
    schedule_spawns_for_chat,
    schedule_all_chats,
    schedule_arcade_spawns,
    start_temp_arcade,
    stop_arcade_for_chat,
    get_arcade_state,
    set_arcade_interval,
    extend_arcade_time,
    restore_temp_arcades,
)

from services.spawn_execute import (  # noqa: E402, F401
    execute_spawn,
)

from services.spawn_resolve import (  # noqa: E402, F401
    resolve_spawn,
    resolve_unresolved_sessions,
)
