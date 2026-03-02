"""Battle stat calculation utilities."""

import config


def calc_battle_stats(rarity: str, stat_type: str, friendship: int) -> dict:
    """Calculate battle stats (HP, ATK, DEF, SPD) from rarity/stat_type/friendship.

    Stats are computed on the fly — never stored in DB.
    """
    base = config.RARITY_BASE_STAT.get(rarity, 45)
    spread = config.STAT_SPREADS.get(stat_type, config.STAT_SPREADS["balanced"])
    bonus = 1.0 + (friendship * config.FRIENDSHIP_BONUS)

    return {
        "hp":  int(base * 3 * spread["hp"] * bonus),
        "atk": int(base * spread["atk"] * bonus),
        "def": int(base * spread["def"] * bonus),
        "spd": int(base * spread["spd"] * bonus),
    }


def get_type_multiplier(attacker_type: str, defender_type: str) -> float:
    """Return damage multiplier based on type matchup."""
    advantages = config.TYPE_ADVANTAGE.get(attacker_type, [])
    if defender_type in advantages:
        return config.BATTLE_TYPE_ADVANTAGE_MULT  # 1.3x
    # Check if defender has advantage over attacker (disadvantage)
    defender_advantages = config.TYPE_ADVANTAGE.get(defender_type, [])
    if attacker_type in defender_advantages:
        return config.BATTLE_TYPE_DISADVANTAGE_MULT  # 0.7x
    return 1.0


def format_stats_line(stats: dict) -> str:
    """Format stats dict as a compact display string."""
    return f"HP:{stats['hp']} ATK:{stats['atk']} DEF:{stats['def']} SPD:{stats['spd']}"
