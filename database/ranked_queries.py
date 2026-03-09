"""Database queries for ranked (season) battle system."""

from database.connection import get_db


# ─── Season CRUD ─────────────────────────────────────────

async def get_or_create_season(season_id: str, weekly_rule: str,
                                starts_at, ends_at, arena_chat_ids: list[int]) -> dict:
    """시즌 조회 또는 생성."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT * FROM seasons WHERE season_id = $1", season_id)
    if row:
        return dict(row)
    row = await pool.fetchrow(
        """INSERT INTO seasons (season_id, weekly_rule, starts_at, ends_at, arena_chat_ids)
           VALUES ($1, $2, $3, $4, $5)
           ON CONFLICT (season_id) DO NOTHING
           RETURNING *""",
        season_id, weekly_rule, starts_at, ends_at, arena_chat_ids)
    if row:
        return dict(row)
    # race condition fallback
    row = await pool.fetchrow(
        "SELECT * FROM seasons WHERE season_id = $1", season_id)
    return dict(row) if row else None


async def get_current_season() -> dict | None:
    """현재 활성 시즌 조회."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT * FROM seasons WHERE NOW() BETWEEN starts_at AND ends_at ORDER BY id DESC LIMIT 1")
    return dict(row) if row else None


async def get_season_by_id(season_id: str) -> dict | None:
    pool = await get_db()
    row = await pool.fetchrow("SELECT * FROM seasons WHERE season_id = $1", season_id)
    return dict(row) if row else None


async def get_recent_rules(n: int = 2) -> list[str]:
    """최근 n개 시즌의 weekly_rule 목록."""
    pool = await get_db()
    rows = await pool.fetch(
        "SELECT weekly_rule FROM seasons ORDER BY id DESC LIMIT $1", n)
    return [r["weekly_rule"] for r in rows]


async def mark_rewards_distributed(season_id: str):
    pool = await get_db()
    await pool.execute(
        "UPDATE seasons SET rewards_distributed = TRUE WHERE season_id = $1",
        season_id)


# ─── Daily Condition ─────────────────────────────────────

