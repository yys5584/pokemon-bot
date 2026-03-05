"""Event service: check active events and calculate boosts.

Uses a short-lived cache (1 query per spawn cycle) to avoid
repeated DB round-trips for event data.
"""

import time
from database import queries

# --- In-memory event cache (refreshed every 30 seconds) ---
_event_cache: list[dict] | None = None
_event_cache_ts: float = 0
_EVENT_CACHE_TTL = 30  # seconds


async def _get_all_active_events() -> list[dict]:
    """Get all active events with caching to avoid repeated DB queries."""
    global _event_cache, _event_cache_ts
    now = time.time()
    if _event_cache is not None and (now - _event_cache_ts) < _EVENT_CACHE_TTL:
        return _event_cache
    _event_cache = await queries.get_active_events()
    _event_cache_ts = now
    return _event_cache


def _filter_events(events: list[dict], event_type: str) -> list[dict]:
    """Filter cached events by type."""
    return [e for e in events if e["event_type"] == event_type]


async def get_spawn_boost() -> float:
    """Get total spawn multiplier from active spawn_boost events."""
    events = _filter_events(await _get_all_active_events(), "spawn_boost")
    multiplier = 1.0
    for e in events:
        multiplier *= e["multiplier"]
    return multiplier


async def get_catch_boost() -> float:
    """Get total catch rate multiplier from active catch_boost events."""
    events = _filter_events(await _get_all_active_events(), "catch_boost")
    multiplier = 1.0
    for e in events:
        multiplier *= e["multiplier"]
    return multiplier


async def get_rarity_weights(base_weights: dict) -> dict:
    """Apply rarity_boost events to base rarity weights."""
    events = _filter_events(await _get_all_active_events(), "rarity_boost")
    weights = dict(base_weights)
    for e in events:
        target = e["target"]
        if target in weights:
            weights[target] = weights[target] * e["multiplier"]
    return weights


async def get_pokemon_boost(pokemon_id: int) -> float:
    """Check if a specific Pokemon has a spawn boost. Returns multiplier."""
    events = _filter_events(await _get_all_active_events(), "pokemon_boost")
    multiplier = 1.0
    for e in events:
        if e["target"] == str(pokemon_id):
            multiplier *= e["multiplier"]
    return multiplier


async def get_all_pokemon_boosts() -> dict[int, float]:
    """Get all pokemon boost multipliers at once (avoids N queries).
    Returns {pokemon_id: multiplier} for boosted pokemon only."""
    events = _filter_events(await _get_all_active_events(), "pokemon_boost")
    boosts: dict[int, float] = {}
    for e in events:
        try:
            pid = int(e["target"])
            boosts[pid] = boosts.get(pid, 1.0) * e["multiplier"]
        except (ValueError, TypeError):
            pass
    return boosts


async def get_shiny_boost() -> float:
    """Get shiny rate multiplier from active shiny_boost events."""
    events = _filter_events(await _get_all_active_events(), "shiny_boost")
    multiplier = 1.0
    for e in events:
        multiplier *= e["multiplier"]
    return multiplier


async def get_friendship_boost() -> int:
    """Get friendship gain multiplier from active friendship_boost events."""
    events = _filter_events(await _get_all_active_events(), "friendship_boost")
    multiplier = 1
    for e in events:
        multiplier *= int(e["multiplier"])
    return multiplier


async def get_active_event_summary() -> str:
    """Get a formatted summary of active events for display."""
    lines = []
    # Permanent config-level events
    from config import SHINY_RATE_NATURAL, SHINY_RATE_ARCADE
    BASE_NAT = 1 / 64
    BASE_ARC = 1 / 512
    if SHINY_RATE_NATURAL > BASE_NAT:
        nat_mult = round(SHINY_RATE_NATURAL / BASE_NAT)
        lines.append(f"  ✨ 이로치 자연발생 {nat_mult}배 증가! ({SHINY_RATE_NATURAL:.0%})")
    if SHINY_RATE_ARCADE > BASE_ARC:
        arc_mult = round(SHINY_RATE_ARCADE / BASE_ARC)
        lines.append(f"  ✨ 이로치 아케이드 {arc_mult}배 증가! ({SHINY_RATE_ARCADE:.1%})")
    # DB events
    events = await _get_all_active_events()
    for e in events:
        lines.append(f"  {e['description']}")
    return "\n".join(lines) if lines else ""


def invalidate_event_cache():
    """Force refresh on next call (call after event create/end)."""
    global _event_cache, _event_cache_ts
    _event_cache = None
    _event_cache_ts = 0
