"""NPC 봇 팀 자동 구성 로직.

시즌 룰의 cost_limit에 맞춰 봇 팀을 구성한다.
- gym 타입: preferred_types에서 같은 타입 포켓몬 6마리
- npc 타입: 랜덤 rarity 조합
"""

import random
import logging

import config
from database.connection import get_db

logger = logging.getLogger(__name__)

# cost per rarity
COST = config.RANKED_COST


async def _get_pokemon_by_type(ptype: str) -> dict[str, list[dict]]:
    """DB에서 특정 타입의 포켓몬을 rarity별로 그룹화하여 반환."""
    pool = await get_db()
    rows = await pool.fetch(
        "SELECT id, name_ko, rarity, pokemon_type FROM pokemon_master "
        "WHERE pokemon_type = $1 ORDER BY id", ptype)
    result: dict[str, list[dict]] = {
        "common": [], "rare": [], "epic": [],
        "legendary": [], "ultra_legendary": [],
    }
    for r in rows:
        result[r["rarity"]].append(dict(r))
    return result


async def _get_all_pokemon() -> dict[str, list[dict]]:
    """DB에서 전체 포켓몬을 rarity별로 그룹화하여 반환."""
    pool = await get_db()
    rows = await pool.fetch(
        "SELECT id, name_ko, rarity, pokemon_type FROM pokemon_master ORDER BY id")
    result: dict[str, list[dict]] = {
        "common": [], "rare": [], "epic": [],
        "legendary": [], "ultra_legendary": [],
    }
    for r in rows:
        result[r["rarity"]].append(dict(r))
    return result


def _build_team_composition(cost_limit: int, tier: str) -> list[str]:
    """코스트 제한 내에서 6마리 rarity 조합을 생성.

    Returns list of 6 rarity strings.
    """
    weights = config.BOT_RARITY_WEIGHTS.get(tier, config.BOT_RARITY_WEIGHTS["bronze"])
    rarity_order = ["ultra_legendary", "legendary", "epic", "rare", "common"]
    rarity_costs = {r: COST[r] for r in rarity_order}

    team: list[str] = []
    remaining = cost_limit

    for _ in range(6):
        # 가능한 rarity만 필터 (남은 슬롯의 최소 코스트 고려)
        slots_left = 6 - len(team) - 1  # 이번 슬롯 제외 남은 슬롯
        min_remaining = slots_left * 1  # 남은 슬롯은 최소 common(1)

        candidates = []
        for r in rarity_order:
            cost = rarity_costs[r]
            if cost <= remaining - min_remaining and weights.get(r, 0) > 0:
                candidates.append((r, weights[r]))

        if not candidates:
            # common만 가능
            team.append("common")
            remaining -= 1
            continue

        # 가중 랜덤 선택
        total_w = sum(w for _, w in candidates)
        roll = random.random() * total_w
        cumulative = 0
        chosen = "common"
        for r, w in candidates:
            cumulative += w
            if roll <= cumulative:
                chosen = r
                break

        team.append(chosen)
        remaining -= rarity_costs[chosen]

    return team


async def build_bot_team(
    bot_def: tuple,
    cost_limit: int,
    season_rule: str | None = None,
) -> list[dict]:
    """봇 정의에서 6마리 팀을 구성.

    Returns list of dicts: [{pokemon_id, is_shiny, iv_hp, ...}, ...]
    """
    user_id, name, tier, mmr, npc_type, preferred_types, is_shiny = bot_def
    iv_min, iv_max = config.BOT_IV_RANGES.get(tier, (10, 20))

    # rarity 조합 생성
    composition = _build_team_composition(cost_limit, tier)

    # 포켓몬 풀 가져오기
    if npc_type == "gym" and preferred_types:
        pool_by_rarity = await _get_pokemon_by_type(preferred_types[0])
    else:
        pool_by_rarity = await _get_all_pokemon()

    # 시즌 룰에 따른 rarity 필터
    rule_info = config.WEEKLY_RULES.get(season_rule or "", {})
    banned_rarities = set()
    if season_rule == "no_ultra":
        banned_rarities.add("ultra_legendary")
    elif season_rule == "no_legendary":
        banned_rarities.update(["legendary", "ultra_legendary"])
    elif season_rule == "epic_below":
        banned_rarities.update(["legendary", "ultra_legendary"])

    # 구성에서 금지 rarity 대체
    adjusted = []
    for r in composition:
        if r in banned_rarities:
            # epic 이하로 대체
            if "epic" not in banned_rarities:
                adjusted.append("epic")
            elif "rare" not in banned_rarities:
                adjusted.append("rare")
            else:
                adjusted.append("common")
        else:
            adjusted.append(r)

    # 코스트 재검증 — 초과 시 하향
    total_cost = sum(COST[r] for r in adjusted)
    while total_cost > cost_limit:
        # 가장 비싼 것부터 한 단계 내림
        for i, r in enumerate(adjusted):
            if r == "ultra_legendary":
                adjusted[i] = "legendary"
                total_cost -= 1
                break
            elif r == "legendary":
                adjusted[i] = "epic"
                total_cost -= 1
                break
            elif r == "epic":
                adjusted[i] = "rare"
                total_cost -= 2
                break
            elif r == "rare":
                adjusted[i] = "common"
                total_cost -= 1
                break

    # 실제 포켓몬 선택 (중복 방지)
    team = []
    used_ids = set()

    for rarity in adjusted:
        candidates = [p for p in pool_by_rarity.get(rarity, [])
                       if p["id"] not in used_ids]

        if not candidates:
            # 해당 rarity+타입에 포켓몬이 없으면 전체 풀에서 검색
            fallback = await _get_all_pokemon()
            candidates = [p for p in fallback.get(rarity, [])
                           if p["id"] not in used_ids]

        if not candidates:
            # 정말 없으면 common으로 대체
            fallback = await _get_all_pokemon()
            candidates = [p for p in fallback.get("common", [])
                           if p["id"] not in used_ids]

        if candidates:
            chosen = random.choice(candidates)
            used_ids.add(chosen["id"])

            # IV 생성
            ivs = {
                "iv_hp": random.randint(iv_min, iv_max),
                "iv_atk": random.randint(iv_min, iv_max),
                "iv_def": random.randint(iv_min, iv_max),
                "iv_spa": random.randint(iv_min, iv_max),
                "iv_spdef": random.randint(iv_min, iv_max),
                "iv_spd": random.randint(iv_min, iv_max),
            }

            team.append({
                "pokemon_id": chosen["id"],
                "is_shiny": 1 if is_shiny else 0,
                **ivs,
            })

    return team


