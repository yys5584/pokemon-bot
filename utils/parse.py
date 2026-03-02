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


def parse_name_arg(text: str) -> str | None:
    """Extract the name argument (non-number) from text.
    e.g. '밥 피카츄' -> '피카츄', '밥 3' -> None, '밥' -> None
    """
    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return None
    arg = parts[1].strip()
    if re.match(r'^\d+$', arg):
        return None  # It's a number, not a name
    return arg