async def get_daily_condition(season_id: str, date) -> str | None:
    """오늘의 일일 조건 키 조회."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT condition_key FROM season_daily_conditions WHERE season_id = $1 AND date = $2",
        season_id, date)
    return row["condition_key"] if row else None


async def set_daily_condition(season_id: str, date, condition_key: str):
    pool = await get_db()
    await pool.execute(
        """INSERT INTO season_daily_conditions (season_id, date, condition_key)
           VALUES ($1, $2, $3)
           ON CONFLICT (season_id, date) DO UPDATE SET condition_key = $3""",
        season_id, date, condition_key)


async def get_recent_conditions(season_id: str, n: int = 2) -> list[str]:
    """최근 n개 일일 조건 키 목록."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT condition_key FROM season_daily_conditions
           WHERE season_id = $1 ORDER BY date DESC LIMIT $2""",
        season_id, n)
    return [r["condition_key"] for r in rows]


# ─── Season Records ──────────────────────────────────────

async def get_season_record(user_id: int, season_id: str) -> dict | None:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT * FROM season_records WHERE user_id = $1 AND season_id = $2",
        user_id, season_id)
    return dict(row) if row else None


async def upsert_season_record(user_id: int, season_id: str,
                                rp: int, tier: str,
                                wins: int = 0, losses: int = 0,
                                streak: int = 0, best_streak: int = 0,
                                peak_rp: int = 0, peak_tier: str = "bronze"):
    """시즌 기록 생성 또는 업데이트."""
    pool = await get_db()
    await pool.execute(
        """INSERT INTO season_records
              (user_id, season_id, rp, tier, ranked_wins, ranked_losses,
               ranked_streak, best_ranked_streak, peak_rp, peak_tier)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
           ON CONFLICT (user_id, season_id) DO UPDATE SET
              rp = $3, tier = $4, ranked_wins = $5, ranked_losses = $6,
              ranked_streak = $7, best_ranked_streak = $8, peak_rp = $9, peak_tier = $10""",
        user_id, season_id, rp, tier, wins, losses,
        streak, best_streak, peak_rp, peak_tier)


async def update_rp_win(user_id: int, season_id: str,
                         rp_gain: int, new_tier: str, new_peak_rp: int, new_peak_tier: str):
    """승리 시 RP + 전적 원자적 업데이트."""
    pool = await get_db()
    await pool.execute(
        """UPDATE season_records SET
              rp = rp + $3,
              tier = $4,
              ranked_wins = ranked_wins + 1,
              ranked_streak = ranked_streak + 1,
              best_ranked_streak = GREATEST(best_ranked_streak, ranked_streak + 1),
              peak_rp = GREATEST(peak_rp, $5),
              peak_tier = CASE WHEN $5 > peak_rp THEN $6 ELSE peak_tier END
           WHERE user_id = $1 AND season_id = $2""",
        user_id, season_id, rp_gain, new_tier, new_peak_rp, new_peak_tier)


async def update_rp_lose(user_id: int, season_id: str,
                          rp_loss: int, new_tier: str):
    """패배 시 RP 차감 + 전적 원자적 업데이트."""
    pool = await get_db()
    await pool.execute(
        """UPDATE season_records SET
              rp = GREATEST(0, rp - $3),
              tier = $4,
              ranked_losses = ranked_losses + 1,
              ranked_streak = 0
           WHERE user_id = $1 AND season_id = $2""",
        user_id, season_id, rp_loss, new_tier)


async def get_ranked_ranking(season_id: str, limit: int = 20) -> list[dict]:
    """시즌 랭킹 (RP 내림차순)."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT sr.user_id, u.display_name, u.title_emoji,
                  sr.rp, sr.tier, sr.ranked_wins, sr.ranked_losses,
                  sr.best_ranked_streak, sr.peak_rp, sr.peak_tier
           FROM season_records sr
           JOIN users u ON sr.user_id = u.user_id
           WHERE sr.season_id = $1 AND (sr.ranked_wins > 0 OR sr.ranked_losses > 0)
           ORDER BY sr.rp DESC
           LIMIT $2""",
        season_id, limit)
    return [dict(r) for r in rows]


async def get_all_season_records(season_id: str) -> list[dict]:
    """보상 분배용: 시즌 전체 기록 (최소 1전 이상)."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT sr.user_id, sr.rp, sr.tier, sr.peak_tier,
                  sr.ranked_wins, sr.ranked_losses
           FROM season_records sr
           WHERE sr.season_id = $1 AND (sr.ranked_wins + sr.ranked_losses) > 0""",
        season_id)
    return [dict(r) for r in rows]


# ─── Ranked Battle Log ───────────────────────────────────

async def log_ranked_battle(battle_record_id: int, season_id: str,
                             w_rp_before: int, w_rp_after: int,
                             l_rp_before: int, l_rp_after: int,
                             w_tier_before: str, w_tier_after: str,
                             l_tier_before: str, l_tier_after: str):
    pool = await get_db()
    await pool.execute(
        """INSERT INTO ranked_battle_log
              (battle_record_id, season_id,
               winner_rp_before, winner_rp_after, loser_rp_before, loser_rp_after,
               winner_tier_before, winner_tier_after, loser_tier_before, loser_tier_after)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
        battle_record_id, season_id,
        w_rp_before, w_rp_after, l_rp_before, l_rp_after,
        w_tier_before, w_tier_after, l_tier_before, l_tier_after)


# ─── Anti-Abuse ──────────────────────────────────────────

async def get_ranked_battles_today(user_id: int, today_str: str) -> int:
    """오늘 랭크전 횟수."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT COUNT(*) as cnt FROM battle_records
           WHERE (winner_id = $1 OR loser_id = $1)
             AND battle_type = 'ranked'
             AND created_at::date = $2::date""",
        user_id, today_str)
    return row["cnt"] if row else 0


async def get_last_ranked_vs(user_id: int, opponent_id: int) -> object:
    """마지막 랭크전 시각 (같은 상대)."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT created_at FROM battle_records
           WHERE battle_type = 'ranked'
             AND ((winner_id = $1 AND loser_id = $2)
               OR (winner_id = $2 AND loser_id = $1))
           ORDER BY created_at DESC LIMIT 1""",
        user_id, opponent_id)
    return row["created_at"] if row else None


# ─── Defense Shield ──────────────────────────────────────

async def increment_defense_losses(user_id: int, season_id: str):
    """방어 패배 횟수 +1."""
    pool = await get_db()
    await pool.execute(
        """UPDATE season_records SET defense_losses = defense_losses + 1
           WHERE user_id = $1 AND season_id = $2""",
        user_id, season_id)


