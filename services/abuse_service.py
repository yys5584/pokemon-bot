"""Anti-bot abuse detection service.

의심 유저 탐지 → 포획 챌린지 발동 → 결과에 따라 점수 조정.
일반 유저는 전혀 영향 없음.
"""

import asyncio
import logging
import random
import time
from collections import defaultdict

from database.connection import get_db

logger = logging.getLogger(__name__)

# ─── 설정값 ────────────────────────────────────────
BOT_SCORE_THRESHOLD_LOW = 0.4     # 이 이상이면 10% 확률로 챌린지
BOT_SCORE_THRESHOLD_MID = 0.7     # 이 이상이면 50% 확률로 챌린지
BOT_SCORE_THRESHOLD_HIGH = 0.9    # 이 이상이면 100% 챌린지
CHALLENGE_TIMEOUT_SEC = 300       # 챌린지 응답 제한시간 (5분)
FAST_REACTION_MS = 2000           # 2초 이하 = 의심 반응
VERY_FAST_REACTION_MS = 1000      # 1초 이하 = 매우 의심
MIN_SAMPLES_FOR_SCORING = 5       # 최소 5회 포획 후부터 점수 계산
SCORE_DECAY_PER_HOUR = 0.02       # 시간당 점수 자연 감소

# 챌린지 실패 시 잠금 시간 (초) — 1차 30분, 2차 1시간, 3차+ 12시간
LOCK_DURATIONS = [30 * 60, 60 * 60, 12 * 60 * 60]

# ─── 메모리 캐시 ───────────────────────────────────
# user_id -> list of recent reaction_ms (최근 20개)
_reaction_cache: dict[int, list[int]] = defaultdict(list)
_REACTION_CACHE_MAX = 20

# user_id -> bot_score (DB 동기화는 비동기)
_score_cache: dict[int, float] = {}

# user_id -> pending challenge info
_pending_challenges: dict[int, dict] = {}

# user_id -> {"locked_until": float(timestamp), "strike": int}
_catch_locks: dict[int, dict] = {}


# ─── 포획 잠금 ────────────────────────────────────
def is_catch_locked(user_id: int) -> tuple[bool, int]:
    """포획 잠금 여부 확인. 반환: (잠김 여부, 남은 초)."""
    lock = _catch_locks.get(user_id)
    if not lock:
        return False, 0
    remaining = int(lock["locked_until"] - time.time())
    if remaining <= 0:
        _catch_locks.pop(user_id, None)
        return False, 0
    return True, remaining


def _apply_catch_lock(user_id: int):
    """챌린지 실패/타임아웃 시 잠금 적용. 연속 실패에 따라 단계적 잠금."""
    lock = _catch_locks.get(user_id)
    strike = (lock["strike"] if lock else 0) + 1
    duration_idx = min(strike - 1, len(LOCK_DURATIONS) - 1)
    duration = LOCK_DURATIONS[duration_idx]
    _catch_locks[user_id] = {
        "locked_until": time.time() + duration,
        "strike": strike,
    }
    return strike, duration


def format_lock_duration(seconds: int) -> str:
    """잠금 시간을 읽기 좋은 형태로 포맷."""
    if seconds >= 3600:
        return f"{seconds // 3600}시간"
    return f"{seconds // 60}분"


