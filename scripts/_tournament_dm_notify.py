"""3/26 토너먼트 참가자 전원에게 보상 지급 확인 DM 발송"""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]

# 이미 IV+3 DM 보낸 1위/2위 제외
ALREADY_NOTIFIED = {7050637391, 336224560}

# 입상자 정보 (BP amount로 구분)
PRIZE_INFO = {
    5000: "🥇 1위: 마스터볼 5개 + 5,000BP + 이로치 포켓몬 + 챔피언 칭호",
    3000: "🥈 2위: 마스터볼 3개 + 3,000BP + 이로치 포켓몬",
    2000: "🏅 4강: 마스터볼 2개 + 2,000BP + 이로치 포켓몬",
    1000: "⚔️ 8강: 마스터볼 2개 + 1,000BP",
    500: "🎟️ 참가: 마스터볼 1개 + 500BP",
}

async def main():
    import asyncpg
    from telegram import Bot

    bot = Bot(token=BOT_TOKEN)
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL'], statement_cache_size=0)

    # 3/26 토너먼트 BP 지급 기록에서 참가자 추출
    rows = await pool.fetch("""
        SELECT user_id, amount FROM bp_log
        WHERE source = 'tournament'
        AND created_at >= '2026-03-26 13:19:00'
        AND created_at <= '2026-03-26 13:21:00'
        ORDER BY amount DESC
    """)

    # 같은 유저가 2번 나올 수 있음 (입상 BP + 참가 BP)
    # 가장 높은 amount로 대표
    user_prizes = {}
    for r in rows:
        uid = r['user_id']
        amt = r['amount']
        if uid not in user_prizes or amt > user_prizes[uid]:
            user_prizes[uid] = amt

    sent = 0
    failed = 0
    skipped = 0

    for uid, amount in user_prizes.items():
        if uid in ALREADY_NOTIFIED:
            skipped += 1
            continue

        prize_text = PRIZE_INFO.get(amount, f"💰 {amount:,}BP")

        try:
            await bot.send_message(
                chat_id=uid,
                text=(
                    "📢 <b>3/26 토너먼트 보상 안내</b>\n\n"
                    "어제 토너먼트 보상이 정상 지급되었으나\n"
                    "알림 메시지가 발송되지 않았습니다.\n\n"
                    f"<b>{prize_text}</b>\n\n"
                    "→ 이미 지급 완료되었습니다!\n"
                    "확인 부탁드립니다 🙏"
                ),
                parse_mode="HTML"
            )
            sent += 1
            print(f"[OK] {uid} ({amount}BP)")
        except Exception as e:
            failed += 1
            print(f"[FAIL] {uid}: {e}")
        await asyncio.sleep(0.15)

    print(f"\n[완료] 전송: {sent}명, 실패: {failed}명, 스킵(이미알림): {skipped}명")

    await pool.close()
    await bot.close()

asyncio.run(main())
