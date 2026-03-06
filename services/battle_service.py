"""Battle engine: automatic PvP battle resolution."""

import asyncio
import random
import logging

import config
from database import battle_queries as bq
from utils.battle_calc import calc_battle_stats, calc_power, get_type_multiplier, EVO_STAGE_MAP, get_normalized_base_stats, iv_total as _iv_total
from utils.helpers import type_badge, icon_emoji, rarity_badge
from models.pokemon_skills import POKEMON_SKILLS
from models.pokemon_base_stats import POKEMON_BASE_STATS

try:
    from models.pokemon_base_stats_gen3 import POKEMON_BASE_STATS_GEN3
    _ALL_BASE_STATS = {**POKEMON_BASE_STATS, **POKEMON_BASE_STATS_GEN3}
except ImportError:
    _ALL_BASE_STATS = POKEMON_BASE_STATS

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
            lines.append(f"── ({ci}/{ct}) {td['c_tb']}{td['c_name']} vs ({di}/{dt}) {td['d_tb']}{td['d_name']} ──")
        elif td["type"] == "turn":
            tn = td["turn_num"]
            c_part = f"→{td['c_dmg']}{td['c_crit']}{td['c_eff']}" if td["c_dmg"] else ""
            d_part = f"←{td['d_dmg']}{td['d_crit']}{td['d_eff']}" if td["d_dmg"] else ""
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


def _prepare_combatant(pokemon: dict, is_partner: bool = False) -> dict:
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

    # Skill data
    pid = pokemon.get("pokemon_id") or pokemon.get("id")
    skill = POKEMON_SKILLS.get(pid, ("몸통박치기", 1.2))

    # IV grade
    iv_sum = _iv_total(
        pokemon.get("iv_hp"), pokemon.get("iv_atk"), pokemon.get("iv_def"),
        pokemon.get("iv_spa"), pokemon.get("iv_spdef"), pokemon.get("iv_spd"),
    )
    iv_grade, _ = config.get_iv_grade(iv_sum)

    # Type badge + dual type list
    tb = type_badge(pid, pokemon.get("pokemon_type"))
    bs = _ALL_BASE_STATS.get(pid)
    dual_types = bs[-1] if bs else [pokemon.get("pokemon_type", "normal")]

    return {
        "name": pokemon["name_ko"],
        "emoji": pokemon["emoji"],
        "type": dual_types,
        "rarity": pokemon["rarity"],
        "stats": stats,
        "current_hp": stats["hp"],
        "instance_id": pokemon.get("pokemon_instance_id") or pokemon.get("instance_id"),
        "skill_name": skill[0],
        "skill_power": skill[1],
        "pokemon_id": pid,
        "tb": tb,
        "iv_grade": iv_grade,
    }


def _calc_damage(attacker: dict, defender: dict) -> tuple[int, str]:
    """Calculate damage from attacker to defender.
    Returns (damage, effect_text).
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

    # Base damage
    base = max(1, attack - defense * 0.4)

    # Type advantage
    type_mult = get_type_multiplier(attacker["type"], defender["type"])

    # Critical hit (10%)
    crit = 1.5 if random.random() < config.BATTLE_CRIT_RATE else 1.0

    # Skill activation (30%)
    skill_activated = random.random() < config.BATTLE_SKILL_RATE
    skill_mult = attacker.get("skill_power", 1.0) if skill_activated else 1.0

    # Random variance (±10%)
    variance = random.uniform(0.9, 1.1)

    damage = int(base * type_mult * crit * skill_mult * variance)
    damage = max(1, damage)  # At least 1 damage

    # Build effect text
    effects = []
    if skill_activated:
        effects.append(f"「{attacker.get('skill_name', '몸통박치기')}」")

    crit_mark = "*" if crit > 1.0 else ""
    effect_text = f" {' '.join(effects)}" if effects else ""
    return damage, effect_text, crit_mark


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
    })

    while c_idx < len(challenger_team) and d_idx < len(defender_team):
        round_num += 1
        match_turn += 1
        if round_num > config.BATTLE_MAX_ROUNDS:
            break

        # Speed determines who goes first
        if c_mon["stats"]["spd"] >= d_mon["stats"]["spd"]:
            first, second = c_mon, d_mon
            first_is_challenger = True
        else:
            first, second = d_mon, c_mon
            first_is_challenger = False

        # First attack
        dmg1, eff1, crit1 = _calc_damage(first, second)
        second["current_hp"] -= dmg1

        # Second attacks back if alive
        dmg2, eff2, crit2 = 0, "", ""
        if second["current_hp"] > 0:
            dmg2, eff2, crit2 = _calc_damage(second, first)
            first["current_hp"] -= dmg2

        # Map to challenger(left)/defender(right) for consistent display
        if first_is_challenger:
            c_dmg, c_eff, c_crit = dmg1, eff1, crit1
            d_dmg, d_eff, d_crit = dmg2, eff2, crit2
        else:
            d_dmg, d_eff, d_crit = dmg1, eff1, crit1
            c_dmg, c_eff, c_crit = dmg2, eff2, crit2

        # → = left attacks right, ← = right attacks left
        c_part = f"→{c_dmg}{c_crit}{c_eff}" if c_dmg else ""
        d_part = f"←{d_dmg}{d_crit}{d_eff}" if d_dmg else ""
        log_lines.append(
            f" {match_turn}턴: {c_mon['name']} {c_part} | {d_mon['name']} {d_part}"
        )

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
) -> dict:
    """Execute a full battle and record results.

    Returns dict with 'display_text' for the chat message.
    """
    # Get partner info
    c_partner = await bq.get_partner(challenger_id)
    d_partner = await bq.get_partner(defender_id)
    c_partner_inst = c_partner["instance_id"] if c_partner else None
    d_partner_inst = d_partner["instance_id"] if d_partner else None

    # Prepare combatants
    c_combatants = [
        _prepare_combatant(p, is_partner=(p["pokemon_instance_id"] == c_partner_inst))
        for p in challenger_team
    ]
    d_combatants = [
        _prepare_combatant(p, is_partner=(p["pokemon_instance_id"] == d_partner_inst))
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

    # Calculate BP (skip for yacha — yacha handles its own payout)
    if skip_bp:
        bp_won = 0
        bp_lose = 0
    else:
        bp_won = _calculate_bp(winner_team_size, loser_team_size, result["perfect_win"], new_streak)
        bp_lose = config.BP_LOSE

    # Update stats
    await bq.update_battle_stats_win(winner_id, bp_won)
    await bq.update_battle_stats_lose(loser_id, bp_lose)

    # Mission: battle win
    asyncio.create_task(_notify_battle_mission(winner_id, bot))

    # Record battle
    await bq.record_battle(
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
    )

    # Get display names — challenger always LEFT, defender always RIGHT
    from database import queries
    c_user = await queries.get_user(challenger_id)
    d_user = await queries.get_user(defender_id)
    c_name = c_user["display_name"] if c_user else "???"
    d_name = d_user["display_name"] if d_user else "???"
    c_te = c_user.get("title_emoji", "") if c_user else ""
    d_te = d_user.get("title_emoji", "") if d_user else ""
    c_title_str = f"{icon_emoji(c_te)} " if c_te and c_te in config.ICON_CUSTOM_EMOJI else ""
    d_title_str = f"{icon_emoji(d_te)} " if d_te and d_te in config.ICON_CUSTOM_EMOJI else ""

    winner_name = c_name if result["winner"] == "challenger" else d_name

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
        "new_streak": new_streak,
        "perfect_win": result["perfect_win"],
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
