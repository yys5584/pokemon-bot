"""Battle engine: automatic PvP battle resolution."""

import asyncio
import random
import logging

import config
from database import battle_queries as bq
from database import queries
from utils.battle_calc import calc_battle_stats, calc_power, get_type_multiplier, EVO_STAGE_MAP, get_normalized_base_stats, iv_total as _iv_total
from utils.helpers import type_badge, icon_emoji, rarity_badge, shiny_emoji
from models.pokemon_skills import POKEMON_SKILLS, get_skill_effect
from models.pokemon_base_stats import POKEMON_BASE_STATS  # already includes gen3

logger = logging.getLogger(__name__)

# In-memory cache for battle detail DMs (auto-expires after 10min)
_battle_detail_cache: dict[int, dict] = {}


def get_battle_detail(cache_key: int) -> dict | None:
    """Retrieve cached battle detail for DM callback."""
    return _battle_detail_cache.get(cache_key)


def _build_battle_detail_dm(
    result: dict,
    c_name: str, d_name: str,
    c_title_str: str, d_title_str: str,
    c_total_power: int, d_total_power: int,
    winner_name: str, winner_remaining: int,
    bp_won: int, new_streak: int, final_stats: dict,
    skip_bp: bool,
) -> str:
    """Build detailed battle DM text from turn_data."""
    vs = icon_emoji('battle')
    bolt = icon_emoji('bolt')
    skull = icon_emoji('skull')
    trophy = icon_emoji('crown')
    coin = icon_emoji('coin')
    clipboard = icon_emoji('bookmark')
    chart = icon_emoji('stationery')
    sparkle = icon_emoji('crystal')
    lines = [
        f"{vs} 배틀 상세 결과",
        f"{rarity_badge('red')} {c_title_str}{c_name}  {vs}  {d_title_str}{d_name} {rarity_badge('blue')}",
        f"{bolt}{c_total_power}          {bolt}{d_total_power}",
        "━━━━━━━━━━━━━━━",
        "",
        f"{clipboard} 턴별 전투 기록",
    ]

    for td in result["turn_data"]:
        if td["type"] == "matchup":
            ci, di = td["c_idx"] + 1, td["d_idx"] + 1
            ct, dt = td["c_total"], td["d_total"]
            c_shiny_mark = f"{shiny_emoji()}" if td.get("c_shiny") else ""
            d_shiny_mark = f"{shiny_emoji()}" if td.get("d_shiny") else ""
            lines.append(f"<b>── ({ci}/{ct}) {td['c_tb']}{c_shiny_mark}{td['c_name']} vs ({di}/{dt}) {td['d_tb']}{d_shiny_mark}{td['d_name']} ──</b>")
        elif td["type"] == "turn":
            tn = td["turn_num"]
            c_part = f"→{td['c_dmg']}{td['c_crit']}{td['c_eff']}" if td["c_dmg"] else (td['c_eff'].strip() if td['c_eff'].strip() else "")
            d_part = f"←{td['d_dmg']}{td['d_crit']}{td['d_eff']}" if td["d_dmg"] else (td['d_eff'].strip() if td['d_eff'].strip() else "")
            lines.append(f" {tn}턴: {td['c_name']} {c_part} | {td['d_name']} {d_part}")
        elif td["type"] == "ko":
            if td["next_name"]:
                lines.append(f" {skull}{td['dead_name']} 쓰러짐! ▶ {td['next_name']} 등장!")
            else:
                lines.append(f" {skull}{td['dead_name']} 쓰러짐!")
        elif td["type"] == "timeout":
            lines.append(" ⏰ 시간 초과!")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append(f"{trophy} {winner_name} 승리! (남은 {winner_remaining}마리)")

    footer = []
    if not skip_bp:
        footer.append(f"{coin} +{bp_won} BP")
    if new_streak >= 2:
        footer.append(f"{new_streak}연승!")
    if result.get("perfect_win"):
        footer.append(f"{sparkle} 완벽한 승리!")
    footer.append(
        f"{chart} {winner_name} {final_stats['battle_wins']}승 "
        f"{final_stats['battle_losses']}패"
    )
    lines.append(" | ".join(footer))

    return "\n".join(lines)


