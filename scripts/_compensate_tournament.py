"""3/26 토너먼트 미지급 보상 처리 + 알림 DM 발송"""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]

# 1위: peterchat7 (7050637391) - IV+3 미지급
# 2위: mc7979 (336224560) - IV+3 미지급
WINNER_ID = 7050637391
RUNNER_UP_ID = 336224560

# 참가자 전원 (보상은 지급됐으나 DM 알림 누락)
# 로그에서 확인된 참가자 목록은 DB에서 가져옴

async def main():
    import asyncpg
    from telegram import Bot

    bot = Bot(token=BOT_TOKEN)
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL'], statement_cache_size=0)

    # 1) IV+3 스톤 지급 (1위, 2위)
    for uid, place in [(WINNER_ID, "1위"), (RUNNER_UP_ID, "2위")]:
        try:
            await pool.execute(
                "INSERT INTO user_items (user_id, item_type, quantity) VALUES ($1, 'iv_stone_3', 1) "
                "ON CONFLICT (user_id, item_type) DO UPDATE SET quantity = user_items.quantity + 1",
                uid
            )
            print(f"[OK] {place} ({uid}) IV+3 스톤 지급 완료")
        except Exception as e:
            print(f"[FAIL] {place} ({uid}) IV+3 지급 실패: {e}")

    # 1위, 2위 DM
    for uid, place in [(WINNER_ID, "1위"), (RUNNER_UP_ID, "2위")]:
        try:
            await bot.send_message(
                chat_id=uid,
                text=(
                    f"📢 <b>3/26 토너먼트 보상 보정 안내</b>\n\n"
                    f"어제 토너먼트 {place} 보상 중 <b>IV+3 스톤</b>이 누락되었습니다.\n"
                    f"지금 <b>IV+3 스톤 1개</b> 추가 지급되었습니다!\n\n"
                    f"불편 드려 죄송합니다 🙏"
                ),
                parse_mode="HTML"
            )
            print(f"[DM] {place} ({uid}) 알림 전송 완료")
        except Exception as e:
            print(f"[DM FAIL] {place} ({uid}): {e}")

    # 2) 참가자 전원에게 보상 지급 알림 DM
    # 이미 보상(마볼1+500BP)은 지급됐으나 알림만 안 간 유저들
    # tournament_results에서 3/26 참가자 목록 가져오기
    participants = await pool.fetch("""
        SELECT DISTINCT tr.user_id
        FROM tournament_player_results tr
        WHERE tr.tournament_id = (
            SELECT id FROM tournament_results
            ORDER BY id DESC LIMIT 1
        )
        AND tr.user_id NOT IN ($1, $2)
    """, WINNER_ID, RUNNER_UP_ID)

    if not participants:
        # tournament_player_results 없으면 다른 방법
        print("[INFO] tournament_player_results에서 참가자를 찾을 수 없음. 스킵.")
    else:
        sent = 0
        failed = 0
        for row in participants:
            uid = row['user_id']
            try:
                await bot.send_message(
                    chat_id=uid,
                    text=(
                        "📢 <b>3/26 토너먼트 보상 안내</b>\n\n"
                        "어제 토너먼트 참가 보상이 정상 지급되었으나\n"
                        "알림 메시지가 발송되지 않았습니다.\n\n"
                        "🟣 마스터볼 1개 + 💰500BP\n"
                        "→ 이미 지급 완료되었습니다!\n\n"
                        "확인 부탁드립니다 🙏"
                    ),
                    parse_mode="HTML"
                )
                sent += 1
            except Exception as e:
                failed += 1
                print(f"[DM FAIL] {uid}: {e}")
            await asyncio.sleep(0.1)  # rate limit 방지

        print(f"[완료] 참가자 DM: {sent}명 성공, {failed}명 실패")

    await pool.close()
    await bot.close()

asyncio.run(main())
