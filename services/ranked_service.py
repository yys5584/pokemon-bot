"""Ranked (season) battle service — 시즌 관리, RP 계산, 규칙 검증."""

import logging
import math
import random
import datetime as dt

import config
from database import ranked_queries as rq
from database.connection import get_db

logger = logging.getLogger(__name__)


# ─── Season Management ───────────────────────────────────

def current_season_id() -> str:
    """현재 KST 기준 시즌 ID. 2주 시즌: '2026-S05' (연간 시즌 번호)."""
    now = config.get_kst_now()
    iso = now.isocalendar()
    # 2주 시즌: ISO week를 2로 나눠 시즌 번호 계산 (1-indexed)
    duration = config.SEASON_DURATION_WEEKS
    season_num = (iso[1] - 1) // duration + 1
    return f"{iso[0]}-S{season_num:02d}"


def season_date_range(season_id: str) -> tuple[dt.datetime, dt.datetime]:
    """시즌 ID로 시작/종료 datetime 계산."""
    year_str, s_part = season_id.split("-S")
    year = int(year_str)
    season_num = int(s_part)
    duration = config.SEASON_DURATION_WEEKS
    # 시즌 시작 ISO week
    start_week = (season_num - 1) * duration + 1
    start = dt.datetime.strptime(f"{year}-W{start_week}-1", "%G-W%V-%u")
    start = start.replace(hour=0, minute=0, second=0, tzinfo=config.KST)
    end = start + dt.timedelta(weeks=duration) - dt.timedelta(seconds=1)
    return start, end


async def ensure_current_season() -> dict:
    """현재 시즌이 없으면 생성. 캐시 불필요 (호출 빈도 낮음)."""
    season = await rq.get_current_season()
    if season:
        return season

    sid = current_season_id()
    starts, ends = season_date_range(sid)

    # 주간 법칙 선택 (최근 2주와 겹치지 않음)
    recent = await rq.get_recent_rules(2)
    rule = pick_random_excluding(list(config.WEEKLY_RULES.keys()), recent)

    # 기본 아레나 (TG포켓 아케이드) — admin이 등록한 후보 중 1~2곳 추가
    # 기본 아레나 chat_id는 환경변수 또는 DB에서 관리
    arena_ids = await _select_arenas()

    season = await rq.get_or_create_season(sid, rule, starts, ends, arena_ids)
    return season


async def _select_arenas() -> list[int]:
    """아레나 후보에서 1~2곳 랜덤 선정 — DM 자동매칭 전환으로 빈 배열 반환."""
    return []


def pick_random_excluding(pool: list[str], exclude: list[str]) -> str:
    """pool에서 exclude 항목을 제외하고 랜덤 선택."""
    available = [x for x in pool if x not in exclude]
    if not available:
        available = pool  # 모두 제외되면 전체에서 선택
    return random.choice(available)


# ─── DM Auto-Matching ────────────────────────────────────

DEFENSE_SHIELD_LIMIT = 5  # 연속 방어 패배 5회 → 보호

async def find_ranked_opponent(user_id: int, season_id: str) -> int | None:
    """비슷한 티어의 상대를 DB에서 찾아 user_id 반환. 없으면 None."""
    from database import battle_queries as bq

    # 유저의 시즌 기록 조회
    rec = await rq.get_season_record(user_id, season_id)
    if rec:
        current_tier = rec["tier"]
    else:
        current_tier = "bronze"

    # 인접 티어 산출 (현재 ± 1)
    tier_idx = config.get_tier_index(current_tier)
    # challenger 제외한 실질 티어 (0~5)
    max_idx = len(config.RANKED_TIERS) - 2  # challenger 제외
    adjacent = set()
    for delta in (-1, 0, 1):
        idx = max(0, min(max_idx, tier_idx + delta))
        adjacent.add(config.RANKED_TIERS[idx][0])
    # challenger도 master 근처이므로 포함
    if "master" in adjacent:
        adjacent.add("challenger")

    tier_keys = list(adjacent)

    # 최근 3경기 상대 제외
    recent_opps = await rq.get_recent_opponents(user_id, season_id, limit=3)
    exclude_ids = [user_id] + recent_opps

    # 1차: season_records에서 인접 티어 + 쉴드 미적용 유저 검색
    candidates = await rq.find_matchable_users(
        season_id, tier_keys, exclude_ids,
        defense_shield_limit=DEFENSE_SHIELD_LIMIT, limit=10,
    )

    # 후보 중 유효한 배틀팀 보유자 찾기
    for c in candidates:
        team = await bq.get_battle_team(c["user_id"])
        if team and len(team) >= 1:
            return c["user_id"]

    # 2차 폴백 (프리시즌 등 season_records가 비어있을 때)
    fallback_ids = await rq.find_any_matchable_users(exclude_ids, limit=10)
    for fid in fallback_ids:
        team = await bq.get_battle_team(fid)
        if team and len(team) >= 1:
            return fid

    return None


