"""전 유저에게 성격 변경권 5개 지급."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()


async def main():
    from database.connection import get_db

    pool = await get_db()

    # 활성 유저 수 확인
    count = await pool.fetchval("SELECT COUNT(*) FROM users")
    print(f"Total users: {count}")

    # 전 유저에게 personality_ticket 5개 지급
    await pool.execute("""
        INSERT INTO user_items (user_id, item_type, quantity)
        SELECT user_id, 'personality_ticket', 5 FROM users
        ON CONFLICT (user_id, item_type)
        DO UPDATE SET quantity = user_items.quantity + 5
    """)

    print(f"Granted 5 personality tickets to {count} users")


if __name__ == "__main__":
    asyncio.run(main())
