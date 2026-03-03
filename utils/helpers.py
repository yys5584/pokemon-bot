"""Utility functions for text formatting, titles, etc."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import TITLES, LEGEND_HUNTER_THRESHOLD, LEGEND_HUNTER_TITLE, RARITY_EMOJI, RARITY_LABEL
from database import queries


def close_button() -> InlineKeyboardMarkup:
    """Return InlineKeyboardMarkup with ❌ close button for group messages."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌", callback_data="close_msg")]])


def hearts_display(friendship: int, max_hearts: int = 5) -> str:
    """Display friendship as hearts: ♥♥♥○○"""
    filled = "♥" * friendship
    empty = "○" * (max_hearts - friendship)
    return filled + empty


def rarity_display(rarity: str) -> str:
    """Display rarity with emoji and label."""
    emoji = RARITY_EMOJI.get(rarity, "⚪")
    label = RARITY_LABEL.get(rarity, rarity)
    return f"{emoji} {label}"


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
