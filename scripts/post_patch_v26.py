"""v2.6 패치노트 압축 버전 — 원페이지."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

TITLE = "🆕 v2.6 업데이트 — 성격 시스템 + 퀴즈 이벤트"

CONTENT = '''🎭 <b>성격 시스템</b>
포켓몬마다 성격이 붙고, 성격이 좋을수록 배틀에서 강해집니다.

⚔️ <b>공격형</b> — 주력 공격 +8%
소심 → ·난폭· → 「사나움」 → 『무쌍』

🛡 <b>방어형</b> — HP+4% 방어+8% 특방+4%
유리몸 → ·단단· → 「억센」 → 『철벽』

⚡ <b>스피드형</b> — 스피드+10% 부공격+3%
굼뜸 → ·재빠름· → 「질풍」 → 『신속』

⚖ <b>밸런스형</b> — 전스탯 각+2.4%
변덕 → ·냉철· → 「명석」 → 『완벽』

• 기존 포켓몬 전부 자동 부여
• 이로치 2등급+ 보장
• 합성 시 부모 성격 50% 유전
• 배틀·던전·토너·랭전 전부 적용
• 카드·내포켓몬·감정에서 확인

🧠 <b>매일 퀴즈 이벤트</b>
매일 밤 20:30~21:00 포켓몬 퀴즈!
• 채널장 구독권 유저 → DM에서 "채널등록"
• 등록된 방 중 매일 랜덤 1곳 선정
• 정답: ㄷ 포켓몬이름
• 정답자에게 BP + 랜덤 상자 보상'''


async def main():
    from database.connection import get_db
    pool = await get_db()
    await pool.execute("DELETE FROM board_posts WHERE title LIKE '%v2.6%'")
    post_id = await pool.fetchval(
        "INSERT INTO board_posts (board_type, user_id, display_name, tag, title, content, is_pinned) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id",
        "notice", 1832746512, "TG포켓", "업데이트", TITLE, CONTENT, 1,
    )
    print(f"Posted: id={post_id}, {len(CONTENT)} chars")


if __name__ == "__main__":
    asyncio.run(main())