# ─── 반응시간 기록 ─────────────────────────────────
async def record_reaction(user_id: int, session_id: int, spawned_at, attempted_at) -> int | None:
    """포획 시 반응시간(ms) 계산 & 기록. 반환: reaction_ms or None."""
    logger.info(f"record_reaction called: user={user_id}, session={session_id}, spawned={spawned_at}, attempted={attempted_at}")
    if not spawned_at or not attempted_at:
        logger.warning(f"record_reaction early return: spawned_at={spawned_at}, attempted_at={attempted_at}")
        return None

    try:
        # timezone 맞추기 (spawned_at은 tz-aware, attempted_at은 tz-naive일 수 있음)
        if hasattr(spawned_at, 'tzinfo') and spawned_at.tzinfo is not None:
            if attempted_at.tzinfo is None:
                attempted_at = attempted_at.replace(tzinfo=spawned_at.tzinfo)
        elif hasattr(attempted_at, 'tzinfo') and attempted_at.tzinfo is not None:
            if spawned_at.tzinfo is None:
                spawned_at = spawned_at.replace(tzinfo=attempted_at.tzinfo)
        diff = (attempted_at - spawned_at).total_seconds()
        reaction_ms = max(0, int(diff * 1000))
    except Exception as e:
        logger.warning(f"record_reaction calc error: {e}")
        return None

    # 비정상 값 필터 (음수 or 5분 초과)
    if reaction_ms > 300_000:
        return None

    logger.info(f"record_reaction: user={user_id}, reaction_ms={reaction_ms}")

    # DB에 reaction_ms 저장
    try:
        pool = await get_db()
        result = await pool.execute(
            """UPDATE catch_attempts SET reaction_ms = $1
               WHERE session_id = $2 AND user_id = $3""",
            reaction_ms, session_id, user_id,
        )
        logger.info(f"record_reaction DB update: user={user_id}, result={result}")
    except Exception as e:
        logger.warning(f"record_reaction DB error: {e}")

    # 메모리 캐시 업데이트
    cache = _reaction_cache[user_id]
    cache.append(reaction_ms)
    if len(cache) > _REACTION_CACHE_MAX:
        cache.pop(0)

    # 점수 업데이트 (백그라운드)
    asyncio.create_task(_update_bot_score(user_id, reaction_ms))

    return reaction_ms


# ─── 의심 점수 계산 ────────────────────────────────
async def _update_bot_score(user_id: int, latest_ms: int):
    """최근 반응시간 패턴으로 봇 의심 점수 갱신."""
    try:
        cache = _reaction_cache.get(user_id, [])
        if len(cache) < MIN_SAMPLES_FOR_SCORING:
            return

        # 1. 빠른 반응 비율 (2초 이내)
        fast_count = sum(1 for ms in cache if ms < FAST_REACTION_MS)
        fast_ratio = fast_count / len(cache)

        # 2. 매우 빠른 반응 비율 (1초 이내)
        very_fast_count = sum(1 for ms in cache if ms < VERY_FAST_REACTION_MS)
        very_fast_ratio = very_fast_count / len(cache)

        # 3. 반응시간 표준편차 (봇은 일정함)
        if len(cache) >= 3:
            mean = sum(cache) / len(cache)
            variance = sum((x - mean) ** 2 for x in cache) / len(cache)
            std_dev = variance ** 0.5
            # 표준편차가 200ms 이하면 매우 의심 (사람은 보통 500ms+ 분산)
            consistency_score = max(0, 1.0 - std_dev / 1000)
        else:
            consistency_score = 0

        # 종합 점수: 가중 평균
        score = (
            fast_ratio * 0.35 +
            very_fast_ratio * 0.35 +
            consistency_score * 0.30
        )

        # 0~1 범위 클램프
        score = max(0.0, min(1.0, score))

        # 기존 점수와 블렌딩 (급격한 변동 방지)
        old_score = _score_cache.get(user_id, 0)
        blended = old_score * 0.3 + score * 0.7

        _score_cache[user_id] = blended

        # DB에 저장
        pool = await get_db()
        await pool.execute(
            """INSERT INTO abuse_scores (user_id, bot_score, updated_at)
               VALUES ($1, $2, NOW())
               ON CONFLICT (user_id) DO UPDATE
               SET bot_score = $2, updated_at = NOW()""",
            user_id, round(blended, 4),
        )

    except Exception as e:
        logger.warning(f"_update_bot_score error: {e}")


async def get_bot_score(user_id: int) -> float:
    """유저의 현재 봇 의심 점수 반환 (0~1)."""
    if user_id in _score_cache:
        return _score_cache[user_id]

    try:
        pool = await get_db()
        row = await pool.fetchrow(
            "SELECT bot_score FROM abuse_scores WHERE user_id = $1",
            user_id,
        )
        score = float(row["bot_score"]) if row else 0.0
        _score_cache[user_id] = score
        return score
    except Exception:
        return 0.0


