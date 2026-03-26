"""Weekly Boss raid service."""

import random
import logging
from datetime import datetime, timedelta, timezone

import config
from database import boss_queries as bq
from database import battle_queries
from database import queries
from services.battle_service import _prepare_combatant, _resolve_battle
from utils.battle_calc import get_normalized_base_stats, calc_battle_stats
from models.pokemon_base_stats import POKEMON_BASE_STATS

logger = logging.getLogger(__name__)

_KST = timezone(timedelta(hours=9))


def current_week_key() -> str:
    """ISO week key like 'W2026-13'."""
    now = datetime.now(_KST)
    return f"W{now.isocalendar()[0]}-{now.isocalendar()[1]:02d}"


def today_kst() -> str:
    """KST date string like '2026-03-26'."""
    return datetime.now(_KST).strftime("%Y-%m-%d")


# ── Boss creation ─────────────────────────────────────────

async def create_weekly_boss(week_key: str | None = None) -> dict | None:
    """Create a new weekly boss. Avoids repeating last week's boss."""
    wk = week_key or current_week_key()

    # Check if already exists
    existing = await bq.get_boss(wk)
    if existing:
        return existing

    # Avoid repeat
    prev = await bq.get_current_boss()
    prev_pid = prev["pokemon_id"] if prev else None

    pool = [b for b in config.BOSS_POKEMON_POOL if b[0] != prev_pid]
    if not pool:
        pool = list(config.BOSS_POKEMON_POOL)

    pid, name, types = random.choice(pool)
    boss = await bq.create_boss(wk, pid, name, types, config.BOSS_MAX_HP)
    if boss:
        logger.info(f"Weekly boss created: {name} (week={wk}, HP={config.BOSS_MAX_HP:,})")
    return boss


async def get_current_boss() -> dict | None:
    """Get this week's boss. Creates one if missing."""
    wk = current_week_key()
    boss = await bq.get_boss(wk)
    if not boss:
        boss = await create_weekly_boss(wk)
    return boss


# ── Boss battle ───────────────────────────────────────────

def _make_boss_combatant(boss: dict) -> dict:
    """Create a combatant dict for the boss (for _resolve_battle)."""
    pid = boss["pokemon_id"]
    base = get_normalized_base_stats(pid)
    mult = config.BOSS_STAT_MULT

    if base:
        stats = {
            "hp": boss["max_hp"],  # 고정 HP 사용
            "atk": int(base["base_atk"] * mult["atk"]),
            "def": int(base["base_def"] * mult["def"]),
            "spa": int(base["base_spa"] * mult["spa"]),
            "spdef": int(base["base_spdef"] * mult["spdef"]),
            "spd": int(base["base_spd"] * mult["spd"]),
        }
    else:
        # Fallback
        stats = {
            "hp": boss["max_hp"],
            "atk": int(200 * mult["atk"]),
            "def": int(150 * mult["def"]),
            "spa": int(200 * mult["spa"]),
            "spdef": int(150 * mult["spdef"]),
            "spd": int(120 * mult["spd"]),
        }

    from models.pokemon_skills import POKEMON_SKILLS
    raw_skill = POKEMON_SKILLS.get(pid, ("몸통박치기", 1.2))
    skills = raw_skill if isinstance(raw_skill, list) else [raw_skill]

    bs = POKEMON_BASE_STATS.get(pid)
    dual_types = bs[-1] if bs else boss["boss_types"]

    return {
        "name": boss["pokemon_name"],
        "emoji": "🐉",
        "type": dual_types,
        "rarity": "ultra_legendary",
        "is_shiny": False,
        "stats": stats,
        "current_hp": stats["hp"],
        "instance_id": None,
        "skills": skills,
        "skill_name": skills[0][0],
        "skill_power": skills[0][1],
        "pokemon_id": pid,
        "tb": "🐉",
        "iv_grade": "X",
        "iv_total": 186,
    }


