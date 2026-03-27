"""Fachenko 24시간 포획 정지."""
import asyncio
import dotenv
dotenv.load_dotenv()

from database.connection import get_db


async def main():
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT user_id FROM users WHERE username = $1", "Fachenko")
    if not row:
        print("Fachenko not found")
        return
    uid = row["user_id"]
    await pool.execute(
        "UPDATE abuse_scores SET locked_until = NOW() + INTERVAL '24 hours', updated_at = NOW() WHERE user_id = $1",
        uid)
    check = await pool.fetchrow(
        "SELECT locked_until FROM abuse_scores WHERE user_id = $1", uid)
    locked = check["locked_until"] if check else "?"
    print(f"Fachenko (uid={uid}) locked until {locked}")


asyncio.run(main())
