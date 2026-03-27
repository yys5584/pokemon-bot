"""Post guide tab + camp system notice — 대시보드 공지 + 텔레그램 DM."""
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from database.connection import get_db

# ── 대시보드 공지사항 (HTML) ──
NOTICE_TITLE = "📖 종합 가이드 & 🏕️ 캠프 시스템 오픈!"
NOTICE_CONTENT = """\
📢 <b>종합 가이드 & 캠프 시스템 업데이트</b>

안녕하세요, TG포켓입니다.
대시보드에 <b>종합 가이드</b>가 추가되었고, <b>캠프 시스템</b>이 오픈되었습니다!

<b style="color:#2ecc71;font-size:15px">■ 📖 종합 가이드 (17개 카테고리)</b>
• 시작하기, 포획, 등급, 육성, 합성, 배틀, 랭크전, 상성표
• 대회, 거래/교환, BP상점, 미션, 채팅방, 캠프, 칭호, 구독, 명령어
• 각 카테고리별 <b>별도 페이지</b>로 상세 안내
• 딥링크 지원: <a href="https://tgpoke.com/guide" style="color:#58a6ff">tgpoke.com/guide</a>

<b style="color:#f39c12;font-size:15px">■ 🏕️ 캠프 시스템 오픈</b>
• 채팅방 멤버들과 함께 캠프를 운영하세요!
• 🌲숲 / 🌊바다 / 🏔️산 / 🏙️도시 / 🌌신비 — <b>5개 지역</b>에 포켓몬 배치
• 지역에 맞는 타입 배치 시 <b>보너스 점수</b>
• 캠프 점수로 BP & 아이템 보상 획득!
• DM에서 <b>캠프</b> 입력, 그룹에서 <b>캠프맵</b>으로 월드맵 확인

<b style="color:#3498db;font-size:15px">■ 💡 가이드 활용 팁</b>
• 초보자라면 <a href="https://tgpoke.com/guide/start" style="color:#58a6ff">시작하기</a> 먼저!
• 배틀 실력 올리기: <a href="https://tgpoke.com/guide/typechart" style="color:#58a6ff">상성표</a> + <a href="https://tgpoke.com/guide/battle" style="color:#58a6ff">배틀 가이드</a>
• 명령어가 헷갈린다면: <a href="https://tgpoke.com/guide/commands" style="color:#58a6ff">명령어 총정리</a>

즐거운 포켓몬 라이프 되세요! 🎮"""

# ── 텔레그램 DM (플레인 텍스트) ──
DM_TEXT = """\
📖 종합 가이드 & 🏕️ 캠프 시스템 오픈!

🆕 대시보드에 종합 가이드가 추가되었어요!
17개 카테고리로 모든 시스템을 상세 안내합니다.

✅ 시작하기 / 포획 / 등급 / 육성 / 합성
✅ 배틀 / 랭크전 / 상성표 / 대회
✅ 거래·교환 / BP상점 / 미션 / 채팅방
✅ 캠프 / 칭호 / 구독 / 명령어 총정리

🏕️ 캠프 시스템도 오픈!
• 5개 지역(숲/바다/산/도시/신비)에 포켓몬 배치
• 타입 매칭 보너스로 점수 UP
• DM → 캠프 / 그룹 → 캠프맵

👉 가이드 바로가기: tgpoke.com/guide"""


async def main():
    pool = await get_db()

    # 1. 대시보드 공지 등록
    await pool.execute(
        "INSERT INTO board_posts (board_type, user_id, display_name, title, content) "
        "VALUES ($1, $2, $3, $4, $5)",
        "notice", 1832746512, "TG포켓", NOTICE_TITLE, NOTICE_CONTENT,
    )
    print(f"✅ 대시보드 공지 등록: {NOTICE_TITLE}")

    # 2. 텔레그램 DM 발송 (최근 6시간 활성 유저)
    rows = await pool.fetch(
        "SELECT user_id FROM users WHERE last_active_at >= NOW() - INTERVAL '6 hours'"
    )
    print(f"📨 {len(rows)}명에게 DM 발송 시작...")

    import aiohttp
    token = os.environ["BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    sent = 0
    fail = 0
    async with aiohttp.ClientSession() as session:
        for r in rows:
            uid = r["user_id"]
            try:
                async with session.post(url, data={"chat_id": str(uid), "text": DM_TEXT}) as resp:
                    if resp.status == 200:
                        sent += 1
                    else:
                        fail += 1
            except Exception:
                fail += 1
            await asyncio.sleep(0.05)
    print(f"✅ 완료. 성공={sent}, 실패={fail}")


if __name__ == "__main__":
    asyncio.run(main())
