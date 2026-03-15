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
                                peak_rp: int = 0, peak_tier: str = "bronze",
                                placement_done: bool = False,
                                placement_games: int = 0):
    """시즌 기록 생성 또는 업데이트."""
    pool = await get_db()
    await pool.execute(
        """INSERT INTO season_records
              (user_id, season_id, rp, tier, ranked_wins, ranked_losses,
               ranked_streak, best_ranked_streak, peak_rp, peak_tier,
               placement_done, placement_games)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
           ON CONFLICT (user_id, season_id) DO UPDATE SET
              rp = $3, tier = $4, ranked_wins = $5, ranked_losses = $6,
              ranked_streak = $7, best_ranked_streak = $8, peak_rp = $9, peak_tier = $10,
              placement_done = $11, placement_games = $12""",
        user_id, season_id, rp, tier, wins, losses,
        streak, best_streak, peak_rp, peak_tier,
        placement_done, placement_games)


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
    """시즌 랭킹 (RP 내림차순). 배치/MMR 정보 포함."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT sr.user_id, u.display_name, u.title_emoji,
                  sr.rp, sr.tier, sr.ranked_wins, sr.ranked_losses,
                  sr.best_ranked_streak, sr.peak_rp, sr.peak_tier,
                  sr.placement_done, sr.placement_games,
                  COALESCE(um.mmr, 1200) AS mmr
           FROM season_records sr
           JOIN users u ON sr.user_id = u.user_id
           LEFT JOIN user_mmr um ON sr.user_id = um.user_id
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
                             l_tier_before: str, l_tier_after: str,
                             w_mmr_before: int = None, w_mmr_after: int = None,
                             l_mmr_before: int = None, l_mmr_after: int = None):
    pool = await get_db()
    await pool.execute(
        """INSERT INTO ranked_battle_log
              (battle_record_id, season_id,
               winner_rp_before, winner_rp_after, loser_rp_before, loser_rp_after,
               winner_tier_before, winner_tier_after, loser_tier_before, loser_tier_after,
               winner_mmr_before, winner_mmr_after, loser_mmr_before, loser_mmr_after)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)""",
        battle_record_id, season_id,
        w_rp_before, w_rp_after, l_rp_before, l_rp_after,
        w_tier_before, w_tier_after, l_tier_before, l_tier_after,
        w_mmr_before, w_mmr_after, l_mmr_before, l_mmr_after)


# ─── Anti-Abuse ──────────────────────────────────────────

async def get_ranked_battles_today(user_id: int, today) -> int:
    """오늘 랭크전 횟수. today: KST date 객체."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT COUNT(*) as cnt FROM battle_records
           WHERE (winner_id = $1 OR loser_id = $1)
             AND battle_type = 'ranked'
             AND (created_at AT TIME ZONE 'Asia/Seoul')::date = $2""",
        user_id, today)
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
        """SELECT user_id FROM (
               SELECT DISTINCT bt.user_id
               FROM battle_teams bt
               WHERE bt.user_id != ALL($1)
           ) sub
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


# ─── MMR (Hidden Elo) ─────────────────────────────────

