"""Battle stat calculation utilities."""

import random
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


def normalize_stat_hp(raw: int) -> int:
    """Real game Lv50 HP formula: base + 60 (simplified, IV0/EV0)."""
    return raw + 60


def normalize_stat(raw: int) -> int:
    """Real game Lv50 other stat formula: base + 5 (simplified, IV0/EV0)."""
    return raw + 5


def get_normalized_base_stats(pokemon_id: int) -> dict | None:
    """Get Lv50 base stats for a pokemon. Returns None if not found."""
    from models.pokemon_base_stats import POKEMON_BASE_STATS
    entry = POKEMON_BASE_STATS.get(pokemon_id)
    if entry is None:
        return None
    hp, atk, def_, spa, spdef, spd = entry[:6]
    return {
        "base_hp": normalize_stat_hp(hp),
        "base_atk": normalize_stat(atk),
        "base_def": normalize_stat(def_),
        "base_spa": normalize_stat(spa),
        "base_spdef": normalize_stat(spdef),
        "base_spd": normalize_stat(spd),
    }


def _iv_mult(iv: int | None) -> float:
    """IV → stat multiplier. None (기존 포켓몬) = 1.0 (변화 없음)."""
    if iv is None:
        return 1.0
    return config.IV_MULT_MIN + (iv / config.IV_MAX) * config.IV_MULT_RANGE


def generate_ivs(is_shiny: bool = False) -> dict[str, int]:
    """Generate random IVs for a newly caught pokemon.

    Returns dict with keys: iv_hp, iv_atk, iv_def, iv_spa, iv_spdef, iv_spd (0~31 each).
    Shiny pokemon get a minimum of IV_SHINY_MIN (10).
    """
    low = config.IV_SHINY_MIN if is_shiny else config.IV_MIN
    high = config.IV_MAX
    return {
        "iv_hp": random.randint(low, high),
        "iv_atk": random.randint(low, high),
        "iv_def": random.randint(low, high),
        "iv_spa": random.randint(low, high),
        "iv_spdef": random.randint(low, high),
        "iv_spd": random.randint(low, high),
    }


def iv_total(iv_hp, iv_atk, iv_def, iv_spa, iv_spdef, iv_spd) -> int:
    """Sum of all 6 IVs. None values treated as 15 (legacy)."""
    return sum(v if v is not None else 15 for v in (iv_hp, iv_atk, iv_def, iv_spa, iv_spdef, iv_spd))


def calc_battle_stats(
    rarity: str,
    stat_type: str,
    friendship: int,
    evo_stage: int = 3,
    iv_hp: int | None = None,
    iv_atk: int | None = None,
    iv_def: int | None = None,
    iv_spa: int | None = None,
    iv_spdef: int | None = None,
    iv_spd: int | None = None,
    *,
    base_hp: int | None = None,
    base_atk: int | None = None,
    base_def: int | None = None,
    base_spa: int | None = None,
    base_spdef: int | None = None,
    base_spd: int | None = None,
) -> dict:
    """Calculate battle stats (HP, ATK, DEF, SPA, SPDEF, SPD).

    Phase 1 (IV only): Uses rarity base + spread + IV multiplier.
    Phase 2 (base stats): If base_hp/atk/def/spa/spdef/spd provided, uses individual base stats.

    Backward compatible: IV=None → multiplier=1.0 (현재와 동일).
    """
    bonus = 1.0 + (friendship * config.FRIENDSHIP_BONUS)
    evo_mult = config.EVOLUTION_STAGE_MULT.get(evo_stage, 1.0)

    hp_mult = getattr(config, 'BATTLE_HP_MULTIPLIER', 1)

    if base_hp is not None:
        # Phase 2: individual base stats (Lv50 formula)
        return {
            "hp":    int(base_hp * bonus * evo_mult * _iv_mult(iv_hp) * hp_mult),
            "atk":   int(base_atk * bonus * evo_mult * _iv_mult(iv_atk)),
            "def":   int(base_def * bonus * evo_mult * _iv_mult(iv_def)),
            "spa":   int(base_spa * bonus * evo_mult * _iv_mult(iv_spa)),
            "spdef": int(base_spdef * bonus * evo_mult * _iv_mult(iv_spdef)),
            "spd":   int(base_spd * bonus * evo_mult * _iv_mult(iv_spd)),
        }

    # Phase 1: rarity-based base stats + spread (legacy)
    base = config.RARITY_BASE_STAT.get(rarity, 65)
    spread = config.STAT_SPREADS.get(stat_type, config.STAT_SPREADS["balanced"])

    return {
        "hp":    int(base * spread["hp"] * bonus * evo_mult * _iv_mult(iv_hp) * hp_mult),
        "atk":   int(base * spread["atk"] * bonus * evo_mult * _iv_mult(iv_atk)),
        "def":   int(base * spread["def"] * bonus * evo_mult * _iv_mult(iv_def)),
        "spa":   int(base * spread["spa"] * bonus * evo_mult * _iv_mult(iv_spa)),
        "spdef": int(base * spread["spdef"] * bonus * evo_mult * _iv_mult(iv_spdef)),
        "spd":   int(base * spread["spd"] * bonus * evo_mult * _iv_mult(iv_spd)),
    }


