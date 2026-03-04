"""Utility functions for text formatting, titles, etc."""

import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import (
    TITLES, LEGEND_HUNTER_THRESHOLD, LEGEND_HUNTER_TITLE,
    RARITY_EMOJI, RARITY_LABEL, RARITY_CUSTOM_EMOJI,
    TYPE_EMOJI, TYPE_CUSTOM_EMOJI,
)
from database import queries

_logger = logging.getLogger(__name__)


def close_button() -> InlineKeyboardMarkup:
    """Return InlineKeyboardMarkup with ❌ close button for group messages."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌", callback_data="close_msg")]])


async def _delete_msg(msg, delay: float):
    """Sleep then delete a message. Silently ignore errors."""
    try:
        await asyncio.sleep(delay)
        await msg.delete()
    except Exception:
        pass


def schedule_delete(msg, delay: float = 10):
    """Fire-and-forget: schedule a message for deletion after *delay* seconds.
    Non-blocking — creates a background asyncio task."""
    asyncio.create_task(_delete_msg(msg, delay))


async def try_delete(msg):
    """Try to delete a message immediately. Silently ignore errors."""
    try:
        await msg.delete()
    except Exception:
        pass


def hearts_display(friendship: int, max_hearts: int = 5) -> str:
    """Display friendship as hearts: ♥♥♥○○"""
    filled = "♥" * friendship
    empty = "○" * (max_hearts - friendship)
    return filled + empty


def rarity_display(rarity: str) -> str:
    """Display rarity with emoji and label (plain text)."""
    emoji = RARITY_EMOJI.get(rarity, "⚪")
    label = RARITY_LABEL.get(rarity, rarity)
    return f"{emoji} {label}"


def _type_emoji(type_key: str) -> str:
    """Return a single type emoji (custom or unicode fallback)."""
    eid = TYPE_CUSTOM_EMOJI.get(type_key, "")
    fallback = TYPE_EMOJI.get(type_key, "")
    if eid:
        return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'
    return fallback


def type_badge(pokemon_id: int, fallback_type: str = None) -> str:
    """Return type emoji(s) for a pokemon, including dual types.

    Looks up dual type info from POKEMON_BASE_STATS.
    Falls back to single fallback_type if pokemon not in base stats.
    """
    from models.pokemon_base_stats import POKEMON_BASE_STATS
    stats = POKEMON_BASE_STATS.get(pokemon_id)
    if stats:
        types = stats[-1]  # last element is [type1] or [type1, type2]
        return "".join(_type_emoji(t) for t in types)
    # Fallback to single type from DB
    if fallback_type:
        return _type_emoji(fallback_type)
    return ""


def rarity_badge(rarity: str) -> str:
    """Return custom emoji HTML tag for rarity badge (no label)."""
    eid = RARITY_CUSTOM_EMOJI.get(rarity, "")
    fallback = RARITY_EMOJI.get(rarity, "⚪")
    if eid:
        return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'
    return fallback


def rarity_badge_label(rarity: str) -> str:
    """Return custom emoji HTML tag + Korean label."""
    eid = RARITY_CUSTOM_EMOJI.get(rarity, "")
    fallback = RARITY_EMOJI.get(rarity, "⚪")
    label = RARITY_LABEL.get(rarity, rarity)
    if eid:
        return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji> {label}'
    return f"{fallback} {label}"


async def calculate_title(user_id: int) -> tuple[str, str]:
    """Calculate title based on pokedex count and legendary count.
    Returns (title, emoji)."""
    count = await queries.count_pokedex(user_id)
    legendary_count = await queries.count_legendary_caught(user_id)

    # Check legendary hunter
    if legendary_count >= LEGEND_HUNTER_THRESHOLD:
        return LEGEND_HUNTER_TITLE

    # Check standard titles
    for threshold, title, emoji in TITLES:
        if count >= threshold:
            return (title, emoji)

    return ("", "")


async def update_title(user_id: int):
    """Recalculate and update user's title."""
    title, emoji = await calculate_title(user_id)
    await queries.update_user_title(user_id, title, emoji)


def time_ago(timestamp_str) -> str:
    """Convert ISO timestamp or datetime to human-readable Korean time ago."""
    from datetime import datetime
    try:
        if isinstance(timestamp_str, datetime):
            ts = timestamp_str.replace(tzinfo=None)
        else:
            ts = datetime.fromisoformat(str(timestamp_str))
        diff = datetime.now() - ts
        seconds = int(diff.total_seconds())

        if seconds < 60:
            return f"{seconds}초 전"
        elif seconds < 3600:
            return f"{seconds // 60}분 전"
        elif seconds < 86400:
            return f"{seconds // 3600}시간 전"
        else:
            days = seconds // 86400
            if days == 1:
                return "어제"
            return f"{days}일 전"
    except (ValueError, TypeError):
        return ""


def escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def truncate_name(name: str, max_len: int = 5) -> str:
    """Truncate a display name to max_len chars + '..' if longer."""
    if len(name) <= max_len:
        return name
    return name[:max_len] + ".."


def get_decorated_name(display_name: str, title: str = "", title_emoji: str = "", username: str = None, html: bool = False) -> str:
    """Format a display name with title badge for chat messages.

    - With title (plain): 「👑 챔피언」문유
    - With title (html):  <b>「👑 챔피언」문유</b>
    - Without title: 문유
    """
    if username:
        name = f"@{username}"
    else:
        name = escape_html(display_name) if html else display_name

    if title and title_emoji:
        if html:
            return f"<b>「{title_emoji} {title}」{name}</b>"
        return f"「{title_emoji} {title}」{name}"
    return name
