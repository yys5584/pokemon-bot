"""Anti-bot abuse detection service.

시간당 포획 50회 초과 시 캡차(챌린지) 발동.
챌린지 실패/타임아웃 시 단계적 잠금.
"""

import asyncio
import logging
import random
import time
from collections import defaultdict

from database.connection import get_db

logger = logging.getLogger(__name__)

# ─── 설정값 ────────────────────────────────────────
HOURLY_CATCH_LIMIT = 50             # 시간당 이 이상이면 챌린지
CHALLENGE_TIMEOUT_SEC = 180         # 챌린지 응답 제한시간 (3분)
DB_HOURLY_CHECK_INTERVAL = 300      # DB 기반 시간당 체크 간격 (5분)

# 챌린지 실패 시 잠금 시간 (초) — 1차 30분, 2차 1시간, 3차+ 12시간
LOCK_DURATIONS = [30 * 60, 60 * 60, 12 * 60 * 60]

# ─── 메모리 캐시 ───────────────────────────────────
# user_id -> list of (timestamp, chat_id) — 최근 1시간 포획 기록
_catch_history: dict[int, list[tuple[float, int]]] = defaultdict(list)
_CATCH_HISTORY_MAX = 120

# user_id -> last DB hourly check timestamp
_last_db_hourly_check: dict[int, float] = {}

# user_id -> 시간당 포획 수 (메모리 or DB 중 큰 값)
_hourly_count_cache: dict[int, int] = {}

# user_id -> 챌린지 통과 시각 (이후 포획만 카운트)
_challenge_passed_at: dict[int, float] = {}

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


# ─── 포획 기록 & 시간당 체크 ─────────────────────
async def record_reaction(user_id: int, session_id: int, spawned_at, attempted_at, chat_id: int = 0) -> int | None:
    """포획 시 반응시간(ms) 기록 + 시간당 포획 수 추적."""
    now = time.time()

    # ── 시간당 포획 추적 ──
    if chat_id:
        history = _catch_history[user_id]
        history.append((now, chat_id))
        # 1시간 이전 기록 정리
        cutoff = now - 3600
        _catch_history[user_id] = [(t, c) for t, c in history if t > cutoff][-_CATCH_HISTORY_MAX:]
        # 메모리 기반 시간당 카운트 갱신
        _hourly_count_cache[user_id] = len(_catch_history[user_id])

    # ── 반응시간 계산 & DB 저장 (통계용) ──
    if not spawned_at or not attempted_at:
        return None

    try:
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

    if reaction_ms > 180_000:
        return None

    try:
        pool = await get_db()
        await pool.execute(
            """UPDATE catch_attempts SET reaction_ms = $1
               WHERE session_id = $2 AND user_id = $3""",
            reaction_ms, session_id, user_id,
        )
    except Exception as e:
        logger.warning(f"record_reaction DB error: {e}")

    return reaction_ms


async def _get_hourly_catch_count(user_id: int) -> int:
    """시간당 포획 수 반환 (메모리 + DB 이중 체크).
    캡차 통과 후에는 통과 시점 이후의 포획만 카운트."""
    memory_count = _hourly_count_cache.get(user_id, 0)

    # DB 체크 (5분마다)
    now = time.time()
    last_check = _last_db_hourly_check.get(user_id, 0)
    if now - last_check > DB_HOURLY_CHECK_INTERVAL:
        _last_db_hourly_check[user_id] = now
        try:
            pool = await get_db()
            # 캡차 통과 시각이 있으면 그 이후만, 없으면 최근 1시간
            reset_at = _challenge_passed_at.get(user_id)
            if reset_at:
                from datetime import datetime, timezone
                reset_dt = datetime.fromtimestamp(reset_at, tz=timezone.utc)
                db_count = await pool.fetchval(
                    "SELECT COUNT(*) FROM catch_attempts "
                    "WHERE user_id = $1 AND attempted_at > $2",
                    user_id, reset_dt,
                )
            else:
                db_count = await pool.fetchval(
                    "SELECT COUNT(*) FROM catch_attempts "
                    "WHERE user_id = $1 AND attempted_at > NOW() - interval '1 hour'",
                    user_id,
                )
            db_count = db_count or 0
            if db_count > memory_count:
                _hourly_count_cache[user_id] = db_count
                return db_count
        except Exception as e:
            logger.warning(f"DB hourly check error: {e}")

    return memory_count