async def attack_boss(user_id: int) -> dict:
    """Execute boss attack. Returns result dict.

    Returns: {
        "success": bool,
        "error": str | None,
        "damage": int,
        "boss": dict,
        "battle_result": dict,
        "milestones": dict,
        "defeated_now": bool,
    }
    """
    boss = await get_current_boss()
    if not boss:
        return {"success": False, "error": "현재 활성 보스가 없습니다."}

    wk = boss["week_key"]
    today = today_kst()

    # Already attacked?
    if await bq.has_attacked_today(wk, user_id, today):
        dmg = await bq.get_today_damage(wk, user_id, today)
        return {"success": False, "error": "already_attacked", "today_damage": dmg}

    # Boss already dead?
    if boss["defeated"]:
        return {"success": False, "error": "보스가 이미 처치되었습니다!"}

    # Get boss team (fallback to battle team)
    team_data = await bq.get_boss_team(user_id)
    if not team_data:
        return {"success": False, "error": "팀이 없습니다! 보스 화면에서 '보스팀 설정'으로 팀을 구성하세요."}

    # Prepare combatants
    player_team = [_prepare_combatant(p) for p in team_data]
    boss_combatant = _make_boss_combatant(boss)

    # Run battle (player = challenger, boss = defender)
    result = _resolve_battle(player_team, [boss_combatant])

    # Calculate damage dealt to boss
    boss_max = boss_combatant["stats"]["hp"]
    boss_remaining = boss_combatant["current_hp"]
    # _resolve_battle modifies current_hp in-place
    damage = max(0, boss_max - boss_remaining)

    # But boss actual HP is much lower than max (shared HP)
    # We cap damage to remaining boss HP
    actual_damage = min(damage, boss["current_hp"])

    # Record attack
    recorded = await bq.record_attack(wk, user_id, actual_damage, today)
    if not recorded:
        return {"success": False, "error": "already_attacked", "today_damage": 0}

    # Deduct boss HP
    updated_boss = await bq.deal_damage(wk, actual_damage)
    defeated_now = updated_boss and updated_boss["defeated"] and not boss["defeated"]

    # Calculate milestone rewards
    milestones = get_milestone_rewards(actual_damage)

    # Grant milestone rewards
    if milestones:
        bp = milestones.get("bp", 0)
        if bp:
            await battle_queries.add_bp(user_id, bp, "boss_daily")
        frags = milestones.get("fragments", 0)
        if frags:
            from database import camp_queries
            # Give random field fragments
            await _give_random_fragments(user_id, frags)
        iv_reroll = milestones.get("iv_reroll_one", 0)
        if iv_reroll:
            from database import item_queries
            await item_queries.add_user_item(user_id, "iv_reroll_one", iv_reroll)

    return {
        "success": True,
        "error": None,
        "damage": actual_damage,
        "boss": updated_boss or boss,
        "battle_result": result,
        "milestones": milestones,
        "defeated_now": defeated_now,
    }


def get_milestone_rewards(damage: int) -> dict:
    """Get the highest milestone reward for given damage."""
    best = {}
    for threshold in sorted(config.BOSS_DAILY_MILESTONES.keys()):
        if damage >= threshold:
            best = config.BOSS_DAILY_MILESTONES[threshold]
    return best


async def _give_random_fragments(user_id: int, count: int):
    """Give random field fragments."""
    try:
        from database import camp_queries
        fields = list(config.CAMP_FIELDS.keys())
        field = random.choice(fields)
        await camp_queries.add_fragments(user_id, field, count)
    except Exception as e:
        logger.error(f"Failed to give fragments to {user_id}: {e}")


# ── Weekly rewards ────────────────────────────────────────

async def distribute_weekly_rewards(prev_week_key: str) -> int:
    """Distribute weekly ranking rewards. Returns number of rewarded users."""
    ranking = await bq.get_weekly_ranking(prev_week_key, limit=30)
    if not ranking:
        return 0

    rewarded = 0
    for i, entry in enumerate(ranking):
        rank = i + 1
        uid = entry["user_id"]
        rewards = _get_rank_rewards(rank)
        if not rewards:
            continue

        bp = rewards.get("bp", 0)
        if bp:
            await battle_queries.add_bp(uid, bp, "boss_weekly")

        mb = rewards.get("masterball", 0)
        if mb:
            await queries.add_master_ball(uid, mb)

        trt = rewards.get("time_reduce_ticket", 0)
        if trt:
            from database import item_queries
            await item_queries.add_user_item(uid, "time_reduce_ticket", trt)

        rewarded += 1

    # Defeat bonus
    boss = await bq.get_boss(prev_week_key)
    if boss and boss["defeated"]:
        participants = await bq.get_participant_ids(prev_week_key)
        bonus = config.BOSS_DEFEAT_BONUS
        for uid in participants:
            bp = bonus.get("bp", 0)
            if bp:
                await battle_queries.add_bp(uid, bp, "boss_defeat_bonus")
            mb = bonus.get("masterball", 0)
            if mb:
                await queries.add_master_ball(uid, mb)
        logger.info(f"Boss defeat bonus given to {len(participants)} participants")

    logger.info(f"Boss weekly rewards distributed: {rewarded} users (week={prev_week_key})")
    return rewarded


def _get_rank_rewards(rank: int) -> dict:
    """Get rewards for a specific rank."""
    for key, rewards in config.BOSS_WEEKLY_REWARDS.items():
        if isinstance(key, int) and key == rank:
            return rewards
        elif isinstance(key, tuple) and key[0] <= rank <= key[1]:
            return rewards
    return {}


def get_weakness_types(boss_types: list[str]) -> list[str]:
    """Get types that are super effective against boss."""
    weaknesses = set()
    for atk_type, targets in config.TYPE_ADVANTAGE.items():
        for bt in boss_types:
            if bt in targets:
                weaknesses.add(atk_type)
    return sorted(weaknesses)
