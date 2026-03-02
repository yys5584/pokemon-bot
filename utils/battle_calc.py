"""Battle stat calculation utilities."""

import config


def _build_evo_stage_map() -> dict[int, int]:
    """Build pokemon_id → evolution_stage (1/2/3) map from pokemon_data."""
    from models.pokemon_data import ALL_POKEMON
    stages = {}
    for p in ALL_POKEMON:
        pid = p[0]
        evolves_from = p[6]
        evolves_to = p[7]
        if evolves_from is None and evolves_to is not None:
            stages[pid] = 1  # 1단 (파이리, 꼬부기 등)
        elif evolves_from is not None and evolves_to is not None:
            stages[pid] = 2  # 2단 (리자드, 어니부기 등)
        else:
            stages[pid] = 3  # 최종진화 or 단일 (리자몽, 뮤츠 등)
    return stages


EVO_STAGE_MAP: dict[int, int] = _build_evo_stage_map()


def calc_battle_stats(rarity: str, stat_type: str, friendship: int,
                      evo_stage: int = 3) -> dict:
    """Calculate battle stats (HP, ATK, DEF, SPD) from rarity/stat_type/friendship.

    evo_stage: 1=1단진화, 2=2단진화, 3=최종진화/단일 (default)
    Stats are computed on the fly — never stored in DB.
    """
    base = config.RARITY_BASE_STAT.get(rarity, 45)
    spread = config.STAT_SPREADS.get(stat_type, config.STAT_SPREADS["balanced"])
    bonus = 1.0 + (friendship * config.FRIENDSHIP_BONUS)
    evo_mult = config.EVOLUTION_STAGE_MULT.get(evo_stage, 1.0)

    return {
        "hp":  int(base * 3 * spread["hp"] * bonus * evo_mult),
        "atk": int(base * spread["atk"] * bonus * evo_mult),
        "def": int(base * spread["def"] * bonus * evo_mult),
        "spd": int(base * spread["spd"] * bonus * evo_mult),
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
