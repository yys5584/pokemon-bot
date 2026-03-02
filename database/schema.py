"""Database schema creation for PostgreSQL."""

from database.connection import get_db

TABLES = [
    # Pokemon master data (251 seed rows)
    """
    CREATE TABLE IF NOT EXISTS pokemon_master (
        id INTEGER PRIMARY KEY,
        name_ko TEXT NOT NULL,
        name_en TEXT NOT NULL,
        emoji TEXT NOT NULL DEFAULT '❓',
        rarity TEXT NOT NULL CHECK(rarity IN ('common','rare','epic','legendary')),
        catch_rate DOUBLE PRECISION NOT NULL DEFAULT 0.5,
        evolves_from INTEGER,
        evolves_to INTEGER,
        evolution_method TEXT DEFAULT 'friendship'
            CHECK(evolution_method IN ('friendship','trade','none'))
    )
    """,

    # Registered users
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        username TEXT,
        display_name TEXT NOT NULL DEFAULT '트레이너',
        title TEXT DEFAULT '',
        title_emoji TEXT DEFAULT '',
        master_balls INTEGER NOT NULL DEFAULT 0,
        registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,

    # User's caught Pokemon collection
    """
    CREATE TABLE IF NOT EXISTS user_pokemon (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users(user_id),
        pokemon_id INTEGER NOT NULL REFERENCES pokemon_master(id),
        nickname TEXT DEFAULT NULL,
        friendship INTEGER NOT NULL DEFAULT 0
            CHECK(friendship >= 0 AND friendship <= 5),
        caught_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        caught_in_chat_id BIGINT,
        is_active INTEGER NOT NULL DEFAULT 1,
        fed_today INTEGER NOT NULL DEFAULT 0,
        played_today INTEGER NOT NULL DEFAULT 0
    )
    """,

    "CREATE INDEX IF NOT EXISTS idx_user_pokemon_user ON user_pokemon(user_id, is_active)",
    "CREATE INDEX IF NOT EXISTS idx_user_pokemon_dex ON user_pokemon(user_id, pokemon_id)",

    # Pokedex completion tracking
    """
    CREATE TABLE IF NOT EXISTS pokedex (
        user_id BIGINT NOT NULL REFERENCES users(user_id),
        pokemon_id INTEGER NOT NULL REFERENCES pokemon_master(id),
        method TEXT NOT NULL DEFAULT 'catch'
            CHECK(method IN ('catch','evolve','trade')),
        first_caught_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (user_id, pokemon_id)
    )
    """,

    # Chat rooms
    """
    CREATE TABLE IF NOT EXISTS chat_rooms (
        chat_id BIGINT PRIMARY KEY,
        chat_title TEXT,
        member_count INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_spawn_at TIMESTAMPTZ,
        daily_spawn_count INTEGER NOT NULL DEFAULT 0,
        spawns_today_target INTEGER NOT NULL DEFAULT 0,
        spawn_multiplier DOUBLE PRECISION NOT NULL DEFAULT 1.0,
        force_spawn_count INTEGER NOT NULL DEFAULT 0
    )
    """,

    # Active spawn sessions
    """
    CREATE TABLE IF NOT EXISTS spawn_sessions (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL REFERENCES chat_rooms(chat_id),
        pokemon_id INTEGER NOT NULL REFERENCES pokemon_master(id),
        spawned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        expires_at TIMESTAMPTZ NOT NULL,
        is_resolved INTEGER NOT NULL DEFAULT 0,
        caught_by_user_id BIGINT REFERENCES users(user_id),
        message_id BIGINT
    )
    """,

    "CREATE INDEX IF NOT EXISTS idx_spawn_active ON spawn_sessions(chat_id, is_resolved)",

    # Catch attempts within a spawn session
    """
    CREATE TABLE IF NOT EXISTS catch_attempts (
        id SERIAL PRIMARY KEY,
        session_id INTEGER NOT NULL REFERENCES spawn_sessions(id),
        user_id BIGINT NOT NULL REFERENCES users(user_id),
        used_master_ball INTEGER NOT NULL DEFAULT 0,
        attempted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,

    "CREATE INDEX IF NOT EXISTS idx_catch_session ON catch_attempts(session_id)",

    # Daily catch limits
    """
    CREATE TABLE IF NOT EXISTS catch_limits (
        user_id BIGINT NOT NULL REFERENCES users(user_id),
        date TEXT NOT NULL,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        consecutive_catches INTEGER NOT NULL DEFAULT 0,
        bonus_catches INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, date)
    )
    """,

    # Spawn log for /로그
    """
    CREATE TABLE IF NOT EXISTS spawn_log (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        pokemon_id INTEGER NOT NULL,
        pokemon_name TEXT NOT NULL,
        pokemon_emoji TEXT NOT NULL DEFAULT '',
        rarity TEXT NOT NULL,
        spawned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        caught_by_user_id BIGINT,
        caught_by_name TEXT,
        participants INTEGER NOT NULL DEFAULT 0
    )
    """,

    # Performance indexes for spawn_log
    "CREATE INDEX IF NOT EXISTS idx_spawn_log_chat ON spawn_log(chat_id, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_spawn_log_chat_pokemon ON spawn_log(chat_id, pokemon_id)",

    # Performance indexes for trades
    "CREATE INDEX IF NOT EXISTS idx_trades_to_user ON trades(to_user_id, status)",

    # Performance indexes for events
    "CREATE INDEX IF NOT EXISTS idx_events_active ON events(active, end_time)",

    # Performance index for spawn sessions expiry
    "CREATE INDEX IF NOT EXISTS idx_spawn_sessions_expires ON spawn_sessions(chat_id, is_resolved, expires_at)",

    # Chat activity tracking
    """
    CREATE TABLE IF NOT EXISTS chat_activity (
        chat_id BIGINT NOT NULL,
        hour_bucket TEXT NOT NULL,
        message_count INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (chat_id, hour_bucket)
    )
    """,

    # Events
    """
    CREATE TABLE IF NOT EXISTS events (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        event_type TEXT NOT NULL
            CHECK(event_type IN ('spawn_boost','catch_boost','rarity_boost','pokemon_boost','friendship_boost')),
        multiplier DOUBLE PRECISION NOT NULL DEFAULT 2.0,
        target TEXT,
        description TEXT,
        start_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        end_time TIMESTAMPTZ NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_by BIGINT
    )
    """,

    # User unlocked titles
    """
    CREATE TABLE IF NOT EXISTS user_titles (
        user_id BIGINT NOT NULL REFERENCES users(user_id),
        title_id TEXT NOT NULL,
        unlocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (user_id, title_id)
    )
    """,

    # User title stats (for tracking unlock conditions)
    """
    CREATE TABLE IF NOT EXISTS user_title_stats (
        user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
        catch_fail_count INTEGER NOT NULL DEFAULT 0,
        midnight_catch_count INTEGER NOT NULL DEFAULT 0,
        master_ball_used INTEGER NOT NULL DEFAULT 0,
        love_count INTEGER NOT NULL DEFAULT 0,
        login_streak INTEGER NOT NULL DEFAULT 0,
        last_active_date TEXT DEFAULT NULL
    )
    """,

    # Trade offers
    """
    CREATE TABLE IF NOT EXISTS trades (
        id SERIAL PRIMARY KEY,
        from_user_id BIGINT NOT NULL REFERENCES users(user_id),
        to_user_id BIGINT NOT NULL REFERENCES users(user_id),
        offer_pokemon_instance_id INTEGER NOT NULL REFERENCES user_pokemon(id),
        request_pokemon_name TEXT,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK(status IN ('pending','accepted','rejected','cancelled')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        resolved_at TIMESTAMPTZ
    )
    """,
]


BATTLE_TABLES = [
    # Battle teams (up to 6 pokemon per user)
    """
    CREATE TABLE IF NOT EXISTS battle_teams (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users(user_id),
        slot INTEGER NOT NULL CHECK(slot BETWEEN 1 AND 6),
        pokemon_instance_id INTEGER NOT NULL REFERENCES user_pokemon(id),
        UNIQUE(user_id, slot),
        UNIQUE(user_id, pokemon_instance_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_battle_teams_user ON battle_teams(user_id)",

    # Battle challenges (pending/accepted/declined/expired)
    """
    CREATE TABLE IF NOT EXISTS battle_challenges (
        id SERIAL PRIMARY KEY,
        challenger_id BIGINT NOT NULL REFERENCES users(user_id),
        defender_id BIGINT NOT NULL REFERENCES users(user_id),
        chat_id BIGINT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK(status IN ('pending', 'accepted', 'declined', 'expired')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        expires_at TIMESTAMPTZ NOT NULL
    )
    """,

    # Battle records (completed battles)
    """
    CREATE TABLE IF NOT EXISTS battle_records (
        id SERIAL PRIMARY KEY,
        challenge_id INTEGER REFERENCES battle_challenges(id),
        chat_id BIGINT NOT NULL,
        winner_id BIGINT REFERENCES users(user_id),
        loser_id BIGINT REFERENCES users(user_id),
        winner_team_size INTEGER NOT NULL,
        loser_team_size INTEGER NOT NULL,
        winner_remaining INTEGER NOT NULL,
        total_rounds INTEGER NOT NULL,
        battle_log TEXT,
        bp_earned INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_battle_records_winner ON battle_records(winner_id)",
    "CREATE INDEX IF NOT EXISTS idx_battle_records_loser ON battle_records(loser_id)",

    # BP purchase log (persistent daily limit tracking)
    """
    CREATE TABLE IF NOT EXISTS bp_purchase_log (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users(user_id),
        item TEXT NOT NULL,
        amount INTEGER NOT NULL DEFAULT 1,
        purchased_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_bp_purchase_log_user_date ON bp_purchase_log(user_id, purchased_at)",
]


# Migrations for adding battle system columns to existing tables
BATTLE_MIGRATIONS = [
    "ALTER TABLE pokemon_master ADD COLUMN pokemon_type TEXT NOT NULL DEFAULT 'normal'",
    "ALTER TABLE pokemon_master ADD COLUMN stat_type TEXT NOT NULL DEFAULT 'balanced'",
    "ALTER TABLE users ADD COLUMN partner_pokemon_id INTEGER",
    "ALTER TABLE users ADD COLUMN battle_wins INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE users ADD COLUMN battle_losses INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE users ADD COLUMN battle_streak INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE users ADD COLUMN best_streak INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE users ADD COLUMN battle_points INTEGER NOT NULL DEFAULT 0",
]


async def create_tables():
    """Create all tables."""
    pool = await get_db()
    for sql in TABLES:
        await pool.execute(sql)
    # Battle tables
    for sql in BATTLE_TABLES:
        await pool.execute(sql)
    # Run battle migrations (ignore if already applied)
    for mig in BATTLE_MIGRATIONS:
        try:
            await pool.execute(mig)
        except Exception:
            pass
