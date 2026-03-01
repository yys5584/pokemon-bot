"""Database schema creation."""

from database.connection import get_db

TABLES = [
    # Pokemon master data (151 seed rows)
    """
    CREATE TABLE IF NOT EXISTS pokemon_master (
        id INTEGER PRIMARY KEY,
        name_ko TEXT NOT NULL,
        name_en TEXT NOT NULL,
        emoji TEXT NOT NULL DEFAULT '❓',
        rarity TEXT NOT NULL CHECK(rarity IN ('common','rare','epic','legendary')),
        catch_rate REAL NOT NULL DEFAULT 0.5,
        evolves_from INTEGER,
        evolves_to INTEGER,
        evolution_method TEXT DEFAULT 'friendship'
            CHECK(evolution_method IN ('friendship','trade','none'))
    )
    """,

    # Registered users
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        display_name TEXT NOT NULL DEFAULT '트레이너',
        title TEXT DEFAULT '',
        title_emoji TEXT DEFAULT '',
        registered_at TEXT NOT NULL DEFAULT (datetime('now')),
        last_active_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,

    # User's caught Pokemon collection
    """
    CREATE TABLE IF NOT EXISTS user_pokemon (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(user_id),
        pokemon_id INTEGER NOT NULL REFERENCES pokemon_master(id),
        nickname TEXT DEFAULT NULL,
        friendship INTEGER NOT NULL DEFAULT 0
            CHECK(friendship >= 0 AND friendship <= 5),
        caught_at TEXT NOT NULL DEFAULT (datetime('now')),
        caught_in_chat_id INTEGER,
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
        user_id INTEGER NOT NULL REFERENCES users(user_id),
        pokemon_id INTEGER NOT NULL REFERENCES pokemon_master(id),
        method TEXT NOT NULL DEFAULT 'catch'
            CHECK(method IN ('catch','evolve','trade')),
        first_caught_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (user_id, pokemon_id)
    )
    """,

    # Chat rooms
    """
    CREATE TABLE IF NOT EXISTS chat_rooms (
        chat_id INTEGER PRIMARY KEY,
        chat_title TEXT,
        member_count INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        joined_at TEXT NOT NULL DEFAULT (datetime('now')),
        last_spawn_at TEXT,
        daily_spawn_count INTEGER NOT NULL DEFAULT 0,
        spawns_today_target INTEGER NOT NULL DEFAULT 0,
        spawn_multiplier REAL NOT NULL DEFAULT 1.0
    )
    """,

    # Active spawn sessions
    """
    CREATE TABLE IF NOT EXISTS spawn_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL REFERENCES chat_rooms(chat_id),
        pokemon_id INTEGER NOT NULL REFERENCES pokemon_master(id),
        spawned_at TEXT NOT NULL DEFAULT (datetime('now')),
        expires_at TEXT NOT NULL,
        is_resolved INTEGER NOT NULL DEFAULT 0,
        caught_by_user_id INTEGER REFERENCES users(user_id),
        message_id INTEGER
    )
    """,

    "CREATE INDEX IF NOT EXISTS idx_spawn_active ON spawn_sessions(chat_id, is_resolved)",

    # Catch attempts within a spawn session
    """
    CREATE TABLE IF NOT EXISTS catch_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL REFERENCES spawn_sessions(id),
        user_id INTEGER NOT NULL REFERENCES users(user_id),
        attempted_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,

    "CREATE INDEX IF NOT EXISTS idx_catch_session ON catch_attempts(session_id)",

    # Daily catch limits
    """
    CREATE TABLE IF NOT EXISTS catch_limits (
        user_id INTEGER NOT NULL REFERENCES users(user_id),
        date TEXT NOT NULL,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        consecutive_catches INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, date)
    )
    """,

    # Spawn log for /로그
    """
    CREATE TABLE IF NOT EXISTS spawn_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        pokemon_id INTEGER NOT NULL,
        pokemon_name TEXT NOT NULL,
        pokemon_emoji TEXT NOT NULL DEFAULT '',
        rarity TEXT NOT NULL,
        spawned_at TEXT NOT NULL DEFAULT (datetime('now')),
        caught_by_user_id INTEGER,
        caught_by_name TEXT,
        participants INTEGER NOT NULL DEFAULT 0
    )
    """,

    # Chat activity tracking
    """
    CREATE TABLE IF NOT EXISTS chat_activity (
        chat_id INTEGER NOT NULL,
        hour_bucket TEXT NOT NULL,
        message_count INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (chat_id, hour_bucket)
    )
    """,

    # Events
    """
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        event_type TEXT NOT NULL
            CHECK(event_type IN ('spawn_boost','catch_boost','rarity_boost','pokemon_boost','friendship_boost')),
        multiplier REAL NOT NULL DEFAULT 2.0,
        target TEXT,
        description TEXT,
        start_time TEXT NOT NULL DEFAULT (datetime('now')),
        end_time TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_by INTEGER
    )
    """,

    # User unlocked titles
    """
    CREATE TABLE IF NOT EXISTS user_titles (
        user_id INTEGER NOT NULL REFERENCES users(user_id),
        title_id TEXT NOT NULL,
        unlocked_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (user_id, title_id)
    )
    """,

    # User title stats (for tracking unlock conditions)
    """
    CREATE TABLE IF NOT EXISTS user_title_stats (
        user_id INTEGER PRIMARY KEY REFERENCES users(user_id),
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
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user_id INTEGER NOT NULL REFERENCES users(user_id),
        to_user_id INTEGER NOT NULL REFERENCES users(user_id),
        offer_pokemon_instance_id INTEGER NOT NULL REFERENCES user_pokemon(id),
        request_pokemon_name TEXT,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK(status IN ('pending','accepted','rejected','cancelled')),
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        resolved_at TEXT
    )
    """,
]


MIGRATIONS = [
    # Add spawn_multiplier to existing chat_rooms
    "ALTER TABLE chat_rooms ADD COLUMN spawn_multiplier REAL NOT NULL DEFAULT 1.0",
    # Add master_balls to users
    "ALTER TABLE users ADD COLUMN master_balls INTEGER NOT NULL DEFAULT 0",
    # Add used_master_ball to catch_attempts
    "ALTER TABLE catch_attempts ADD COLUMN used_master_ball INTEGER NOT NULL DEFAULT 0",
    # Add bonus_catches to catch_limits for easter egg
    "ALTER TABLE catch_limits ADD COLUMN bonus_catches INTEGER NOT NULL DEFAULT 0",
    # Add force_spawn_count to chat_rooms
    "ALTER TABLE chat_rooms ADD COLUMN force_spawn_count INTEGER NOT NULL DEFAULT 0",
]


async def create_tables():
    """Create all tables."""
    db = await get_db()
    for sql in TABLES:
        await db.execute(sql)
    # Run migrations (ignore if already applied)
    for mig in MIGRATIONS:
        try:
            await db.execute(mig)
        except Exception:
            pass
    await db.commit()
