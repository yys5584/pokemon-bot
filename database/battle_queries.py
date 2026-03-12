"""Battle system database queries (PostgreSQL / asyncpg)."""

from database.connection import get_db


# ============================================================
# Partner Pokemon
# ============================================================

async def set_partner(user_id: int, pokemon_instance_id: int | None):
    """Set a user's partner pokemon (or clear with None)."""
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET partner_pokemon_id = $1 WHERE user_id = $2",
        pokemon_instance_id, user_id,
    )


async def get_partner(user_id: int) -> dict | None:
    """Get user's current partner pokemon details."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT up.id as instance_id, up.pokemon_id, up.friendship,
                  up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd,
                  pm.name_ko, pm.emoji, pm.rarity,
                  pm.pokemon_type, pm.stat_type
           FROM users u
           JOIN user_pokemon up ON u.partner_pokemon_id = up.id
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE u.user_id = $1 AND up.is_active = 1""",
        user_id,
    )
    return dict(row) if row else None


# ============================================================
# Battle Team
# ============================================================

async def get_battle_team(user_id: int, team_number: int | None = None) -> list[dict]:
    """Get user's battle team in slot order. If team_number is None, use active_team."""
    pool = await get_db()
    if team_number is None:
        row = await pool.fetchrow("SELECT active_team FROM users WHERE user_id = $1", user_id)
        team_number = row["active_team"] if row else 1
    rows = await pool.fetch(
        """SELECT bt.slot, bt.pokemon_instance_id,
                  up.pokemon_id, up.friendship, up.is_shiny,
                  up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd,
                  pm.name_ko, pm.emoji, pm.rarity,
                  pm.pokemon_type, pm.stat_type
           FROM battle_teams bt
           JOIN user_pokemon up ON bt.pokemon_instance_id = up.id
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE bt.user_id = $1 AND bt.team_number = $2 AND up.is_active = 1
           ORDER BY bt.slot""",
        user_id, team_number,
    )
    return [dict(r) for r in rows]


async def set_battle_team(user_id: int, instance_ids: list[int], team_number: int = 1):
    """Set user's battle team. Replaces existing team for given team_number."""
    pool = await get_db()
    await pool.execute(
        "DELETE FROM battle_teams WHERE user_id = $1 AND team_number = $2",
        user_id, team_number,
    )
    await pool.executemany(
        """INSERT INTO battle_teams (user_id, slot, pokemon_instance_id, team_number)
           VALUES ($1, $2, $3, $4)""",
        [(user_id, slot, inst_id, team_number)
         for slot, inst_id in enumerate(instance_ids, 1)],
    )


async def clear_battle_team(user_id: int, team_number: int | None = None):
    """Remove pokemon from user's battle team. If team_number is None, clear all."""
    pool = await get_db()
    if team_number is None:
        await pool.execute("DELETE FROM battle_teams WHERE user_id = $1", user_id)
    else:
        await pool.execute(
            "DELETE FROM battle_teams WHERE user_id = $1 AND team_number = $2",
            user_id, team_number,
        )


async def set_active_team(user_id: int, team_number: int):
    """Set which team to use in battles (1 or 2)."""
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET active_team = $1 WHERE user_id = $2",
        team_number, user_id,
    )


async def get_active_team_number(user_id: int) -> int:
    """Get user's active team number."""
    pool = await get_db()
    row = await pool.fetchrow("SELECT active_team FROM users WHERE user_id = $1", user_id)
    return row["active_team"] if row else 1


async def swap_teams(user_id: int):
    """Swap team 1 and team 2 entirely, then flip active_team.

    DELETE+INSERT 방식으로 unique index (user_id, team_number, slot) 충돌 회피.
    """
    pool = await get_db()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # 양쪽 팀 데이터 조회
            t1 = await conn.fetch(
                "SELECT slot, pokemon_instance_id FROM battle_teams "
                "WHERE user_id = $1 AND team_number = 1", user_id)
            t2 = await conn.fetch(
                "SELECT slot, pokemon_instance_id FROM battle_teams "
                "WHERE user_id = $1 AND team_number = 2", user_id)

            # 삭제
            await conn.execute(
                "DELETE FROM battle_teams WHERE user_id = $1 AND team_number IN (1, 2)",
                user_id)

            # 재삽입: 팀1 → 팀2, 팀2 → 팀1
            for row in t1:
                await conn.execute(
                    "INSERT INTO battle_teams (user_id, team_number, slot, pokemon_instance_id) "
                    "VALUES ($1, 2, $2, $3)", user_id, row["slot"], row["pokemon_instance_id"])
            for row in t2:
                await conn.execute(
                    "INSERT INTO battle_teams (user_id, team_number, slot, pokemon_instance_id) "
                    "VALUES ($1, 1, $2, $3)", user_id, row["slot"], row["pokemon_instance_id"])

    # Flip active team
    active = await get_active_team_number(user_id)
    new_active = 2 if active == 1 else 1
    await set_active_team(user_id, new_active)


