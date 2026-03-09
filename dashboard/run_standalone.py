"""Standalone dashboard server — production entry point.

Run as a separate process from the Telegram bot:
    python dashboard/run_standalone.py

Systemd service: pokemon-dashboard.service
"""
import asyncio
import logging
import os
import signal
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_DIR)
sys.path.insert(0, PROJECT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_DIR, ".env"))

# Sentry (optional)
_sentry_dsn = os.getenv("SENTRY_DSN", "")
if _sentry_dsn:
    import sentry_sdk
    sentry_sdk.init(
        dsn=_sentry_dsn,
        traces_sample_rate=0.02,  # 2% (was 10%) — reduce PgBouncer cleanup noise
        environment="dashboard",
        send_default_pii=False,
    )

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
)
logger = logging.getLogger("dashboard")

from aiohttp import web
from database.connection import get_db, close_db
from dashboard.server import (
    create_app,
    _ensure_session_table,
    _ensure_llm_usage_table,
    _ensure_analytics_table,
    _ensure_board_tables,
)


async def main():
    """Initialize DB, ensure tables, start aiohttp server."""
    logger.info("Starting dashboard server...")

    # DB 초기화
    await get_db()
    logger.info("Database connected.")

    # 대시보드 전용 테이블 확인
    await _ensure_session_table()
    await _ensure_llm_usage_table()
    await _ensure_analytics_table()
    await _ensure_board_tables()
    logger.info("Dashboard tables ready.")

    # aiohttp 서버 시작
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("DASHBOARD_PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Dashboard running at http://0.0.0.0:{port}")

    # Graceful shutdown 대기
    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)
    await stop_event.wait()

    # Cleanup
    logger.info("Shutting down dashboard...")
    await runner.cleanup()
    await close_db()
    logger.info("Dashboard stopped.")


if __name__ == "__main__":
    asyncio.run(main())
