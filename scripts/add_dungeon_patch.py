"""던전 v2 패치노트 등록."""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
from database.connection import get_db

async def main():
    pool = await get_db()
    title = "\U0001f3f0 던전 시스템 v2 업데이트"
    content = (
        "<h3>\U0001f3f0 던전 시스템 밸런스 대규모 업데이트</h3>"
        "<h4>\u2694\ufe0f 밸런스 조정</h4>"
        "<ul>"
        "<li><b>버프 슬롯 상한 8개</b> \u2014 최대 8개까지만 보유 가능</li>"
        "<li><b>생존 계열 1택</b> \u2014 흡혈/층간회복/보호막 중 1개만 선택 가능</li>"
        "<li><b>BP 상한 2,000</b> \u2014 구독 배율 포함 최대 2,000BP</li>"
        "<li><b>BP 마일스톤 하향</b> \u2014 전체적으로 BP 보상 감소</li>"
        "<li><b>입장권 구매 비용 300BP</b>로 인상</li>"
        "</ul>"
        "<h4>\U0001f3ab 입장권 &amp; 횟수 변경</h4>"
        "<ul>"
        "<li>일일 런 횟수: 일반 <b>3회</b> / 프리미엄 구독 <b>5회</b></li>"
        "<li>입장권 보상: <b>40층</b>에서만 1장 (기존 10/20/50층 제거)</li>"
        "<li>구매 비용: 일반 300BP / 베이직 250BP / 채널장 200BP</li>"
        "</ul>"
        "<h4>\U0001f4ca 적 스탯 배율 표시</h4>"
        "<ul>"
        "<li>적 포켓몬에 <b>(\u00d71.4)</b> 같은 스탯 배율이 표시됩니다</li>"
        "<li>고층일수록 배율이 높아져 난이도를 직관적으로 알 수 있습니다</li>"
        "</ul>"
        "<h4>\U0001f6e0 버그 수정</h4>"
        "<ul>"
        "<li>던전 입장이 씹히는 현상 수정</li>"
        "<li>관장전에서 전투가 멈추는 현상 수정</li>"
        "<li>보상 지급 실패 시 나머지 보상이 누락되는 문제 수정</li>"
        "<li>포켓몬 로드 실패 시 런이 영구 stuck 되는 문제 수정 (자동 환불)</li>"
        "</ul>"
        "<h4>\U0001f48e 보상 아이템</h4>"
        "<ul>"
        "<li><b>\U0001f4a0 IV스톤</b> \u2014 원하는 포켓몬의 IV 스탯 +3 (최대 31). 아이템 메뉴에서 사용</li>"
        "<li><b>\U0001f9e9 만능 조각</b> \u2014 캠프 이로치 전환 시 아무 타입 조각으로 자동 보충</li>"
        "</ul>"
        '<p style="margin-top:12px;color:#888;font-size:12px">자세한 내용은 가이드 &gt; 던전 탭을 참고해주세요.</p>'
    )
    post_id = await pool.fetchval(
        "INSERT INTO board_posts (board_type, user_id, display_name, tag, title, content) "
        "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
        "notice", 1832746512, "TG\ud3ec\ucf13", "\ud328\uce58\ub178\ud2b8", title, content
    )
    print(f"Post created: id={post_id}")

asyncio.run(main())