# ─── 챌린지 판정 ──────────────────────────────────
async def should_challenge(user_id: int) -> bool:
    """이 유저에게 포획 챌린지를 발동할지 판정."""
    score = await get_bot_score(user_id)

    if score >= BOT_SCORE_THRESHOLD_HIGH:
        return True
    elif score >= BOT_SCORE_THRESHOLD_MID:
        return random.random() < 0.50
    elif score >= BOT_SCORE_THRESHOLD_LOW:
        return random.random() < 0.10
    return False


# ─── 챌린지 생성/검증 ─────────────────────────────
def _generate_wrong_choices(correct_name: str, count: int = 3) -> list[str]:
    """정답을 제외한 랜덤 오답 보기 생성."""
    from models.pokemon_data import ALL_POKEMON
    all_names = [p[1] for p in ALL_POKEMON if p[1] != correct_name]
    return random.sample(all_names, min(count, len(all_names)))


def create_challenge(user_id: int, session_id: int, pokemon_name: str) -> dict:
    """포획 챌린지 생성. 4지선다 이름 선택."""
    wrong = _generate_wrong_choices(pokemon_name, 3)
    choices = wrong + [pokemon_name]
    random.shuffle(choices)

    challenge = {
        "user_id": user_id,
        "session_id": session_id,
        "type": "name_choice",
        "expected": pokemon_name,
        "choices": choices,
        "created_at": time.time(),
        "answered": False,
    }
    _pending_challenges[user_id] = challenge
    return challenge


def get_pending_challenge(user_id: int) -> dict | None:
    """유저의 대기 중인 챌린지 반환."""
    ch = _pending_challenges.get(user_id)
    if not ch:
        return None
    # 타임아웃 체크
    if time.time() - ch["created_at"] > CHALLENGE_TIMEOUT_SEC:
        return ch  # 만료됐지만 반환 (처리용)
    return ch


def is_challenge_expired(challenge: dict) -> bool:
    """챌린지가 타임아웃됐는지 확인."""
    return time.time() - challenge["created_at"] > CHALLENGE_TIMEOUT_SEC