# ─── RP Calculation ──────────────────────────────────────

def calculate_rp_change(winner_tier: str, loser_tier: str,
                         winner_streak: int) -> tuple[int, int]:
    """(winner_gain, loser_loss) 계산."""
    w_idx = config.get_tier_index(winner_tier)
    l_idx = config.get_tier_index(loser_tier)

    # 승자 RP
    tier_diff = min(config.RP_TIER_DIFF_MAX,
                    max(-config.RP_TIER_DIFF_MAX,
                        (l_idx - w_idx) * config.RP_TIER_DIFF_PER))
    streak_bonus = min(config.RP_STREAK_MAX, winner_streak * config.RP_STREAK_PER)
    rp_gain = config.RP_WIN_BASE + tier_diff + streak_bonus

    # 패자 RP
    if l_idx <= 1:  # bronze/silver 보호
        rp_loss = config.RP_LOSE_PROTECTED
    else:
        rp_loss = config.RP_LOSE_BASE

    return max(1, rp_gain), max(5, rp_loss)


async def get_pair_count_today(user_a: int, user_b: int, season_id: str) -> int:
    """오늘 두 유저 간 대전 횟수 조회."""
    pool = await get_db()
    today = config.get_kst_now().date()
    row = await pool.fetchrow(
        """SELECT COUNT(*) AS cnt FROM ranked_battle_log rbl
           JOIN battle_records br ON rbl.battle_record_id = br.id
           WHERE rbl.season_id = $1
             AND br.battle_date::date = $2
             AND (
               (br.winner_id = $3 AND br.loser_id = $4)
               OR (br.winner_id = $4 AND br.loser_id = $3)
             )""",
        season_id, today, user_a, user_b)
    return row["cnt"] if row else 0