async def validate_team_pokemon(user_id: int, instance_ids: list[int]) -> list[dict]:
    """Validate that all instance IDs belong to the user and are active.
    Returns list of valid pokemon dicts."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT up.id as instance_id, up.pokemon_id, up.friendship,
                  up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd,
                  pm.name_ko, pm.emoji, pm.rarity,
                  pm.pokemon_type, pm.stat_type
           FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.user_id = $1 AND up.is_active = 1 AND up.id = ANY($2)""",
        user_id, instance_ids,
    )
    return [dict(r) for r in rows]


# ============================================================
# Battle Challenges
# ============================================================

async def create_challenge(
    challenger_id: int, defender_id: int, chat_id: int, expires_at,
    bet_type: str | None = None, bet_amount: int = 0,
    battle_type: str = "normal",
) -> int:
    """Create a battle challenge. Returns challenge ID.
    bet_type: None (normal battle), 'bp' or 'masterball' (yacha).
    battle_type: 'normal', 'ranked', 'yacha'.
    """
    pool = await get_db()
    row = await pool.fetchrow(
        """INSERT INTO battle_challenges
               (challenger_id, defender_id, chat_id, expires_at, bet_type, bet_amount, battle_type)
           VALUES ($1, $2, $3, $4, $5, $6, $7)
           RETURNING id""",
        challenger_id, defender_id, chat_id, expires_at, bet_type, bet_amount, battle_type,
    )
    return row["id"]


async def get_pending_challenge(challenger_id: int, defender_id: int) -> dict | None:
    """Check for existing pending challenge between two users."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT * FROM battle_challenges
           WHERE challenger_id = $1 AND defender_id = $2
             AND status = 'pending' AND expires_at > NOW()""",
        challenger_id, defender_id,
    )
    return dict(row) if row else None


async def get_challenge_by_id(challenge_id: int) -> dict | None:
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT * FROM battle_challenges WHERE id = $1",
        challenge_id,
    )
    return dict(row) if row else None


async def update_challenge_status(challenge_id: int, status: str):
    pool = await get_db()
    await pool.execute(
        "UPDATE battle_challenges SET status = $1 WHERE id = $2",
        status, challenge_id,
    )


async def expire_old_challenges():
    """Expire challenges past their deadline."""
    pool = await get_db()
    await pool.execute(
        """UPDATE battle_challenges
           SET status = 'expired'
           WHERE status = 'pending' AND expires_at <= NOW()"""
    )


async def get_last_battle_time(user_id: int, opponent_id: int) -> str | None:
    """Get the time of the last completed battle between two users."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT created_at FROM battle_records
           WHERE (winner_id = $1 AND loser_id = $2)
              OR (winner_id = $2 AND loser_id = $1)
           ORDER BY created_at DESC LIMIT 1""",
        user_id, opponent_id,
    )
    return str(row["created_at"]) if row else None


async def get_last_battle_time_any(user_id: int) -> str | None:
    """Get the time of the user's last battle (any opponent)."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT created_at FROM battle_records
           WHERE winner_id = $1 OR loser_id = $1
           ORDER BY created_at DESC LIMIT 1""",
        user_id,
    )
    return str(row["created_at"]) if row else None


# ============================================================
# Battle Records
# ============================================================

