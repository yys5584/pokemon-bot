"""Rollback board_posts id=17 to original content + add image only."""
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from database.connection import get_db


async def main():
    pool = await get_db()

    # Rollback: restore original content from send_skill_patch_notice.py + add image
    from scripts.send_skill_patch_notice import NOTICE_CONTENT
    r = await pool.execute(
        "UPDATE board_posts SET content=$1, image_filename=$2 WHERE id=17",
        NOTICE_CONTENT, "17_patch_v24.png",
    )
    print("✅ 공지사항 롤백 + 이미지 추가:", r)


if __name__ == "__main__":
    asyncio.run(main())
