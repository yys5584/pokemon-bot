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

# ─── 봇 시작 시각 (재시작 시 이전 포획 무시) ────────
_bot_started_at: float = time.time()

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
# DB 캐시: {user_id: locked_until_timestamp}
_db_lock_cache: dict[int, float] = {}

def is_catch_locked(user_id: int) -> tuple[bool, int]:
    """포획 잠금 여부 확인 (메모리 + DB). 반환: (잠김 여부, 남은 초)."""
    # 메모리 체크
    lock = _catch_locks.get(user_id)
    if lock:
        remaining = int(lock["locked_until"] - time.time())
        if remaining > 0:
            return True, remaining
        _catch_locks.pop(user_id, None)
    # DB 캐시 체크
    db_until = _db_lock_cache.get(user_id, 0)
    if db_until > time.time():
        return True, int(db_until - time.time())
    return False, 0


def _apply_catch_lock(user_id: int, duration_override: int = None):
    """챌린지 실패/타임아웃 시 잠금 적용. duration_override로 직접 시간 지정 가능."""
    if duration_override:
        duration = duration_override
        lock = _catch_locks.get(user_id)
        strike = (lock["strike"] if lock else 0) + 1
    else:
        lock = _catch_locks.get(user_id)
        strike = (lock["strike"] if lock else 0) + 1
        duration_idx = min(strike - 1, len(LOCK_DURATIONS) - 1)
        duration = LOCK_DURATIONS[duration_idx]
    _catch_locks[user_id] = {
        "locked_until": time.time() + duration,
        "strike": strike,
    }
    # DB에도 저장 (재시작 후에도 유지)
    _db_lock_cache[user_id] = time.time() + duration
    asyncio.get_event_loop().create_task(_save_lock_to_db(user_id, duration))
    return strike, duration


async def _save_lock_to_db(user_id: int, duration: int):
    """잠금을 DB에 영속화."""
    try:
        pool = await get_db()
        await pool.execute(
            """UPDATE abuse_scores SET locked_until = NOW() + make_interval(secs => $2), updated_at = NOW()
               WHERE user_id = $1""",
            user_id, float(duration))
    except Exception as e:
        logger.warning(f"_save_lock_to_db error: {e}")


