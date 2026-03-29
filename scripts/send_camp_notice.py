"""Send camp system patch DM (image + custom emoji text) + post homepage notice."""

import asyncio
import os
import sys
from datetime import timedelta
import aiohttp
import asyncpg
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DATABASE_URL = os.getenv("DATABASE_URL")
BOT_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_ID = 1832746512
IMAGE_PATH = os.path.join(os.path.dirname(__file__), "patch_note_camp.png")


def ce(eid, fallback=""):
    return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'


# --- Icons ---
crystal = ce("6143120589944004477", "💎")
battle = ce("6143344370625026850", "⚔️")
check = ce("6143254176311811828", "✅")
pokecenter = ce("6142954550803307680", "🏥")
footsteps = ce("6143075514262233319", "👣")
game = ce("6143111020756868297", "🎮")
bookmark = ce("6143229132357509310", "📖")
computer = ce("6143068826998151784", "🖥️")
exchange = ce("6143035201699193195", "🔄")

# Type emojis
t_grass = ce("6143236339312632261", "🌿")
t_fire = ce("6143060735279766934", "🔥")
t_water = ce("6143459776396271425", "💧")
t_electric = ce("6142971438614715696", "⚡")
t_rock = ce("6143423024361118748", "🪨")
t_psychic = ce("6143119490432375666", "🔮")

# --- DM Caption (with image) ---
CAPTION = (
    f"{game} <b>🏕️ 캠프 시스템 오픈!</b>\n"
    f"\n"
    f"{footsteps} <b>캠프란?</b>\n"
    f"  {check} 채팅방 멤버들과 함께 캠프 운영\n"
    f"  {check} 포켓몬을 필드에 배치하고 조각 획득\n"
    f"  {check} 조각을 모아 이로치 전환!\n"
    f"\n"
    f"{crystal} <b>6개 필드</b>\n"
    f"  {t_grass} 숲 (풀/벌레/독)\n"
    f"  {t_fire} 화산 (불꽃/드래곤/격투)\n"
    f"  {t_water} 호수 (물/얼음/비행)\n"
    f"  {t_electric} 도시 (전기/강철/노말)\n"
    f"  {t_rock} 동굴 (땅/바위/고스트)\n"
    f"  {t_psychic} 신전 (에스퍼/악/페어리)\n"
    f"\n"
    f"{battle} <b>라운드 (하루 6회)</b>\n"
    f"  {check} 09 / 12 / 15 / 18 / 21 / 00시\n"
    f"  {check} 접수 30분 → 파밍 2.5시간 → 정산\n"
    f"  {check} 보너스 포켓몬 배치 시 최대 7점!\n"
    f"\n"
    f"{exchange} <b>이로치 전환 (조각 소모)</b>\n"
    f"  {check} 일반 12 / 레어 24 / 에픽 42\n"
    f"  {check} 전설 60+크리스탈15 / 초전설 84+25+무지개3\n"
    f"\n"
    f"{computer} <b>명령어</b>\n"
    f"  {check} 그룹: 캠프 / 캠프맵 / 캠프개설 / 캠프설정\n"
    f"  {check} DM: 내캠프 / 이로치전환 / 분해\n"
    f"\n"
    f"{bookmark} 상세 가이드: tgpoke.com/camp\n"
    f"\n"
    f"{pokecenter} <i>수신거부: '수신거부' 입력</i>"
)

# --- Homepage Notice (HTML) ---
NOTICE_TITLE = "🏕️ 캠프 시스템 오픈!"
NOTICE_CONTENT = """\
📢 <b>🏕️ 캠프 시스템 오픈!</b>

안녕하세요, TG포켓입니다.
채팅방 멤버들과 함께 운영하는 <b>캠프 시스템</b>이 오픈되었습니다!

<b style="color:#4CAF50;font-size:15px">■ 🗺️ 6개 필드</b>
• 🌿숲 / 🔥화산 / 💧호수 / ⚡도시 / 🪨동굴 / 🔮신전
• 각 필드별 <b>보너스 타입</b> 존재 — 타입 매칭 시 추가 점수!

<b style="color:#FF9800;font-size:15px">■ ⏰ 라운드 시스템 (하루 6회)</b>
• 09:00 / 12:00 / 15:00 / 18:00 / 21:00 / 00:00
• 접수 30분 → 파밍 2시간 30분 → 정산
• 보너스 포켓몬 + IV + 이로치 = <b style="color:#e74c3c">최대 7점</b>

<b style="color:#2196F3;font-size:15px">■ ✨ 이로치 전환</b>
• 조각을 모아 보유 포켓몬을 이로치로 전환!
• 일반 12조각 / 레어 24 / 에픽 42+크리스탈5
• 전설 60+15 / 초전설 84+25+무지개3

<b style="color:#9C27B0;font-size:15px">■ 🏛️ Lv.10 기준 (최대 레벨)</b>
• 필드 6개 / 기본 슬롯 18 / 필드 캡 8
• 멤버 500명당 슬롯 +1 추가 보너스

<b style="color:#607D8B;font-size:15px">■ 💬 명령어</b>
• 그룹: <b>캠프</b> / <b>캠프맵</b> / <b>캠프개설</b> / <b>캠프설정</b>
• DM: <b>내캠프</b> / <b>이로치전환</b> / <b>분해</b>

👉 상세 가이드: <a href="https://tgpoke.com/camp" style="color:#58a6ff">tgpoke.com/camp</a>
즐거운 포켓몬 라이프 되세요! 🎮"""


async def send_photo_with_caption(session, bot_token, chat_id, image_path, caption):
    """Send photo + caption via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    with open(image_path, "rb") as f:
        data = aiohttp.FormData()
        data.add_field("chat_id", str(chat_id))
        data.add_field("caption", caption)
        data.add_field("parse_mode", "HTML")
        data.add_field("photo", f, filename="patch_note_camp.png",
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

    if mode == "notice":
        # Post homepage notice only
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2,
                                         statement_cache_size=0)
        await pool.execute(
            "INSERT INTO board_posts (board_type, user_id, display_name, title, content) "
            "VALUES ($1, $2, $3, $4, $5)",
            "notice", ADMIN_ID, "TG포켓", NOTICE_TITLE, NOTICE_CONTENT,
        )
        print(f"[OK] Notice posted: {NOTICE_TITLE}")
        await pool.close()
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
                        if "blocked" in desc.lower() or "deactivated" in desc.lower():
                            pass  # expected
                        else:
                            print(f"  [WARN] {uid}: {desc}")
                except Exception as e:
                    failed += 1
                    print(f"  [ERR] {uid}: {e}")
                await asyncio.sleep(0.05)

        print(f"[DONE] sent={sent}, failed={failed}")
        await pool.close()
        return

    print("Usage: python send_camp_notice.py [preview|notice|send] [minutes]")


if __name__ == "__main__":
    asyncio.run(main())