async def reset_defense_losses(user_id: int, season_id: str):
    """유저가 랭전 시작 시 방어 패배 카운트 리셋."""
    pool = await get_db()
    await pool.execute(
        """UPDATE season_records SET defense_losses = 0
           WHERE user_id = $1 AND season_id = $2""",
        user_id, season_id)


async def get_defense_losses(user_id: int, season_id: str) -> int:
    """방어 연속 패배 횟수 조회."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT defense_losses FROM season_records WHERE user_id = $1 AND season_id = $2",
        user_id, season_id)
    return row["defense_losses"] if row else 0


# ─── Recent Opponents ───────────────────────────────────

async def get_recent_opponents(user_id: int, season_id: str, limit: int = 3) -> list[int]:
    """최근 N경기 상대 유저 ID 목록 (중복 제거 X, 순서 유지)."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT CASE WHEN br.winner_id = $1 THEN br.loser_id ELSE br.winner_id END AS opp
           FROM ranked_battle_log rbl
           JOIN battle_records br ON rbl.battle_record_id = br.id
           WHERE (br.winner_id = $1 OR br.loser_id = $1) AND rbl.season_id = $2
           ORDER BY rbl.id DESC LIMIT $3""",
        user_id, season_id, limit)
    return [r["opp"] for r in rows]


# ─── Matchmaking ────────────────────────────────────────

async def find_matchable_users(season_id: str, tier_keys: list[str],
                                exclude_ids: list[int],
                                defense_shield_limit: int = 5,
                                limit: int = 10) -> list[dict]:
    """매칭 가능한 유저 목록 (인접 티어, 보호쉴드 제외, 최근 상대 제외)."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT sr.user_id, sr.rp, sr.tier
           FROM season_records sr
           WHERE sr.season_id = $1
             AND sr.tier = ANY($2)
             AND sr.user_id != ALL($3)
             AND sr.defense_losses < $4
           ORDER BY RANDOM()
           LIMIT $5""",
        season_id, tier_keys, exclude_ids, defense_shield_limit, limit)
    return [dict(r) for r in rows]


async def find_any_matchable_users(exclude_ids: list[int],
                                    limit: int = 10) -> list[int]:
    """프리시즌 폴백: season_records가 비어있을 때, 유효 팀 보유 유저 직접 조회."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT DISTINCT bt.user_id
           FROM battle_teams bt
           WHERE bt.user_id != ALL($1)
           ORDER BY RANDOM()
           LIMIT $2""",
        exclude_ids, limit)
    return [r["user_id"] for r in rows]


# ─── Arena ───────────────────────────────────────────────

async def register_arena(chat_id: int, chat_name: str, registered_by: int):
    pool = await get_db()
    await pool.execute(
        """INSERT INTO arena_candidates (chat_id, chat_name, registered_by)
           VALUES ($1, $2, $3)
           ON CONFLICT (chat_id) DO UPDATE SET chat_name = $2""",
        chat_id, chat_name, registered_by)


async def get_arena_candidates() -> list[dict]:
    pool = await get_db()
    rows = await pool.fetch("SELECT * FROM arena_candidates ORDER BY registered_at")
    return [dict(r) for r in rows]


async def is_arena(chat_id: int) -> bool:
    """현재 시즌에서 이 채팅방이 아레나인지 확인."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT 1 FROM seasons
           WHERE NOW() BETWEEN starts_at AND ends_at
             AND $1 = ANY(arena_chat_ids)
           LIMIT 1""", chat_id)
    return row is not None


# ─── Challenger Tier ────────────────────────────────────

async def get_users_by_tier(season_id: str, tier: str) -> list[int]:
    """특정 티어의 유저 ID 목록."""
    pool = await get_db()
    rows = await pool.fetch(
        "SELECT user_id FROM season_records WHERE season_id = $1 AND tier = $2",
        season_id, tier)
    return [r["user_id"] for r in rows]


async def update_tier(user_id: int, season_id: str, new_tier: str):
    """유저의 티어만 변경 (챌린저 승급/강등용)."""
    pool = await get_db()
    await pool.execute(
        "UPDATE season_records SET tier = $3 WHERE user_id = $1 AND season_id = $2",
        user_id, season_id, new_tier)
