"""Post v2.0 notice to dashboard board."""
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from database.connection import get_db

NOTICE_TITLE = "v2.0 랭크전 & COST 시스템"
NOTICE_CONTENT = """\
🎉 드디어 v2.0 업데이트!

배틀의 새로운 시대가 열립니다.
랭크전, COST 시스템, 시즌제가 도입됩니다!

<b style="color:#e74c3c;font-size:15px">■ COST 시스템</b>
• 배틀팀 편성에 <b>코스트 제한</b>이 생깁니다
• ⬜일반 <b>1</b> / 🟦레어 <b>2</b> / 🟪에픽 <b>4</b> / 🟨전설 <b>5</b> / 🟧초전설 <b>6</b>
• 6마리 합계 <span style="color:#e74c3c;font-weight:700">18 COST 이하</span>로 편성해야 합니다
• 초전설은 팀당 <b>1마리</b> 제한
• 토너먼트 / 랭크전 모두 적용

💡 초전설1 + 전설1 + 에픽1 + 레어1 + 일반1 = 6+5+4+2+1 = <b>18 ✅</b>
💡 초전설1 + 에픽3 + 일반1 = 6+4+4+4+1 = <b>19 ❌</b>

<b style="color:#f39c12;font-size:15px">■ 랭크전 — DM 자동매칭</b>
• 봇 DM에서 <span style="color:#f39c12;font-weight:700">'랭전'</span> 입력 → 비슷한 티어 상대와 자동 대전!
• 실시간 대기 없이 상대의 팀 데이터와 바로 배틀합니다
• 이기면 <span style="color:#2ecc71;font-weight:700">RP 획득</span>, 지면 <span style="color:#e74c3c;font-weight:700">RP 차감</span>
• 상대에게도 결과가 <b>DM으로 전달</b>됩니다

<b style="color:#9b59b6;font-size:15px">■ 티어 시스템</b>
• RP를 쌓아 티어를 올려보세요!
• 🥉브론즈 → 🥈실버 → 🏅골드 → 💎플래티넘 → 💠다이아 → 👑마스터
• 마스터 상위 10명은 <span style="color:#9b59b6;font-weight:700">⚔️챌린저</span> 등극!
• 시즌 종료 시 티어별 <b>보상</b> 지급 (마스터볼, BP)

<b style="color:#3498db;font-size:15px">■ 시즌 조건</b>
• <b>2주 단위</b>로 시즌이 교체되며 매번 특별 조건이 걸립니다
• 🏆 제한 없음 — 풀 오픈 최강전
• 🚫 초전설 금지 / 전설 금지 / 드래곤 금지
• 🎯 에픽 이하 전용 / 👶 최종진화 금지
• 🔸 에픽 2마리 제한 등등...
• 시즌마다 <span style="color:#3498db;font-weight:700">메타가 바뀌니</span> 다양한 팀을 준비해두세요!

<b style="color:#2ecc71;font-size:15px">■ DM 명령어</b>
• <b>랭전</b> — 랭크 매칭 대전
• <b>시즌</b> — 현재 시즌 정보 확인
• <b>랭킹</b> — 시즌 순위 확인

프리시즌은 오늘 밤부터 시작됩니다.
즐거운 포켓몬 라이프 되세요! 🎮"""


async def main():
    pool = await get_db()
    await pool.execute(
        "INSERT INTO board_posts (board_type, user_id, display_name, title, content) "
        "VALUES ($1, $2, $3, $4, $5)",
        "notice", 1723681348, "TG포켓", NOTICE_TITLE, NOTICE_CONTENT,
    )
    print(f"✅ Notice posted: {NOTICE_TITLE}")


if __name__ == "__main__":
    asyncio.run(main())