async def process_ranked_result(winner_id: int, loser_id: int,
                                  season_id: str, battle_record_id: int) -> dict:
    """랭크전 결과 처리 → RP 변동 + DB 업데이트. dict 반환."""
    # 시즌 기록 조회/생성
    w_rec = await rq.get_season_record(winner_id, season_id)
    l_rec = await rq.get_season_record(loser_id, season_id)

    if not w_rec:
        await rq.upsert_season_record(winner_id, season_id, 0, "bronze")
        w_rec = await rq.get_season_record(winner_id, season_id)
    if not l_rec:
        await rq.upsert_season_record(loser_id, season_id, 0, "bronze")
        l_rec = await rq.get_season_record(loser_id, season_id)

    w_rp_before = w_rec["rp"]
    l_rp_before = l_rec["rp"]
    w_tier_before = w_rec["tier"]
    l_tier_before = l_rec["tier"]
    w_streak = w_rec["ranked_streak"]
    w_total = w_rec["ranked_wins"] + w_rec["ranked_losses"]
    l_total = l_rec["ranked_wins"] + l_rec["ranked_losses"]

    rp_gain, rp_loss = calculate_rp_change(w_tier_before, l_tier_before, w_streak)

    # ── 윈트레이딩 방지: 같은 상대 반복 대전 RP 감소 ──
    pair_count = await get_pair_count_today(winner_id, loser_id, season_id)
    decay_list = config.RANKED_SAME_PAIR_RP_DECAY
    if pair_count < len(decay_list):
        decay = decay_list[pair_count]
    else:
        decay = 0.0  # 5회 초과: RP 0
    rp_gain = max(1, int(rp_gain * decay)) if decay > 0 else 0

    # ── 티어 갭 페널티: 상위 티어가 하위 티어를 이기면 RP 최소화 ──
    w_idx = config.get_tier_index(w_tier_before)
    l_idx = config.get_tier_index(l_tier_before)
    if w_idx - l_idx >= config.RANKED_TIER_GAP_PENALTY:
        rp_gain = min(rp_gain, config.RANKED_TIER_GAP_RP_MIN)

    # ── 신규 보호: 첫 N전 RP 손실 50% 감소 ──
    if l_total < config.RANKED_NEWBIE_PROTECTION:
        rp_loss = max(5, rp_loss // 2)

    w_rp_after = w_rp_before + rp_gain
    l_rp_after = max(0, l_rp_before - rp_loss)

    w_tier_after_key, w_tier_after_name, _ = config.get_tier(w_rp_after)
    l_tier_after_key, l_tier_after_name, _ = config.get_tier(l_rp_after)

    # 피크 업데이트
    w_peak_rp = max(w_rec["peak_rp"], w_rp_after)
    w_peak_tier = w_tier_after_key if w_rp_after >= w_rec["peak_rp"] else w_rec["peak_tier"]

    # 원자적 업데이트
    await rq.update_rp_win(winner_id, season_id, rp_gain, w_tier_after_key,
                            w_peak_rp, w_peak_tier)
    await rq.update_rp_lose(loser_id, season_id, rp_loss, l_tier_after_key)

    # 배틀 로그 기록
    await rq.log_ranked_battle(
        battle_record_id, season_id,
        w_rp_before, w_rp_after, l_rp_before, l_rp_after,
        w_tier_before, w_tier_after_key, l_tier_before, l_tier_after_key)

    # ── 챌린저 티어 갱신 ──
    await refresh_challenger_tier(season_id)

    return {
        "winner_rp_before": w_rp_before,
        "winner_rp_after": w_rp_after,
        "winner_rp_gain": rp_gain,
        "winner_tier_before": w_tier_before,
        "winner_tier_after": w_tier_after_key,
        "winner_tier_name": w_tier_after_name,
        "loser_rp_before": l_rp_before,
        "loser_rp_after": l_rp_after,
        "loser_rp_loss": rp_loss,
        "loser_tier_before": l_tier_before,
        "loser_tier_after": l_tier_after_key,
        "loser_tier_name": l_tier_after_name,
        "pair_decay": decay,
    }


# ─── Rule Validation ─────────────────────────────────────

async def get_team_with_types(user_id: int) -> list[dict]:
    """배틀팀을 타입+등급+진화정보 포함하여 조회 (규칙 검증용, 1 query)."""
    pool = await get_db()
    row = await pool.fetchrow("SELECT active_team FROM users WHERE user_id = $1", user_id)
    team_num = row["active_team"] if row else 1
    rows = await pool.fetch(
        """SELECT bt.slot, pm.rarity, pm.pokemon_type, pm.evolves_to, pm.name_ko
           FROM battle_teams bt
           JOIN user_pokemon up ON bt.pokemon_instance_id = up.id
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE bt.user_id = $1 AND bt.team_number = $2 AND up.is_active = 1
           ORDER BY bt.slot""",
        user_id, team_num)
    return [dict(r) for r in rows]


def _has_type(pokemon: dict, type_name: str) -> bool:
    """포켓몬이 특정 타입을 가지고 있는지 확인. pokemon_type='fire,flying' 형식."""
    return type_name in (pokemon.get("pokemon_type") or "").split(",")


def validate_weekly_rule(team: list[dict], rule_key: str) -> tuple[bool, str]:
    """시즌 법칙 검증. (통과 여부, 에러 메시지)"""
    rule = config.WEEKLY_RULES.get(rule_key)
    if not rule:
        return True, ""

    if rule_key == "open":
        return True, ""

    # --- 등급 제한 ---
    elif rule_key == "no_ultra":
        if any(p["rarity"] == "ultra_legendary" for p in team):
            return False, rule["error"]
    elif rule_key == "no_legendary":
        if any(p["rarity"] in ("legendary", "ultra_legendary") for p in team):
            return False, rule["error"]
    elif rule_key == "epic_below":
        if any(p["rarity"] in ("legendary", "ultra_legendary") for p in team):
            return False, rule["error"]
    elif rule_key == "no_final_evo":
        if any(p.get("evolves_to") is None for p in team):
            return False, rule["error"]

    # --- 타입 금지 ---
    elif rule_key == "no_normal":
        if any(_has_type(p, "normal") for p in team):
            return False, rule["error"]
    elif rule_key == "no_dragon":
        if any(_has_type(p, "dragon") for p in team):
            return False, rule["error"]
    elif rule_key == "no_psychic":
        if any(_has_type(p, "psychic") for p in team):
            return False, rule["error"]

    # --- 에픽 제한 ---
    elif rule_key == "epic_max_2":
        epic_count = sum(1 for p in team if p["rarity"] == "epic")
        if epic_count > 2:
            return False, rule["error"]
    elif rule_key == "epic_water_ice":
        for p in team:
            if p["rarity"] == "epic":
                if not (_has_type(p, "water") or _has_type(p, "ice")):
                    return False, rule["error"]
    elif rule_key == "epic_fire_fight":
        for p in team:
            if p["rarity"] == "epic":
                if not (_has_type(p, "fire") or _has_type(p, "fighting")):
                    return False, rule["error"]

    return True, ""


async def validate_team_for_ranked(user_id: int, season: dict) -> tuple[bool, str]:
    """유저 팀이 현재 시즌 법칙을 만족하는지 검증."""
    team = await get_team_with_types(user_id)
    if not team:
        return False, "배틀팀이 없습니다! 팀을 먼저 등록하세요."

    ok, err = validate_weekly_rule(team, season["weekly_rule"])
    if not ok:
        return False, f"🔒 시즌 법칙 위반: {err}"

    return True, ""


# ─── Season Reset & Rewards ──────────────────────────────

async def process_season_rewards(season_id: str) -> list[dict]:
    """시즌 보상 분배. 반환: 보상 받은 유저 리스트."""
    season = await rq.get_season_by_id(season_id)
    if not season or season["rewards_distributed"]:
        return []

    records = await rq.get_all_season_records(season_id)
    rewarded = []

    from database import queries  # 순환 import 방지

    for rec in records:
        peak = rec["peak_tier"]
        reward = config.RANKED_REWARDS.get(peak)
        if not reward:
            continue

        uid = rec["user_id"]
        if reward.get("masterball", 0) > 0:
            await queries.add_master_ball(uid, reward["masterball"])
        if reward.get("bp", 0) > 0:
            from database.battle_queries import add_bp
            await add_bp(uid, reward["bp"])

        rewarded.append({
            "user_id": uid,
            "tier": peak,
            "masterball": reward.get("masterball", 0),
            "bp": reward.get("bp", 0),
        })

    await rq.mark_rewards_distributed(season_id)
    return rewarded


async def soft_reset_new_season(prev_season_id: str) -> dict:
    """소프트 리셋 + 새 시즌 생성."""
    prev_records = await rq.get_all_season_records(prev_season_id)

    new_sid = current_season_id()
    starts, ends = season_date_range(new_sid)

    recent = await rq.get_recent_rules(2)
    rule = pick_random_excluding(list(config.WEEKLY_RULES.keys()), recent)

    new_season = await rq.get_or_create_season(new_sid, rule, starts, ends, [])

    # 소프트 리셋: 이전 RP의 40%로 새 시즌 기록 생성
    for rec in prev_records:
        new_rp = math.floor(rec["rp"] * config.RP_SOFT_RESET_MULT)
        new_tier_key, _, _ = config.get_tier(new_rp)
        await rq.upsert_season_record(
            rec["user_id"], new_sid, new_rp, new_tier_key,
            peak_rp=new_rp, peak_tier=new_tier_key)

    return new_season


# ─── Challenger Tier ─────────────────────────────────────

async def refresh_challenger_tier(season_id: str):
    """마스터 티어 Top N명에게 챌린저 부여, 나머지는 마스터로 되돌림."""
    top_n = config.CHALLENGER_TOP_N
    top_users = await rq.get_ranked_ranking(season_id, limit=top_n)

    # 마스터 이상인 유저만 챌린저 후보
    challenger_ids = set()
    for r in top_users:
        if r["rp"] >= 2000:  # 마스터 최소 RP
            challenger_ids.add(r["user_id"])

    # 현재 챌린저인 유저 중 탈락자 → 마스터로 되돌림
    current_challengers = await rq.get_users_by_tier(season_id, "challenger")
    for uid in current_challengers:
        if uid not in challenger_ids:
            rec = await rq.get_season_record(uid, season_id)
            if rec:
                tier_key, _, _ = config.get_tier(rec["rp"])
                await rq.update_tier(uid, season_id, tier_key)

    # 새 챌린저 부여
    for uid in challenger_ids:
        await rq.update_tier(uid, season_id, "challenger")


async def get_season_champion(season_id: str) -> int | None:
    """시즌 1위 유저 ID 반환."""
    top = await rq.get_ranked_ranking(season_id, limit=1)
    if top and top[0]["rp"] >= 2000:
        return top[0]["user_id"]
    return None


# ─── Helper: Tier Display ────────────────────────────────

def tier_display(tier_key: str) -> str:
    """'silver' → '🥈실버'"""
    for t in config.RANKED_TIERS:
        if t[0] == tier_key:
            return f"{t[2]}{t[1]}"
    return tier_key