def _prepare_combatant(pokemon: dict, is_partner: bool = False, camp_placed: bool = False) -> dict:
    """Prepare a single pokemon for battle with computed stats."""
    pid = pokemon.get("pokemon_id") or pokemon.get("id")
    base = get_normalized_base_stats(pid)
    stats = calc_battle_stats(
        pokemon["rarity"],
        pokemon["stat_type"],
        pokemon["friendship"],
        evo_stage=3 if base else EVO_STAGE_MAP.get(pid, 3),
        iv_hp=pokemon.get("iv_hp"),
        iv_atk=pokemon.get("iv_atk"),
        iv_def=pokemon.get("iv_def"),
        iv_spa=pokemon.get("iv_spa"),
        iv_spdef=pokemon.get("iv_spdef"),
        iv_spd=pokemon.get("iv_spd"),
        **(base or {}),
    )

    # Partner bonus: ATK +5%
    if is_partner:
        stats["atk"] = int(stats["atk"] * 1.05)

    # Camp placement bonus: all stats +3%
    if camp_placed:
        bonus = config.CAMP_BATTLE_BONUS
        for key in ("hp", "atk", "def", "spa", "spdef", "spd"):
            stats[key] = int(stats[key] * (1 + bonus))

    # Skill data — 이중 속성 포켓몬은 [("name",pow), ("name",pow)] 리스트
    pid = pokemon.get("pokemon_id") or pokemon.get("id")
    raw_skill = POKEMON_SKILLS.get(pid, ("몸통박치기", 1.2))
    if isinstance(raw_skill, list):
        # 이중 속성: skills[0]=type1 스킬, skills[1]=type2 스킬
        skills = raw_skill
    else:
        # 단일 속성: 동일 스킬 하나
        skills = [raw_skill]

    # IV grade
    iv_sum = _iv_total(
        pokemon.get("iv_hp"), pokemon.get("iv_atk"), pokemon.get("iv_def"),
        pokemon.get("iv_spa"), pokemon.get("iv_spdef"), pokemon.get("iv_spd"),
    )
    iv_grade, _ = config.get_iv_grade(iv_sum)

    # Type badge + dual type list
    tb = type_badge(pid, pokemon.get("pokemon_type"))
    bs = POKEMON_BASE_STATS.get(pid)
    dual_types = bs[-1] if bs else [pokemon.get("pokemon_type", "normal")]

    is_shiny = bool(pokemon.get("is_shiny"))

    return {
        "name": pokemon["name_ko"],
        "emoji": pokemon["emoji"],
        "type": dual_types,
        "rarity": pokemon["rarity"],
        "is_shiny": is_shiny,
        "stats": stats,
        "current_hp": stats["hp"],
        "instance_id": pokemon.get("pokemon_instance_id") or pokemon.get("instance_id"),
        "skills": skills,           # [("name",pow)] or [("name",pow),("name",pow)]
        "skill_name": skills[0][0], # fallback: 1차 속성 스킬명 (표시용)
        "skill_power": skills[0][1],
        "pokemon_id": pid,
        "tb": tb,
        "iv_grade": iv_grade,
        "iv_total": iv_sum,
    }


def _calc_damage(attacker: dict, defender: dict, received_dmg: int = 0) -> tuple[int, str, str, float, dict | None]:
    """Calculate damage from attacker to defender.
    Returns (damage, effect_text, crit_mark, type_mult, effect_info).
    effect_info: dict with skill effect details, or None.
    received_dmg: damage received this turn (for counter calculation).
    """
    # Physical vs Special: use whichever offensive stat is higher
    atk_phys = attacker["stats"]["atk"]
    atk_spec = attacker["stats"]["spa"]
    if atk_spec > atk_phys:
        attack = atk_spec
        defense = defender["stats"]["spdef"]
    else:
        attack = atk_phys
        defense = defender["stats"]["def"]

    # Base damage — 본가(Gen V+) 스타일 공식: ratio-based (A/D)
    base = max(1, int((22 * config.BATTLE_BASE_POWER * attack / defense) / 50 + 2))

    # Type advantage — 이중 속성 중 유리한 타입 자동 선택
    type_mult, best_type_idx = get_type_multiplier(attacker["type"], defender["type"])

    # 선택된 타입에 맞는 스킬 사용
    skills = attacker.get("skills", [])
    if skills and best_type_idx < len(skills):
        chosen_skill = skills[best_type_idx]
    elif skills:
        chosen_skill = skills[0]
    else:
        chosen_skill = ("몸통박치기", 1.2)
    skill_name, skill_power = chosen_skill

    # Skill effect lookup
    effect = get_skill_effect(skill_name)
    effect_info = None

    # Critical hit (10%)
    crit = 1.5 if random.random() < config.BATTLE_CRIT_RATE else 1.0

    # Skill activation (30%)
    skill_activated = random.random() < config.BATTLE_SKILL_RATE

    if skill_activated and effect:
        etype = effect["type"]

        if etype == "splash":
            # 튀어오르기: 데미지 0
            damage = 0
            effect_info = {"type": "splash"}

        elif etype == "rest":
            # 잠자기: 공격 안 하고 HP 회복
            max_hp = attacker["stats"]["hp"]
            heal = int(max_hp * effect["heal_pct"])
            damage = 0
            effect_info = {"type": "rest", "heal": heal}

        elif etype == "self_destruct":
            # 자폭/대폭발: 데미지 대폭 증가 + 자신 즉사
            skill_mult = effect["damage_bonus"]
            variance = random.uniform(0.9, 1.1)
            damage = max(1, int(base * type_mult * crit * skill_mult * variance))
            effect_info = {"type": "self_destruct"}

        elif etype == "random_power":
            # 손가락흔들기: 랜덤 배율
            rand_mult = random.uniform(effect["min"], effect["max"])
            variance = random.uniform(0.9, 1.1)
            damage = max(1, int(base * type_mult * crit * rand_mult * variance))
            effect_info = {"type": "random_power", "mult": rand_mult}

        elif etype == "counter":
            # 반격: 받은 데미지 × mult 반사 (후공 시에만)
            if received_dmg > 0:
                damage = int(received_dmg * effect["mult"])
                effect_info = {"type": "counter", "reflected": damage}
            else:
                # 선공이면 일반 스킬 발동
                skill_mult = skill_power
                variance = random.uniform(0.9, 1.1)
                damage = max(1, int(base * type_mult * crit * skill_mult * variance))
                effect_info = None

        elif etype == "recoil":
            # 반동계: damage_bonus가 있으면 skill_power 대신 사용 (고위력 반동기)
            skill_mult = effect.get("damage_bonus", skill_power)
            variance = random.uniform(0.9, 1.1)
            damage = max(1, int(base * type_mult * crit * skill_mult * variance))
            effect_info = {"type": "recoil", "pct": effect.get("pct", 0)}

        else:
            # drain: 일반 데미지 계산 후 효과 정보 첨부
            skill_mult = skill_power
            variance = random.uniform(0.9, 1.1)
            damage = max(1, int(base * type_mult * crit * skill_mult * variance))
            effect_info = {"type": etype, "pct": effect.get("pct", 0)}

    else:
        # 스킬 미발동 또는 효과 없는 일반 스킬
        skill_mult = skill_power if skill_activated else 1.0
        variance = random.uniform(0.9, 1.1)
        damage = max(1, int(base * type_mult * crit * skill_mult * variance))

    # Build effect text
    effects = []
    if skill_activated:
        effects.append(f"「{skill_name}」")
    if effect_info:
        etype_display = effect_info["type"]
        if etype_display == "self_destruct":
            effects.append("💥")
        elif etype_display == "recoil":
            effects.append("💢")
        elif etype_display == "drain":
            effects.append("🌿")
        elif etype_display == "rest":
            effects.append("💤")
        elif etype_display == "counter":
            effects.append("🔄")
        elif etype_display == "random_power":
            effects.append(f"🎲x{effect_info.get('mult', 1):.1f}")
        elif etype_display == "splash":
            effects.clear()
            effects.append("아무일도일어나지않았다!")

    crit_mark = "*" if crit > 1.0 else ""
    effect_text = f" {' '.join(effects)}" if effects else ""
    return damage, effect_text, crit_mark, type_mult, effect_info


