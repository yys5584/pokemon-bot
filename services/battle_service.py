"""Battle engine: automatic PvP battle resolution."""

import random
import logging

import config
from database import battle_queries as bq
from utils.battle_calc import calc_battle_stats, get_type_multiplier

logger = logging.getLogger(__name__)


def _prepare_combatant(pokemon: dict, is_partner: bool = False) -> dict:
    """Prepare a single pokemon for battle with computed stats."""
    stats = calc_battle_stats(
        pokemon["rarity"],
        pokemon["stat_type"],
        pokemon["friendship"],
    )

    # Partner bonus: ATK +5%
    if is_partner:
        stats["atk"] = int(stats["atk"] * 1.05)

    return {
        "name": pokemon["name_ko"],
        "emoji": pokemon["emoji"],
        "type": pokemon["pokemon_type"],
        "rarity": pokemon["rarity"],
        "stats": stats,
        "current_hp": stats["hp"],
        "instance_id": pokemon.get("pokemon_instance_id") or pokemon.get("instance_id"),
    }


def _calc_damage(attacker: dict, defender: dict) -> tuple[int, str]:
    """Calculate damage from attacker to defender.
    Returns (damage, effect_text).
    """
    # Base damage
    base = max(1, attacker["stats"]["atk"] - defender["stats"]["def"] * 0.4)

    # Type advantage
    type_mult = get_type_multiplier(attacker["type"], defender["type"])

    # Critical hit (10%)
    crit = 1.5 if random.random() < config.BATTLE_CRIT_RATE else 1.0

    # Random variance (±10%)
    variance = random.uniform(0.9, 1.1)

    damage = int(base * type_mult * crit * variance)
    damage = max(1, damage)  # At least 1 damage

    # Build effect text
    effects = []
    if type_mult > 1.0:
        type_emoji = config.TYPE_EMOJI.get(attacker["type"], "")
        effects.append(f"{type_emoji}효과적!")
    elif type_mult < 1.0:
        effects.append("별로...")
    if crit > 1.0:
        effects.append("크리티컬!")

    effect_text = f" ({' '.join(effects)})" if effects else ""
    return damage, effect_text


def _resolve_battle(challenger_team: list[dict], defender_team: list[dict]) -> dict:
    """Run the automatic battle between two teams.

    Each team is a list of _prepare_combatant() dicts.
    Returns battle result dict.
    """
    log_lines = []
    c_idx = 0
    d_idx = 0
    round_num = 0

    c_mon = challenger_team[c_idx]
    d_mon = defender_team[d_idx]

    log_lines.append(
        f"{c_mon['emoji']}{c_mon['name']} vs {d_mon['emoji']}{d_mon['name']}"
    )

    while c_idx < len(challenger_team) and d_idx < len(defender_team):
        round_num += 1
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
        dmg1, eff1 = _calc_damage(first, second)
        second["current_hp"] -= dmg1

        # Second attacks back if alive
        dmg2, eff2 = 0, ""
        if second["current_hp"] > 0:
            dmg2, eff2 = _calc_damage(second, first)
            first["current_hp"] -= dmg2

        # Build round log
        f_label = f"{first['emoji']}{first['name']}"
        s_label = f"{second['emoji']}{second['name']}"
        log_lines.append(
            f" → {f_label} {dmg1}{eff1} | {s_label} {dmg2}{eff2}"
        )

        # KO check - challenger's pokemon
        if c_mon["current_hp"] <= 0:
            dead_name = f"{c_mon['emoji']}{c_mon['name']}"
            c_idx += 1
            if c_idx < len(challenger_team):
                c_mon = challenger_team[c_idx]
                log_lines.append(
                    f" 💀 {dead_name} 쓰러짐! → {c_mon['emoji']}{c_mon['name']} 등장!"
                )
            else:
                log_lines.append(f" 💀 {dead_name} 쓰러짐!")

        # KO check - defender's pokemon
        if d_mon["current_hp"] <= 0:
            dead_name = f"{d_mon['emoji']}{d_mon['name']}"
            d_idx += 1
            if d_idx < len(defender_team):
                d_mon = defender_team[d_idx]
                log_lines.append(
                    f" 💀 {dead_name} 쓰러짐! → {d_mon['emoji']}{d_mon['name']} 등장!"
                )
                if c_idx < len(challenger_team):
                    log_lines.append(
                        f"\n{challenger_team[c_idx]['emoji']}{challenger_team[c_idx]['name']}"
                        f" vs {d_mon['emoji']}{d_mon['name']}"
                    )
            else:
                log_lines.append(f" 💀 {dead_name} 쓰러짐!")

    # Determine winner
    if round_num > config.BATTLE_MAX_ROUNDS:
        # Timeout: compare remaining HP
        c_hp = sum(m["current_hp"] for m in challenger_team[c_idx:] if m["current_hp"] > 0)
        d_hp = sum(m["current_hp"] for m in defender_team[d_idx:] if m["current_hp"] > 0)
        winner = "challenger" if c_hp >= d_hp else "defender"
        log_lines.append(f"\n⏰ {config.BATTLE_MAX_ROUNDS}라운드 초과! HP합산 판정")
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

    # Calculate BP
    bp_won = _calculate_bp(winner_team_size, loser_team_size, result["perfect_win"], new_streak)

    # Update stats
    await bq.update_battle_stats_win(winner_id, bp_won)
    await bq.update_battle_stats_lose(loser_id, config.BP_LOSE)

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

    # Get display names
    from database import queries
    winner_user = await queries.get_user(winner_id)
    loser_user = await queries.get_user(loser_id)
    winner_name = winner_user["display_name"] if winner_user else "???"
    loser_name = loser_user["display_name"] if loser_user else "???"

    w_title = ""
    if winner_user and winner_user.get("title"):
        w_title = f"「{winner_user.get('title_emoji', '')}{winner_user['title']}」"
    l_title = ""
    if loser_user and loser_user.get("title"):
        l_title = f"「{loser_user.get('title_emoji', '')}{loser_user['title']}」"

    # Get updated stats for display
    final_stats = await bq.get_battle_stats(winner_id)

    # Build display text
    lines = [
        "⚔️ 배틀 결과!",
        "━━━━━━━━━━━━━━━",
        f"{w_title}{winner_name}  VS  {l_title}{loser_name}",
        f"({len(challenger_team)}마리)          ({len(defender_team)}마리)",
        "━━━━━━━━━━━━━━━",
        "",
        result["log"],
        "",
        "━━━━━━━━━━━━━━━",
        f"🏆 {winner_name} 승리! (남은 포켓몬: {winner_remaining}마리)",
        "",
        f"💰 +{bp_won} BP",
    ]

    if new_streak >= 3:
        lines.append(f"🔥 {new_streak}연승!")

    if result["perfect_win"]:
        lines.append("✨ 완벽한 승리!")

    w_total = final_stats["battle_wins"] + final_stats["battle_losses"]
    lines.append(
        f"📊 {winner_name} 전적: {final_stats['battle_wins']}승 "
        f"{final_stats['battle_losses']}패"
    )

    # Check and unlock battle titles
    await _check_battle_titles(winner_id, final_stats, result["perfect_win"])
    await _check_battle_titles(loser_id, await bq.get_battle_stats(loser_id), False)

    return {
        "display_text": "\n".join(lines),
        "winner_id": winner_id,
        "loser_id": loser_id,
        "bp_earned": bp_won,
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