async def seed_bots_for_season(season_id: str, weekly_rule: str):
    """현재 시즌에 대해 모든 봇의 팀을 (재)구성한다."""
    pool = await get_db()

    # cost_limit 결정
    rule_info = config.WEEKLY_RULES.get(weekly_rule, {})
    cost_limit = rule_info.get("cost_limit", config.RANKED_COST_LIMIT)

    # 티어별 시작 RP
    tier_rp = {
        "bronze": 50, "silver": 250, "gold": 450,
        "platinum": 650, "diamond": 850, "master": 1050,
    }

    for bot_def in config.RANKED_BOTS:
        user_id, display_name, tier, mmr, npc_type, preferred_types, is_shiny_flag = bot_def

        try:
            # 1. 유저 생성/업데이트
            await pool.execute(
                """INSERT INTO users (user_id, display_name, username, is_bot, battle_points)
                   VALUES ($1, $2, $3, TRUE, 0)
                   ON CONFLICT (user_id) DO UPDATE
                   SET display_name = $2, is_bot = TRUE""",
                user_id, display_name, f"BOT_{user_id}")

            # 2. 팀 구성
            team = await build_bot_team(bot_def, cost_limit, weekly_rule)
            if len(team) < 6:
                logger.warning(f"봇 {display_name}: 팀 구성 실패 ({len(team)}/6)")
                continue

            # 3. 기존 봇 포켓몬/팀 삭제
            await pool.execute(
                "DELETE FROM battle_teams WHERE user_id = $1", user_id)
            await pool.execute(
                "DELETE FROM user_pokemon WHERE user_id = $1", user_id)

            # 4. 포켓몬 인스턴스 생성 + 팀 등록
            instance_ids = []
            for p in team:
                inst_id = await pool.fetchval(
                    """INSERT INTO user_pokemon
                       (user_id, pokemon_id, is_shiny, iv_hp, iv_atk, iv_def,
                        iv_spa, iv_spdef, iv_spd, friendship, is_active)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 7, 1)
                       RETURNING id""",
                    user_id, p["pokemon_id"], p["is_shiny"],
                    p["iv_hp"], p["iv_atk"], p["iv_def"],
                    p["iv_spa"], p["iv_spdef"], p["iv_spd"])
                instance_ids.append(inst_id)

            for slot, inst_id in enumerate(instance_ids, 1):
                await pool.execute(
                    """INSERT INTO battle_teams (user_id, slot, pokemon_instance_id, team_number)
                       VALUES ($1, $2, $3, 1)""",
                    user_id, slot, inst_id)

            # 5. 시즌 레코드
            base_rp = tier_rp.get(tier, 50)
            rp = base_rp + random.randint(0, 100)
            await pool.execute(
                """INSERT INTO season_records
                   (user_id, season_id, rp, tier, placement_done, placement_games,
                    ranked_wins, ranked_losses, defense_losses)
                   VALUES ($1, $2, $3, $4, TRUE, 0, 0, 0, 0)
                   ON CONFLICT (user_id, season_id) DO UPDATE
                   SET rp = $3, tier = $4, defense_losses = 0""",
                user_id, season_id, rp, tier)

            # 6. MMR
            await pool.execute(
                """INSERT INTO user_mmr (user_id, mmr, peak_mmr, games_played)
                   VALUES ($1, $2, $2, 0)
                   ON CONFLICT (user_id) DO UPDATE
                   SET mmr = $2, peak_mmr = $2""",
                user_id, mmr)

            # 코스트 검증 (안전장치)
            actual_cost = 0
            for p in team:
                pm = await pool.fetchrow(
                    "SELECT rarity FROM pokemon_master WHERE id = $1",
                    p["pokemon_id"])
                if pm:
                    actual_cost += COST.get(pm["rarity"], 1)
            if actual_cost > cost_limit:
                logger.error(
                    f"⚠️ 봇 {display_name} 코스트 초과! "
                    f"{actual_cost}/{cost_limit} — 팀 삭제")
                await pool.execute(
                    "DELETE FROM battle_teams WHERE user_id = $1", user_id)
                await pool.execute(
                    "DELETE FROM user_pokemon WHERE user_id = $1", user_id)
                continue

            logger.info(
                f"✅ 봇 시딩: {display_name} ({tier}) "
                f"cost={actual_cost}/{cost_limit} rp={rp}")

        except Exception as e:
            logger.error(f"봇 시딩 실패 {display_name}: {e}")
