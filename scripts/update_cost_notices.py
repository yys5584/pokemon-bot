"""Update existing notices to reflect legendary cost 6 -> 5."""
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from database.connection import get_db


async def main():
    pool = await get_db()

    # Update notice ID=11 v2.0
    row = await pool.fetchrow("SELECT content FROM board_posts WHERE id = 11")
    if row:
        content = row["content"]
        content = content.replace(
            "⬜일반 <b>1</b> / 🟦레어 <b>2</b> / 🟪에픽 <b>4</b> / 🟨전설 <b>6</b> / 🟧초전설 <b>6</b>",
            "⬜일반 <b>1</b> / 🟦레어 <b>2</b> / 🟪에픽 <b>4</b> / 🟨전설 <b>5</b> / 🟧초전설 <b>6</b>",
        )
        content = content.replace(
            "초전설1 + 에픽2 + 레어1 + 일반2 = 6+4+4+2+1+1 = <b>18 ✅</b>",
            "초전설1 + 전설1 + 에픽1 + 레어1 + 일반1 = 6+5+4+2+1 = <b>18 ✅</b>",
        )
        await pool.execute("UPDATE board_posts SET content = $1 WHERE id = 11", content)
        print("Updated notice ID=11")

    # Update notice ID=10 v1.9.3
    row = await pool.fetchrow("SELECT content FROM board_posts WHERE id = 10")
    if row:
        content10 = row["content"]
        content10 = content10.replace(
            "초전설 코스트 7 → <b>6</b> (전설과 동일)",
            "초전설 코스트 7 → <b>6</b>, 전설 코스트 6 → <b>5</b>",
        )
        await pool.execute("UPDATE board_posts SET content = $1 WHERE id = 10", content10)
        print("Updated notice ID=10")

    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
