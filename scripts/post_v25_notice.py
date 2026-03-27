"""Post v2.5 patch notice — 이로치 생태계 보호."""
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from database.connection import get_db

NOTICE_TITLE = "v2.5 패치노트 — 이로치 생태계 보호"
NOTICE_CONTENT = """\
📢 <b>v2.5 패치노트 — 이로치 생태계 보호</b>

안녕하세요, TG포켓입니다.

이로치는 본래 1%의 확률로 출현하는 희귀 포켓몬입니다.
하지만 최근 특정 채널에서 이로치 포획률이 비정상적으로 높고,
소수의 트레이너에게 집중되는 현상이 확인되었습니다.

모든 트레이너가 공정하게 이로치를 만날 수 있도록
아래와 같이 조정합니다.

<b style="color:#e74c3c;font-size:15px">■ 🔹 포켓볼 충전 쿨타임 조정</b>
• 충전 간격: 30초 → <b>5분</b>
• 구독자는 포켓볼 무제한이므로 충전이 필요 없습니다

<b style="color:#f39c12;font-size:15px">■ 🔹 아케이드 이용 조건 추가</b>
• 멤버 <b>10명 이상</b>인 채팅방에서만 아케이드 사용 가능
• 더 많은 트레이너와 함께 즐겨주세요!

<b style="color:#3498db;font-size:15px">■ 🔹 교환 일일 제한</b>
• 보내기/받기 각 <b>10회/일</b>

이로치의 희소성을 유지하고,
모든 트레이너에게 공정한 기회가 돌아갈 수 있도록
지속적으로 모니터링하겠습니다.
감사합니다 🙇"""


async def main():
    pool = await get_db()

    # v2.5 공지 등록
    await pool.execute(
        "INSERT INTO board_posts (board_type, user_id, display_name, title, content) "
        "VALUES ($1, $2, $3, $4, $5)",
        "notice", 1832746512, "TG포켓", NOTICE_TITLE, NOTICE_CONTENT,
    )
    print(f"✅ Notice posted: {NOTICE_TITLE}")


if __name__ == "__main__":
    asyncio.run(main())
