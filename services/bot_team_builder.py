"""NPC 봇 팀 자동 구성 로직.

시즌 룰의 cost_limit에 맞춰 봇 팀을 구성한다.
- gym 타입: preferred_types에서 같은 타입 포켓몬 우선, 부족하면 전체 풀 보충
- npc 타입: 전체 풀에서 강한 포켓몬 조합
- 베이스스탯 높은 순으로 선택 (랜덤 아님)
"""

import random
import logging

import config
from database.connection import get_db

logger = logging.getLogger(__name__)

COST = config.RANKED_COST

# 베이스스탯 총합 캐시
_BASE_STAT_CACHE: dict[int, int] = {}


async def _load_base_stats():
    """pokemon_base_stats에서 베이스스탯 총합을 로드."""
    global _BASE_STAT_CACHE
    if _BASE_STAT_CACHE:
        return
    try:
        from models.pokemon_base_stats import POKEMON_BASE_STATS
        for pid, stats in POKEMON_BASE_STATS.items():
            # stats = [hp, atk, def, spa, spdef, spd, [type1, type2]]
            _BASE_STAT_CACHE[pid] = sum(stats[:6])
    except Exception as e:
        logger.warning(f"베이스스탯 로드 실패: {e}")


def _get_bst(pokemon_id: int) -> int:
    """포켓몬의 베이스스탯 총합 반환."""
    return _BASE_STAT_CACHE.get(pokemon_id, 300)


async def _get_pokemon_pool(ptype: str | None = None) -> list[dict]:
    """DB에서 포켓몬 목록을 가져온다. ptype이 있으면 해당 타입만."""
    pool = await get_db()
    if ptype:
        rows = await pool.fetch(
            "SELECT id, name_ko, rarity, pokemon_type FROM pokemon_master "
            "WHERE pokemon_type = $1 ORDER BY id", ptype)
    else:
        rows = await pool.fetch(
            "SELECT id, name_ko, rarity, pokemon_type FROM pokemon_master ORDER BY id")
    return [dict(r) for r in rows]


def _best_team_for_cost(
    pokemon_pool: list[dict],
    cost_limit: int,
    team_size: int = 6,
    banned_rarities: set | None = None,
    used_ids: set | None = None,
) -> list[dict]:
    """코스트 제한 내에서 베이스스탯 총합이 높은 6마리를 선택.

    그리디 알고리즘: 코스트 대비 BST가 높은 순으로 채움.
    """
    if banned_rarities is None:
        banned_rarities = set()
    if used_ids is None:
        used_ids = set()

    # 사용 가능한 포켓몬 필터
    available = [
        p for p in pokemon_pool
        if p["id"] not in used_ids and p["rarity"] not in banned_rarities
    ]

    # BST/cost 효율 기준 정렬 (높은 순)
    def sort_key(p):
        bst = _get_bst(p["id"])
        cost = COST.get(p["rarity"], 1)
        return bst  # 순수 BST 높은 순

    available.sort(key=sort_key, reverse=True)

    team = []
    remaining = cost_limit

    for p in available:
        if len(team) >= team_size:
            break

        cost = COST.get(p["rarity"], 1)
        slots_left = team_size - len(team) - 1  # 이번 제외 남은 슬롯
        min_needed = slots_left * 1  # 남은 슬롯은 최소 common(1)

        if cost <= remaining - min_needed:
            team.append(p)
            remaining -= cost

    return team


async def build_bot_team(
    bot_def: tuple,
    cost_limit: int,
    season_rule: str | None = None,
) -> list[dict]:
    """봇 정의에서 6마리 팀을 구성.

    Returns list of dicts: [{pokemon_id, is_shiny, iv_hp, ...}, ...]
    """
    await _load_base_stats()

    user_id, name, tier, mmr, npc_type, preferred_types, is_shiny_flag = bot_def
    iv_min, iv_max = config.BOT_IV_RANGES.get(tier, (10, 20))

    # 시즌 룰에 따른 rarity 금지
    banned_rarities: set[str] = set()
    if season_rule == "no_ultra":
        banned_rarities.add("ultra_legendary")
    elif season_rule == "no_legendary":
        banned_rarities.update(["legendary", "ultra_legendary"])
    elif season_rule == "epic_below":
        banned_rarities.update(["legendary", "ultra_legendary"])

    used_ids: set[int] = set()

    if npc_type == "gym" and preferred_types:
        # gym 봇: 메인 타입에서 최강 팀 구성
        type_pool = await _get_pokemon_pool(preferred_types[0])
        team_picks = _best_team_for_cost(
            type_pool, cost_limit, 6, banned_rarities, used_ids)

        # 부족하면 전체 풀에서 보충
        if len(team_picks) < 6:
            used_ids.update(p["id"] for p in team_picks)
            remaining_cost = cost_limit - sum(
                COST.get(p["rarity"], 1) for p in team_picks)
            all_pool = await _get_pokemon_pool()
            extra = _best_team_for_cost(
                all_pool, remaining_cost, 6 - len(team_picks),
                banned_rarities, used_ids)
            team_picks.extend(extra)
    else:
        # npc 봇: 전체 풀에서 최강 팀
        all_pool = await _get_pokemon_pool()
        # 약간의 랜덤성을 위해 상위 50명 중에서 셔플 후 선택
        available = [
            p for p in all_pool
            if p["rarity"] not in banned_rarities
        ]
        available.sort(key=lambda p: _get_bst(p["id"]), reverse=True)

        # 티어별 풀 범위 (마스터는 상위, 브론즈는 중하위)
        pool_ranges = {
            "master": (0, 80), "diamond": (20, 120),
            "platinum": (40, 160), "gold": (60, 200),
            "silver": (100, 300), "bronze": (150, 400),
        }
        lo, hi = pool_ranges.get(tier, (100, 300))
        hi = min(hi, len(available))
        lo = min(lo, hi)
        subset = available[lo:hi]
        random.shuffle(subset)

        team_picks = _best_team_for_cost(
            subset, cost_limit, 6, banned_rarities, used_ids)

    # 팀 데이터 생성
    team = []
    for p in team_picks:
        ivs = {
            "iv_hp": random.randint(iv_min, iv_max),
            "iv_atk": random.randint(iv_min, iv_max),
            "iv_def": random.randint(iv_min, iv_max),
            "iv_spa": random.randint(iv_min, iv_max),
            "iv_spdef": random.randint(iv_min, iv_max),
            "iv_spd": random.randint(iv_min, iv_max),
        }
        team.append({
            "pokemon_id": p["id"],
            "is_shiny": 1 if is_shiny_flag else 0,
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