async def resolve_challenge(user_id: int, answer: str) -> bool:
    """챌린지 응답 처리. 반환: 통과 여부."""
    ch = _pending_challenges.pop(user_id, None)
    if not ch:
        return False

    expired = is_challenge_expired(ch)
    expected = ch["expected"].strip()

    # 정답 판정: 완전 일치 또는 공백 무시 일치
    passed = not expired and answer.strip() == expected

    # DB 기록
    try:
        reaction_ms = int((time.time() - ch["created_at"]) * 1000) if not expired else None
        pool = await get_db()
        await pool.execute(
            """INSERT INTO catch_challenges
               (user_id, session_id, challenge_type, expected_answer, given_answer, passed, reaction_ms)
               VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            user_id, ch["session_id"], ch["type"], expected, answer.strip(), passed, reaction_ms,
        )

        # abuse_scores 업데이트
        if passed:
            await pool.execute(
                """INSERT INTO abuse_scores (user_id, total_challenges, challenge_passes, last_challenge_at, updated_at)
                   VALUES ($1, 1, 1, NOW(), NOW())
                   ON CONFLICT (user_id) DO UPDATE SET
                       total_challenges = abuse_scores.total_challenges + 1,
                       challenge_passes = abuse_scores.challenge_passes + 1,
                       bot_score = GREATEST(0, abuse_scores.bot_score - 0.15),
                       last_challenge_at = NOW(), updated_at = NOW()""",
                user_id,
            )
            # 캐시도 감소
            if user_id in _score_cache:
                _score_cache[user_id] = max(0, _score_cache[user_id] - 0.15)
            # 정답 시 잠금 스트라이크 초기화
            _catch_locks.pop(user_id, None)
        else:
            await pool.execute(
                """INSERT INTO abuse_scores (user_id, bot_score, total_challenges, challenge_fails, last_challenge_at, last_flagged_at, updated_at)
                   VALUES ($1, 0.3, 1, 1, NOW(), NOW(), NOW())
                   ON CONFLICT (user_id) DO UPDATE SET
                       total_challenges = abuse_scores.total_challenges + 1,
                       challenge_fails = abuse_scores.challenge_fails + 1,
                       bot_score = LEAST(1.0, abuse_scores.bot_score + 0.25),
                       last_challenge_at = NOW(), last_flagged_at = NOW(), updated_at = NOW()""",
                user_id,
            )
            # 캐시도 증가
            if user_id in _score_cache:
                _score_cache[user_id] = min(1.0, _score_cache[user_id] + 0.25)
            # 실패 시 포획 잠금 적용
            _apply_catch_lock(user_id)

    except Exception as e:
        logger.warning(f"resolve_challenge DB error: {e}")

    return passed


def clear_challenge(user_id: int):
    """챌린지 제거 (타임아웃 등)."""
    _pending_challenges.pop(user_id, None)


async def handle_challenge_timeout(user_id: int):
    """챌린지 무응답 처리 — 실패로 기록."""
    ch = _pending_challenges.pop(user_id, None)
    if not ch:
        return

    try:
        pool = await get_db()
        await pool.execute(
            """INSERT INTO catch_challenges
               (user_id, session_id, challenge_type, expected_answer, given_answer, passed, reaction_ms)
               VALUES ($1, $2, $3, $4, NULL, FALSE, NULL)""",
            user_id, ch["session_id"], ch["type"], ch["expected"],
        )
        await pool.execute(
            """INSERT INTO abuse_scores (user_id, bot_score, total_challenges, challenge_fails, last_challenge_at, last_flagged_at, updated_at)
               VALUES ($1, 0.3, 1, 1, NOW(), NOW(), NOW())
               ON CONFLICT (user_id) DO UPDATE SET
                   total_challenges = abuse_scores.total_challenges + 1,
                   challenge_fails = abuse_scores.challenge_fails + 1,
                   bot_score = LEAST(1.0, abuse_scores.bot_score + 0.25),
                   last_challenge_at = NOW(), last_flagged_at = NOW(), updated_at = NOW()""",
            user_id,
        )
        if user_id in _score_cache:
            _score_cache[user_id] = min(1.0, _score_cache[user_id] + 0.25)
        # 타임아웃도 실패로 잠금 적용
        _apply_catch_lock(user_id)
    except Exception as e:
        logger.warning(f"handle_challenge_timeout DB error: {e}")


# ─── 관리자용 조회 ─────────────────────────────────
async def get_flagged_users(limit: int = 20) -> list[dict]:
    """의심 점수 높은 유저 목록 조회."""
    try:
        pool = await get_db()
        rows = await pool.fetch(
            """SELECT a.*, u.display_name, u.username
               FROM abuse_scores a
               JOIN users u ON a.user_id = u.user_id
               WHERE a.bot_score >= $1
               ORDER BY a.bot_score DESC
               LIMIT $2""",
            BOT_SCORE_THRESHOLD_LOW, limit,
        )
        return [dict(r) for r in rows]
    except Exception:
        return []


async def get_user_abuse_detail(user_id: int) -> dict | None:
    """특정 유저의 어뷰징 상세 정보."""
    try:
        pool = await get_db()
        score_row = await pool.fetchrow(
            "SELECT * FROM abuse_scores WHERE user_id = $1", user_id
        )
        recent_challenges = await pool.fetch(
            """SELECT * FROM catch_challenges
               WHERE user_id = $1 ORDER BY created_at DESC LIMIT 10""",
            user_id,
        )
        recent_reactions = await pool.fetch(
            """SELECT reaction_ms, attempted_at FROM catch_attempts
               WHERE user_id = $1 AND reaction_ms IS NOT NULL
               ORDER BY attempted_at DESC LIMIT 20""",
            user_id,
        )
        return {
            "score": dict(score_row) if score_row else None,
            "challenges": [dict(r) for r in recent_challenges],
            "reactions": [dict(r) for r in recent_reactions],
        }
    except Exception:
        return None


async def admin_reset_score(user_id: int):
    """관리자가 수동으로 점수 초기화."""
    try:
        pool = await get_db()
        await pool.execute(
            "UPDATE abuse_scores SET bot_score = 0, updated_at = NOW() WHERE user_id = $1",
            user_id,
        )
        _score_cache.pop(user_id, None)
        _reaction_cache.pop(user_id, None)
    except Exception as e:
        logger.warning(f"admin_reset_score error: {e}")
