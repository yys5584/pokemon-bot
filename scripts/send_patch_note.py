"""Send patch note DM to recently active users (custom emoji + opt-out)."""

import asyncio
import os
import sys
from datetime import timedelta
import aiohttp
import asyncpg

# Load .env
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Custom emoji helper
def _ce(eid, fallback="⭐"):
    return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'

# Icon shortcuts
BATTLE = _ce("6143344370625026850", "⚔️")
EXCHANGE = _ce("6143035201699193195", "🔄")
GOTCHA = _ce("6143385318843227267", "🎯")
BOOKMARK = _ce("6143229132357509310", "📖")
COIN = _ce("6143083713354801765", "💰")
BOLT = _ce("6143251942928818741", "⚡")
POKECENTER = _ce("6142954550803307680", "🏥")
CHECK = _ce("6143254176311811828", "✅")

PATCH_NOTE = f"""{BATTLE} <b>밸런스 패치!!</b>

{BOLT} <b>상성 배율 변경 (본가 동일)</b>
• 유리 상성: <b>2.0x</b> (기존 1.3x)
• 불리 상성: <b>0.5x</b> (기존 0.7x)
• 면역: <b>0x</b> (기존 0.3x)

{EXCHANGE} <b>89종 레어리티 재분류</b>
• 종족값(BST) 기준 재분류
• 윈디/갸라도스 → 에픽, 피카츄/메타몽 → 커먼 등

{GOTCHA} <b>출현률/포획률 상향</b>
• 에픽 출현 3배, 전설 출현 3배
• 전체 포획률 2배 (상시 적용)

{BOOKMARK} <b>홈페이지 가이드 개설</b>
• tgpoke.com → 가이드 탭
• 배틀/상성/등급/포획/육성/미션 가이드

{POKECENTER} <i>이 메시지를 받고 싶지 않으시면 '수신거부'를 입력해주세요.</i>"""


async def main():
    minutes = int(sys.argv[1]) if len(sys.argv) > 1 else 30

    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3,
                                     statement_cache_size=0)

    rows = await pool.fetch(
        """SELECT user_id FROM users
           WHERE last_active_at > NOW() - $1::interval
             AND (patch_optout IS NULL OR patch_optout = FALSE)""",
        timedelta(minutes=minutes),
    )
    user_ids = [r["user_id"] for r in rows]
    print(f"[INFO] {minutes}분 내 활성 유저 (수신거부 제외): {len(user_ids)}명")

    if "--dry-run" in sys.argv:
        print("[DRY-RUN] 실제 발송하지 않음")
        print(f"[PREVIEW]\n{PATCH_NOTE}")
        await pool.close()
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    sent, failed = 0, 0

    async with aiohttp.ClientSession() as session:
        for uid in user_ids:
            try:
                async with session.post(url, json={
                    "chat_id": uid,
                    "text": PATCH_NOTE,
                    "parse_mode": "HTML",
                }) as resp:
                    result = await resp.json()
                    if result.get("ok"):
                        sent += 1
                    else:
                        failed += 1
                        print(f"  [FAIL] {uid}: {result.get('description','')}")
            except Exception as e:
                failed += 1
                print(f"  [ERROR] {uid}: {e}")
            await asyncio.sleep(0.05)  # rate limit

    print(f"[DONE] 발송: {sent}, 실패: {failed}")
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
