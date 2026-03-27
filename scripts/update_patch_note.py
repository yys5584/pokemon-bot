"""Update patch note post on dashboard board."""
import asyncio
import os
import asyncpg
from dotenv import load_dotenv
load_dotenv()

CONTENT = """v1.9 패치가 적용되었습니다!

<b style="color:#e74c3c;font-size:15px">■ 합성 시스템</b>
• 같은 종 포켓몬 <b>2마리 → 랜덤 IV 1마리</b>
• 텔레그램 DM + 대시보드 양쪽 지원
• <span style="color:#ff6b6b;font-weight:700">이로치 합성 시 결과도 이로치 보장</span>
• 합성 결과 <b>DM 알림</b> 발송

<b style="color:#f39c12;font-size:15px">■ 대시보드 리뉴얼</b>
• UI <b>전면 리디자인</b>
• 도감 <b>상세모달</b> + 스텟바 정규화
• <b>방생 기능</b> 추가 (세대 필터 포함)
• 볼 <b>커스텀이모지</b> 적용

<b style="color:#2ecc71;font-size:15px">■ 배틀 & 대회 개선</b>
• 결승전 스킬 사용 시 <b>카드 이미지</b> 표시
• 교체 대사 <b>4티어 분리</b> (일반/에픽/전설/초전설)
• 드라마틱 연출 <b>8강 확장</b> + 마지막 포켓몬 연출
• 티배깅 멘트 전면 개편 (<span style="color:#e74c3c">유머/상황극 47개</span>)
• 대회 등록자 <b>DB 저장</b> → 재시작 시 자동 복구
• 연속 클릭 <b>중복 응답 방지</b>

<b style="color:#9b59b6;font-size:15px">■ 거래소 필터</b>
• <b>등급 필터</b>: 커먼 ~ 초전설
• <b>개체값 필터</b>: <span style="color:#e74c3c">S</span> / <span style="color:#f39c12">A</span> / <span style="color:#3498db">B</span> 등급 이상

<b style="color:#3498db;font-size:15px">■ AI 어드바이저 개편</b>
• 채팅 모드 제거, <b>빠른분석만 유지</b>
• 카운터 추천: <b>실전 메타 + 전투력 기반</b> 개선

<b style="color:#95a5a6;font-size:15px">■ 기타</b>
• 게을킹 스킬 너프 (<span style="color:#95a5a6">나태 특성</span> 반영)
• 이로치 카드 별 색상 <span style="color:#ff69b4">핑크</span>~<span style="color:#e74c3c">빨강</span> 변경
• 이벤트 DM 알림 시스템
• 도감왕 랭킹 총 포켓몬 수 동적 계산

즐거운 포켓몬 라이프 되세요! 🎮"""


async def main():
    pool = await asyncpg.create_pool(
        os.getenv("DATABASE_URL"), statement_cache_size=0
    )
    await pool.execute(
        "UPDATE board_posts SET content = $1 WHERE id = 4", CONTENT
    )
    row = await pool.fetchrow("SELECT title, display_name, content FROM board_posts WHERE id = 4")
    print(f"Title: {row['title']}")
    print(f"Author: {row['display_name']}")
    print(f"Content updated ({len(row['content'])} chars)")
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