def _has_priority(mon: dict) -> bool:
    """Check if pokemon has a priority move (선제기)."""
    for skill_name, _ in mon.get("skills", []):
        eff = get_skill_effect(skill_name)
        if eff and eff["type"] == "priority":
            return True
    return False


def _hp_bar(current: int, max_hp: int, length: int = 6) -> str:
    """Generate a text HP bar like ████░░."""
    filled = max(0, round(current / max_hp * length)) if max_hp > 0 else 0
    return "█" * filled + "░" * (length - filled)


def _resolve_battle(challenger_team: list[dict], defender_team: list[dict]) -> dict:
    """Run the automatic battle between two teams.

    Each team is a list of _prepare_combatant() dicts.
    Returns battle result dict with structured turn_data for rich display.
    """
    SKULL = icon_emoji("skull")
    log_lines = []
    turn_data = []  # structured data for detailed display
    c_idx = 0
    d_idx = 0
    round_num = 0
    match_turn = 0  # turn counter per matchup (resets on new opponent)

    c_mon = challenger_team[c_idx]
    d_mon = defender_team[d_idx]

    c_total = len(challenger_team)
    d_total = len(defender_team)

    log_lines.append(
        f"({c_idx+1}/{c_total}) {c_mon['tb']}{c_mon['name']}({c_mon['iv_grade']})"
        f" ⚔ ({d_idx+1}/{d_total}) {d_mon['tb']}{d_mon['name']}({d_mon['iv_grade']})"
    )
    turn_data.append({
        "type": "matchup",
        "c_name": c_mon["name"], "d_name": d_mon["name"],
        "c_tb": c_mon["tb"], "d_tb": d_mon["tb"],
        "c_idx": c_idx, "d_idx": d_idx,
        "c_total": c_total, "d_total": d_total,
        "c_hp": c_mon["current_hp"], "d_hp": d_mon["current_hp"],
        "c_max_hp": c_mon["stats"]["hp"], "d_max_hp": d_mon["stats"]["hp"],
        "c_pokemon_id": c_mon["pokemon_id"], "d_pokemon_id": d_mon["pokemon_id"],
        "c_rarity": c_mon["rarity"], "d_rarity": d_mon["rarity"],
        "c_shiny": c_mon.get("is_shiny", False), "d_shiny": d_mon.get("is_shiny", False),
    })

    while c_idx < len(challenger_team) and d_idx < len(defender_team):
        round_num += 1
        match_turn += 1
        if round_num > config.BATTLE_MAX_ROUNDS:
            break

        # Speed determines who goes first (선제기: 30% 확률 발동)
        c_prio = _has_priority(c_mon) and random.random() < config.BATTLE_SKILL_RATE
        d_prio = _has_priority(d_mon) and random.random() < config.BATTLE_SKILL_RATE
        if c_prio and not d_prio:
            first, second = c_mon, d_mon
            first_is_challenger = True
        elif d_prio and not c_prio:
            first, second = d_mon, c_mon
            first_is_challenger = False
        elif c_mon["stats"]["spd"] >= d_mon["stats"]["spd"]:
            first, second = c_mon, d_mon
            first_is_challenger = True
        else:
            first, second = d_mon, c_mon
            first_is_challenger = False

        # First attack
        dmg1, eff1, crit1, tmult1, fx1 = _calc_damage(first, second)
        # Rest: 공격 안 하고 HP 회복
        rest_lines = []
        if fx1 and fx1["type"] == "rest":
            max_hp = first["stats"]["hp"]
            first["current_hp"] = min(max_hp, first["current_hp"] + fx1["heal"])
            rest_lines.append(f"  💤 {first['name']} HP +{fx1['heal']} 회복")
        else:
            second["current_hp"] -= dmg1

        # Second attacks back if alive
        dmg2, eff2, crit2, tmult2, fx2 = 0, "", "", 1.0, None
        if second["current_hp"] > 0:
            # 반격: 받은 데미지를 전달
            received = dmg1 if (fx1 is None or fx1["type"] != "rest") else 0
            dmg2, eff2, crit2, tmult2, fx2 = _calc_damage(second, first, received_dmg=received)
            if fx2 and fx2["type"] == "rest":
                max_hp = second["stats"]["hp"]
                second["current_hp"] = min(max_hp, second["current_hp"] + fx2["heal"])
                rest_lines.append(f"  💤 {second['name']} HP +{fx2['heal']} 회복")
            else:
                first["current_hp"] -= dmg2

        # --- 스킬 효과 적용 + 로그 ---
        fx_lines = []
        # First attacker effects
        if fx1:
            if fx1["type"] == "self_destruct":
                first["current_hp"] = 0
                fx_lines.append(f"  💥 {first['name']}의 자폭!")
            elif fx1["type"] == "recoil" and dmg1 > 0:
                recoil_dmg = max(1, int(dmg1 * fx1["pct"]))
                first["current_hp"] -= recoil_dmg
                fx_lines.append(f"  💢 {first['name']} 반동 -{recoil_dmg}")
            elif fx1["type"] == "drain" and dmg1 > 0:
                heal = max(1, int(dmg1 * fx1["pct"]))
                max_hp = first["stats"]["hp"]
                first["current_hp"] = min(max_hp, first["current_hp"] + heal)
                fx_lines.append(f"  🌿 {first['name']} HP +{heal} 흡수")

        # Second attacker effects
        if fx2:
            if fx2["type"] == "self_destruct":
                second["current_hp"] = 0
                fx_lines.append(f"  💥 {second['name']}의 자폭!")
            elif fx2["type"] == "recoil" and dmg2 > 0:
                recoil_dmg = max(1, int(dmg2 * fx2["pct"]))
                second["current_hp"] -= recoil_dmg
                fx_lines.append(f"  💢 {second['name']} 반동 -{recoil_dmg}")
            elif fx2["type"] == "drain" and dmg2 > 0:
                heal = max(1, int(dmg2 * fx2["pct"]))
                max_hp = second["stats"]["hp"]
                second["current_hp"] = min(max_hp, second["current_hp"] + heal)
                fx_lines.append(f"  🌿 {second['name']} HP +{heal} 흡수")

        # Map to challenger(left)/defender(right) for consistent display
        if first_is_challenger:
            c_dmg, c_eff, c_crit, c_tmult = dmg1, eff1, crit1, tmult1
            d_dmg, d_eff, d_crit, d_tmult = dmg2, eff2, crit2, tmult2
        else:
            d_dmg, d_eff, d_crit, d_tmult = dmg1, eff1, crit1, tmult1
            c_dmg, c_eff, c_crit, c_tmult = dmg2, eff2, crit2, tmult2

        # → = left attacks right, ← = right attacks left
        # rest/splash 등 dmg=0이어도 효과 텍스트가 있으면 표시
        c_part = f"→{c_dmg}{c_crit}{c_eff}" if c_dmg else (c_eff.strip() if c_eff.strip() else "")
        d_part = f"←{d_dmg}{d_crit}{d_eff}" if d_dmg else (d_eff.strip() if d_eff.strip() else "")
        log_lines.append(
            f" {match_turn}턴: {c_mon['name']} {c_part} | {d_mon['name']} {d_part}"
        )
        for fl in rest_lines + fx_lines:
            log_lines.append(fl)

        # Structured turn data
        # Store max_hp from the matchup entry
        last_matchup = next((t for t in reversed(turn_data) if t["type"] == "matchup"), None)
        c_max = last_matchup["c_max_hp"] if last_matchup else c_mon["current_hp"]
        d_max = last_matchup["d_max_hp"] if last_matchup else d_mon["current_hp"]
        turn_data.append({
            "type": "turn",
            "turn_num": match_turn,
            "c_name": c_mon["name"], "d_name": d_mon["name"],
            "c_dmg": c_dmg, "d_dmg": d_dmg,
            "c_crit": c_crit, "d_crit": d_crit,
            "c_eff": c_eff, "d_eff": d_eff,
            "c_hp": max(0, c_mon["current_hp"]), "d_hp": max(0, d_mon["current_hp"]),
            "c_max_hp": c_max, "d_max_hp": d_max,
            "c_idx": c_idx, "d_idx": d_idx,
            "c_total": c_total, "d_total": d_total,
            "first_is_challenger": first_is_challenger,
            "c_pokemon_id": c_mon["pokemon_id"], "d_pokemon_id": d_mon["pokemon_id"],
            "c_rarity": c_mon["rarity"], "d_rarity": d_mon["rarity"],
            "c_shiny": c_mon.get("is_shiny", False), "d_shiny": d_mon.get("is_shiny", False),
            "c_type_mult": c_tmult, "d_type_mult": d_tmult,
        })

        # KO check - challenger's pokemon
        if c_mon["current_hp"] <= 0:
            dead_name = c_mon['name']
            c_idx += 1
            if c_idx < len(challenger_team):
                c_mon = challenger_team[c_idx]
                log_lines.append(
                    f" {SKULL}{dead_name} 쓰러짐! ▶ {c_mon['name']} 등장!"
                )
                turn_data.append({"type": "ko", "dead_name": dead_name, "next_name": c_mon["name"], "next_rarity": c_mon.get("rarity", ""), "next_idx": c_idx, "next_total": c_total, "side": "challenger"})
                # New matchup entry for correct max_hp tracking
                if d_idx < len(defender_team) and d_mon["current_hp"] > 0:
                    match_turn = 0
                    log_lines.append(
                        f"\n({c_idx+1}/{c_total}) {c_mon['tb']}{c_mon['name']}({c_mon['iv_grade']})"
                        f" ⚔ ({d_idx+1}/{d_total}) {d_mon['tb']}{d_mon['name']}({d_mon['iv_grade']})"
                    )
                    turn_data.append({
                        "type": "matchup",
                        "c_name": c_mon["name"], "d_name": d_mon["name"],
                        "c_tb": c_mon["tb"], "d_tb": d_mon["tb"],
                        "c_idx": c_idx, "d_idx": d_idx,
                        "c_total": c_total, "d_total": d_total,
                        "c_hp": c_mon["current_hp"], "d_hp": d_mon["current_hp"],
                        "c_max_hp": c_mon["stats"]["hp"], "d_max_hp": d_mon["stats"]["hp"],
                        "c_shiny": c_mon.get("is_shiny", False), "d_shiny": d_mon.get("is_shiny", False),
                    })
            else:
                log_lines.append(f" {SKULL}{dead_name} 쓰러짐!")
                turn_data.append({"type": "ko", "dead_name": dead_name, "next_name": None, "side": "challenger"})

        # KO check - defender's pokemon
        if d_mon["current_hp"] <= 0:
            dead_name = d_mon['name']
            d_idx += 1
            if d_idx < len(defender_team):
                d_mon = defender_team[d_idx]
                log_lines.append(
                    f" {SKULL}{dead_name} 쓰러짐! ▶ {d_mon['name']} 등장!"
                )
                turn_data.append({"type": "ko", "dead_name": dead_name, "next_name": d_mon["name"], "next_rarity": d_mon.get("rarity", ""), "next_idx": d_idx, "next_total": d_total, "side": "defender"})
                if c_idx < len(challenger_team):
                    match_turn = 0  # reset turn counter for new matchup
                    log_lines.append(
                        f"\n({c_idx+1}/{c_total}) {challenger_team[c_idx]['tb']}{challenger_team[c_idx]['name']}({challenger_team[c_idx]['iv_grade']})"
                        f" ⚔ ({d_idx+1}/{d_total}) {d_mon['tb']}{d_mon['name']}({d_mon['iv_grade']})"
                    )
                    turn_data.append({
                        "type": "matchup",
                        "c_name": challenger_team[c_idx]["name"], "d_name": d_mon["name"],
                        "c_tb": challenger_team[c_idx]["tb"], "d_tb": d_mon["tb"],
                        "c_idx": c_idx, "d_idx": d_idx,
                        "c_total": c_total, "d_total": d_total,
                        "c_hp": challenger_team[c_idx]["current_hp"], "d_hp": d_mon["current_hp"],
                        "c_max_hp": challenger_team[c_idx]["stats"]["hp"], "d_max_hp": d_mon["stats"]["hp"],
                        "c_shiny": challenger_team[c_idx].get("is_shiny", False), "d_shiny": d_mon.get("is_shiny", False),
                    })
            else:
                log_lines.append(f" {SKULL}{dead_name} 쓰러짐!")
                turn_data.append({"type": "ko", "dead_name": dead_name, "next_name": None, "side": "defender"})

    # Determine winner
    if round_num > config.BATTLE_MAX_ROUNDS:
        # Timeout: compare remaining HP
        c_hp = sum(m["current_hp"] for m in challenger_team[c_idx:] if m["current_hp"] > 0)
        d_hp = sum(m["current_hp"] for m in defender_team[d_idx:] if m["current_hp"] > 0)
        winner = "challenger" if c_hp >= d_hp else "defender"
        log_lines.append(f"\n⏰ {config.BATTLE_MAX_ROUNDS}라운드 초과! HP합산 판정")
        turn_data.append({"type": "timeout"})
    elif d_idx >= len(defender_team):
        winner = "challenger"
    else:
        winner = "defender"

    c_remaining = len(challenger_team) - c_idx
    d_remaining = len(defender_team) - d_idx

    return {
        "winner": winner,
        "rounds": round_num,
        "challenger_remaining": max(0, c_remaining),
        "defender_remaining": max(0, d_remaining),
        "log": "\n".join(log_lines),
        "turn_data": turn_data,
        "perfect_win": (
            (winner == "challenger" and c_remaining == len(challenger_team))
            or (winner == "defender" and d_remaining == len(defender_team))
        ),
    }


