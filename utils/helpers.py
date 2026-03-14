"""Utility functions for text formatting, titles, etc."""

import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import config
from config import (
    TITLES, LEGEND_HUNTER_THRESHOLD, LEGEND_HUNTER_TITLE,
    RARITY_EMOJI, RARITY_LABEL, RARITY_CUSTOM_EMOJI,
    TYPE_EMOJI, TYPE_CUSTOM_EMOJI, BALL_CUSTOM_EMOJI, ICON_CUSTOM_EMOJI,
    UNLOCKABLE_TITLES,
)
from utils.battle_calc import iv_total
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


# --- Ball emoji fallbacks ---
_BALL_FALLBACK = {
    "pokeball": "🔴",
    "hyperball": "🔵",
    "masterball": "🟣",
    "greatball": "🟢",
}


def ball_emoji(ball_key: str) -> str:
    """Return custom emoji HTML tag for a ball type."""
    eid = BALL_CUSTOM_EMOJI.get(ball_key, "")
    fallback = _BALL_FALLBACK.get(ball_key, "⚪")
    if eid:
        return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'
    return fallback


_ICON_FALLBACK = {
    # Special
    "skull": "💀",
    "crystal": "✨",
    # Numbers
    "1": "1️⃣", "2": "2️⃣", "3": "3️⃣", "4": "4️⃣", "5": "5️⃣",
    "6": "6️⃣", "7": "7️⃣", "8": "8️⃣", "9": "9️⃣", "10": "🔟",
    "check": "✅",
    # UI Icons
    "bookmark": "📋",
    "container": "📦",
    "pokedex": "📖",
    "battle": "⚔️",
    "ham": "🍖",
    "game": "🎮",
    "favorite": "❤️",
    "pokemon-love": "💕",
    "gotcha": "🎯",
    "windy": "💨",
    "exchange": "🔄",
    "computer": "💻",
    "coin": "💰",
    "footsteps": "👣",
    "pokecenter": "🏥",
    "shopping-bag": "🛍️",
    "bolt": "⚡",
    "skill": "💥",
    "stationery": "📊",
    # Pokemon characters (titles)
    "caterpie": "🐛",
    "rattata": "🐭",
    "pikachu": "⚡",
    "charmander": "🔥",
    "crown": "👑",
    "mew": "🌟",
    "chikorita": "🌿",
    "bellsprout": "🌱",
    "eevee": "🦊",
    "victini": "✌️",
    "dratini": "🐉",
    "bulbasaur": "🌱",
    "mankey": "👊",
    "zubat": "🦇",
    "venonat": "👁️",
    "meowth": "🐱",
    "jigglypuff": "🎤",
    "abra": "🔮",
    "articuno": "❄️",
    "snorlax": "😴",
    "squirtle": "💧",
    "moltres": "🔥",
    "psyduck": "🐤",
}


def icon_emoji(key: str) -> str:
    """Return custom emoji HTML tag for an icon."""
    eid = ICON_CUSTOM_EMOJI.get(key, "")
    fallback = _ICON_FALLBACK.get(key, "⭐")
    if eid:
        return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'
    return fallback


def shiny_emoji() -> str:
    """Return crystal custom emoji for shiny (이로치) indicator."""
    return icon_emoji("crystal")


async def calculate_title(user_id: int) -> tuple[str, str]:
    """Calculate title based on pokedex count and legendary count.
    Returns (title, emoji)."""
    count = await queries.count_pokedex(user_id)
    legendary_count = await queries.count_legendary_caught(user_id)

    # Check legendary hunter
    if legendary_count >= LEGEND_HUNTER_THRESHOLD:
        return (LEGEND_HUNTER_TITLE[0], icon_emoji("dratini"))

    # Check standard titles
    for threshold, title, emoji in TITLES:
        if count >= threshold:
            return (title, emoji)

    return ("", "")


