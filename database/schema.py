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
        rarity TEXT NOT NULL CHECK(rarity IN ('common','rare','epic','legendary','ultra_legendary')),
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
        force_spawn_count INTEGER NOT NULL DEFAULT 0,
        is_arcade INTEGER NOT NULL DEFAULT 0
    )
    """,
    # Migration: add is_arcade column if missing
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'chat_rooms' AND column_name = 'is_arcade'
        ) THEN
            ALTER TABLE chat_rooms ADD COLUMN is_arcade INTEGER NOT NULL DEFAULT 0;
        END IF;
    END $$
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
            CHECK(event_type IN ('spawn_boost','catch_boost','rarity_boost','pokemon_boost','friendship_boost','shiny_boost')),
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
        bet_type TEXT DEFAULT NULL,
        bet_amount INTEGER NOT NULL DEFAULT 0,
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

    # Battle Pokemon Stats (per-pokemon performance analytics)
    """
    CREATE TABLE IF NOT EXISTS battle_pokemon_stats (
        id SERIAL PRIMARY KEY,
        battle_record_id INTEGER REFERENCES battle_records(id) ON DELETE CASCADE,
        battle_type TEXT NOT NULL DEFAULT 'normal',
        user_id BIGINT NOT NULL,
        pokemon_id INTEGER NOT NULL,
        rarity TEXT NOT NULL,
        is_shiny BOOLEAN DEFAULT FALSE,
        iv_total INTEGER DEFAULT 0,
        damage_dealt INTEGER DEFAULT 0,
        damage_taken INTEGER DEFAULT 0,
        kills INTEGER DEFAULT 0,
        deaths INTEGER DEFAULT 0,
        turns_alive INTEGER DEFAULT 0,
        crits_landed INTEGER DEFAULT 0,
        crits_received INTEGER DEFAULT 0,
        skills_activated INTEGER DEFAULT 0,
        super_effective_hits INTEGER DEFAULT 0,
        not_effective_hits INTEGER DEFAULT 0,
        side TEXT NOT NULL,
        won BOOLEAN NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_bps_pokemon ON battle_pokemon_stats(pokemon_id)",
    "CREATE INDEX IF NOT EXISTS idx_bps_battle ON battle_pokemon_stats(battle_record_id)",
    "CREATE INDEX IF NOT EXISTS idx_bps_user ON battle_pokemon_stats(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_bps_created ON battle_pokemon_stats(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_bps_type ON battle_pokemon_stats(battle_type)",

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


TOURNAMENT_MIGRATIONS = [
    "ALTER TABLE user_title_stats ADD COLUMN tournament_wins INTEGER NOT NULL DEFAULT 0",
]

SHOP_MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN force_spawn_tickets INTEGER NOT NULL DEFAULT 0",
]

HYPER_BALL_MIGRATIONS = [
    "ALTER TABLE catch_attempts ADD COLUMN used_hyper_ball INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE users ADD COLUMN hyper_balls INTEGER NOT NULL DEFAULT 0",
]

ARCADE_TICKET_MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN arcade_tickets INTEGER NOT NULL DEFAULT 0",
    # NOTE: DROP TABLE arcade_passes 제거 — 이미 1회 적용됨.
    # 매 재시작마다 실행되면 활성 아케이드 세션이 전부 날아가는 버그 원인이었음.
]

ARCADE_PASS_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS arcade_passes (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        activated_by BIGINT NOT NULL REFERENCES users(user_id),
        activated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        expires_at TIMESTAMPTZ NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_arcade_passes_chat ON arcade_passes(chat_id, is_active, expires_at)",
]

LLM_QUOTA_MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN llm_bonus_quota INTEGER NOT NULL DEFAULT 0",
]

