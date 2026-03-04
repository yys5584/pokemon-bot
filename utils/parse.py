"""Parse arguments from plain text messages (since Korean commands can't use CommandHandler)."""

import re


def _strip_emoji_prefix(text: str) -> str:
    """Strip leading emoji prefix from keyboard button text.
    e.g. '📖 도감 파이리' -> '도감 파이리', '밥 3' -> '밥 3'
    """
    return re.sub(r'^[^\w가-힣]+\s*', '', text.strip())


def parse_args(text: str) -> list[str]:
    """Extract arguments from a message text.
    e.g. '밥 3' -> ['3'], '📖 도감 파이리' -> ['파이리']
    """
    parts = _strip_emoji_prefix(text).split()
    return parts[1:] if len(parts) > 1 else []


def parse_number(text: str) -> int | None:
    """Extract the number argument from text (only if the arg is purely a number).
    e.g. '밥 3' -> 3, '📦 내포켓몬 3' -> 3
    """
    parts = _strip_emoji_prefix(text).split(maxsplit=1)
    if len(parts) < 2:
        return None
    arg = parts[1].strip()
    if re.match(r'^\d+$', arg):
        return int(arg)
    return None


def parse_name_arg(text: str) -> str | None:
    """Extract the name argument (non-number) from text.
    e.g. '밥 피카츄' -> '피카츄', '📖 도감 파이리' -> '파이리'
    """
    parts = _strip_emoji_prefix(text).split(maxsplit=1)
    if len(parts) < 2:
        return None
    arg = parts[1].strip()
    if re.match(r'^\d+$', arg):
        return None  # It's a number, not a name
    return arg
