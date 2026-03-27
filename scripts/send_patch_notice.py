"""One-time script: send v1.9.1 patch DMs + post homepage notice."""
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from database.connection import get_db

DM_TEXT = (
    "🏠 채팅방 레벨 시스템 업데이트!\n\n"
    "채팅방에서 포켓몬을 잡고, 배틀하고, 교환하면 채팅방 경험치(CXP)가 쌓여요!\n"
    "(일일 상한 50 CXP)\n\n"
    "📊 레벨별 혜택\n"
    "• Lv.2+ 보너스 스폰 & 이로치 확률 UP\n"
    "• Lv.4+ 매일 이로치 스폰 1회 보장 ✨\n"
    "• Lv.8+ 매일 자동 아케이드 1시간 🎰\n\n"
    "💬 채팅방에서 '방정보' 입력으로 현재 레벨과 혜택을 확인하세요!"
)

NOTICE_TITLE = "v1.9.1 채팅방 레벨 시스템"
NOTICE_CONTENT = (
    'v1.9.1 패치가 적용되었습니다!\n\n'
    '<b style="color:#2ecc71;font-size:15px">■ 채팅방 레벨 시스템</b>\n'
    '• 포획(<b>+1</b>), 배틀(<b>+2</b>), 교환(<b>+1</b>)으로 채팅방 CXP 획득 '
    '<span style="color:#f39c12;font-weight:700">(일일 상한 50)</span>\n'
    '• Lv.1~10 레벨업 시 <b>보너스 스폰</b>, <b>이로치율</b>, <b>레어리티 부스트</b>\n'
    '• Lv.4+ <span style="color:#ff6b6b;font-weight:700">매일 이로치 스폰 1회 보장</span>\n'
    '• Lv.8+ <span style="color:#9b59b6;font-weight:700">매일 자동 아케이드 1시간</span>\n'
    '• <b>방정보</b> 명령어로 레벨/혜택 확인\n\n'
    '즐거운 포켓몬 라이프 되세요! 🎮'
)


async def main():
    pool = await get_db()

    # 1. Post notice
    await pool.execute(
        "INSERT INTO board_posts (board_type, user_id, display_name, title, content) "
        "VALUES ($1, $2, $3, $4, $5)",
        "notice", 1723681348, "TG포켓", NOTICE_TITLE, NOTICE_CONTENT,
    )
    print("Notice posted.")

    # 2. Send DMs to 6h active users
    rows = await pool.fetch(
        "SELECT user_id FROM users WHERE last_active_at >= NOW() - INTERVAL '6 hours'"
    )
    print(f"Sending DMs to {len(rows)} users...")

    import aiohttp
    token = os.environ["BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    sent = 0
    fail = 0
    async with aiohttp.ClientSession() as session:
        for r in rows:
            uid = r["user_id"]
            try:
                async with session.post(url, data={"chat_id": str(uid), "text": DM_TEXT}) as resp:
                    if resp.status == 200:
                        sent += 1
                    else:
                        fail += 1
            except Exception:
                fail += 1
            await asyncio.sleep(0.05)
    print(f"Done. sent={sent}, fail={fail}")


if __name__ == "__main__":
    asyncio.run(main())
