"""Post dungeon v2.0 patch notice — 뱀서식 레벨업 + 시너지."""
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from database.connection import get_db

NOTICE_TITLE = "🏰 던전 대규모 업데이트 — 뱀서식 빌드 + 히든 시너지"
NOTICE_CONTENT = """\
📢 <b>던전 v2.0 업데이트</b>

던전 시스템이 대규모로 리뉴얼되었습니다!

━━━━━━━━━━━━━━━━━━━━

<b style="color:#8b5cf6;font-size:15px">⬆️ 뱀서식 레벨업 시스템</b>

같은 버프를 다시 선택하면 레벨업됩니다!

• <b>Lv.1 → Lv.2 → Lv.3 (MAX)</b>
• MAX 도달 시 선택지에서 사라짐
• 전략적 빌드 구성이 가능해졌습니다

━━━━━━━━━━━━━━━━━━━━

<b style="color:#f43f5e;font-size:15px">🗡 신규 전투 버프 4종</b>

• ⚡ <b>크리 강화</b> — 크리티컬 확률 +10~25%
• ⚔️ <b>이중타격</b> — 15~30% 확률 2회 공격
• 💨 <b>회피 본능</b> — 10~25% 적 공격 회피
• 🦔 <b>가시갑옷</b> — 받은 피해 15~35% 반사

━━━━━━━━━━━━━━━━━━━━

<b style="color:#22c55e;font-size:15px">🛡️ 신규 생존 버프</b>

• <b>보호막</b> — 매 층 시작 시 HP 10~20% 실드
• 스킵 HP 회복: 5% → <b>50%</b>로 대폭 상향
• 전능의 기운: +10% → <b>+15%</b>로 상향

━━━━━━━━━━━━━━━━━━━━

<b style="color:#f59e0b;font-size:15px">✨ 히든 시너지 (총 6종)</b>

특정 버프 조합을 완성하면 숨겨진 효과가 발동!

🔥 <b>필살연격</b> — 크리 시 특수 효과
👻 <b>잔상</b> — 회피 시 특수 효과
💀 <b>사신의 낫</b> — 적 즉사 효과
... 외 3종

💡 비슷한 성격의 버프를 Lv.2 이상으로 조합해보세요!

━━━━━━━━━━━━━━━━━━━━

<b style="color:#3b82f6;font-size:15px">🎬 스킬 GIF 연출</b>

• 매 층 배틀에서 <b>Canvas 스킬 GIF</b> 재생
• 내 공격 GIF → 적 반격 GIF → 결과
• 초전설 포켓몬은 <b>전용 궁극기 연출!</b>
  (뮤츠 · 레쿠쟈 · 루기아 · 칠색조)

━━━━━━━━━━━━━━━━━━━━

<b>📋 기타 변경</b>

• 던전 UI 커스텀이모지 전면 적용
• 배틀 결과에 상세 전투 요약 표시
• 보유 버프 + 시너지 실시간 표시
• HP바 애니메이션 개선

━━━━━━━━━━━━━━━━━━━━

봇 DM → <b>「던전」</b> 입력으로 시작하세요!
자세한 가이드는 tgpoke.com 가이드 탭에서 확인!
"""


async def main():
    pool = await get_db()
    await pool.execute(
        "INSERT INTO board_posts (board_type, user_id, display_name, tag, title, content) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        "notice",
        1832746512,
        "TG포켓",
        "패치노트",
        NOTICE_TITLE,
        NOTICE_CONTENT,
    )
    print("Notice posted OK")


if __name__ == "__main__":
    asyncio.run(main())