BOT_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS bot_settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
"""

MARKET_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS market_listings (
        id SERIAL PRIMARY KEY,
        seller_id BIGINT NOT NULL REFERENCES users(user_id),
        pokemon_instance_id INTEGER NOT NULL REFERENCES user_pokemon(id),
        pokemon_id INTEGER NOT NULL REFERENCES pokemon_master(id),
        pokemon_name TEXT NOT NULL,
        is_shiny INTEGER NOT NULL DEFAULT 0,
        price_bp INTEGER NOT NULL CHECK(price_bp >= 100),
        status TEXT NOT NULL DEFAULT 'active'
            CHECK(status IN ('active','sold','cancelled','expired')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        buyer_id BIGINT REFERENCES users(user_id),
        sold_at TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_market_active ON market_listings(status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_market_seller ON market_listings(seller_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_market_pokemon ON market_listings(pokemon_id, status)",
]

GROUP_TRADE_MIGRATIONS = [
    "ALTER TABLE trades ADD COLUMN trade_type TEXT NOT NULL DEFAULT 'dm'",
    "ALTER TABLE trades ADD COLUMN chat_id BIGINT DEFAULT NULL",
    "ALTER TABLE trades ADD COLUMN message_id BIGINT DEFAULT NULL",
]

IV_MIGRATIONS = [
    "ALTER TABLE user_pokemon ADD COLUMN iv_hp SMALLINT DEFAULT NULL",
    "ALTER TABLE user_pokemon ADD COLUMN iv_atk SMALLINT DEFAULT NULL",
    "ALTER TABLE user_pokemon ADD COLUMN iv_def SMALLINT DEFAULT NULL",
    "ALTER TABLE user_pokemon ADD COLUMN iv_spa SMALLINT DEFAULT NULL",
    "ALTER TABLE user_pokemon ADD COLUMN iv_spdef SMALLINT DEFAULT NULL",
    "ALTER TABLE user_pokemon ADD COLUMN iv_spd SMALLINT DEFAULT NULL",
]

SHINY_MIGRATIONS = [
    "ALTER TABLE user_pokemon ADD COLUMN is_shiny INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE spawn_sessions ADD COLUMN is_shiny INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE spawn_log ADD COLUMN is_shiny INTEGER NOT NULL DEFAULT 0",
    # 이로치 친밀도 7 허용: CHECK 제약 완화
    "ALTER TABLE user_pokemon DROP CONSTRAINT IF EXISTS user_pokemon_friendship_check",
    "ALTER TABLE user_pokemon ADD CONSTRAINT user_pokemon_friendship_check CHECK(friendship >= 0 AND friendship <= 7)",
]

SHINY_BOOST_MIGRATIONS = [
    "ALTER TABLE events DROP CONSTRAINT IF EXISTS events_event_type_check",
    "ALTER TABLE events ADD CONSTRAINT events_event_type_check CHECK(event_type IN ('spawn_boost','catch_boost','rarity_boost','pokemon_boost','friendship_boost','shiny_boost'))",
]

TEAM_SLOT_MIGRATIONS = [
    "ALTER TABLE battle_teams ADD COLUMN team_number INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE battle_teams DROP CONSTRAINT IF EXISTS battle_teams_user_id_slot_key",
    "ALTER TABLE battle_teams DROP CONSTRAINT IF EXISTS battle_teams_user_id_pokemon_instance_id_key",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_bt_user_team_slot ON battle_teams(user_id, team_number, slot)",
    "ALTER TABLE users ADD COLUMN active_team INTEGER NOT NULL DEFAULT 1",
    # team_number must be 1 or 2
    "ALTER TABLE battle_teams DROP CONSTRAINT IF EXISTS bt_team_number_check",
    "ALTER TABLE battle_teams ADD CONSTRAINT bt_team_number_check CHECK(team_number IN (1, 2))",
]

MISSION_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS daily_missions (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users(user_id),
        mission_date TEXT NOT NULL,
        mission_key TEXT NOT NULL,
        target INTEGER NOT NULL,
        progress INTEGER NOT NULL DEFAULT 0,
        completed BOOLEAN NOT NULL DEFAULT FALSE,
        reward_claimed BOOLEAN NOT NULL DEFAULT FALSE,
        all_clear_claimed BOOLEAN NOT NULL DEFAULT FALSE
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_dm_user_date_key ON daily_missions(user_id, mission_date, mission_key)",
    "CREATE INDEX IF NOT EXISTS idx_dm_user_date ON daily_missions(user_id, mission_date)",
]

TUTORIAL_MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN tutorial_step INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE users ADD COLUMN tutorial_restarted BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE users ADD COLUMN tutorial_legendary_id INTEGER DEFAULT NULL",
]

PATCH_OPTOUT_MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN patch_optout BOOLEAN NOT NULL DEFAULT FALSE",
]

JOURNEY_MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN journey_step SMALLINT NOT NULL DEFAULT 0",
    "ALTER TABLE users ADD COLUMN journey_last_tip_date DATE DEFAULT NULL",
]

# 3진화 최종형 + 게을킹: legendary → epic 하향
RARITY_FIX_MIGRATIONS = [
    "UPDATE pokemon_master SET rarity = 'epic', catch_rate = 0.15 WHERE id IN (289, 373, 376) AND rarity = 'legendary'",
]

# 2026-03-11 밸런스 등급 조정
RARITY_BALANCE_MIGRATIONS = [
    # 에픽 → 레어 (나인테일, 골덕, 날쌩마, 점토도리)
    "UPDATE pokemon_master SET rarity = 'rare', catch_rate = 0.50 WHERE id IN (38, 55, 78, 344) AND rarity = 'epic'",
    # 레어 → 커먼 (토게틱, 코산호, 마이농)
    "UPDATE pokemon_master SET rarity = 'common', catch_rate = 0.80 WHERE id IN (176, 222, 312) AND rarity = 'rare'",
]

CHAT_LEVEL_MIGRATIONS = [
    "ALTER TABLE chat_rooms ADD COLUMN cxp INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE chat_rooms ADD COLUMN chat_level INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE chat_rooms ADD COLUMN cxp_today INTEGER NOT NULL DEFAULT 0",
]

# ─── 구독 시스템 ─────────────────────────────────
SUBSCRIPTION_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS subscription_payments (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users(user_id),
        tier TEXT NOT NULL,
        amount_raw BIGINT NOT NULL,
        amount_usd NUMERIC(10,6) NOT NULL,
        token TEXT NOT NULL,
        chain TEXT NOT NULL DEFAULT 'base',
        tx_hash TEXT UNIQUE,
        from_address TEXT,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK(status IN ('pending','confirmed','expired')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        confirmed_at TIMESTAMPTZ,
        expires_at TIMESTAMPTZ NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_subpay_status ON subscription_payments(status, expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_subpay_user ON subscription_payments(user_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_subpay_amount ON subscription_payments(amount_raw, token, status)",
    """
    CREATE TABLE IF NOT EXISTS subscriptions (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users(user_id),
        tier TEXT NOT NULL,
        starts_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        expires_at TIMESTAMPTZ NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        payment_id INTEGER REFERENCES subscription_payments(id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_subs_active ON subscriptions(user_id, is_active, expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_subs_expiry ON subscriptions(is_active, expires_at)",
]

CHAT_CXP_LOG_TABLE = """
CREATE TABLE IF NOT EXISTS chat_cxp_log (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    action TEXT NOT NULL,
    user_id BIGINT,
    amount INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
)
"""

TOURNAMENT_REG_TABLE = """
CREATE TABLE IF NOT EXISTS tournament_registrations (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
    display_name TEXT NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

# ─── 랭크전 (시즌 배틀) 테이블 ─────────────────────────
RANKED_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS seasons (
        id SERIAL PRIMARY KEY,
        season_id TEXT NOT NULL UNIQUE,
        weekly_rule TEXT NOT NULL,
        starts_at TIMESTAMPTZ NOT NULL,
        ends_at TIMESTAMPTZ NOT NULL,
        arena_chat_ids BIGINT[] NOT NULL DEFAULT '{}',
        rewards_distributed BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_seasons_id ON seasons(season_id)",
    """
    CREATE TABLE IF NOT EXISTS season_daily_conditions (
        id SERIAL PRIMARY KEY,
        season_id TEXT NOT NULL,
        date DATE NOT NULL,
        condition_key TEXT NOT NULL,
        UNIQUE(season_id, date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS season_records (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users(user_id),
        season_id TEXT NOT NULL,
        rp INTEGER NOT NULL DEFAULT 0,
        tier TEXT NOT NULL DEFAULT 'bronze',
        ranked_wins INTEGER NOT NULL DEFAULT 0,
        ranked_losses INTEGER NOT NULL DEFAULT 0,
        ranked_streak INTEGER NOT NULL DEFAULT 0,
        best_ranked_streak INTEGER NOT NULL DEFAULT 0,
        peak_rp INTEGER NOT NULL DEFAULT 0,
        peak_tier TEXT NOT NULL DEFAULT 'bronze',
        UNIQUE(user_id, season_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_sr_season ON season_records(season_id, rp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_sr_user ON season_records(user_id)",
    """
    CREATE TABLE IF NOT EXISTS ranked_battle_log (
        id SERIAL PRIMARY KEY,
        battle_record_id INTEGER REFERENCES battle_records(id),
        season_id TEXT NOT NULL,
        winner_rp_before INTEGER NOT NULL,
        winner_rp_after INTEGER NOT NULL,
        loser_rp_before INTEGER NOT NULL,
        loser_rp_after INTEGER NOT NULL,
        winner_tier_before TEXT NOT NULL,
        winner_tier_after TEXT NOT NULL,
        loser_tier_before TEXT NOT NULL,
        loser_tier_after TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rbl_season ON ranked_battle_log(season_id)",
    """
    CREATE TABLE IF NOT EXISTS arena_candidates (
        chat_id BIGINT PRIMARY KEY,
        chat_name TEXT NOT NULL,
        registered_by BIGINT NOT NULL,
        registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
]

RANKED_MIGRATIONS = [
    "ALTER TABLE battle_challenges ADD COLUMN battle_type TEXT NOT NULL DEFAULT 'normal'",
    "ALTER TABLE battle_records ADD COLUMN battle_type TEXT NOT NULL DEFAULT 'normal'",
    # Defense shield: 연속 방어 패배 카운트 (5회 → 자동 보호)
    "ALTER TABLE season_records ADD COLUMN defense_losses INTEGER NOT NULL DEFAULT 0",
]

# ─── MMR / 배치전 / 디비전 시스템 (2026-03-12) ─────────
MMR_MIGRATIONS = [
    # 1. user_mmr 테이블 (시즌 독립, 영구 Elo)
    """CREATE TABLE IF NOT EXISTS user_mmr (
        user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
        mmr INTEGER NOT NULL DEFAULT 1200,
        peak_mmr INTEGER NOT NULL DEFAULT 1200,
        games_played INTEGER NOT NULL DEFAULT 0,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_user_mmr_mmr ON user_mmr(mmr DESC)",

    # 2. season_records: 배치전 + 승급 보호 + 디케이
    "ALTER TABLE season_records ADD COLUMN placement_games INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE season_records ADD COLUMN placement_done BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE season_records ADD COLUMN mmr_at_start INTEGER NOT NULL DEFAULT 1200",
    "ALTER TABLE season_records ADD COLUMN promo_shield_until TIMESTAMPTZ",
    "ALTER TABLE season_records ADD COLUMN last_ranked_at TIMESTAMPTZ",

    # 3. ranked_battle_log: MMR 기록
    "ALTER TABLE ranked_battle_log ADD COLUMN winner_mmr_before INTEGER",
    "ALTER TABLE ranked_battle_log ADD COLUMN winner_mmr_after INTEGER",
    "ALTER TABLE ranked_battle_log ADD COLUMN loser_mmr_before INTEGER",
    "ALTER TABLE ranked_battle_log ADD COLUMN loser_mmr_after INTEGER",

    # 4. seasons: 중간 리셋
    "ALTER TABLE seasons ADD COLUMN mid_reset_done BOOLEAN NOT NULL DEFAULT FALSE",

]

ULTRA_LEGENDARY_MIGRATIONS = [
    # CHECK 제약 업데이트 (ultra_legendary 추가)
    "ALTER TABLE pokemon_master DROP CONSTRAINT IF EXISTS pokemon_master_rarity_check",
    "ALTER TABLE pokemon_master ADD CONSTRAINT pokemon_master_rarity_check "
    "CHECK(rarity IN ('common','rare','epic','legendary','ultra_legendary'))",
    # BST 680 3종을 ultra_legendary로 승격
    "UPDATE pokemon_master SET rarity = 'ultra_legendary' WHERE id IN (150, 249, 250)",
]

# 2026-03-12 교환 진화 경로 복구 (롱스톤/시드라/스라크/폴리곤)
TRADE_EVO_FIX_MIGRATIONS = [
    "UPDATE pokemon_master SET evolves_to = 208, evolution_method = 'trade' WHERE id = 95",   # 롱스톤 → 강철톤
    "UPDATE pokemon_master SET evolves_to = 230, evolution_method = 'trade' WHERE id = 117",  # 시드라 → 킹드라
    "UPDATE pokemon_master SET evolves_to = 212, evolution_method = 'trade' WHERE id = 123",  # 스라크 → 핫삼
    "UPDATE pokemon_master SET evolves_to = 233, evolution_method = 'trade' WHERE id = 137",  # 폴리곤 → 폴리곤2
]



# ─── 캠프 v2 시스템 (2026-03-13) ─────────
CAMP_TABLES = [
    # 캠프 설정 (채팅방당 1개)
    """CREATE TABLE IF NOT EXISTS camps (
        chat_id BIGINT PRIMARY KEY,
        level INTEGER NOT NULL DEFAULT 1,
        xp INTEGER NOT NULL DEFAULT 0,
        created_by BIGINT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",

    # 캠프 필드 (소유자가 선택한 타입 필드)
    """CREATE TABLE IF NOT EXISTS camp_fields (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL REFERENCES camps(chat_id),
        field_type VARCHAR(20) NOT NULL,
        unlock_order INTEGER NOT NULL DEFAULT 1,
        unlocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(chat_id, field_type)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_camp_fields_chat ON camp_fields(chat_id)",

    # 캠프 슬롯 배치
    """CREATE TABLE IF NOT EXISTS camp_placements (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        field_id INTEGER NOT NULL REFERENCES camp_fields(id),
        user_id BIGINT NOT NULL,
        pokemon_id INTEGER NOT NULL,
        instance_id INTEGER NOT NULL,
        slot_type VARCHAR(10) NOT NULL DEFAULT 'free',
        score INTEGER NOT NULL DEFAULT 1,
        placed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(chat_id, field_id, user_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_camp_place_chat ON camp_placements(chat_id)",
    "CREATE INDEX IF NOT EXISTS idx_camp_place_user ON camp_placements(user_id)",

    # 라운드 보너스 포켓몬
    """CREATE TABLE IF NOT EXISTS camp_round_bonus (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        field_id INTEGER NOT NULL REFERENCES camp_fields(id),
        pokemon_id INTEGER NOT NULL,
        stat_type VARCHAR(10) NOT NULL,
        stat_value INTEGER NOT NULL,
        round_time TIMESTAMPTZ NOT NULL,
        UNIQUE(chat_id, field_id, round_time)
    )""",

    # 유저 조각 (필드 타입별 귀속)
    """CREATE TABLE IF NOT EXISTS camp_fragments (
        user_id BIGINT NOT NULL,
        field_type VARCHAR(20) NOT NULL,
        amount INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(user_id, field_type)
    )""",

    # 조각 획득 로그
    """CREATE TABLE IF NOT EXISTS camp_fragment_log (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        chat_id BIGINT NOT NULL,
        field_type VARCHAR(20) NOT NULL,
        amount INTEGER NOT NULL,
        source VARCHAR(30) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cflog_user ON camp_fragment_log(user_id, created_at)",

    # 분해 결정 보유
    """CREATE TABLE IF NOT EXISTS camp_crystals (
        user_id BIGINT PRIMARY KEY,
        crystal INTEGER NOT NULL DEFAULT 0,
        rainbow INTEGER NOT NULL DEFAULT 0
    )""",

    # 이로치 전환 쿨타임
    """CREATE TABLE IF NOT EXISTS camp_shiny_cooldown (
        user_id BIGINT PRIMARY KEY,
        last_convert_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",

    # 유저 캠프 설정 (거점 등)
    """CREATE TABLE IF NOT EXISTS camp_user_settings (
        user_id BIGINT PRIMARY KEY,
        home_chat_id BIGINT,
        home_changed_date DATE
    )""",

    # 소유자 캠프 설정 (승인제 등)
    """CREATE TABLE IF NOT EXISTS camp_chat_settings (
        chat_id BIGINT PRIMARY KEY REFERENCES camps(chat_id),
        approval_mode BOOLEAN NOT NULL DEFAULT FALSE,
        approval_slots INTEGER NOT NULL DEFAULT 0,
        last_mode_change TIMESTAMPTZ,
        last_field_change TIMESTAMPTZ
    )""",

    # 배치 일일 횟수 추적
    """CREATE TABLE IF NOT EXISTS camp_daily_placements (
        user_id BIGINT NOT NULL,
        date DATE NOT NULL DEFAULT CURRENT_DATE,
        count INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(user_id, date)
    )""",

    # 승인 대기열
    """CREATE TABLE IF NOT EXISTS camp_approval_queue (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        field_id INTEGER NOT NULL,
        user_id BIGINT NOT NULL,
        pokemon_id INTEGER NOT NULL,
        instance_id INTEGER NOT NULL,
        requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        status VARCHAR(10) NOT NULL DEFAULT 'pending',
        UNIQUE(chat_id, field_id, user_id)
    )""",
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
    # Run tournament migrations (ignore if already applied)
    for mig in TOURNAMENT_MIGRATIONS:
        try:
            await pool.execute(mig)
        except Exception:
            pass
    # Run shop migrations
    for mig in SHOP_MIGRATIONS:
        try:
            await pool.execute(mig)
        except Exception:
            pass
    # Run hyper ball migrations
    for mig in HYPER_BALL_MIGRATIONS:
        try:
            await pool.execute(mig)
        except Exception:
            pass
    # Arcade ticket migrations (drop old table + add user column)
    for mig in ARCADE_TICKET_MIGRATIONS:
        try:
            await pool.execute(mig)
        except Exception:
            pass
    # Arcade pass tables (chat-based, recreated after drop)
    for sql in ARCADE_PASS_TABLES:
        try:
            await pool.execute(sql)
        except Exception:
            pass
    # Run shiny migrations
    for mig in SHINY_MIGRATIONS:
        try:
            await pool.execute(mig)
        except Exception:
            pass
    # Run team slot migrations
    for mig in TEAM_SLOT_MIGRATIONS:
        try:
            await pool.execute(mig)
        except Exception:
            pass
    # Run IV system migrations
    for mig in IV_MIGRATIONS:
        try:
            await pool.execute(mig)
        except Exception:
            pass
    # Favorite column
    try:
        await pool.execute("ALTER TABLE user_pokemon ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0")
    except Exception:
        pass
    # LLM bonus quota migration
    for mig in LLM_QUOTA_MIGRATIONS:
        try:
            await pool.execute(mig)
        except Exception:
            pass
    # Shiny boost event type migration
    for mig in SHINY_BOOST_MIGRATIONS:
        try:
            await pool.execute(mig)
        except Exception:
            pass
    # Tutorial migration
    for mig in TUTORIAL_MIGRATIONS:
        try:
            await pool.execute(mig)
        except Exception:
            pass
    # Bot settings table
    await pool.execute(BOT_SETTINGS_TABLE)

    # Marketplace tables
    for sql in MARKET_TABLES:
        try:
            await pool.execute(sql)
        except Exception:
            pass

    # Daily missions tables
    for sql in MISSION_TABLES:
        try:
            await pool.execute(sql)
        except Exception:
            pass
    # Patch note opt-out migration
    for mig in PATCH_OPTOUT_MIGRATIONS:
        try:
            await pool.execute(mig)
        except Exception:
            pass

    # Group trade migrations
    for mig in GROUP_TRADE_MIGRATIONS:
        try:
            await pool.execute(mig)
        except Exception:
            pass

    # Ultra-legendary rarity migration
    for mig in ULTRA_LEGENDARY_MIGRATIONS:
        try:
            await pool.execute(mig)
        except Exception:
            pass

    # Journey system migrations
    for mig in JOURNEY_MIGRATIONS:
        try:
            await pool.execute(mig)
        except Exception:
            pass

    # Rarity fix: 3-stage evolution final forms → epic
    for mig in RARITY_FIX_MIGRATIONS:
        try:
            await pool.execute(mig)
        except Exception:
            pass

    # Tournament registrations table
    try:
        await pool.execute(TOURNAMENT_REG_TABLE)
    except Exception:
        pass

    # Chat level system migrations
    for mig in CHAT_LEVEL_MIGRATIONS:
        try:
            await pool.execute(mig)
        except Exception:
            pass
    try:
        await pool.execute(CHAT_CXP_LOG_TABLE)
    except Exception:
        pass
    try:
        await pool.execute("CREATE INDEX IF NOT EXISTS idx_cxp_log_chat ON chat_cxp_log(chat_id, created_at)")
    except Exception:
        pass

    # Ranked (season) battle tables
    for sql in RANKED_TABLES:
        try:
            await pool.execute(sql)
        except Exception:
            pass
    for mig in RANKED_MIGRATIONS:
        try:
            await pool.execute(mig)
        except Exception:
            pass

    # MMR / 배치전 / 디비전 시스템 (2026-03-12)
    for mig in MMR_MIGRATIONS:
        try:
            await pool.execute(mig)
        except Exception:
            pass

    # Rarity balance adjustments (2026-03-11)
    for mig in RARITY_BALANCE_MIGRATIONS:
        try:
            await pool.execute(mig)
        except Exception:
            pass

    # Subscription system tables
    for sql in SUBSCRIPTION_TABLES:
        try:
            await pool.execute(sql)
        except Exception:
            pass

    # KPI daily snapshots table
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS kpi_daily_snapshots (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL UNIQUE,
            dau INTEGER NOT NULL DEFAULT 0,
            new_users INTEGER NOT NULL DEFAULT 0,
            spawns INTEGER NOT NULL DEFAULT 0,
            catches INTEGER NOT NULL DEFAULT 0,
            shiny_caught INTEGER NOT NULL DEFAULT 0,
            battles INTEGER NOT NULL DEFAULT 0,
            ranked_battles INTEGER NOT NULL DEFAULT 0,
            bp_earned INTEGER NOT NULL DEFAULT 0,
            active_user_ids BIGINT[] NOT NULL DEFAULT '{}',
            d1_retention REAL,
            d7_retention REAL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # Camp v2 system (2026-03-13)
    for sql in CAMP_TABLES:
        try:
            await pool.execute(sql)
        except Exception:
            pass

    # Camp renewal migrations (2026-03-14)
    camp_renewal_migs = [
        "ALTER TABLE camp_user_settings ADD COLUMN home_camp_set_at TIMESTAMPTZ",
        "ALTER TABLE camp_user_settings ADD COLUMN camp_notify BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE chat_rooms ADD COLUMN invite_link TEXT",
    ]
    for mig in camp_renewal_migs:
        try:
            await pool.execute(mig)
        except Exception:
            pass

    # Gacha system tables (2026-03-14)
    gacha_tables = [
        # 유저 아이템 인벤토리
        """CREATE TABLE IF NOT EXISTS user_items (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(user_id),
            item_type TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (user_id, item_type)
        )""",
        # 이로치 알
        """CREATE TABLE IF NOT EXISTS shiny_eggs (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(user_id),
            pokemon_id INTEGER NOT NULL,
            rarity TEXT NOT NULL,
            is_shiny BOOLEAN NOT NULL DEFAULT TRUE,
            hatches_at TIMESTAMPTZ NOT NULL,
            hatched BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS idx_shiny_eggs_hatch ON shiny_eggs(hatched, hatches_at)",
        # 가챠 로그
        """CREATE TABLE IF NOT EXISTS gacha_log (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            result_key TEXT NOT NULL,
            bp_spent INTEGER NOT NULL DEFAULT 100,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""",
    ]
    for sql in gacha_tables:
        try:
            await pool.execute(sql)
        except Exception:
            pass

    # 이로치 강스권: users 테이블에 플래그 추가
    try:
        await pool.execute("ALTER TABLE users ADD COLUMN shiny_spawn_tickets INTEGER NOT NULL DEFAULT 0")
    except Exception:
        pass

    # ── Performance indexes (idempotent) ──
    perf_indexes = [
        "CREATE INDEX IF NOT EXISTS idx_catch_limits_date ON catch_limits(date)",
        "CREATE INDEX IF NOT EXISTS idx_chatrooms_active ON chat_rooms(is_active)",
        "CREATE INDEX IF NOT EXISTS idx_battle_defender ON battle_challenges(defender_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_trades_from ON trades(from_user_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active_at)",
    ]
    for idx_sql in perf_indexes:
        try:
            await pool.execute(idx_sql)
        except Exception:
            pass