# ─── 챌린지 판정 ──────────────────────────────────
async def should_challenge(user_id: int) -> bool:
    """시간당 50회 초과 시 챌린지 발동. 캡차 통과하면 카운트 리셋."""
    count = await _get_hourly_catch_count(user_id)
    if count >= HOURLY_CATCH_LIMIT:
        logger.info(f"Challenge triggered uid={user_id}: {count} catches/hour (limit={HOURLY_CATCH_LIMIT})")
        return True
    return False


# ─── bot_score 호환 (리포트/관리자 조회용) ────────
async def get_bot_score(user_id: int) -> float:
    """시간당 포획 수를 0~1 점수로 변환 (리포트 호환)."""
    count = await _get_hourly_catch_count(user_id)
    if count < HOURLY_CATCH_LIMIT:
        return 0.0
    # 50회=0.5, 100회=1.0 스케일
    return min(1.0, count / (HOURLY_CATCH_LIMIT * 2))


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

    passed = not expired and answer.strip() == expected

    try:
        reaction_ms = int((time.time() - ch["created_at"]) * 1000) if not expired else None
        pool = await get_db()
        await pool.execute(
            """INSERT INTO catch_challenges
               (user_id, session_id, challenge_type, expected_answer, given_answer, passed, reaction_ms)
               VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            user_id, ch["session_id"], ch["type"], expected, answer.strip(), passed, reaction_ms,
        )

        if passed:
            await pool.execute(
                """INSERT INTO abuse_scores (user_id, total_challenges, challenge_passes, last_challenge_at, updated_at)
                   VALUES ($1, 1, 1, NOW(), NOW())
                   ON CONFLICT (user_id) DO UPDATE SET
                       total_challenges = abuse_scores.total_challenges + 1,
                       challenge_passes = abuse_scores.challenge_passes + 1,
                       last_challenge_at = NOW(), updated_at = NOW()""",
                user_id,
            )
            # 정답 시: 카운트 리셋 + 잠금 초기화
            # 여기서부터 다시 50회 카운트 시작
            _catch_history[user_id] = []
            _hourly_count_cache[user_id] = 0
            _challenge_passed_at[user_id] = time.time()
            _catch_locks.pop(user_id, None)
        else:
            await pool.execute(
                """INSERT INTO abuse_scores (user_id, total_challenges, challenge_fails, last_challenge_at, last_flagged_at, updated_at)
                   VALUES ($1, 1, 1, NOW(), NOW(), NOW())
                   ON CONFLICT (user_id) DO UPDATE SET
                       total_challenges = abuse_scores.total_challenges + 1,
                       challenge_fails = abuse_scores.challenge_fails + 1,
                       last_challenge_at = NOW(), last_flagged_at = NOW(), updated_at = NOW()""",
                user_id,
            )
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
            """INSERT INTO abuse_scores (user_id, total_challenges, challenge_fails, last_challenge_at, last_flagged_at, updated_at)
               VALUES ($1, 1, 1, NOW(), NOW(), NOW())
               ON CONFLICT (user_id) DO UPDATE SET
                   total_challenges = abuse_scores.total_challenges + 1,
                   challenge_fails = abuse_scores.challenge_fails + 1,
                   last_challenge_at = NOW(), last_flagged_at = NOW(), updated_at = NOW()""",
            user_id,
        )
        _apply_catch_lock(user_id)
    except Exception as e:
        logger.warning(f"handle_challenge_timeout DB error: {e}")


# ─── 관리자용 조회 ─────────────────────────────────
async def get_flagged_users(limit: int = 20) -> list[dict]:
    """시간당 과다포획 유저 목록 (리포트용, DB에서 최근 1시간 기준)."""
    try:
        pool = await get_db()
        rows = await pool.fetch(
            """SELECT ca.user_id, u.display_name, u.username,
                      COUNT(*) as hourly_catches,
                      a.total_challenges, a.challenge_passes, a.challenge_fails
               FROM catch_attempts ca
               JOIN users u ON ca.user_id = u.user_id
               LEFT JOIN abuse_scores a ON ca.user_id = a.user_id
               WHERE ca.attempted_at > NOW() - interval '1 hour'
               GROUP BY ca.user_id, u.display_name, u.username,
                        a.total_challenges, a.challenge_passes, a.challenge_fails
               HAVING COUNT(*) >= $1
               ORDER BY COUNT(*) DESC
               LIMIT $2""",
            HOURLY_CATCH_LIMIT, limit,
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
        _hourly_count_cache.pop(user_id, None)
        _catch_locks.pop(user_id, None)
    except Exception as e:
        logger.warning(f"admin_reset_score error: {e}")
