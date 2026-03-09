"""Post v2.1 patch notice + pin v2.0 post."""
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from database.connection import get_db

NOTICE_TITLE = "v2.1 패치노트 — 거래소 & QoL 업데이트"
NOTICE_CONTENT = """\
🛠️ v2.1 패치가 적용되었습니다!

거래소 웹 오픈, 배틀 밸런스 강화, 다수의 편의성 개선이 포함되어 있습니다.

<b style="color:#e74c3c;font-size:15px">■ 🏪 거래소 — tgpoke.com에서 사고팔기</b>
• <b>tgpoke.com</b>에 <span style="color:#e74c3c;font-weight:700">거래소 탭</span>이 새로 추가되었습니다!
• 🔍 <b>매물 둘러보기</b> — 로그인 없이도 현재 등록된 매물을 검색할 수 있습니다
• 등급(일반~초전설), IV등급(S/A/B/C), ✨이로치, 가격대, 이름으로 <b>필터 & 검색</b> 가능
• 정렬: 최신순 / 가격 낮은순 / 가격 높은순 / 등급순
• 📤 <b>판매 등록</b> — 내 포켓몬 중 팀·즐겨찾기에 등록되지 않은 포켓몬을 선택해 가격을 설정하고 매물로 등록
• 수수료 5%가 실시간으로 표시되며 예상 수익이 자동 계산됩니다
• 💰 <b>구매</b> — 매물 카드에서 [구매] 버튼 → 확인 모달에서 내 BP 잔고와 가격 비교 → 즉시 거래 완료
• 구매 성공 시 판매자에게 <b>텔레그램 DM 알림</b>이 자동 발송됩니다
• 📋 <b>나의 매물</b> — 내가 등록한 매물 관리 + 취소 기능
• 기존 봇 DM 거래소와 <b>동일한 시스템</b>을 공유하므로, 봇에서 등록한 매물도 홈페이지에서 보입니다

<b style="color:#f39c12;font-size:15px">■ ⚔️ 배틀 COST 18 제한 강화</b>
• 기존에는 COST가 초과되어도 팀 편성이 가능했으나, 이제 <span style="color:#f39c12;font-weight:700">18 COST를 초과하면 팀 저장 자체가 차단</span>됩니다
• 팀 드래프트 완료 시점과 팀 직접 등록 시점 모두에서 검증합니다
• 초과 시 <b>"❌ 팀 코스트 초과! (현재 XX / 제한 18)"</b> 경고가 표시됩니다
• 초전설(6) + 전설(5) + 에픽(4) + 레어(2) + 일반(1) = <b>18 ✅</b>
• 전략적인 팀 구성이 더욱 중요해졌습니다!

<b style="color:#3498db;font-size:15px">■ 📊 배틀/랭킹 유저 누락 수정</b>
• 배틀에서 <b>패배만 기록된 유저</b>가 랭킹에 표시되지 않던 버그가 수정되었습니다
• 이제 1판이라도 배틀을 진행한 모든 유저가 랭킹에 정상 표시됩니다
• 랭킹 표시 수가 <span style="color:#3498db;font-weight:700">최대 100명</span>으로 확대되었습니다 (기존 20명)

<b style="color:#2ecc71;font-size:15px">■ ✨ 이로치 표시 & 팀 분류 개선</b>
• 팀 편성(드래프트/등록) 시 이로치 포켓몬에 <span style="color:#2ecc71;font-weight:700">✨ 반짝이 표시</span>가 추가되었습니다
• 같은 포켓몬이라도 이로치는 별도로 구분되어 표시됩니다
• 내 포켓몬 목록에서 이로치가 <b>같은 종류끼리 묶여서</b> 정렬됩니다 (이름순 → 이로치 우선)
• 팀 바꿀 때 이로치 여부를 한눈에 확인할 수 있습니다

<b style="color:#9b59b6;font-size:15px">■ 📜 칭호 목록 페이지네이션</b>
• 칭호가 많아져 스크롤이 길어지는 문제를 해결했습니다
• <b>칭호목록</b> 명령 — 카테고리별 3개씩 페이지 단위로 표시, [◀ 이전] [다음 ▶] 버튼으로 넘기기
• <b>칭호</b> 명령 (장착) — 8개씩 페이지 단위로 표시, 페이지 네비게이션 지원
• 한 화면에 모든 칭호가 나오던 <span style="color:#9b59b6;font-weight:700">스크롤 압박이 크게 줄어듭니다</span>

<b style="color:#e67e22;font-size:15px">■ 📋 포켓몬 티어표 — 전 진화단계 표시</b>
• tgpoke.com 포켓몬 티어 페이지에서 기존에는 <b>최종 진화체</b>만 표시되었습니다
• 이제 <span style="color:#e67e22;font-weight:700">1진화(기본) · 2진화 · 3진화(최종)</span> 포켓몬이 모두 표시됩니다
• 상단 필터 버튼으로 진화 단계별 필터링이 가능합니다
• 일반·레어 포켓몬도 배틀에서 활용되는 만큼, 전체 스탯을 한눈에 비교해보세요!

행복한 포켓몬 라이프 되세요! 🎮"""


async def main():
    pool = await get_db()

    # 1) v2.1 공지 등록
    await pool.execute(
        "INSERT INTO board_posts (board_type, user_id, display_name, title, content) "
        "VALUES ($1, $2, $3, $4, $5)",
        "notice", 1832746512, "TG포켓", NOTICE_TITLE, NOTICE_CONTENT,
    )
    print(f"✅ Notice posted: {NOTICE_TITLE}")

    # 2) v2.0 글 고정 (기존 고정 해제 → v2.0 고정)
    # 기존 고정 글 모두 해제
    unpinned = await pool.execute(
        "UPDATE board_posts SET is_pinned = 0 WHERE is_pinned = 1 AND board_type = 'notice'"
    )
    print(f"📌 Unpinned existing: {unpinned}")

    # v2.0 글 찾기 & 고정
    v2_post = await pool.fetchrow(
        "SELECT id, title FROM board_posts WHERE title LIKE '%v2.0%' AND board_type = 'notice' AND is_active = 1 "
        "ORDER BY created_at DESC LIMIT 1"
    )
    if v2_post:
        await pool.execute(
            "UPDATE board_posts SET is_pinned = 1 WHERE id = $1", v2_post["id"]
        )
        print(f"📌 Pinned v2.0 post: id={v2_post['id']} title={v2_post['title']}")
    else:
        print("⚠️ v2.0 post not found!")


if __name__ == "__main__":
    asyncio.run(main())
