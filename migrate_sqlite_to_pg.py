"""Migrate data from SQLite to PostgreSQL (Supabase)."""
import asyncio
import sqlite3
import os
import ssl
from datetime import datetime, timezone, timedelta
import asyncpg
from dotenv import load_dotenv

load_dotenv()

KST = timezone(timedelta(hours=9))
DEFAULT_DT = datetime(2026, 1, 1, tzinfo=KST)

def make_ssl():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def parse_dt(val):
    """Parse SQLite datetime string to Python datetime."""
    if not val:
        return DEFAULT_DT
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(val, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=KST)
            return dt
        except ValueError:
            continue
    return DEFAULT_DT

async def main():
    lite = sqlite3.connect("data/pokemon_bot.db")
    lite.row_factory = sqlite3.Row
    c = lite.cursor()

    dsn = os.getenv("DATABASE_URL")
    pool = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=5, ssl=make_ssl(), statement_cache_size=0)

    print("Clearing PostgreSQL tables...")
    for t in ["bp_purchase_log", "battle_records", "battle_challenges", "battle_teams",
              "user_title_stats", "user_titles", "trades", "events",
              "chat_activity", "catch_limits", "catch_attempts", "spawn_log",
              "spawn_sessions", "pokedex", "user_pokemon", "chat_rooms", "users"]:
        try:
            await pool.execute(f"DELETE FROM {t}")
        except Exception as e:
            print(f"  skip {t}: {e}")

    # 1. Users
    c.execute("SELECT * FROM users")
    rows = c.fetchall()
    print(f"Migrating users: {len(rows)} rows")
    for r in rows:
        await pool.execute(
            """INSERT INTO users (user_id, username, display_name, title, title_emoji, master_balls, registered_at, last_active_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
               ON CONFLICT (user_id) DO NOTHING""",
            r["user_id"], r["username"], r["display_name"],
            r["title"] or "", r["title_emoji"] or "",
            r["master_balls"] or 0,
            parse_dt(r["registered_at"]),
            parse_dt(r["last_active_at"])
        )

    # 2. Chat rooms
    c.execute("SELECT * FROM chat_rooms")
    rows = c.fetchall()
    print(f"Migrating chat_rooms: {len(rows)} rows")
    for r in rows:
        await pool.execute(
            """INSERT INTO chat_rooms (chat_id, chat_title, member_count, is_active, joined_at, last_spawn_at,
               daily_spawn_count, spawns_today_target, spawn_multiplier, force_spawn_count)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
               ON CONFLICT (chat_id) DO NOTHING""",
            r["chat_id"], r["chat_title"], r["member_count"] or 0,
            r["is_active"] or 1,
            parse_dt(r["joined_at"]),
            parse_dt(r["last_spawn_at"]) if r["last_spawn_at"] else None,
            r["daily_spawn_count"] or 0, r["spawns_today_target"] or 0,
            r["spawn_multiplier"] or 1.0, r["force_spawn_count"] or 0
        )

    # 3. User pokemon
    c.execute("SELECT * FROM user_pokemon ORDER BY id")
    rows = c.fetchall()
    print(f"Migrating user_pokemon: {len(rows)} rows")
    for r in rows:
        await pool.execute(
            """INSERT INTO user_pokemon (id, user_id, pokemon_id, nickname, friendship, caught_at, caught_in_chat_id, is_active, fed_today, played_today)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
               ON CONFLICT (id) DO NOTHING""",
            r["id"], r["user_id"], r["pokemon_id"], r["nickname"],
            r["friendship"] or 0,
            parse_dt(r["caught_at"]),
            r["caught_in_chat_id"], r["is_active"] or 1,
            r["fed_today"] or 0, r["played_today"] or 0
        )
    max_id = max((r["id"] for r in rows), default=0)
    if max_id:
        await pool.execute(f"SELECT setval('user_pokemon_id_seq', {max_id})")

    # 4. Pokedex
    c.execute("SELECT * FROM pokedex")
    rows = c.fetchall()
    print(f"Migrating pokedex: {len(rows)} rows")
    for r in rows:
        await pool.execute(
            """INSERT INTO pokedex (user_id, pokemon_id, method, first_caught_at)
               VALUES ($1,$2,$3,$4)
               ON CONFLICT (user_id, pokemon_id) DO NOTHING""",
            r["user_id"], r["pokemon_id"], r["method"] or "catch",
            parse_dt(r["first_caught_at"])
        )

    # 5. Spawn sessions
    c.execute("SELECT * FROM spawn_sessions ORDER BY id")
    rows = c.fetchall()
    print(f"Migrating spawn_sessions: {len(rows)} rows")
    for r in rows:
        await pool.execute(
            """INSERT INTO spawn_sessions (id, chat_id, pokemon_id, spawned_at, expires_at, is_resolved, caught_by_user_id, message_id)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
               ON CONFLICT (id) DO NOTHING""",
            r["id"], r["chat_id"], r["pokemon_id"],
            parse_dt(r["spawned_at"]),
            parse_dt(r["expires_at"]),
            r["is_resolved"] or 0, r["caught_by_user_id"], r["message_id"]
        )
    max_id = max((r["id"] for r in rows), default=0)
    if max_id:
        await pool.execute(f"SELECT setval('spawn_sessions_id_seq', {max_id})")

    # 6. Catch attempts
    c.execute("SELECT * FROM catch_attempts ORDER BY id")
    rows = c.fetchall()
    print(f"Migrating catch_attempts: {len(rows)} rows")
    for r in rows:
        await pool.execute(
            """INSERT INTO catch_attempts (id, session_id, user_id, used_master_ball, attempted_at)
               VALUES ($1,$2,$3,$4,$5)
               ON CONFLICT (id) DO NOTHING""",
            r["id"], r["session_id"], r["user_id"],
            r["used_master_ball"] or 0,
            parse_dt(r["attempted_at"])
        )
    max_id = max((r["id"] for r in rows), default=0)
    if max_id:
        await pool.execute(f"SELECT setval('catch_attempts_id_seq', {max_id})")

    # 7. Catch limits
    c.execute("SELECT * FROM catch_limits")
    rows = c.fetchall()
    print(f"Migrating catch_limits: {len(rows)} rows")
    for r in rows:
        await pool.execute(
            """INSERT INTO catch_limits (user_id, date, attempt_count, consecutive_catches, bonus_catches)
               VALUES ($1,$2,$3,$4,$5)
               ON CONFLICT (user_id, date) DO NOTHING""",
            r["user_id"], r["date"], r["attempt_count"] or 0,
            r["consecutive_catches"] or 0, r["bonus_catches"] or 0
        )

    # 8. Spawn log
    c.execute("SELECT * FROM spawn_log ORDER BY id")
    rows = c.fetchall()
    print(f"Migrating spawn_log: {len(rows)} rows")
    for r in rows:
        await pool.execute(
            """INSERT INTO spawn_log (id, chat_id, pokemon_id, pokemon_name, pokemon_emoji, rarity, spawned_at, caught_by_user_id, caught_by_name, participants)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
               ON CONFLICT (id) DO NOTHING""",
            r["id"], r["chat_id"], r["pokemon_id"], r["pokemon_name"],
            r["pokemon_emoji"] or "", r["rarity"],
            parse_dt(r["spawned_at"]),
            r["caught_by_user_id"], r["caught_by_name"], r["participants"] or 0
        )
    max_id = max((r["id"] for r in rows), default=0)
    if max_id:
        await pool.execute(f"SELECT setval('spawn_log_id_seq', {max_id})")

    # 9. Chat activity
    c.execute("SELECT * FROM chat_activity")
    rows = c.fetchall()
    print(f"Migrating chat_activity: {len(rows)} rows")
    for r in rows:
        await pool.execute(
            """INSERT INTO chat_activity (chat_id, hour_bucket, message_count)
               VALUES ($1,$2,$3)
               ON CONFLICT (chat_id, hour_bucket) DO NOTHING""",
            r["chat_id"], r["hour_bucket"], r["message_count"] or 0
        )

    # 10. Trades
    c.execute("SELECT * FROM trades ORDER BY id")
    rows = c.fetchall()
    print(f"Migrating trades: {len(rows)} rows")
    for r in rows:
        await pool.execute(
            """INSERT INTO trades (id, from_user_id, to_user_id, offer_pokemon_instance_id, request_pokemon_name, status, created_at, resolved_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
               ON CONFLICT (id) DO NOTHING""",
            r["id"], r["from_user_id"], r["to_user_id"],
            r["offer_pokemon_instance_id"], r["request_pokemon_name"],
            r["status"] or "pending",
            parse_dt(r["created_at"]),
            parse_dt(r["resolved_at"]) if r["resolved_at"] else None
        )
    max_id = max((r["id"] for r in rows), default=0)
    if max_id:
        await pool.execute(f"SELECT setval('trades_id_seq', {max_id})")

    # 11. User titles
    c.execute("SELECT * FROM user_titles")
    rows = c.fetchall()
    print(f"Migrating user_titles: {len(rows)} rows")
    for r in rows:
        await pool.execute(
            """INSERT INTO user_titles (user_id, title_id, unlocked_at)
               VALUES ($1,$2,$3)
               ON CONFLICT (user_id, title_id) DO NOTHING""",
            r["user_id"], r["title_id"],
            parse_dt(r["unlocked_at"])
        )

    # 12. User title stats
    c.execute("SELECT * FROM user_title_stats")
    rows = c.fetchall()
    print(f"Migrating user_title_stats: {len(rows)} rows")
    for r in rows:
        await pool.execute(
            """INSERT INTO user_title_stats (user_id, catch_fail_count, midnight_catch_count, master_ball_used, love_count, login_streak, last_active_date)
               VALUES ($1,$2,$3,$4,$5,$6,$7)
               ON CONFLICT (user_id) DO NOTHING""",
            r["user_id"], r["catch_fail_count"] or 0,
            r["midnight_catch_count"] or 0, r["master_ball_used"] or 0,
            r["love_count"] or 0, r["login_streak"] or 0,
            r["last_active_date"]
        )

    lite.close()
    await pool.close()
    print("Migration complete!")

asyncio.run(main())
