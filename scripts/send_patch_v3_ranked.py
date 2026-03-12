"""Send v3.0 patch note DM (image + custom emoji text) to admin preview / all users."""

import asyncio
import os
import sys
from datetime import timedelta
import aiohttp
import asyncpg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
BOT_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_ID = 1832746512
IMAGE_PATH = os.path.join(os.path.dirname(__file__), "patch_note_v3_ranked.png")


def ce(eid, fallback=""):
    return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'


# --- Icons ---
crystal = ce("6143120589944004477", "💎")
battle = ce("6143344370625026850", "⚔️")
bolt = ce("6143251942928818741", "⚡")
coin = ce("6143083713354801765", "💰")
pokeball = ce("6143151702687095487", "🔴")
hyperball = ce("6142944354550946803", "🔵")
masterball = ce("6143130859210807699", "⚫")
gotcha = ce("6143385318843227267", "🎯")
check = ce("6143254176311811828", "✅")
pikachu = ce("6143424549074508692", "🟢")
crown = ce("6143265588039916937", "🟣")
shopping = ce("6143287260444892433", "🏪")
exchange = ce("6143035201699193195", "🔄")
pokecenter = ce("6142954550803307680", "🏥")
computer = ce("6143068826998151784", "🖥️")
bookmark = ce("6143229132357509310", "📖")
skill = ce("6143088085631507366", "📊")

# --- Patch Note Text ---
CAPTION = (
    f"{battle} <b>v3.0 랭크전 시즌 리워크 + 월간 구독</b>\n"
    f"\n"
    f"{gotcha} <b>랭크전 시즌 시스템</b>\n"
    f"  {check} 배치전 5판 후 티어 배정\n"
    f"  {check} 숨겨진 MMR (Elo 기반 실력 지표)\n"
    f"  {check} 승급 보호: 새 디비전 진입 후 12시간\n"
    f"  {check} 디케이: 마스터+ 3일 미플레이 시 RP 감소\n"
    f"  {check} 2주 시즌, 7일차 RP 60% 리셋\n"
    f"\n"
    f"{crystal} <b>월간 구독 서비스</b>\n"
    f"  {pikachu} <b>베이직</b> $3.90/월\n"
    f"    {pokeball} 포케볼 무제한 / 쿨다운 해제\n"
    f"    {masterball} 마스터볼 +1 / {hyperball} 하이퍼볼 +5\n"
    f"    {coin} BP/미션 보상 1.5배\n"
    f"  {crown} <b>채널장</b> $9.90/월\n"
    f"    {check} 베이직 전부 포함\n"
    f"    {bolt} 강제스폰 무제한 / 스폰률 +50%\n"
    f"\n"
    f"{computer} <b>대시보드 & 기타</b>\n"
    f"  {bookmark} 시즌 랭킹 + 내 푸키몬 랭크카드\n"
    f"  {exchange} 교환 진화 경로 수정 (킹드라 등 4종)\n"
    f"\n"
    f"{pokecenter} <i>수신거부: '수신거부' 입력</i>"
)


async def send_photo_with_caption(session, bot_token, chat_id, image_path, caption):
    """Send photo + caption via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    with open(image_path, "rb") as f:
        data = aiohttp.FormData()
        data.add_field("chat_id", str(chat_id))
        data.add_field("caption", caption)
        data.add_field("parse_mode", "HTML")
        data.add_field("photo", f, filename="patch_note_v3.png",
                       content_type="image/png")
        async with session.post(url, data=data) as resp:
            return await resp.json()


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "preview"

    if mode == "preview":
        # Admin preview only
        print(f"[PREVIEW] Sending to admin {ADMIN_ID}...")
        async with aiohttp.ClientSession() as session:
            result = await send_photo_with_caption(
                session, BOT_TOKEN, ADMIN_ID, IMAGE_PATH, CAPTION)
            if result.get("ok"):
                print("[OK] Preview sent!")
            else:
                print(f"[FAIL] {result}")
        return

    if mode == "send":
        # Send to all active users
        minutes = int(sys.argv[2]) if len(sys.argv) > 2 else 10080  # 7 days
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
            await pool.close()
            return

        sent, failed = 0, 0
        async with aiohttp.ClientSession() as session:
            for uid in user_ids:
                try:
                    result = await send_photo_with_caption(
                        session, BOT_TOKEN, uid, IMAGE_PATH, CAPTION)
                    if result.get("ok"):
                        sent += 1
                    else:
                        failed += 1
                        desc = result.get("description", "")
                        print(f"  [FAIL] {uid}: {desc}")
                except Exception as e:
                    failed += 1
                    print(f"  [ERROR] {uid}: {e}")
                await asyncio.sleep(0.05)

        print(f"[DONE] 발송: {sent}, 실패: {failed}")
        await pool.close()
        return

    print("Usage: python send_patch_v3_ranked.py [preview|send] [minutes] [--dry-run]")


if __name__ == "__main__":
    asyncio.run(main())
