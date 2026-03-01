"""Event service: check active events and calculate boosts."""

from database import queries


async def get_spawn_boost() -> float:
    """Get total spawn multiplier from active spawn_boost events."""
    events = await queries.get_active_events_by_type("spawn_boost")
    multiplier = 1.0
    for e in events:
        multiplier *= e["multiplier"]
    return multiplier


async def get_catch_boost() -> float:
    """Get total catch rate multiplier from active catch_boost events."""
    events = await queries.get_active_events_by_type("catch_boost")
    multiplier = 1.0
    for e in events:
        multiplier *= e["multiplier"]
    return multiplier


async def get_rarity_weights(base_weights: dict) -> dict:
    """Apply rarity_boost events to base rarity weights.
    Boosts the weight of the targeted rarity."""
    events = await queries.get_active_events_by_type("rarity_boost")
    weights = dict(base_weights)
    for e in events:
        target = e["target"]
        if target in weights:
            weights[target] = weights[target] * e["multiplier"]
    return weights


async def get_pokemon_boost(pokemon_id: int) -> float:
    """Check if a specific Pokemon has a spawn boost. Returns multiplier."""
    events = await queries.get_active_events_by_type("pokemon_boost")
    multiplier = 1.0
    for e in events:
        if e["target"] == str(pokemon_id):
            multiplier *= e["multiplier"]
    return multiplier


async def get_friendship_boost() -> int:
    """Get friendship gain multiplier from active friendship_boost events."""
    events = await queries.get_active_events_by_type("friendship_boost")
    multiplier = 1
    for e in events:
        multiplier *= int(e["multiplier"])
    return multiplier


async def get_active_event_summary() -> str:
    """Get a formatted summary of active events for display."""
    events = await queries.get_active_events()
    if not events:
        return ""
    lines = []
    for e in events:
        lines.append(f"  {e['description']}")
    return "\n".join(lines)