async def update_title(user_id: int):
    """Recalculate and update user's title.
    Skip if user has manually equipped an unlockable title."""
    user = await queries.get_user(user_id)
    if user:
        current = user.get("title", "")
        if current:
            # Check if current title matches any unlocked title from user_titles
            unlocked = await queries.get_user_titles(user_id)
            unlocked_ids = {r["title_id"] for r in unlocked}
            for tid, (name, *_) in UNLOCKABLE_TITLES.items():
                if name == current and tid in unlocked_ids:
                    return  # User manually equipped this title, don't overwrite
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
        diff = config.get_kst_now().replace(tzinfo=None) - ts
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


# Reverse map: title name → icon key (for DB records with old basic emoji)
_TITLE_NAME_TO_ICON = {name: emoji for _id, (name, emoji, *_rest) in UNLOCKABLE_TITLES.items()}


def resolve_title_badge(title_emoji_raw: str, title_name: str = "") -> str:
    """Resolve title emoji (DB value or icon key) to rendered badge string."""
    ek = title_emoji_raw if title_emoji_raw in ICON_CUSTOM_EMOJI else _TITLE_NAME_TO_ICON.get(title_name, title_emoji_raw)
    return icon_emoji(ek) if ek in ICON_CUSTOM_EMOJI else ek


def _sub_tier_badge(sub_tier: str | None) -> str:
    """구독 티어 배지 문자열 반환."""
    if sub_tier == "channel_owner":
        return "👑"
    elif sub_tier == "basic":
        return "⭐"
    return ""


def get_decorated_name(display_name: str, title: str = "", title_emoji: str = "",
                       username: str = None, html: bool = False,
                       ranked_badge: str = "", sub_tier: str = None) -> str:
    """Format a display name with sub badge + ranked badge + title for chat messages.

    ranked_badge: 랭크 뱃지 HTML (config.get_ranked_badge_html() 결과)
    sub_tier: 구독 티어 ("basic", "channel_owner", None)
    - With badge+title: <b>👑「🐉 레전드 헌터」<badge> 문유</b>
    - With badge only:  <b><badge> 문유</b>
    - Without badge/title: 문유
    """
    sub_badge = _sub_tier_badge(sub_tier)

    if username:
        name = f"@{username}"
    else:
        name = escape_html(display_name) if html else display_name

    if title and title_emoji:
        ek = title_emoji if title_emoji in ICON_CUSTOM_EMOJI else _TITLE_NAME_TO_ICON.get(title, title_emoji)
        badge = icon_emoji(ek) if ek in ICON_CUSTOM_EMOJI else ek
        if html and ranked_badge:
            return f"<b>{sub_badge}「{badge} {title}」{ranked_badge}{name}</b>"
        if html:
            return f"<b>{sub_badge}「{badge} {title}」{name}</b>"
        return f"{sub_badge}「{badge} {title}」{name}"

    # 칭호 없어도 랭크 뱃지가 있으면 표시
    if html and ranked_badge:
        return f"<b>{sub_badge}{ranked_badge} {name}</b>"
    if sub_badge:
        return f"<b>{sub_badge}{name}</b>" if html else f"{sub_badge}{name}"
    return name


# ── IV helper functions (공용) ──────────────────────────────


def pokemon_iv_total(p: dict) -> int:
    """dict에서 IV 합계 계산. iv_hp가 None이면 0 반환."""
    if p.get("iv_hp") is None:
        return 0
    return iv_total(
        p.get("iv_hp"), p.get("iv_atk"), p.get("iv_def"),
        p.get("iv_spa"), p.get("iv_spdef"), p.get("iv_spd"),
    )


def iv_grade(total: int) -> str:
    """IV 합계 → 등급 문자 ('S', 'A', 'B', ...)."""
    grade, _ = config.get_iv_grade(total)
    return grade


def iv_grade_tag(p: dict, show_total: bool = False) -> str:
    """포켓몬 dict → ' [A]' 또는 ' [A]155' 형태 태그. IV 없으면 빈 문자열."""
    if p.get("iv_hp") is None:
        return ""
    total = iv_total(
        p.get("iv_hp"), p.get("iv_atk"), p.get("iv_def"),
        p.get("iv_spa"), p.get("iv_spdef"), p.get("iv_spd"),
    )
    grade, _ = config.get_iv_grade(total)
    if show_total:
        return f" [{grade}]{total}"
    return f" [{grade}]"