async def record_battle(
    challenge_id: int | None,
    chat_id: int,
    winner_id: int,
    loser_id: int,
    winner_team_size: int,
    loser_team_size: int,
    winner_remaining: int,
    total_rounds: int,
    battle_log: str,
    bp_earned: int,
    battle_type: str = "normal",
) -> int:
    """Record a completed battle. Returns record ID."""
    pool = await get_db()
    row = await pool.fetchrow(
        """INSERT INTO battle_records
               (challenge_id, chat_id, winner_id, loser_id,
                winner_team_size, loser_team_size, winner_remaining,
                total_rounds, battle_log, bp_earned, battle_type)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
           RETURNING id""",
        challenge_id, chat_id, winner_id, loser_id,
        winner_team_size, loser_team_size, winner_remaining,
        total_rounds, battle_log, bp_earned, battle_type,
    )
    return row["id"]


async def update_battle_stats_win(user_id: int, bp: int):
    """Update winner's stats after a battle."""
    pool = await get_db()
    await pool.execute(
        """UPDATE users SET
               battle_wins = battle_wins + 1,
               battle_streak = battle_streak + 1,
               best_streak = GREATEST(best_streak, battle_streak + 1),
               battle_points = battle_points + $1
           WHERE user_id = $2""",
        bp, user_id,
    )


async def update_battle_stats_lose(user_id: int, bp: int):
    """Update loser's stats after a battle."""
    pool = await get_db()
    await pool.execute(
        """UPDATE users SET
               battle_losses = battle_losses + 1,
               battle_streak = 0,
               battle_points = battle_points + $1
           WHERE user_id = $2""",
        bp, user_id,
    )


async def get_battle_stats(user_id: int) -> dict:
    """Get user's battle stats."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT battle_wins, battle_losses, battle_streak,
                  best_streak, battle_points
           FROM users WHERE user_id = $1""",
        user_id,
    )
    if row:
        return dict(row)
    return {
        "battle_wins": 0, "battle_losses": 0,
        "battle_streak": 0, "best_streak": 0, "battle_points": 0,
    }


async def get_battle_ranking(limit: int = 10) -> list[dict]:
    """Get battle ranking by BP (primary) and wins (secondary)."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT u.user_id, u.display_name, u.title, u.title_emoji,
                  u.battle_wins, u.battle_losses, u.best_streak,
                  u.battle_points
           FROM users u
           WHERE u.battle_points > 0 OR u.battle_wins > 0 OR u.battle_losses > 0
           ORDER BY u.battle_points DESC, u.battle_wins DESC
           LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_winrate_ranking(limit: int = 5, min_games: int = 5) -> list[dict]:
    """Get battle ranking by win rate (min_games required)."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT u.user_id, u.display_name, u.username,
                  u.title, u.title_emoji,
                  u.battle_wins, u.battle_losses,
                  (u.battle_wins + u.battle_losses) AS total_games,
                  ROUND(u.battle_wins * 100.0
                        / NULLIF(u.battle_wins + u.battle_losses, 0), 1)
                      AS winrate
           FROM users u
           WHERE (u.battle_wins + u.battle_losses) >= $2
           ORDER BY winrate DESC, u.battle_wins DESC
           LIMIT $1""",
        limit,
        min_games,
    )
    return [dict(r) for r in rows]


# ============================================================
# BP (Battle Points)
# ============================================================

async def get_bp(user_id: int) -> int:
    """Get user's current BP."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT battle_points FROM users WHERE user_id = $1",
        user_id,
    )
    return row["battle_points"] if row else 0


async def spend_bp(user_id: int, amount: int) -> bool:
    """Spend BP. Returns True if successful."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT battle_points FROM users WHERE user_id = $1",
        user_id,
    )
    if not row or row["battle_points"] < amount:
        return False
    await pool.execute(
        "UPDATE users SET battle_points = battle_points - $1 WHERE user_id = $2",
        amount, user_id,
    )
    return True


async def add_bp(user_id: int, amount: int):
    """Add BP to a user (for yacha winnings, etc.)."""
    pool = await get_db()
    await pool.execute(
        "UPDATE users SET battle_points = battle_points + $1 WHERE user_id = $2",
        amount, user_id,
    )


# ============================================================
# Pokemon Battle Data Helper
# ============================================================

async def get_pokemon_with_battle_data(instance_id: int) -> dict | None:
    """Get a pokemon instance with all battle-relevant data."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT up.id as instance_id, up.user_id, up.pokemon_id,
                  up.friendship, up.is_active,
                  up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd,
                  pm.name_ko, pm.emoji, pm.rarity,
                  pm.pokemon_type, pm.stat_type
           FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.id = $1""",
        instance_id,
    )
    return dict(row) if row else None


async def get_user_pokemon_for_battle(user_id: int) -> list[dict]:
    """Get all user's active pokemon with battle data (for team selection)."""
    pool = await get_db()
    rows = await pool.fetch(
        """SELECT up.id as instance_id, up.pokemon_id,
                  up.friendship, up.iv_hp, up.iv_atk, up.iv_def,
                  up.iv_spa, up.iv_spdef, up.iv_spd,
                  pm.name_ko, pm.emoji, pm.rarity,
                  pm.pokemon_type, pm.stat_type
           FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.user_id = $1 AND up.is_active = 1
           ORDER BY up.id""",
        user_id,
    )
    return [dict(r) for r in rows]