async def get_user_mmr(user_id: int) -> dict:
    """유저 MMR 레코드 조회. 없으면 자동 생성."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT * FROM user_mmr WHERE user_id = $1", user_id)
    if row:
        return dict(row)
    # 자동 생성
    await pool.execute(
        """INSERT INTO user_mmr (user_id, mmr, peak_mmr, games_played)
           VALUES ($1, 1200, 1200, 0)
           ON CONFLICT (user_id) DO NOTHING""", user_id)
    row = await pool.fetchrow(
        "SELECT * FROM user_mmr WHERE user_id = $1", user_id)
    return dict(row) if row else {"user_id": user_id, "mmr": 1200, "peak_mmr": 1200, "games_played": 0}


async def update_user_mmr(user_id: int, new_mmr: int):
    """MMR 업데이트 + 피크 갱신 + games_played 증가."""
    pool = await get_db()
    await pool.execute(
        """UPDATE user_mmr SET
              mmr = $2,
              peak_mmr = GREATEST(peak_mmr, $2),
              games_played = games_played + 1,
              updated_at = NOW()
           WHERE user_id = $1""",
        user_id, new_mmr)


async def soft_reset_all_mmr(reset_factor: float = 0.25):
    """시즌 종료 시 전체 MMR 소프트 리셋. 1200 방향으로 축소."""
    pool = await get_db()
    # new_mmr = 1200 + (mmr - 1200) * (1 - factor)
    # 예: factor=0.25 → mmr=1600 → 1200 + 400*0.75 = 1500
    await pool.execute(
        """UPDATE user_mmr SET
              mmr = 1200 + CAST((mmr - 1200) * (1.0 - $1) AS INT),
              updated_at = NOW()""",
        reset_factor)


# ─── Placement (배치전) ──────────────────────────────

async def increment_placement_games(user_id: int, season_id: str) -> int:
    """배치전 횟수 +1, 새 값 반환."""
    pool = await get_db()
    row = await pool.fetchrow(
        """UPDATE season_records SET placement_games = placement_games + 1
           WHERE user_id = $1 AND season_id = $2
           RETURNING placement_games""",
        user_id, season_id)
    return row["placement_games"] if row else 0


async def set_placement_done(user_id: int, season_id: str,
                              rp: int, tier: str, peak_rp: int, peak_tier: str):
    """배치 완료: tier 배정 + RP 설정."""
    pool = await get_db()
    await pool.execute(
        """UPDATE season_records SET
              placement_done = TRUE,
              rp = $3, tier = $4,
              peak_rp = $5, peak_tier = $6
           WHERE user_id = $1 AND season_id = $2""",
        user_id, season_id, rp, tier, peak_rp, peak_tier)


# ─── Promotion Shield (승급 보호) ─────────────────────

async def set_promo_shield(user_id: int, season_id: str, until):
    """승급 보호 시각 설정."""
    pool = await get_db()
    await pool.execute(
        """UPDATE season_records SET promo_shield_until = $3
           WHERE user_id = $1 AND season_id = $2""",
        user_id, season_id, until)


async def clear_promo_shield(user_id: int, season_id: str):
    """승급 보호 해제 (랭전 재진입 시)."""
    pool = await get_db()
    await pool.execute(
        """UPDATE season_records SET promo_shield_until = NULL
           WHERE user_id = $1 AND season_id = $2""",
        user_id, season_id)


# ─── Last Ranked At (디케이 추적) ─────────────────────

async def update_last_ranked(user_id: int, season_id: str):
    """마지막 랭크전 시각 갱신."""
    pool = await get_db()
    await pool.execute(
        """UPDATE season_records SET last_ranked_at = NOW()
           WHERE user_id = $1 AND season_id = $2""",
        user_id, season_id)


# ─── Decay (디케이) ──────────────────────────────────

async def apply_decay(season_id: str, cutoff, rp_per_day: int,
                       min_rp: int, inactive_days: int) -> list[dict]:
    """마스터+ 유저 중 미플레이 기간 초과자에게 디케이 적용.
    Returns: 디케이된 유저 목록 [{user_id, rp_before, rp_after}]"""
    pool = await get_db()
    # 디케이 대상: 마스터 이상(rp>=1000), 배치 완료, last_ranked_at < cutoff
    rows = await pool.fetch(
        """SELECT user_id, rp, last_ranked_at FROM season_records
           WHERE season_id = $1
             AND rp >= $2
             AND placement_done = TRUE
             AND last_ranked_at IS NOT NULL
             AND last_ranked_at < $3""",
        season_id, min_rp, cutoff)

    results = []
    for row in rows:
        import datetime as dt
        if row["last_ranked_at"].tzinfo is None:
            days_inactive = (cutoff.replace(tzinfo=None) - row["last_ranked_at"]).days
        else:
            days_inactive = (cutoff - row["last_ranked_at"]).days
        decay_amount = rp_per_day * max(0, days_inactive - inactive_days + 1)
        if decay_amount <= 0:
            continue
        new_rp = max(min_rp, row["rp"] - decay_amount)
        if new_rp == row["rp"]:
            continue
        await pool.execute(
            """UPDATE season_records SET rp = $3, tier = $4
               WHERE user_id = $1 AND season_id = $2""",
            row["user_id"], season_id, new_rp, "master")
        results.append({
            "user_id": row["user_id"],
            "rp_before": row["rp"],
            "rp_after": new_rp,
        })
    return results


# ─── MMR-Based Matchmaking ─────────────────────────────

async def find_matchable_users_by_mmr(season_id: str, user_mmr: int,
                                       mmr_range: int, exclude_ids: list[int],
                                       defense_shield_limit: int = 5,
                                       limit: int = 10) -> list[dict]:
    """MMR 범위 내 매칭 가능한 유저 목록."""
    pool = await get_db()
    low = user_mmr - mmr_range
    high = user_mmr + mmr_range
    rows = await pool.fetch(
        """SELECT sr.user_id, sr.rp, sr.tier, sr.placement_done,
                  COALESCE(um.mmr, 1200) AS mmr
           FROM season_records sr
           LEFT JOIN user_mmr um ON sr.user_id = um.user_id
           WHERE sr.season_id = $1
             AND sr.user_id != ALL($2)
             AND sr.defense_losses < $3
             AND COALESCE(um.mmr, 1200) BETWEEN $4 AND $5
           ORDER BY ABS(COALESCE(um.mmr, 1200) - $6)
           LIMIT $7""",
        season_id, exclude_ids, defense_shield_limit,
        low, high, user_mmr, limit)
    return [dict(r) for r in rows]


# ─── Mid-Season Reset ─────────────────────────────────

async def get_all_placed_records(season_id: str) -> list[dict]:
    """배치 완료된 전체 시즌 레코드 (중간 리셋용)."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT sr.user_id, sr.rp, sr.tier, sr.ranked_streak,
                  sr.promo_shield_until,
                  COALESCE(um.mmr, 1200) AS mmr
           FROM season_records sr
           LEFT JOIN user_mmr um ON sr.user_id = um.user_id
           WHERE sr.season_id = $1 AND sr.placement_done = TRUE""",
        season_id)
    return [dict(r) for r in rows]


async def bulk_update_mid_reset(season_id: str, user_id: int,
                                  new_rp: int, new_tier: str):
    """중간 리셋 시 개별 유저 RP/티어 업데이트."""
    pool = await get_db()
    await pool.execute(
        """UPDATE season_records SET
              rp = $3, tier = $4,
              ranked_streak = 0,
              promo_shield_until = NULL
           WHERE user_id = $1 AND season_id = $2""",
        user_id, season_id, new_rp, new_tier)


async def mark_mid_reset_done(season_id: str):
    """중간 리셋 완료 표시."""
    pool = await get_db()
    await pool.execute(
        "UPDATE seasons SET mid_reset_done = TRUE WHERE season_id = $1",
        season_id)