def _single_type_mult(atk_type: str, def_type: str) -> float:
    """Return damage multiplier for a single attacker type vs single defender type."""
    # Immunity (0x)
    if def_type in config.TYPE_IMMUNITY.get(atk_type, []):
        return 0.0
    # Super effective (2x)
    if def_type in config.TYPE_ADVANTAGE.get(atk_type, []):
        return config.BATTLE_TYPE_ADVANTAGE_MULT  # 2.0
    # Not very effective (0.5x)
    if atk_type in config.TYPE_ADVANTAGE.get(def_type, []):
        return config.BATTLE_TYPE_DISADVANTAGE_MULT  # 0.5
    return 1.0


def get_type_multiplier(attacker_type, defender_type) -> float:
    """Return damage multiplier based on type matchup (이중 속성 지원).

    attacker_type: str or list[str] — 공격자의 속성
    defender_type: str or list[str] — 수비자의 속성

    공격자: 이중 속성이면 더 유리한 속성으로 자동 공격
    수비자: 이중 속성이면 배수를 곱함 (본가 동일)
    예) [페어리,에스퍼] vs [악,불]
        페어리→악 2.0 × 페어리→불 0.5 = 1.0
        에스퍼→악 0.0 × ... = 0.0
        → max(1.0, 0.0) = 1.0 (페어리로 공격)
    예) [불] vs [풀,강철] → 2.0 × 2.0 = 4.0
    """
    # 속성 리스트로 통일
    atk_types = [attacker_type] if isinstance(attacker_type, str) else attacker_type
    def_types = [defender_type] if isinstance(defender_type, str) else defender_type

    # 공격자의 각 속성으로 시도 → 가장 유리한 배수 선택
    best = 0.0
    for at in atk_types:
        mult = 1.0
        for dt in def_types:
            mult *= _single_type_mult(at, dt)
        if mult > best:
            best = mult
    return best


def _iv_tag(val: int, base: int) -> str:
    """Format a single stat with IV diff: '191(+5)', '180(-3)', or '191'."""
    diff = val - base
    if diff > 0:
        return f"{val}(+{diff})"
    elif diff < 0:
        return f"{val}({diff})"
    return str(val)


def format_stats_line(stats: dict, base: dict = None) -> str:
    """Format stats dict with Korean labels, optionally showing IV bonus."""
    keys = [("hp", "체"), ("atk", "공"), ("def", "방"),
            ("spa", "특공"), ("spdef", "특방"), ("spd", "속")]
    if base:
        return " ".join(f"{lb}{_iv_tag(stats[k], base[k])}" for k, lb in keys)
    return " ".join(f"{lb}{stats[k]}" for k, lb in keys)


def calc_power(stats: dict) -> int:
    """Calculate total battle power (sum of all 6 stats)."""
    return stats['hp'] + stats['atk'] + stats['def'] + stats['spa'] + stats['spdef'] + stats['spd']


def format_power(stats: dict, base: dict = None) -> str:
    """Format power as '639(+50)', '639(-30)', or '639'."""
    power = calc_power(stats)
    if base:
        base_power = calc_power(base)
        diff = power - base_power
        if diff > 0:
            return f"{power}(+{diff})"
        elif diff < 0:
            return f"{power}({diff})"
    return str(power)
