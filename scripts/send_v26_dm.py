"""v2.6 DM 공지 브로드캐스트."""
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from database.connection import get_db

DM_TEXT = """\
📢 <b>v2.6 업데이트 — 문박사의 패치노트</b>

안녕하세요, 문박사입니다.
오늘 꽤 큰 업데이트가 있어서 직접 설명드립니다.




<b>🏕️ 캠프 시스템 리뉴얼</b>

TG포켓에는 배틀을 즐기는 허슬러 유저와, 수집을 즐기는 일반 유저가 있습니다.
캠프는 원래 일반 유저분들도 포켓몬을 활용할 수 있게 만든 시스템인데...
솔직히 너무 어려웠습니다. 그래서 전면 리뉴얼했습니다.

거점캠프를 정하고, 포켓몬을 배치하면 매일 자동 정산.
DM에서 '캠프' 한 마디면 끝입니다.

<blockquote expandable>
<b>캠프 리뉴얼 상세</b>
• 거점캠프 — 내 채팅방 하나를 거점으로 지정
• 상시배치 — 포켓몬 배치 후 매일 자동 보상 정산
• DM 직접 배치 — DM에서 '캠프' 입력
• 일일 정산 DM — 매일 결과 알림
• 대시보드 캠프 탭 추가
• 캠프 가이드 10단계 튜토리얼 (DM에서 '캠프가이드')
</blockquote>




<b>🎰 BP 뽑기 (신규!)</b>

BP 인플레이션이 심각했습니다.
열심히 배틀하시는 분들의 BP가 쌓이기만 하고 쓸 곳이 없었어요.

그래서 만들었습니다 — BP 가챠.
100 BP로 피카츄 점술사의 구슬을 돌려보세요.

구슬이 잔잔하면 평범한 결과,
<b>구슬이 미친듯이 빛나면... 대박입니다.</b>
(뒤에 어떤 포켓몬이 보이는지도 잘 살펴보세요 👀)

DM에서 '뽑기'를 입력하세요!

<blockquote expandable>
<b>보상 목록</b>
💰 BP 환급 (20~50) — 35%
🔵 하이퍼볼 ×2 — 20%
🟣 마스터볼 ×1 — 15%
🔄 개체값 재설정권 ×1 — 12%
💎 BP 잭팟 +300 — 8%
🎯 IV 선택 리롤 ×1 — 5%
🥚 이로치 알 ×1 — 3%
✨ 이로치 강스권 ×1 — 2%

<b>신규 아이템 가이드</b>
🔄 <b>개체값 재설정권</b> — 포켓몬 1마리의 IV 6종 전부 리롤
   → DM '아이템' → 포켓몬 선택 → 자동 리롤

🎯 <b>IV 선택 리롤</b> — 원하는 스탯 1개만 골라서 리롤
   → DM '아이템' → 포켓몬 선택 → 스탯 선택

🥚 <b>이로치 알</b> — 24시간 후 부화 → 확정 이로치!
   → DM '아이템'으로 부화 시간 확인

✨ <b>이로치 강스권</b> — 강제스폰 시 자동 소비 → 확정 이로치
</blockquote>




<b>💰 포획 BP 보상 (신규!)</b>

"배틀 안 하는데 BP를 어떻게 모아요?"

이제 포켓몬을 잡으면 <b>20~50 BP</b>를 자동으로 받습니다.
포켓몬 잡고 → BP 모으고 → 뽑기 돌리고 → 아이템으로 강화하고...
이 순환을 만들고 싶었습니다.




<b>⚔️ 랭크전 개선</b>

"랭크전 해도 BP가 똑같으면 왜 하지?" — 맞는 말이었습니다.

• 랭크전 BP <b>2배</b> (도전자)
• 동일 상대 RP 최소 보장




<blockquote expandable>
<b>기타 변경사항</b>
• 포획 메시지에 랭크 티어 뱃지 표시
• 배틀/대회 로그에 이로치 이모지
• UTC/KST 타임존 버그 수정
• 가이드 페이지 리뉴얼
</blockquote>

이번 패치의 핵심은 <b>"할 게 생겼다"</b>입니다.
재미있게 즐겨주세요!

— 문박사 드림 🧑‍🔬"""


async def main():
    from telegram import Bot
    bot = Bot(token=os.environ["BOT_TOKEN"])
    pool = await get_db()

    # 최근 7일 활성 유저
    rows = await pool.fetch(
        "SELECT DISTINCT user_id FROM user_pokemon WHERE caught_at > NOW() - INTERVAL '7 days'"
    )
    user_ids = [r["user_id"] for r in rows]
    print(f"📤 {len(user_ids)}명에게 DM 발송 시작...")

    success = 0
    fail = 0
    for uid in user_ids:
        try:
            await bot.send_message(chat_id=uid, text=DM_TEXT, parse_mode="HTML")
            success += 1
        except Exception as e:
            fail += 1
            if "bot was blocked" not in str(e).lower():
                print(f"  ❌ {uid}: {e}")
        await asyncio.sleep(0.05)  # rate limit

    print(f"✅ 완료: {success}명 성공, {fail}명 실패")


if __name__ == "__main__":
    asyncio.run(main())
