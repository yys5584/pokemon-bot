"""일일 KPI 리포트 수동 발송 스크립트.

main.py의 _send_daily_kpi_report 함수를 직접 호출하여
패치내역, 인사이트 등 모든 섹션 포함.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))


async def main():
    from database import connection
    await connection.get_db()

    # main.py의 리포트 함수 직접 사용
    from main import _send_daily_kpi_report
    from telegram import Bot

    BOT_TOKEN = os.getenv("BOT_TOKEN")

    class FakeContext:
        def __init__(self):
            self.bot = Bot(token=BOT_TOKEN)

    ctx = FakeContext()
    await _send_daily_kpi_report(ctx)
    print("Daily KPI report sent!")


asyncio.run(main())
