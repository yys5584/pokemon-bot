"""Parse arguments from plain text messages (since Korean commands can't use CommandHandler)."""

import re


def parse_args(text: str) -> list[str]:
    """Extract arguments from a message text.
    e.g. '밥 3' -> ['3'], '교환 @철수 피카츄' -> ['@철수', '피카츄']
    """
    parts = text.strip().split()
    return parts[1:] if len(parts) > 1 else []


def parse_number(text: str) -> int | None:
    """Extract the first number from text.
    e.g. '밥 3' -> 3, '밥' -> None
    """
    match = re.search(r'\d+', text)
    return int(match.group()) if match else None
