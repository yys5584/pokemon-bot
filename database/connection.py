"""SQLite async connection manager."""

import os
import aiosqlite

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    """Get or create the singleton database connection."""
    global _db
    if _db is None:
        db_path = os.getenv("DB_PATH", "./data/pokemon_bot.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        _db = await aiosqlite.connect(db_path)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
    return _db


async def close_db():
    """Close the database connection."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None
