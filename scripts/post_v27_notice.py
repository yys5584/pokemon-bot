"""Post v2.7 patch notice — 캠꾸, 방문, UX 개선."""
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from database.connection import get_db

NOTICE_TITLE = "v2.7 패치노트 — 캠프 꾸미기, 방문 시스템, UX 개선"
NOTICE_CONTENT = """\
📢 <b>v2.7 패치노트</b>

안녕하세요, 문박사입니다.

뽑기가 배틀생성의 <b>591.9%</b>를 소각하고 있습니다.
여러분의 미친 뽑기 사랑 덕분에 포획량과 배틀 참여가 급증했고,
DAU와 신규유저도 양전했습니다. 감사합니다!

DB 업그레이드를 마친 만큼, 차주에는
<b>4세대</b>와 <b>무한의 탑(PVE)</b> 같은 대형 업데이트를 준비하고 있습니다.

━━━━━━━━━━━━━━━━━━━━

<b style="color:#27ae60;font-size:15px">🏕️ 캠프 꾸미기 (캠꾸)</b>

캠프 소유자가 자신의 캠프를 꾸밀 수 있게 되었습니다.

• <b>환영 메시지 설정</b> — 방문자에게 보여지는 인사말을 직접 작성
• 최대 100자까지 자유롭게 작성 가능
• 캠프의 개성과 분위기를 표현해보세요!

<b>설정 방법:</b>
DM → <b>내캠프</b> → <b>⚙️ 캠프 관리</b> → <b>✏️ 멘트 설정</b>

━━━━━━━━━━━━━━━━━━━━

<b style="color:#2196F3;font-size:15px">🏕️ 캠프 방문 시스템</b>

다른 캠프에 놀러 가서 조각을 받을 수 있습니다!

• 캠프가 있는 <b>다른 채팅방</b>에서 <b>"방문"</b> 입력
• 해당 캠프의 활성 필드 중 <b>랜덤 조각</b>을 획득
• <b>캠프 레벨이 높을수록</b> 더 많은 조각! (Lv.1: 1개, Lv.10: 2~3개)
• 캠프당 <b>하루 1회</b> 방문 가능
• 소유자가 설정한 <b>환영 메시지</b>가 표시됩니다

💡 레벨이 높은 캠프일수록 방문 보상이 좋으니,
여러 캠프를 돌아다니며 조각을 모아보세요!

━━━━━━━━━━━━━━━━━━━━

<b style="color:#9C27B0;font-size:15px">✨ 내캠프 기능 강화</b>

DM에서 <b>"내캠프"</b>를 입력하면 이제 바로 사용할 수 있는 버튼이 제공됩니다.

• 🏕 <b>배치하기</b> — 포켓몬 배치
• ✨ <b>이로치전환</b> — 조각으로 이로치 변환
• 🔨 <b>분해</b> — 이로치를 결정으로 분해
• 🏠 <b>거점캠프</b> — 거점 확인/변경
• ⚙️ <b>캠프 관리</b> — 환영 메시지 등 설정 (소유자 전용)

━━━━━━━━━━━━━━━━━━━━

<b style="color:#FF9800;font-size:15px">🔧 UX 개선</b>

전체적으로 사용성을 개선했습니다.

• <b>분해 목록</b> — 8개씩 페이지네이션 (이전/다음 버튼)
• <b>이로치전환 목록</b> — 8개씩 페이지네이션 + 닫기 버튼
• <b>분해 목록에 IV 표시</b> — 같은 포켓몬도 IV로 구분 가능
• <b>IV재설정에 등급 필터</b> — 원하는 등급만 골라서 선택
• <b>전체 메뉴에 닫기 버튼</b> — 캠프, 내캠프, 아이템, IV재설정 등
• <b>명령어 오작동 방지</b> — "교환 뮤 라고 하셔야해요" 같은 대화가 명령어로 인식되던 문제 수정

━━━━━━━━━━━━━━━━━━━━

다음 업데이트도 기대해주세요!
— 문박사 드림 🧑‍🔬"""


async def main():
    pool = await get_db()

    await pool.execute(
        "INSERT INTO board_posts (board_type, user_id, display_name, tag, title, content) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        "notice", 1832746512, "TG포켓", "패치노트", NOTICE_TITLE, NOTICE_CONTENT,
    )
    print("OK: Notice posted")


if __name__ == "__main__":
    asyncio.run(main())