def _extract_pokemon_stats(
    turn_data: list[dict],
    c_combatants: list[dict],
    d_combatants: list[dict],
    winner_id: int,
    loser_id: int,
    challenger_id: int,
    defender_id: int,
    battle_type: str,
) -> list[dict]:
    """Extract per-pokemon battle stats from turn_data for analytics.

    Returns a list of dicts ready for DB insertion (max 12 for 6v6).
    """
    # Init stats from combatant lists
    # Key: ("c", idx) or ("d", idx)
    stats: dict[tuple[str, int], dict] = {}

    for idx, mon in enumerate(c_combatants):
        stats[("c", idx)] = {
            "battle_type": battle_type,
            "user_id": challenger_id,
            "pokemon_id": mon["pokemon_id"],
            "rarity": mon["rarity"],
            "is_shiny": mon.get("is_shiny", False),
            "iv_total": mon.get("iv_total", 0),
            "damage_dealt": 0,
            "damage_taken": 0,
            "kills": 0,
            "deaths": 0,
            "turns_alive": 0,
            "crits_landed": 0,
            "crits_received": 0,
            "skills_activated": 0,
            "super_effective_hits": 0,
            "not_effective_hits": 0,
            "side": "challenger",
            "won": challenger_id == winner_id,
        }

    for idx, mon in enumerate(d_combatants):
        stats[("d", idx)] = {
            "battle_type": battle_type,
            "user_id": defender_id,
            "pokemon_id": mon["pokemon_id"],
            "rarity": mon["rarity"],
            "is_shiny": mon.get("is_shiny", False),
            "iv_total": mon.get("iv_total", 0),
            "damage_dealt": 0,
            "damage_taken": 0,
            "kills": 0,
            "deaths": 0,
            "turns_alive": 0,
            "crits_landed": 0,
            "crits_received": 0,
            "skills_activated": 0,
            "super_effective_hits": 0,
            "not_effective_hits": 0,
            "side": "defender",
            "won": defender_id == winner_id,
        }

    # Track current active pokemon index per side
    cur_c_idx = 0
    cur_d_idx = 0

    for entry in turn_data:
        etype = entry.get("type")

        if etype == "matchup":
            cur_c_idx = entry.get("c_idx", cur_c_idx)
            cur_d_idx = entry.get("d_idx", cur_d_idx)

        elif etype == "turn":
            ci = entry.get("c_idx", cur_c_idx)
            di = entry.get("d_idx", cur_d_idx)
            c_s = stats.get(("c", ci))
            d_s = stats.get(("d", di))

            if c_s:
                c_s["turns_alive"] += 1
                c_s["damage_dealt"] += entry.get("c_dmg", 0)
                c_s["damage_taken"] += entry.get("d_dmg", 0)
                if entry.get("c_crit") == "*":
                    c_s["crits_landed"] += 1
                if entry.get("d_crit") == "*":
                    c_s["crits_received"] += 1
                if entry.get("c_eff") and "「" in entry["c_eff"]:
                    c_s["skills_activated"] += 1
                c_tm = entry.get("c_type_mult", 1.0)
                if c_tm and entry.get("c_dmg", 0) > 0:
                    if c_tm > 1.0:
                        c_s["super_effective_hits"] += 1
                    elif c_tm < 1.0:
                        c_s["not_effective_hits"] += 1

            if d_s:
                d_s["turns_alive"] += 1
                d_s["damage_dealt"] += entry.get("d_dmg", 0)
                d_s["damage_taken"] += entry.get("c_dmg", 0)
                if entry.get("d_crit") == "*":
                    d_s["crits_landed"] += 1
                if entry.get("c_crit") == "*":
                    d_s["crits_received"] += 1
                if entry.get("d_eff") and "「" in entry["d_eff"]:
                    d_s["skills_activated"] += 1
                d_tm = entry.get("d_type_mult", 1.0)
                if d_tm and entry.get("d_dmg", 0) > 0:
                    if d_tm > 1.0:
                        d_s["super_effective_hits"] += 1
                    elif d_tm < 1.0:
                        d_s["not_effective_hits"] += 1

        elif etype == "ko":
            side = entry.get("side")
            if side == "challenger":
                s = stats.get(("c", cur_c_idx))
                if s:
                    s["deaths"] = 1
                # The opponent (defender) gets a kill
                ds = stats.get(("d", cur_d_idx))
                if ds:
                    ds["kills"] += 1
                cur_c_idx += 1
            elif side == "defender":
                s = stats.get(("d", cur_d_idx))
                if s:
                    s["deaths"] = 1
                # The opponent (challenger) gets a kill
                cs = stats.get(("c", cur_c_idx))
                if cs:
                    cs["kills"] += 1
                cur_d_idx += 1

    return list(stats.values())


