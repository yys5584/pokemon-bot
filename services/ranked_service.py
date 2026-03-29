"""Ranked (season) battle service — LoL 스타일 MMR/배치/디비전/디케이."""

import logging
import math
import random
import datetime as dt

import config
from database import ranked_queries as rq
from database.connection import get_db

logger = logging.getLogger(__name__)


# ─── Season Management ───────────────────────────────────

def _season_start_for_date(d: dt.datetime) -> dt.datetime:
    """주어진 날짜가 속한 시즌의 시작 목요일 00:00 KST를 반환."""
    weekday = d.weekday()  # 0=월 ... 3=목
    start_wd = config.SEASON_START_WEEKDAY  # 3=목
    # 이번 주 목요일 이전이면 지난 주 목요일이 시즌 시작
    days_since = (weekday - start_wd) % 7
    start = (d - dt.timedelta(days=days_since)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return start


def _get_epoch() -> dt.datetime:
    """시즌 1 기준점 (SEASON_EPOCH config)."""
    return dt.datetime.strptime(config.SEASON_EPOCH, "%Y-%m-%d").replace(
        hour=0, minute=0, second=0, tzinfo=config.KST)


def current_season_id() -> str:
    """현재 KST 기준 시즌 ID. 매주 목요일 전환.

    네이밍: S01 → S01.5 → S02 → S02.5 → S03 ...
    week_num 0=S01, 1=S01.5, 2=S02, 3=S02.5, ...
    """
    now = config.get_kst_now()
    start = _season_start_for_date(now)
    epoch = _get_epoch()
    week_num = int((start - epoch).days / 7)
    major = week_num // 2 + 1
    is_half = week_num % 2 == 1
    suffix = f"{major:02d}.5" if is_half else f"{major:02d}"
    return f"{start.year}-S{suffix}"


def season_date_range(season_id: str) -> tuple[dt.datetime, dt.datetime]:
    """시즌 ID로 시작/종료 datetime 계산.

    S01 → week_num 0, S01.5 → week_num 1, S02 → week_num 2, ...
    """
    year_str, s_part = season_id.split("-S")
    if "." in s_part:
        major = int(s_part.split(".")[0])
        week_num = (major - 1) * 2 + 1  # .5 시즌
    else:
        major = int(s_part)
        week_num = (major - 1) * 2  # 정규 시즌
    epoch = _get_epoch()
    start = epoch + dt.timedelta(weeks=week_num)
    end = start + dt.timedelta(weeks=1) - dt.timedelta(seconds=1)
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
    rule = pick_random_excluding(config.SEASON_RULE_POOL, recent)

    arena_ids = await _select_arenas()
    season = await rq.get_or_create_season(sid, rule, starts, ends, arena_ids)

    # 새 시즌 생성 시 NPC 봇 팀 시딩
    try:
        from services.bot_team_builder import seed_bots_for_season
        await seed_bots_for_season(sid, rule)
        logger.info(f"시즌 {sid} 봇 시딩 완료 (룰: {rule})")
    except Exception as e:
        logger.error(f"시즌 {sid} 봇 시딩 실패: {e}")

    return season


async def _select_arenas() -> list[int]:
    """아레나 후보에서 1~2곳 랜덤 선정 — DM 자동매칭 전환으로 빈 배열 반환."""
    return []


def pick_random_excluding(pool: list[str], exclude: list[str]) -> str:
    """pool에서 exclude 항목을 제외하고 랜덤 선택."""
    available = [x for x in pool if x not in exclude]
    if not available:
        available = pool
    return random.choice(available)


# ─── Elo (MMR) Engine ─────────────────────────────────────

def elo_expected(my_mmr: int, opp_mmr: int) -> float:
    """Elo 기대 승률."""
    return 1.0 / (1.0 + 10 ** ((opp_mmr - my_mmr) / 400))


def elo_update(my_mmr: int, opp_mmr: int, won: bool, k: int) -> int:
    """Elo MMR 업데이트. 최소 0."""
    expected = elo_expected(my_mmr, opp_mmr)
    return max(0, int(round(my_mmr + k * ((1.0 if won else 0.0) - expected))))


def get_k_factor(is_placement: bool) -> int:
    """K-factor: 배치전은 큰 값, 일반은 작은 값."""
    return config.MMR_K_PLACEMENT if is_placement else config.MMR_K_NORMAL


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


# ─── Placement (배치전) ──────────────────────────────────

def mmr_to_starting_rp(mmr: int) -> int:
    """배치 완료 시 MMR→시작 RP 매핑. 해당 디비전 중간값 배정."""
    thresholds = [
        (1500, 850),   # 다이아 II 50 RP
        (1350, 650),   # 플래티넘 II 50 RP
        (1200, 450),   # 골드 II 50 RP
        (1050, 250),   # 실버 II 50 RP
        (900,  50),    # 브론즈 II 50 RP
    ]
    for min_mmr, start_rp in thresholds:
        if mmr >= min_mmr:
            return start_rp
    return 50  # 최소 브론즈 II 50 RP


async def assign_placement_tier(user_id: int, season_id: str) -> dict:
    """배치 완료 → MMR→티어 배정. 반환: {tier, division, rp, display}"""
    mmr_rec = await rq.get_user_mmr(user_id)
    user_mmr = mmr_rec["mmr"]

    start_rp = mmr_to_starting_rp(user_mmr)
    tier_key, _, _ = config.get_tier(start_rp)
    div_info = config.get_division_info(start_rp)

    await rq.set_placement_done(
        user_id, season_id, start_rp, tier_key,
        peak_rp=start_rp, peak_tier=tier_key)

    display = config.tier_division_display(
        div_info[0], div_info[1], div_info[2],
        placement_done=True, total_rp=start_rp)

    return {
        "tier_key": tier_key,
        "tier_display": display,
        "rp": start_rp,
        "division": div_info[1],
        "display_rp": div_info[2],
        "mmr": user_mmr,
    }


# ─── DM Auto-Matching (MMR 기반) ─────────────────────────

DEFENSE_SHIELD_LIMIT = 5  # 연속 방어 패배 5회 → 보호

async def find_ranked_opponent(user_id: int, season_id: str) -> int | None:
    """MMR 기반 매칭. 점진적 범위 확장."""
    from database import battle_queries as bq

    # MMR 조회
    mmr_rec = await rq.get_user_mmr(user_id)
    user_mmr = mmr_rec["mmr"]

    # 최근 3경기 상대 제외
    recent_opps = await rq.get_recent_opponents(user_id, season_id, limit=3)
    exclude_ids = [user_id] + recent_opps

    # 점진적 MMR 범위 확장
    for mmr_range in config.MMR_MATCH_RANGES:  # [200, 300, 400]
        candidates = await rq.find_matchable_users_by_mmr(
            season_id, user_mmr, mmr_range, exclude_ids,
            defense_shield_limit=DEFENSE_SHIELD_LIMIT, limit=10)
        for c in candidates:
            team = await bq.get_battle_team(c["user_id"])
            if team and len(team) >= config.RANKED_TEAM_SIZE:
                return c["user_id"]

    # 폴백: 기존 티어 기반 (프리시즌/유저 부족 시)
    rec = await rq.get_season_record(user_id, season_id)
    if rec:
        current_tier = rec["tier"]
        if current_tier == "unranked":
            current_tier = "bronze"
    else:
        current_tier = "bronze"

    tier_idx = config.get_tier_index(current_tier)
    max_idx = len(config.RANKED_TIERS) - 2
    adjacent = set()
    for delta in (-1, 0, 1):
        idx = max(0, min(max_idx, tier_idx + delta))
        adjacent.add(config.RANKED_TIERS[idx][0])
    if "master" in adjacent:
        adjacent.add("challenger")
    # unranked 제거
    adjacent.discard("unranked")
    tier_keys = list(adjacent)

    candidates = await rq.find_matchable_users(
        season_id, tier_keys, exclude_ids,
        defense_shield_limit=DEFENSE_SHIELD_LIMIT, limit=10)
    for c in candidates:
        team = await bq.get_battle_team(c["user_id"])
        if team and len(team) >= 1:
            return c["user_id"]

    return None


# ─── RP Calculation (MMR 영향) ───────────────────────────

def calculate_rp_change(winner_tier: str, loser_tier: str,
                         winner_streak: int) -> tuple[int, int]:
    """(winner_gain, loser_loss) 기본 계산. 하위호환."""
    w_idx = config.get_tier_index(winner_tier)
    l_idx = config.get_tier_index(loser_tier)

    tier_diff = min(config.RP_TIER_DIFF_MAX,
                    max(-config.RP_TIER_DIFF_MAX,
                        (l_idx - w_idx) * config.RP_TIER_DIFF_PER))
    streak_bonus = min(config.RP_STREAK_MAX, winner_streak * config.RP_STREAK_PER)
    rp_gain = config.RP_WIN_BASE + tier_diff + streak_bonus

    if l_idx <= 2:  # bronze/silver 보호 (인덱스 1~2)
        rp_loss = config.RP_LOSE_PROTECTED
    else:
        rp_loss = config.RP_LOSE_BASE

    return max(1, rp_gain), max(5, rp_loss)


def calculate_rp_change_with_mmr(winner_tier: str, loser_tier: str,
                                   winner_streak: int,
                                   winner_mmr: int, loser_mmr: int) -> tuple[int, int]:
    """MMR 영향을 반영한 RP 계산."""
    base_gain, base_loss = calculate_rp_change(winner_tier, loser_tier, winner_streak)

    # 승자: 내 MMR이 내 티어 기대값보다 높으면 RP 더 받음 (승급 가속)
    expected_w = config.MMR_TIER_EXPECTED.get(winner_tier, 1200)
    mmr_diff_w = winner_mmr - expected_w
    gain_mult = 1.0 + _clamp(mmr_diff_w / 400, -0.3, 0.5)
    rp_gain = max(1, int(base_gain * gain_mult))

    # 패자: MMR이 티어 기대값보다 낮으면 RP 더 많이 잃음 (강등 가속)
    expected_l = config.MMR_TIER_EXPECTED.get(loser_tier, 1200)
    mmr_diff_l = loser_mmr - expected_l
    loss_mult = 1.0 + _clamp(-mmr_diff_l / 400, -0.3, 0.3)
    rp_loss = max(5, int(base_loss * loss_mult))

    return rp_gain, rp_loss


async def get_pair_count_today(user_a: int, user_b: int, season_id: str) -> int:
    """오늘 두 유저 간 대전 횟수 조회."""
    pool = await get_db()
    today = config.get_kst_now().date()
    row = await pool.fetchrow(
        """SELECT COUNT(*) AS cnt FROM ranked_battle_log rbl
           JOIN battle_records br ON rbl.battle_record_id = br.id
           WHERE rbl.season_id = $1
             AND br.created_at::date = $2
             AND (
               (br.winner_id = $3 AND br.loser_id = $4)
               OR (br.winner_id = $4 AND br.loser_id = $3)
             )""",
        season_id, today, user_a, user_b)
    return row["cnt"] if row else 0


# ─── Promotion Shield (승급 보호) ─────────────────────────

async def check_and_set_promo_shield(user_id: int, season_id: str,
                                       old_rp: int, new_rp: int):
    """승급 발생 시 보호 설정 (12시간, 랭전 진입 시 해제)."""
    old_div = config.get_division_info(old_rp)
    new_div = config.get_division_info(new_rp)

    # 디비전이 바뀌었으면 승급
    if (new_div[0], new_div[1]) != (old_div[0], old_div[1]):
        shield_until = config.get_kst_now() + dt.timedelta(hours=config.PROMO_SHIELD_HOURS)
        await rq.set_promo_shield(user_id, season_id, shield_until)
        return True
    return False


async def apply_rp_loss_with_shield(user_id: int, season_id: str,
                                      rp_loss: int, rec: dict) -> tuple[int, bool]:
    """RP 손실 적용 + 승급 보호 체크.
    Returns: (actual_rp_loss, shield_protected)"""
    old_rp = rec["rp"]
    new_rp = max(0, old_rp - rp_loss)

    old_div = config.get_division_info(old_rp)
    new_div = config.get_division_info(new_rp)

    shield_protected = False

    # 강등 발생? (디비전이 바뀌었는지 체크)
    if (new_div[0], new_div[1]) != (old_div[0], old_div[1]):
        shield = rec.get("promo_shield_until")
        now = config.get_kst_now()
        if shield and shield.tzinfo is None:
            # naive datetime인 경우 KST로 변환
            import zoneinfo
            shield = shield.replace(tzinfo=zoneinfo.ZoneInfo("Asia/Seoul"))
        if shield and shield > now:
            # 보호 중: 현재 디비전 최소 RP로 클램프
            div_min_rp = config.get_division_base_rp(old_div[0], old_div[1])
            new_rp = max(new_rp, div_min_rp)
            shield_protected = True

    actual_loss = old_rp - new_rp
    return actual_loss, shield_protected


# ─── Process Ranked Result (핵심) ──────────────────────────

async def process_ranked_result(winner_id: int, loser_id: int,
                                  season_id: str, battle_record_id: int) -> dict:
    """랭크전 결과 처리 → MMR + RP 변동 + 배치 + 승급보호. dict 반환."""
    # 1. 시즌 기록 조회/생성
    w_rec = await rq.get_season_record(winner_id, season_id)
    l_rec = await rq.get_season_record(loser_id, season_id)

    if not w_rec:
        await rq.upsert_season_record(winner_id, season_id, 0, "unranked",
                                       placement_done=False, placement_games=0)
        w_rec = await rq.get_season_record(winner_id, season_id)
    if not l_rec:
        await rq.upsert_season_record(loser_id, season_id, 0, "unranked",
                                       placement_done=False, placement_games=0)
        l_rec = await rq.get_season_record(loser_id, season_id)

    # 2. MMR 레코드 조회
    w_mmr_rec = await rq.get_user_mmr(winner_id)
    l_mmr_rec = await rq.get_user_mmr(loser_id)
    w_mmr = w_mmr_rec["mmr"]
    l_mmr = l_mmr_rec["mmr"]

    # 3. 배치 여부
    w_is_placement = not w_rec.get("placement_done", False)
    l_is_placement = not l_rec.get("placement_done", False)

    # 4. MMR 업데이트 (봇이면 스킵)
    w_is_bot = winner_id in config.RANKED_BOT_IDS
    l_is_bot = loser_id in config.RANKED_BOT_IDS
    k_w = get_k_factor(w_is_placement)
    k_l = get_k_factor(l_is_placement)
    new_w_mmr = elo_update(w_mmr, l_mmr, True, k_w)
    new_l_mmr = elo_update(l_mmr, w_mmr, False, k_l)
    if not w_is_bot:
        await rq.update_user_mmr(winner_id, new_w_mmr)
    if not l_is_bot:
        await rq.update_user_mmr(loser_id, new_l_mmr)

    # 5. 배치 처리
    w_placement_result = None
    l_placement_result = None

    if w_is_placement:
        new_count = await rq.increment_placement_games(winner_id, season_id)
        # 승/패 카운트도 업데이트
        await rq.update_rp_win(winner_id, season_id, 0, "unranked", 0, "unranked")
        if new_count >= config.PLACEMENT_GAMES_REQUIRED:
            w_placement_result = await assign_placement_tier(winner_id, season_id)

    if l_is_placement:
        new_count = await rq.increment_placement_games(loser_id, season_id)
        await rq.update_rp_lose(loser_id, season_id, 0, "unranked")
        if new_count >= config.PLACEMENT_GAMES_REQUIRED:
            l_placement_result = await assign_placement_tier(loser_id, season_id)

    # 6. RP 처리 (배치 완료 유저만)
    w_rp_before = w_rec["rp"]
    l_rp_before = l_rec["rp"]
    w_tier_before = w_rec["tier"]
    l_tier_before = l_rec["tier"]
    rp_gain = 0
    rp_loss = 0
    w_promoted = False
    l_demoted = False
    l_shield_protected = False
    pair_decay = 1.0

    if not w_is_placement:
        w_streak = w_rec["ranked_streak"]
        rp_gain, rp_loss_base = calculate_rp_change_with_mmr(
            w_tier_before, l_tier_before if not l_is_placement else "bronze",
            w_streak, w_mmr, l_mmr)

        # 윈트레이딩 방지
        pair_count = await get_pair_count_today(winner_id, loser_id, season_id)
        decay_list = config.RANKED_SAME_PAIR_RP_DECAY
        if pair_count < len(decay_list):
            pair_decay = decay_list[pair_count]
        else:
            pair_decay = decay_list[-1]  # 최소 배율 유지 (0.15)
        rp_gain = max(1, int(rp_gain * pair_decay)) if pair_decay > 0 else 0

        # MMR 갭 페널티 (기존 티어갭→MMR갭 교체)
        mmr_gap = abs(w_mmr - l_mmr)
        if mmr_gap >= 400 and w_mmr > l_mmr:
            rp_gain = min(rp_gain, config.RANKED_TIER_GAP_RP_MIN)

        w_rp_after = w_rp_before + rp_gain
        w_tier_after_key, _, _ = config.get_tier(w_rp_after)

        # 봇이면 RP/승급 업데이트 스킵
        if w_is_bot:
            w_rp_after = w_rp_before
            w_tier_after_key = w_tier_before
        else:
            # 승급 보호 설정
            w_promoted = await check_and_set_promo_shield(
                winner_id, season_id, w_rp_before, w_rp_after)

            # 피크 업데이트
            w_peak_rp = max(w_rec["peak_rp"], w_rp_after)
            w_peak_tier = w_tier_after_key if w_rp_after >= w_rec["peak_rp"] else w_rec["peak_tier"]

            await rq.update_rp_win(winner_id, season_id, rp_gain, w_tier_after_key,
                                    w_peak_rp, w_peak_tier)
    else:
        w_rp_after = w_rp_before
        w_tier_after_key = w_tier_before

    if not l_is_placement:
        _, rp_loss_calc = calculate_rp_change_with_mmr(
            w_tier_before if not w_is_placement else "bronze",
            l_tier_before, 0, w_mmr, l_mmr)

        # 신규 보호
        l_total = l_rec["ranked_wins"] + l_rec["ranked_losses"]
        if l_total < config.RANKED_NEWBIE_PROTECTION:
            rp_loss_calc = max(5, rp_loss_calc // 2)

        # 봇이면 RP 손실 스킵
        if l_is_bot:
            l_rp_after = l_rp_before
            l_tier_after_key = l_tier_before
            rp_loss = 0
        else:
            # 승급 보호 적용
            # 최신 rec 다시 조회 (placement_done 상태 반영)
            l_rec_fresh = await rq.get_season_record(loser_id, season_id)
            rp_loss, l_shield_protected = await apply_rp_loss_with_shield(
                loser_id, season_id, rp_loss_calc, l_rec_fresh or l_rec)

            l_rp_after = max(0, l_rp_before - rp_loss)
            l_tier_after_key, _, _ = config.get_tier(l_rp_after)

            # 강등 체크
            old_div = config.get_division_info(l_rp_before)
            new_div = config.get_division_info(l_rp_after)
            l_demoted = (new_div[0], new_div[1]) != (old_div[0], old_div[1])

            await rq.update_rp_lose(loser_id, season_id, rp_loss, l_tier_after_key)
    else:
        l_rp_after = l_rp_before
        l_tier_after_key = l_tier_before
        rp_loss = 0

    # 7. last_ranked_at 갱신 (디케이 방지)
    await rq.update_last_ranked(winner_id, season_id)
    await rq.update_last_ranked(loser_id, season_id)

    # 8. 챌린저 티어 갱신
    await refresh_challenger_tier(season_id)

    # 9. 배틀 로그 (MMR 포함)
    await rq.log_ranked_battle(
        battle_record_id, season_id,
        w_rp_before, w_rp_after, l_rp_before, l_rp_after,
        w_tier_before, w_tier_after_key, l_tier_before, l_tier_after_key,
        w_mmr, new_w_mmr, l_mmr, new_l_mmr)

    # 10. 최종 레코드 조회 (배치 진행 상태 반환용)
    w_rec_final = await rq.get_season_record(winner_id, season_id) or {}
    l_rec_final = await rq.get_season_record(loser_id, season_id) or {}

    # 11. 반환
    return {
        "winner_rp_before": w_rp_before,
        "winner_rp_after": w_rp_after,
        "winner_rp_gain": rp_gain,
        "winner_tier_before": w_tier_before,
        "winner_tier_after": w_tier_after_key,
        "winner_tier_name": config.get_tier(w_rp_after)[1],
        "loser_rp_before": l_rp_before,
        "loser_rp_after": l_rp_after,
        "loser_rp_loss": rp_loss,
        "loser_tier_before": l_tier_before,
        "loser_tier_after": l_tier_after_key,
        "loser_tier_name": config.get_tier(l_rp_after)[1],
        "pair_decay": pair_decay,
        # MMR 정보
        "w_mmr_before": w_mmr,
        "w_mmr_after": new_w_mmr,
        "l_mmr_before": l_mmr,
        "l_mmr_after": new_l_mmr,
        # 배치 정보
        "w_is_placement": w_is_placement,
        "l_is_placement": l_is_placement,
        "w_placement_result": w_placement_result,
        "l_placement_result": l_placement_result,
        "w_placement_games": w_rec_final.get("placement_games", 0) if w_is_placement else 0,
        "l_placement_games": l_rec_final.get("placement_games", 0) if l_is_placement else 0,
        "w_wins_after": w_rec_final.get("ranked_wins", 0),
        "w_losses_after": w_rec_final.get("ranked_losses", 0),
        "l_wins_after": l_rec_final.get("ranked_wins", 0),
        "l_losses_after": l_rec_final.get("ranked_losses", 0),
        # 승급/강등 정보
        "w_promoted": w_promoted,
        "l_demoted": l_demoted,
        "l_shield_protected": l_shield_protected,
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
        if any(p["rarity"] in ("legendary", "ultra_legendary") for p in team):
            return False, "이번 시즌은 에픽 이하만 편성 가능합니다!"
        for p in team:
            if p["rarity"] == "epic":
                if not (_has_type(p, "water") or _has_type(p, "ice")):
                    return False, rule["error"]
    elif rule_key == "epic_fire_fight":
        if any(p["rarity"] in ("legendary", "ultra_legendary") for p in team):
            return False, "이번 시즌은 에픽 이하만 편성 가능합니다!"
        for p in team:
            if p["rarity"] == "epic":
                if not (_has_type(p, "fire") or _has_type(p, "fighting")):
                    return False, rule["error"]

    # --- 코스트 제한 ---
    if rule.get("cost_limit"):
        total_cost = sum(config.RANKED_COST.get(p.get("rarity", ""), 0) for p in team)
        limit = rule["cost_limit"]
        if total_cost > limit:
            return False, f"이번 시즌은 팀 코스트 {limit} 이하만 가능합니다! (현재: {total_cost})"

    return True, ""


async def validate_team_for_ranked(user_id: int, season: dict) -> tuple[bool, str]:
    """유저 팀이 현재 시즌 법칙을 만족하는지 검증."""
    team = await get_team_with_types(user_id)
    if not team:
        return False, "배틀팀이 없습니다! 팀을 먼저 등록하세요."

    # 6마리 필수
    if len(team) < config.RANKED_TEAM_SIZE:
        return False, f"팀이 {len(team)}마리뿐입니다! {config.RANKED_TEAM_SIZE}마리를 모두 채워야 배틀할 수 있습니다."

    # COST 제한 (시즌 룰에 cost_limit이 있으면 그쪽에서 검증)
    rule_info = config.WEEKLY_RULES.get(season.get("weekly_rule", ""), {})
    if not rule_info.get("cost_limit"):
        total_cost = sum(config.RANKED_COST.get(p.get("rarity", ""), 0) for p in team)
        if total_cost > config.RANKED_COST_LIMIT:
            return False, f"팀 코스트 초과! ({total_cost}/{config.RANKED_COST_LIMIT}) 팀을 다시 편성해주세요."

    # 초전설 제한
    ultra_count = sum(1 for p in team if p.get("rarity") == "ultra_legendary")
    if ultra_count > config.RANKED_ULTRA_MAX:
        return False, f"초전설은 팀당 {config.RANKED_ULTRA_MAX}마리까지만 편성 가능합니다."

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

    # RP 순으로 정렬 → 순위 결정 (1~3위 추가 보상용)
    sorted_records = sorted(records, key=lambda r: r["rp"], reverse=True)
    rank_map = {}  # user_id → rank
    for i, rec in enumerate(sorted_records):
        rank_map[rec["user_id"]] = i + 1

    for rec in records:
        peak = rec["peak_tier"]
        reward = config.RANKED_REWARDS.get(peak)
        if not reward:
            continue

        uid = rec["user_id"]

        # 마스터볼
        if reward.get("masterball", 0) > 0:
            await queries.add_master_ball(uid, reward["masterball"])

        # BP
        if reward.get("bp", 0) > 0:
            from database.battle_queries import add_bp
            await add_bp(uid, reward["bp"], "ranked_reward")

        # IV+3 스톤
        iv_cnt = reward.get("iv_stone_3", 0)
        if iv_cnt > 0:
            try:
                from database import item_queries
                await item_queries.add_user_item(uid, "iv_stone_3", iv_cnt)
            except Exception as e:
                logger.error(f"Failed to give IV+3 stone to {uid}: {e}")

        # 이로치 포켓몬 (티어 보상: 마스터→에픽)
        shiny_rarity = reward.get("shiny")
        shiny_name = ""
        if shiny_rarity:
            try:
                pid, pname = _random_shiny_pokemon(shiny_rarity)
                await queries.give_pokemon_to_user(uid, pid, 0, is_shiny=True)
                shiny_name = pname
            except Exception as e:
                logger.error(f"Failed to give shiny {shiny_rarity} to {uid}: {e}")

        # 순위별 추가 보상 (1~3위 이로치)
        rank = rank_map.get(uid, 999)
        top_reward = config.RANKED_TOP_REWARDS.get(rank)
        top_shiny_name = ""
        if top_reward and top_reward.get("shiny"):
            try:
                pid, pname = _random_shiny_pokemon(top_reward["shiny"])
                await queries.give_pokemon_to_user(uid, pid, 0, is_shiny=True)
                top_shiny_name = pname
            except Exception as e:
                logger.error(f"Failed to give rank {rank} shiny to {uid}: {e}")

        rewarded.append({
            "user_id": uid,
            "tier": peak,
            "rank": rank,
            "masterball": reward.get("masterball", 0),
            "bp": reward.get("bp", 0),
            "iv_stone_3": iv_cnt,
            "shiny": shiny_name,
            "top_shiny": top_shiny_name,
        })

    await rq.mark_rewards_distributed(season_id)
    return rewarded


def _random_shiny_pokemon(rarity: str) -> tuple[int, str]:
    """Pick a random pokemon of the given rarity."""
    from models.pokemon_data import ALL_POKEMON
    candidates = [(p[0], p[1]) for p in ALL_POKEMON if p[4] == rarity]
    return random.choice(candidates)


async def soft_reset_new_season(prev_season_id: str) -> dict:
    """소프트 리셋 + 새 시즌 생성 (LoL 스타일: 전원 언랭 + 배치 필요)."""
    prev_records = await rq.get_all_season_records(prev_season_id)

    new_sid = current_season_id()
    starts, ends = season_date_range(new_sid)

    recent = await rq.get_recent_rules(2)
    rule = pick_random_excluding(config.SEASON_RULE_POOL, recent)

    new_season = await rq.get_or_create_season(new_sid, rule, starts, ends, [])

    # MMR 소프트 리셋 (1200 방향 25%)
    await rq.soft_reset_all_mmr(config.MMR_SEASON_RESET_FACTOR)

    # 기존 참여자: 새 시즌 언랭 + 배치 미완료
    for rec in prev_records:
        await rq.upsert_season_record(
            rec["user_id"], new_sid, 0, "unranked",
            placement_done=False, placement_games=0)

    return new_season


# ─── Mid-Season Reset ────────────────────────────────────

async def process_mid_season_reset(season: dict) -> int:
    """중간 리셋 (7일차): RP × 0.6, MMR 바닥 보장, 연승 리셋.
    Returns: 리셋된 유저 수."""
    season_id = season["season_id"]

    if season.get("mid_reset_done"):
        return 0

    records = await rq.get_all_placed_records(season_id)
    reset_count = 0

    for rec in records:
        old_rp = rec["rp"]
        new_rp = int(old_rp * config.RP_MID_SEASON_RESET_MULT)

        # MMR 바닥 보장: 유저 MMR 기반 최소 디비전
        user_mmr = rec.get("mmr", 1200)
        mmr_floor_rp = max(0, mmr_to_starting_rp(user_mmr) - 50)
        new_rp = max(new_rp, mmr_floor_rp)

        new_tier_key, _, _ = config.get_tier(new_rp)

        await rq.bulk_update_mid_reset(season_id, rec["user_id"], new_rp, new_tier_key)
        reset_count += 1

    await rq.mark_mid_reset_done(season_id)
    logger.info(f"Mid-season reset completed for {season_id}: {reset_count} users")
    return reset_count


# ─── Decay (디케이) ──────────────────────────────────────

async def process_ranked_decay(season_id: str) -> list[dict]:
    """마스터+ 유저 디케이 처리. Returns: 디케이된 유저 리스트."""
    now = config.get_kst_now()
    cutoff = now - dt.timedelta(days=config.DECAY_INACTIVE_DAYS)

    results = await rq.apply_decay(
        season_id, cutoff,
        config.DECAY_RP_PER_DAY, config.DECAY_MIN_RP,
        config.DECAY_INACTIVE_DAYS)

    if results:
        logger.info(f"Ranked decay: {len(results)} users affected in {season_id}")

    return results


# ─── Challenger Tier ─────────────────────────────────────

async def refresh_challenger_tier(season_id: str):
    """마스터 티어 Top N명에게 챌린저 부여, 나머지는 마스터로 되돌림."""
    top_n = config.CHALLENGER_TOP_N
    top_users = await rq.get_ranked_ranking(season_id, limit=top_n)

    # 마스터 이상인 유저만 챌린저 후보
    challenger_ids = set()
    for r in top_users:
        if r["rp"] >= 1000:  # 마스터 최소 RP
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
    if top and top[0]["rp"] >= 1000:
        return top[0]["user_id"]
    return None


# ─── Helper: Tier Display ────────────────────────────────

def tier_display(tier_key: str) -> str:
    """'silver' → '🥈실버' (하위호환)"""
    for t in config.RANKED_TIERS:
        if t[0] == tier_key:
            return f"{t[2]}{t[1]}"
    return tier_key


def tier_display_full(rec: dict) -> str:
    """시즌 레코드로 전체 티어 표시 (디비전 포함)."""
    tier_key = rec.get("tier", "unranked")
    rp = rec.get("rp", 0)
    placement_done = rec.get("placement_done", False)
    placement_games = rec.get("placement_games", 0)

    if tier_key == "unranked" or not placement_done:
        wins = rec.get("ranked_wins", 0)
        losses = rec.get("ranked_losses", 0)
        return config.tier_division_display(
            "unranked", placement_done=False,
            placement_games=placement_games,
            placement_wins=wins, placement_losses=losses)

    if tier_key == "challenger":
        return config.tier_division_display("challenger", total_rp=rp)

    div_info = config.get_division_info(rp)
    return config.tier_division_display(
        div_info[0], div_info[1], div_info[2],
        placement_done=True, total_rp=rp)
