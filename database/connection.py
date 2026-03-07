"""PostgreSQL async connection manager using asyncpg.

Features:
- Connection pool with auto-reconnect
- Retry wrapper for transient failures
- Keepalive to prevent idle disconnects
"""

import asyncio
import logging
import os
import ssl
import asyncpg

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY = 1.0  # seconds


def _make_ssl():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def get_db() -> asyncpg.Pool:
    """Get or create the connection pool with auto-reconnect."""
    global _pool
    if _pool is None or _pool._closed:
        _pool = await _create_pool()
    return _pool


async def _create_pool() -> asyncpg.Pool:
    """Create a new connection pool with retry."""
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL not set in .env")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            pool = await asyncpg.create_pool(
                dsn=dsn,
                min_size=int(os.getenv("DB_POOL_MIN", "2")),
                max_size=int(os.getenv("DB_POOL_MAX", "7")),
                ssl=_make_ssl(),
                statement_cache_size=0,  # Supabase uses PgBouncer (no prepared statements)
                command_timeout=30,
            )
            if attempt > 1:
                logger.info(f"DB pool created (attempt {attempt})")
            return pool
        except Exception as e:
            logger.warning(f"DB pool creation failed (attempt {attempt}/{MAX_RETRIES}): {e}")
            if attempt == MAX_RETRIES:
                raise
            await asyncio.sleep(RETRY_DELAY * attempt)


async def execute_with_retry(coro_factory, *args, **kwargs):
    """Execute a DB operation with auto-retry on connection failure.

    Usage:
        row = await execute_with_retry(lambda p: p.fetchrow(sql, x, y))
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            pool = await get_db()
            return await coro_factory(pool)
        except (
            asyncpg.ConnectionDoesNotExistError,
            asyncpg.InterfaceError,
            ConnectionResetError,
            OSError,
        ) as e:
            logger.warning(f"DB connection error (attempt {attempt}/{MAX_RETRIES}): {e}")
            if attempt == MAX_RETRIES:
                raise
            # Force pool recreation
            await _force_reconnect()
            await asyncio.sleep(RETRY_DELAY * attempt)


async def _force_reconnect():
    """Close broken pool and force recreation on next get_db()."""
    global _pool
    if _pool is not None:
        try:
            await _pool.close()
        except Exception:
            pass
        _pool = None


async def close_db():
    """Close the connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