def _calculate_bp(winner_team_size: int, loser_team_size: int, perfect: bool, streak: int) -> int:
    """Calculate BP reward for the winner."""
    # Base: 20 + team size bonus (loser_team_size × BP_WIN_PER_ENEMY)
    bp = config.BP_WIN_BASE + loser_team_size * config.BP_WIN_PER_ENEMY

    # Perfect win bonus
    if perfect:
        bp += config.BP_PERFECT_WIN

    # Streak bonus (every 3 wins)
    if streak > 0 and streak % 3 == 0:
        bp += config.BP_STREAK_BONUS

    return bp


async def execute_battle(
    challenger_id: int,
    defender_id: int,
    challenger_team: list[dict],
    defender_team: list[dict],
    challenge_id: int | None,
    chat_id: int,
    skip_bp: bool = False,
    bot=None,
    battle_type: str = "normal",
    season_id: str | None = None,
) -> dict:
    """Execute a full battle and record results.

    battle_type: 'normal', 'yacha', 'ranked'
    Returns dict with 'display_text' for the chat message.
    """
    is_ranked = battle_type == "ranked"
    # Get partner info
    c_partner = await bq.get_partner(challenger_id)
    d_partner = await bq.get_partner(defender_id)
    c_partner_inst = c_partner["instance_id"] if c_partner else None
    d_partner_inst = d_partner["instance_id"] if d_partner else None

    # Camp placement bonus
    from database import camp_queries as _cq
    c_camp_ids, d_camp_ids = await asyncio.gather(
        _cq.get_user_placed_instance_ids(challenger_id),
        _cq.get_user_placed_instance_ids(defender_id),
    )

    # Prepare combatants
    c_combatants = [
        _prepare_combatant(
            p,
            is_partner=(p["pokemon_instance_id"] == c_partner_inst),
            camp_placed=(p["pokemon_instance_id"] in c_camp_ids),
        )
        for p in challenger_team
    ]
    d_combatants = [
        _prepare_combatant(
            p,
            is_partner=(p["pokemon_instance_id"] == d_partner_inst),
            camp_placed=(p["pokemon_instance_id"] in d_camp_ids),
        )
        for p in defender_team
    ]

    # Run battle
    result = _resolve_battle(c_combatants, d_combatants)

    # Determine winner/loser IDs
    if result["winner"] == "challenger":
        winner_id = challenger_id
        loser_id = defender_id
        winner_remaining = result["challenger_remaining"]
        winner_team_size = len(challenger_team)
        loser_team_size = len(defender_team)
    else:
        winner_id = defender_id
        loser_id = challenger_id
        winner_remaining = result["defender_remaining"]
        winner_team_size = len(defender_team)
        loser_team_size = len(challenger_team)

    # Get current streak before update
    winner_stats = await bq.get_battle_stats(winner_id)
    new_streak = winner_stats["battle_streak"] + 1

    # Calculate BP
    if skip_bp:
        bp_won = 0
        bp_lose = 0
    elif is_ranked:
        # 랭크전: 도전자(challenger)에게만 2배 BP 지급
        base_bp = _calculate_bp(winner_team_size, loser_team_size, result["perfect_win"], new_streak)
        ranked_bp = base_bp * 2
        ranked_lose_bp = config.BP_LOSE * 2
        if winner_id == challenger_id:
            bp_won = ranked_bp
            bp_lose = 0  # 수비자(패배) — BP 없음
        else:
            bp_won = 0   # 수비자(승리) — BP 없음
            bp_lose = ranked_lose_bp  # 도전자(패배)도 2배
    else:
        bp_won = _calculate_bp(winner_team_size, loser_team_size, result["perfect_win"], new_streak)
        bp_lose = config.BP_LOSE

    # 구독자 BP 배율 적용 (일반 + 랭크전 모두)
    if bp_won > 0:
        try:
            from services.subscription_service import get_benefit_value
            multiplier = await get_benefit_value(winner_id, "bp_multiplier", 1.0)
            if multiplier > 1.0:
                bp_won = int(bp_won * multiplier)
        except Exception:
            pass

    # Update stats (ranked still counts in overall battle_wins/losses)
    await bq.update_battle_stats_win(winner_id, bp_won)
    await bq.update_battle_stats_lose(loser_id, bp_lose)

    # Mission: battle win
    asyncio.create_task(_notify_battle_mission(winner_id, bot))

    # CXP: +2 for battle (only real battles, not yacha)
    if not skip_bp and chat_id and bot:
        async def _battle_cxp():
            try:
                new_level = await queries.add_chat_cxp(chat_id, config.CXP_PER_BATTLE, "battle", winner_id)
                if new_level:
                    info = config.get_chat_level_info(
                        (await queries.get_chat_level(chat_id))["cxp"]
                    )
                    bonus_txt = f"+{info['spawn_bonus']} 스폰" if info["spawn_bonus"] else ""
                    shiny_txt = f"+{info['shiny_boost_pct']:.1f}% 이로치" if info["shiny_boost_pct"] else ""
                    parts = [p for p in [bonus_txt, shiny_txt] if p]
                    perks = f" ({', '.join(parts)})" if parts else ""
                    special = ""
                    if "daily_shiny" in info["specials"]:
                        special = "\n✨ 일일 이로치 스폰 해금!"
                    if "auto_arcade" in info["specials"]:
                        special = "\n🎰 일일 자동 아케이드 해금!"
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"🎊 채팅방 레벨 UP! Lv.{new_level}{perks}{special}",
                        parse_mode="HTML",
                    )
            except Exception as e:
                logger.error(f"Battle CXP failed: {e}")
        asyncio.create_task(_battle_cxp())

    # Record battle
    battle_record_id = await bq.record_battle(
        challenge_id=challenge_id,
        chat_id=chat_id,
        winner_id=winner_id,
        loser_id=loser_id,
        winner_team_size=winner_team_size,
        loser_team_size=loser_team_size,
        winner_remaining=winner_remaining,
        total_rounds=result["rounds"],
        battle_log=result["log"],
        bp_earned=bp_won,
        battle_type=battle_type,
    )

    # Save per-pokemon battle stats for analytics (non-blocking)
    try:
        pokemon_stats = _extract_pokemon_stats(
            result["turn_data"], c_combatants, d_combatants,
            winner_id, loser_id, challenger_id, defender_id, battle_type,
        )
        if pokemon_stats:
            await bq.save_battle_pokemon_stats(battle_record_id, pokemon_stats)
    except Exception as e:
        logger.error(f"Battle stats save failed: {e}")

    # Ranked: process RP changes
    ranked_info = None
    if is_ranked and season_id:
        from services.ranked_service import process_ranked_result
        ranked_info = await process_ranked_result(
            winner_id, loser_id, season_id, battle_record_id,
        )

    # Get display names — challenger always LEFT, defender always RIGHT
    c_user = await queries.get_user(challenger_id)
    d_user = await queries.get_user(defender_id)
    c_name = c_user["display_name"] if c_user else "???"
    d_name = d_user["display_name"] if d_user else "???"

    # 구독자 존칭 적용
    try:
        from utils.honorific import honorific_name as _hon_name
        from services.subscription_service import get_user_tier
        c_tier = await get_user_tier(challenger_id)
        d_tier = await get_user_tier(defender_id)
        c_name = _hon_name(c_name, c_tier)
        d_name = _hon_name(d_name, d_tier)
    except Exception:
        pass
    c_te = c_user.get("title_emoji", "") if c_user else ""
    d_te = d_user.get("title_emoji", "") if d_user else ""
    c_title_str = f"{icon_emoji(c_te)} " if c_te and c_te in config.ICON_CUSTOM_EMOJI else ""
    d_title_str = f"{icon_emoji(d_te)} " if d_te and d_te in config.ICON_CUSTOM_EMOJI else ""

    winner_name = c_name if result["winner"] == "challenger" else d_name
    loser_name = d_name if result["winner"] == "challenger" else c_name

    # Get updated stats for display
    final_stats = await bq.get_battle_stats(winner_id)

    # Calculate total team power
    c_total_power = sum(calc_power(c["stats"]) for c in c_combatants)
    d_total_power = sum(calc_power(d["stats"]) for d in d_combatants)

    # Build simplified group chat display
    vs = icon_emoji('battle')
    trophy = icon_emoji('crown')
    lines = [
        f"{vs} 배틀 결과!",
        f"{rarity_badge('red')} {c_title_str}{c_name}  {vs}  {d_title_str}{d_name} {rarity_badge('blue')}",
        "━━━━━━━━━━━━━━━",
        f"{trophy} {winner_name} 승리!",
    ]

    # Build detailed DM text from turn_data
    detail_dm = _build_battle_detail_dm(
        result, c_name, d_name, c_title_str, d_title_str,
        c_total_power, d_total_power,
        winner_name, winner_remaining,
        bp_won, new_streak, final_stats, skip_bp,
    )

    # Cache detail for button callback
    cache_key = challenge_id or id(result)  # fallback for yacha
    _battle_detail_cache[cache_key] = {
        "detail_dm": detail_dm,
        "winner_id": winner_id,
        "loser_id": loser_id,
    }
    # Auto-expire after 10 minutes
    try:
        loop = asyncio.get_event_loop()
        loop.call_later(600, _battle_detail_cache.pop, cache_key, None)
    except Exception:
        pass

    # Check and unlock battle titles
    await _check_battle_titles(winner_id, final_stats, result["perfect_win"])
    await _check_battle_titles(loser_id, await bq.get_battle_stats(loser_id), False)

    return {
        "display_text": "\n".join(lines),
        "winner_id": winner_id,
        "loser_id": loser_id,
        "bp_earned": bp_won,
        "cache_key": cache_key,
        "winner_name": winner_name,
        "loser_name": loser_name,
        "new_streak": new_streak,
        "perfect_win": result["perfect_win"],
        "battle_type": battle_type,
        "ranked_info": ranked_info,
    }