async def load_locks_from_db():
    """봇 시작 시 DB에서 잠금 복원."""
    try:
        pool = await get_db()
        # locked_until 컬럼 존재 확인 및 추가
        await pool.execute(
            "ALTER TABLE abuse_scores ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ")
        rows = await pool.fetch(
            "SELECT user_id, locked_until FROM abuse_scores WHERE locked_until > NOW()")
        for r in rows:
            remaining = (r["locked_until"].timestamp() - time.time())
            if remaining > 0:
                _catch_locks[r["user_id"]] = {"locked_until": r["locked_until"].timestamp(), "strike": 5}
                _db_lock_cache[r["user_id"]] = r["locked_until"].timestamp()
        logger.info(f"Loaded {len(rows)} catch locks from DB")
    except Exception as e:
        logger.warning(f"load_locks_from_db error: {e}")


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
            # 기준 시각: 캡차 통과 > 봇 시작 > 1시간 전 중 가장 늦은 시각
            from datetime import datetime, timezone
            reset_at = _challenge_passed_at.get(user_id)
            if reset_at:
                cutoff_ts = reset_at
            else:
                cutoff_ts = _bot_started_at
            cutoff_dt = datetime.fromtimestamp(cutoff_ts, tz=timezone.utc)
            db_count = await pool.fetchval(
                "SELECT COUNT(*) FROM catch_attempts "
                "WHERE user_id = $1 AND attempted_at > $2",
                user_id, cutoff_dt,
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
    """감시 대상(is_watched) 유저만 시간당 50회 초과 시 챌린지 발동."""
    # 감시 대상인지 먼저 확인
    try:
        pool = await get_db()
        watched = await pool.fetchval(
            "SELECT is_watched FROM abuse_scores WHERE user_id = $1",
            user_id,
        )
        if not watched:
            return False  # 감시 대상 아니면 CAPTCHA 안 함
    except Exception:
        return False

    count = await _get_hourly_catch_count(user_id)
    if count >= HOURLY_CATCH_LIMIT:
        logger.info(f"Challenge triggered uid={user_id} (watched): {count} catches/hour")
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


async def compute_monitor_scores():
    """일일 매크로 모니터링 스코어 계산 (job에서 호출).

    포획/배틀 패턴 분석 → 의심 스코어 0~100 계산.
    50+ 시 is_watched = TRUE → 해당 유저만 CAPTCHA 대상.
    """
    import json
    try:
        pool = await get_db()
        # 활성 유저 (최근 3일 포획 or 배틀)
        users = await pool.fetch("""
            SELECT DISTINCT user_id FROM (
                SELECT user_id FROM catch_attempts
                WHERE attempted_at > NOW() - INTERVAL '3 days'
                UNION
                SELECT challenger_id AS user_id FROM battle_challenges
                WHERE created_at > NOW() - INTERVAL '3 days'
                UNION
                SELECT defender_id AS user_id FROM battle_challenges
                WHERE created_at > NOW() - INTERVAL '3 days'
            ) t
        """)

        for row in users:
            uid = row["user_id"]
            score = 0
            detail = {}

            # 1) 동일 상대 배틀 반복 (7일, 상위 1쌍)
            top_pair = await pool.fetchrow("""
                SELECT opponent_id, cnt FROM (
                    SELECT CASE WHEN challenger_id = $1 THEN defender_id ELSE challenger_id END AS opponent_id,
                           COUNT(*) AS cnt
                    FROM battle_challenges
                    WHERE (challenger_id = $1 OR defender_id = $1)
                      AND status = 'completed'
                      AND created_at > NOW() - INTERVAL '7 days'
                    GROUP BY opponent_id
                ) t ORDER BY cnt DESC LIMIT 1
            """, uid)
            if top_pair and top_pair["cnt"] >= 20:
                s = min(40, int(top_pair["cnt"] / 2))
                score += s
                detail["battle_repeat"] = {"opponent": top_pair["opponent_id"], "count": top_pair["cnt"], "score": s}

            # 2) 새벽 3~6시(KST) 포획 활동량 (3일)
            dawn_count = await pool.fetchval("""
                SELECT COUNT(*) FROM catch_attempts
                WHERE user_id = $1
                  AND attempted_at > NOW() - INTERVAL '3 days'
                  AND EXTRACT(HOUR FROM attempted_at AT TIME ZONE 'Asia/Seoul') BETWEEN 3 AND 5
            """, uid)
            if dawn_count and dawn_count >= 30:
                s = min(25, dawn_count // 4)
                score += s
                detail["dawn_activity"] = {"count": dawn_count, "score": s}

            # 3) 포획 응답시간 표준편차 (최근 100건)
            reaction_stats = await pool.fetchrow("""
                SELECT STDDEV(reaction_ms) AS std, AVG(reaction_ms) AS avg, COUNT(*) AS cnt
                FROM (
                    SELECT reaction_ms FROM catch_attempts
                    WHERE user_id = $1 AND reaction_ms IS NOT NULL
                      AND attempted_at > NOW() - INTERVAL '3 days'
                    ORDER BY attempted_at DESC LIMIT 100
                ) t
            """, uid)
            if reaction_stats and reaction_stats["cnt"] and reaction_stats["cnt"] >= 20:
                std = reaction_stats["std"] or 0
                avg = reaction_stats["avg"] or 0
                # 표준편차 300ms 이하 + 평균 2초 이하 → 봇 의심
                if std < 300 and avg < 2000:
                    s = 30
                    score += s
                    detail["reaction_consistency"] = {"std_ms": round(float(std)), "avg_ms": round(float(avg)), "score": s}
                elif std < 500 and avg < 3000:
                    s = 15
                    score += s
                    detail["reaction_consistency"] = {"std_ms": round(float(std)), "avg_ms": round(float(avg)), "score": s}

            # 4) 최장 무중단 활동 (3일, 포획 간격 5분 이내 연속)
            catches_ts = await pool.fetch("""
                SELECT attempted_at FROM catch_attempts
                WHERE user_id = $1 AND attempted_at > NOW() - INTERVAL '3 days'
                ORDER BY attempted_at
            """, uid)
            if catches_ts:
                max_streak_min = 0
                current_streak_start = catches_ts[0]["attempted_at"]
                prev = catches_ts[0]["attempted_at"]
                for c in catches_ts[1:]:
                    gap = (c["attempted_at"] - prev).total_seconds()
                    if gap <= 300:  # 5분 이내
                        pass
                    else:
                        streak_min = (prev - current_streak_start).total_seconds() / 60
                        max_streak_min = max(max_streak_min, streak_min)
                        current_streak_start = c["attempted_at"]
                    prev = c["attempted_at"]
                streak_min = (prev - current_streak_start).total_seconds() / 60
                max_streak_min = max(max_streak_min, streak_min)

                if max_streak_min >= 240:  # 4시간+
                    s = min(20, int(max_streak_min / 30))
                    score += s
                    detail["continuous_play"] = {"max_minutes": round(max_streak_min), "score": s}

            # 5) 스폰 이로치 과다 포획 (3일간, spawn_log 기준)
            shiny_stats = await pool.fetchrow("""
                SELECT COUNT(*) as shiny_cnt,
                       COUNT(DISTINCT (spawned_at AT TIME ZONE 'Asia/Seoul')::date) as days
                FROM spawn_log
                WHERE caught_by_user_id = $1 AND is_shiny = 1
                  AND spawned_at > NOW() - INTERVAL '3 days'
            """, uid)
            catch_3d = await pool.fetchval(
                "SELECT COUNT(*) FROM catch_attempts WHERE user_id = $1 AND attempted_at > NOW() - INTERVAL '3 days'",
                uid)
            if shiny_stats and shiny_stats["shiny_cnt"] >= 5:
                shiny_cnt = shiny_stats["shiny_cnt"]
                days = max(shiny_stats["days"], 1)
                daily_avg = shiny_cnt / days
                shiny_pct = round(shiny_cnt / max(catch_3d, 1) * 100, 1) if catch_3d else 0

                # 일평균 20마리+ → 최대 30점, 비율 10%+ → 최대 20점
                s = 0
                if daily_avg >= 40:
                    s += 30
                elif daily_avg >= 20:
                    s += min(30, int(daily_avg))
                elif daily_avg >= 10:
                    s += min(15, int(daily_avg / 2))

                if shiny_pct >= 10:
                    s += min(20, int(shiny_pct))

                if s > 0:
                    score += s
                    detail["shiny_farming"] = {
                        "shiny_3d": shiny_cnt, "catches_3d": catch_3d,
                        "daily_avg": round(daily_avg, 1), "pct": shiny_pct, "score": s
                    }

            # DB 업데이트
            is_watched = score >= 50
            await pool.execute("""
                INSERT INTO abuse_scores (user_id, monitor_score, monitor_detail, monitored_at, is_watched, updated_at)
                VALUES ($1, $2, $3, NOW(), $4, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    monitor_score = $2, monitor_detail = $3, monitored_at = NOW(),
                    is_watched = $4, updated_at = NOW()
            """, uid, score, json.dumps(detail, ensure_ascii=False), is_watched)

        watched = await pool.fetchval("SELECT COUNT(*) FROM abuse_scores WHERE is_watched = TRUE")
        logger.info(f"Monitor scores computed: {len(users)} users, {watched} watched")
        return len(users), watched
    except Exception as e:
        logger.error(f"compute_monitor_scores error: {e}")
        return 0, 0


async def get_watched_users(limit: int = 50) -> list[dict]:
    """감시 대상 유저 목록 (관리자 대시보드용)."""
    try:
        pool = await get_db()
        rows = await pool.fetch("""
            SELECT a.user_id, u.display_name, u.username,
                   a.monitor_score, a.monitor_detail, a.monitored_at, a.is_watched
            FROM abuse_scores a
            JOIN users u ON a.user_id = u.user_id
            WHERE a.monitor_score > 0
            ORDER BY a.monitor_score DESC
            LIMIT $1
        """, limit)
        return [dict(r) for r in rows]
    except Exception:
        return []


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
