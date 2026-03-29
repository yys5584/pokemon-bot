"""Post v2.8 patch notice — 던전 대규모 업데이트."""
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from database.connection import get_db


def _e(eid, fb="⭐"):
    """커스텀 이모지 헬퍼."""
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'


# 커스텀 이모지
E_BATTLE = _e("6143344370625026850", "⚔️")
E_CROWN = _e("6143265588039916937", "👑")
E_CRYSTAL = _e("6143120589944004477", "💎")
E_COIN = _e("6143083713354801765", "💰")
E_GOTCHA = _e("6143385318843227267", "🎯")
E_GAME = _e("6143111020756868297", "🎮")
E_POKECENTER = _e("6142954550803307680", "🏥")
E_MASTERBALL = _e("6143130859210807699", "🟣")
E_BOLT = _e("6143251942928818741", "⚡")
E_SKILL = _e("6143088085631507366", "💫")
E_CHECK = _e("6143254176311811828", "✅")


NOTICE_TITLE = "v2.8 패치노트 — 🏰 던전 대규모 업데이트"
NOTICE_CONTENT = f"""\
{E_BATTLE} <b>v2.8 던전 대규모 업데이트</b>

{E_SKILL} <b>턴제 수동 전투</b>
• 자동배틀 → <b>턴제 수동</b>으로 전환
• 매 턴 스킬/일반공격/방어 선택 · 적 의도 미리 표시
• 버튼 컬러 — 스킬(<b>빨강</b>) · 방어(<b>파랑</b>)

{E_COIN} <b>보상 시스템</b>
• 5층마다 BP · 조각 · 신규 아이템 지급
• 일일 TOP 5 — 개체선택리롤권 ×2
• 주간 1~3위 — IV스톤 · 전환권 · 리롤권 + 칭호
 ㄴ 매일/매주 DM 자동 지급

{E_GOTCHA} <b>신규 아이템 5종</b>
• ✨이로치전환권 · {E_GOTCHA}우선포획볼 · 🔮던전부적 · ⏰시간단축권 · 🥚알즉부화권

{E_GAME} <b>버프 리롤</b> — 보스 클리어 후 선택지 다시 굴리기
 ㄴ 무료 🔒 / 베이직 <b>1회</b> / 채널장 <b>3회</b>

{E_CROWN} <b>구독자 혜택 강화</b>
• BP — ×1 / <b>×1.2</b> / <b>×1.5</b>
• 아이템·조각 — ×1 / <b>×2</b> / <b>×3</b>
• 일일 런 — 3회 / 3회 / <b>5회</b>

{E_BOLT} <b>포켓몬 밸런스</b>
• 지라치·테오키스·마나피·다크라이·쉐이미 — 초전설→<b>전설</b> 강등
• 게을킹·레지기가스 — 던전 <b>게으름 특성</b> 적용 (짝수턴 강제 방어)
• 전설/초전설 PP <b>상향</b>
• 가이오가·그란돈 → <b>초전설</b> 정정
• BST 하한선 — 약한 최종진화 능력치 보정

{E_POKECENTER} <b>캡차 보안</b> — 매크로 탐지 시 <b>자동 24h 정지</b>

🦕 구독권이 별로라는 의견 많았는데, 이번에 확실히 차별화했습니다. 채널장이면 아이템 3배에 리롤 3회.. 체감 다를 거예요.

봇 DM → <b>「던전」</b>
— 문박사 드림 🧑‍🔬"""


# 봇 DM 브로드캐스트용 짧은 캡션 (이미지와 함께 전송)
DM_CAPTION = f"""\
{E_BATTLE} <b>v2.8 던전 대규모 업데이트!</b>

{E_SKILL} 턴제 수동 전투 · {E_COIN} 일일/주간 랭킹
{E_GOTCHA} 신규 아이템 5종 · {E_GAME} 버프 리롤
{E_CROWN} 구독자 보상 최대 3배

자세한 내용은 대시보드 공지사항에서 확인하세요!
봇 DM → <b>「던전」</b>"""


async def main():
    pool = await get_db()

    # 1) 대시보드 공지사항 등록
    await pool.execute(
        "INSERT INTO board_posts (board_type, user_id, display_name, tag, title, content) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        "notice", 1832746512, "TG포켓", "패치노트", NOTICE_TITLE, NOTICE_CONTENT,
    )
    print("OK: Notice posted to dashboard")

    # 2) 활성 유저에게 DM 브로드캐스트 (이미지 + 캡션)
    from telegram import Bot
    bot = Bot(os.environ["BOT_TOKEN"])

    rows = await pool.fetch(
        "SELECT user_id FROM users WHERE last_active >= NOW() - INTERVAL '7 days'"
    )
    print(f"Broadcasting to {len(rows)} users...")

    sent, failed = 0, 0
    img_path = os.path.join(os.path.dirname(__file__), "patch_v28_final.png")

    for row in rows:
        try:
            with open(img_path, "rb") as f:
                await bot.send_photo(
                    chat_id=row["user_id"],
                    photo=f,
                    caption=DM_CAPTION,
                    parse_mode="HTML",
                )
            sent += 1
            if sent % 20 == 0:
                await asyncio.sleep(1)  # rate limit
        except Exception as e:
            failed += 1

    print(f"Done: {sent} sent, {failed} failed")


if __name__ == "__main__":
    asyncio.run(main())