# ============================================================
# BP Purchase Log (persistent daily limit)
# ============================================================

async def get_bp_purchases_today(user_id: int, item: str) -> int:
    """Get how many of an item a user purchased today."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT COALESCE(SUM(amount), 0) as total
           FROM bp_purchase_log
           WHERE user_id = $1 AND item = $2
             AND (purchased_at AT TIME ZONE 'Asia/Seoul')::date = (NOW() AT TIME ZONE 'Asia/Seoul')::date""",
        user_id, item,
    )
    return row["total"] if row else 0


async def log_bp_purchase(user_id: int, item: str, amount: int = 1):
    """Log a BP shop purchase."""
    pool = await get_db()
    await pool.execute(
        """INSERT INTO bp_purchase_log (user_id, item, amount)
           VALUES ($1, $2, $3)""",
        user_id, item, amount,
    )


# ============================================================
# Yacha (야차 - Betting Battle) Queries
# ============================================================

async def get_last_yacha_time(user_id: int, opponent_id: int) -> str | None:
    """Get time of the last yacha battle between two users."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT br.created_at FROM battle_records br
           JOIN battle_challenges bc ON br.challenge_id = bc.id
           WHERE bc.bet_type IS NOT NULL
             AND ((br.winner_id = $1 AND br.loser_id = $2)
               OR (br.winner_id = $2 AND br.loser_id = $1))
           ORDER BY br.created_at DESC LIMIT 1""",
        user_id, opponent_id,
    )
    return str(row["created_at"]) if row else None


async def get_last_yacha_time_any(user_id: int) -> str | None:
    """Get time of the user's last yacha battle (any opponent)."""
    pool = await get_db()
    row = await pool.fetchrow(
        """SELECT br.created_at FROM battle_records br
           JOIN battle_challenges bc ON br.challenge_id = bc.id
           WHERE bc.bet_type IS NOT NULL
             AND (br.winner_id = $1 OR br.loser_id = $1)
           ORDER BY br.created_at DESC LIMIT 1""",
        user_id,
    )
    return str(row["created_at"]) if row else None


async def save_battle_pokemon_stats(battle_record_id: int, stats: list[dict]):
    """Save per-pokemon battle stats for analytics."""
    if not stats:
        return
    pool = await get_db()
    for s in stats:
        await pool.execute(
            """INSERT INTO battle_pokemon_stats
                   (battle_record_id, battle_type, user_id, pokemon_id, rarity, is_shiny,
                    iv_total, damage_dealt, damage_taken, kills, deaths, turns_alive,
                    crits_landed, crits_received, skills_activated,
                    super_effective_hits, not_effective_hits, side, won)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)""",
            battle_record_id, s["battle_type"], s["user_id"], s["pokemon_id"],
            s["rarity"], s["is_shiny"], s["iv_total"],
            s["damage_dealt"], s["damage_taken"], s["kills"], s["deaths"],
            s["turns_alive"], s["crits_landed"], s["crits_received"],
            s["skills_activated"], s["super_effective_hits"], s["not_effective_hits"],
            s["side"], s["won"],
        )


async def use_master_balls(user_id: int, count: int) -> bool:
    """Use multiple master balls. Returns True if successful (atomic)."""
    pool = await get_db()
    row = await pool.fetchrow(
        """UPDATE users SET master_balls = master_balls - $1
           WHERE user_id = $2 AND master_balls >= $1
           RETURNING master_balls""",
        count, user_id,
    )
    return row is not None