async def _check_battle_titles(user_id: int, stats: dict, perfect_win: bool):
    """Check and unlock battle-related titles."""
    from database import queries

    total_battles = stats["battle_wins"] + stats["battle_losses"]
    wins = stats["battle_wins"]
    best_streak = stats["best_streak"]

    title_checks = [
        ("battle_first", total_battles >= 1),
        ("battle_fighter", wins >= 5),
        ("battle_champion", wins >= 20),
        ("battle_legend", wins >= 50),
        ("battle_streak3", best_streak >= 3),
        ("battle_streak10", best_streak >= 10),
    ]

    if perfect_win:
        title_checks.append(("battle_sweep", True))

    for title_id, condition in title_checks:
        if condition and title_id in config.BATTLE_TITLES:
            already = await queries.has_title(user_id, title_id)
            if not already:
                await queries.unlock_title(user_id, title_id)
                logger.info(f"Battle title unlocked: {user_id} -> {title_id}")


async def _notify_battle_mission(user_id: int, bot):
    """Fire-and-forget: check battle mission progress and DM user on completion."""
    try:
        from services.mission_service import check_mission_progress
        msg = await check_mission_progress(user_id, "battle")
        if msg and bot:
            await bot.send_message(chat_id=user_id, text=msg, parse_mode="HTML")
    except Exception:
        pass
