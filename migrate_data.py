"""Migrate data from SQLite to Supabase PostgreSQL.

Usage:
    python migrate_data.py

Reads from local SQLite (DB_PATH in .env) and writes to PostgreSQL (DATABASE_URL in .env).
Tables are created via schema.py before running this script — just start the bot once.
"""

import asyncio
import os
import ssl
import sqlite3
from datetime import datetime

import asyncpg
from dotenv import load_dotenv

load_dotenv()


def parse_ts(val):
    """Convert SQLite timestamp string to datetime object."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        # Try common SQLite formats
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
            try:
                return datetime.strptime(str(val), fmt)
            except ValueError:
                continue
        # Fallback: fromisoformat
        return datetime.fromisoformat(str(val))
    except Exception:
        return None


def get_sqlite_data():
    """Read all data from SQLite."""
    db_path = os.getenv("DB_PATH", "./data/pokemon_bot.db")
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row

    data = {}

    # Order matters for FK constraints
    tables = [
        "pokemon_master",
        "users",
        "user_pokemon",
        "pokedex",
        "chat_rooms",
        "spawn_sessions",
        "catch_attempts",
        "catch_limits",
        "spawn_log",
        "chat_activity",
        "events",
        "user_titles",
        "user_title_stats",
        "trades",
    ]

    for table in tables:
        try:
            rows = db.execute(f"SELECT * FROM {table}").fetchall()
            data[table] = [dict(r) for r in rows]
            print(f"  {table}: {len(data[table])} rows")
        except Exception as e:
            print(f"  {table}: SKIP ({e})")
            data[table] = []

    db.close()
    return data


async def migrate_to_pg(data: dict):
    """Write data to PostgreSQL."""
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("ERROR: DATABASE_URL not set in .env")
        return

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    pool = await asyncpg.create_pool(
        dsn=dsn, min_size=1, max_size=5,
        ssl=ssl_ctx, statement_cache_size=0,
    )

    # --- pokemon_master ---
    print("\nMigrating pokemon_master...")
    for r in data.get("pokemon_master", []):
        await pool.execute(
            """INSERT INTO pokemon_master (id, name_ko, name_en, emoji, rarity, catch_rate,
                   evolves_from, evolves_to, evolution_method)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
               ON CONFLICT (id) DO NOTHING""",
            r["id"], r["name_ko"], r["name_en"], r.get("emoji", "?"),
            r["rarity"], r.get("catch_rate", 0.5),
            r.get("evolves_from"), r.get("evolves_to"),
            r.get("evolution_method", "friendship"),
        )
    print(f"  Done: {len(data.get('pokemon_master', []))} rows")

    # --- users ---
    print("Migrating users...")
    for r in data.get("users", []):
        await pool.execute(
            """INSERT INTO users (user_id, username, display_name, title, title_emoji,
                   master_balls, registered_at, last_active_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
               ON CONFLICT (user_id) DO NOTHING""",
            r["user_id"], r.get("username"), r.get("display_name", "trainer"),
            r.get("title", ""), r.get("title_emoji", ""),
            r.get("master_balls", 0),
            parse_ts(r.get("registered_at")), parse_ts(r.get("last_active_at")),
        )
    print(f"  Done: {len(data.get('users', []))} rows")

    # --- chat_rooms ---
    print("Migrating chat_rooms...")
    for r in data.get("chat_rooms", []):
        await pool.execute(
            """INSERT INTO chat_rooms (chat_id, chat_title, member_count, is_active,
                   joined_at, last_spawn_at, daily_spawn_count,
                   spawns_today_target, spawn_multiplier, force_spawn_count)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
               ON CONFLICT (chat_id) DO NOTHING""",
            r["chat_id"], r.get("chat_title"), r.get("member_count", 0),
            r.get("is_active", 1),
            parse_ts(r.get("joined_at")), parse_ts(r.get("last_spawn_at")),
            r.get("daily_spawn_count", 0),
            r.get("spawns_today_target", 0),
            r.get("spawn_multiplier", 1.0),
            r.get("force_spawn_count", 0),
        )
    print(f"  Done: {len(data.get('chat_rooms', []))} rows")

    # --- user_pokemon (SERIAL id — need to set sequence after) ---
    print("Migrating user_pokemon...")
    max_up_id = 0
    for r in data.get("user_pokemon", []):
        max_up_id = max(max_up_id, r["id"])
        await pool.execute(
            """INSERT INTO user_pokemon (id, user_id, pokemon_id, nickname, friendship,
                   caught_at, caught_in_chat_id, is_active, fed_today, played_today)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
               ON CONFLICT (id) DO NOTHING""",
            r["id"], r["user_id"], r["pokemon_id"], r.get("nickname"),
            r.get("friendship", 0), parse_ts(r.get("caught_at")),
            r.get("caught_in_chat_id"), r.get("is_active", 1),
            r.get("fed_today", 0), r.get("played_today", 0),
        )
    if max_up_id > 0:
        await pool.execute(f"SELECT setval('user_pokemon_id_seq', {max_up_id})")
    print(f"  Done: {len(data.get('user_pokemon', []))} rows")

    # --- pokedex ---
    print("Migrating pokedex...")
    for r in data.get("pokedex", []):
        await pool.execute(
            """INSERT INTO pokedex (user_id, pokemon_id, method, first_caught_at)
               VALUES ($1,$2,$3,$4)
               ON CONFLICT (user_id, pokemon_id) DO NOTHING""",
            r["user_id"], r["pokemon_id"], r.get("method", "catch"),
            parse_ts(r.get("first_caught_at")),
        )
    print(f"  Done: {len(data.get('pokedex', []))} rows")

    # --- spawn_sessions ---
    print("Migrating spawn_sessions...")
    max_ss_id = 0
    for r in data.get("spawn_sessions", []):
        max_ss_id = max(max_ss_id, r["id"])
        await pool.execute(
            """INSERT INTO spawn_sessions (id, chat_id, pokemon_id, spawned_at, expires_at,
                   is_resolved, caught_by_user_id, message_id)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
               ON CONFLICT (id) DO NOTHING""",
            r["id"], r["chat_id"], r["pokemon_id"],
            parse_ts(r.get("spawned_at")), parse_ts(r.get("expires_at")),
            r.get("is_resolved", 0), r.get("caught_by_user_id"),
            r.get("message_id"),
        )
    if max_ss_id > 0:
        await pool.execute(f"SELECT setval('spawn_sessions_id_seq', {max_ss_id})")
    print(f"  Done: {len(data.get('spawn_sessions', []))} rows")

    # --- catch_attempts ---
    print("Migrating catch_attempts...")
    max_ca_id = 0
    for r in data.get("catch_attempts", []):
        max_ca_id = max(max_ca_id, r["id"])
        await pool.execute(
            """INSERT INTO catch_attempts (id, session_id, user_id, used_master_ball, attempted_at)
               VALUES ($1,$2,$3,$4,$5)
               ON CONFLICT (id) DO NOTHING""",
            r["id"], r["session_id"], r["user_id"],
            r.get("used_master_ball", 0), parse_ts(r.get("attempted_at")),
        )
    if max_ca_id > 0:
        await pool.execute(f"SELECT setval('catch_attempts_id_seq', {max_ca_id})")
    print(f"  Done: {len(data.get('catch_attempts', []))} rows")

    # --- catch_limits ---
    print("Migrating catch_limits...")
    for r in data.get("catch_limits", []):
        await pool.execute(
            """INSERT INTO catch_limits (user_id, date, attempt_count, consecutive_catches, bonus_catches)
               VALUES ($1,$2,$3,$4,$5)
               ON CONFLICT (user_id, date) DO NOTHING""",
            r["user_id"], r["date"],
            r.get("attempt_count", 0), r.get("consecutive_catches", 0),
            r.get("bonus_catches", 0),
        )
    print(f"  Done: {len(data.get('catch_limits', []))} rows")

    # --- spawn_log ---
    print("Migrating spawn_log...")
    max_sl_id = 0
    for r in data.get("spawn_log", []):
        max_sl_id = max(max_sl_id, r["id"])
        await pool.execute(
            """INSERT INTO spawn_log (id, chat_id, pokemon_id, pokemon_name, pokemon_emoji,
                   rarity, spawned_at, caught_by_user_id, caught_by_name, participants)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
               ON CONFLICT (id) DO NOTHING""",
            r["id"], r["chat_id"], r["pokemon_id"],
            r.get("pokemon_name", ""), r.get("pokemon_emoji", ""),
            r["rarity"], parse_ts(r.get("spawned_at")),
            r.get("caught_by_user_id"), r.get("caught_by_name"),
            r.get("participants", 0),
        )
    if max_sl_id > 0:
        await pool.execute(f"SELECT setval('spawn_log_id_seq', {max_sl_id})")
    print(f"  Done: {len(data.get('spawn_log', []))} rows")

    # --- chat_activity ---
    print("Migrating chat_activity...")
    for r in data.get("chat_activity", []):
        await pool.execute(
            """INSERT INTO chat_activity (chat_id, hour_bucket, message_count)
               VALUES ($1,$2,$3)
               ON CONFLICT (chat_id, hour_bucket) DO NOTHING""",
            r["chat_id"], r["hour_bucket"], r.get("message_count", 0),
        )
    print(f"  Done: {len(data.get('chat_activity', []))} rows")

    # --- events ---
    print("Migrating events...")
    max_ev_id = 0
    for r in data.get("events", []):
        max_ev_id = max(max_ev_id, r["id"])
        await pool.execute(
            """INSERT INTO events (id, name, event_type, multiplier, target,
                   description, start_time, end_time, active, created_by)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
               ON CONFLICT (id) DO NOTHING""",
            r["id"], r["name"], r["event_type"],
            r.get("multiplier", 2.0), r.get("target"),
            r.get("description"), parse_ts(r.get("start_time")),
            parse_ts(r.get("end_time")), r.get("active", 1), r.get("created_by"),
        )
    if max_ev_id > 0:
        await pool.execute(f"SELECT setval('events_id_seq', {max_ev_id})")
    print(f"  Done: {len(data.get('events', []))} rows")

    # --- user_titles ---
    print("Migrating user_titles...")
    for r in data.get("user_titles", []):
        await pool.execute(
            """INSERT INTO user_titles (user_id, title_id, unlocked_at)
               VALUES ($1,$2,$3)
               ON CONFLICT (user_id, title_id) DO NOTHING""",
            r["user_id"], r["title_id"], parse_ts(r.get("unlocked_at")),
        )
    print(f"  Done: {len(data.get('user_titles', []))} rows")

    # --- user_title_stats ---
    print("Migrating user_title_stats...")
    for r in data.get("user_title_stats", []):
        await pool.execute(
            """INSERT INTO user_title_stats (user_id, catch_fail_count, midnight_catch_count,
                   master_ball_used, love_count, login_streak, last_active_date)
               VALUES ($1,$2,$3,$4,$5,$6,$7)
               ON CONFLICT (user_id) DO NOTHING""",
            r["user_id"], r.get("catch_fail_count", 0),
            r.get("midnight_catch_count", 0), r.get("master_ball_used", 0),
            r.get("love_count", 0), r.get("login_streak", 0),
            r.get("last_active_date"),
        )
    print(f"  Done: {len(data.get('user_title_stats', []))} rows")

    # --- trades ---
    print("Migrating trades...")
    max_tr_id = 0
    for r in data.get("trades", []):
        max_tr_id = max(max_tr_id, r["id"])
        await pool.execute(
            """INSERT INTO trades (id, from_user_id, to_user_id, offer_pokemon_instance_id,
                   request_pokemon_name, status, created_at, resolved_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
               ON CONFLICT (id) DO NOTHING""",
            r["id"], r["from_user_id"], r["to_user_id"],
            r["offer_pokemon_instance_id"], r.get("request_pokemon_name"),
            r.get("status", "pending"),
            parse_ts(r.get("created_at")), parse_ts(r.get("resolved_at")),
        )
    if max_tr_id > 0:
        await pool.execute(f"SELECT setval('trades_id_seq', {max_tr_id})")
    print(f"  Done: {len(data.get('trades', []))} rows")

    await pool.close()
    print("\nMigration complete!")


async def main():
    print("=" * 50)
    print("SQLite -> PostgreSQL Migration")
    print("=" * 50)
    print("\nReading SQLite data...")
    data = get_sqlite_data()

    total = sum(len(v) for v in data.values())
    print(f"\nTotal rows to migrate: {total}")

    print("\nWriting to PostgreSQL...")
    await migrate_to_pg(data)


if __name__ == "__main__":
    asyncio.run(main())
