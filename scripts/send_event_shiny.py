"""Send shiny+ultra 2x event DM to recently active users."""

import asyncio
import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import timedelta
import asyncpg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
BOT_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_ID = 1832746512


def ce(eid, fallback=""):
    return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'


# --- Icons ---
crystal = ce("6143120589944004477", "✨")       # 이로치
ultra = ce("6143244830462975904", "🔴")          # 초전설
bolt = ce("6143251942928818741", "⚡")
gotcha = ce("6143385318843227267", "🎯")
pokecenter = ce("6142954550803307680", "🏥")
battle = ce("6143344370625026850", "⚔️")
computer = ce("6143068826998151784", "🖥️")

# --- Event DM Text ---
TEXT = (
    f"{crystal} <b>이로치 & 초전설 2배 이벤트!</b>\n"
    f"\n"
    f"v3.0 랭크전 시즌 리워크 기념!\n"
    f"지금부터 이로치 · 초전설 스폰 확률이\n"
    f"<b>2배</b>로 증가합니다 {bolt}\n"
    f"\n"
    f"{crystal} 이로치 출현률 <b>x2</b>\n"
    f"{ultra} 초전설 스폰률 <b>x2</b>\n"
    f"\n"
    f"{battle} v3.0 패치노트: https://t.me/tg_poke_myu/38\n"
    f"\n"
    f"{pokecenter} <i>수신거부: '수신거부' 입력</i>"
)


def send_msg(bot_token, chat_id, text):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload,
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "preview"

    if mode == "preview":
        print(f"[PREVIEW] Sending to admin {ADMIN_ID}...")
        result = send_msg(BOT_TOKEN, ADMIN_ID, TEXT)
        if result.get("ok"):
            print("[OK] Preview sent!")
        else:
            print(f"[FAIL] {result}")
        return

    if mode == "send":
        minutes = int(sys.argv[2]) if len(sys.argv) > 2 else 180  # 3시간
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
        for uid in user_ids:
            try:
                result = send_msg(BOT_TOKEN, uid, TEXT)
                if result.get("ok"):
                    sent += 1
                else:
                    failed += 1
                    print(f"  [FAIL] {uid}: {result.get('description','')}")
            except Exception as e:
                failed += 1
                print(f"  [ERROR] {uid}: {e}")
            await asyncio.sleep(0.05)

        print(f"[DONE] 발송: {sent}, 실패: {failed}")
        await pool.close()
        return

    print("Usage: python send_event_shiny.py [preview|send] [minutes] [--dry-run]")


if __name__ == "__main__":
    asyncio.run(main())
