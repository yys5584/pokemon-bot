"""v2.6 패치노트 압축 버전 — 원페이지."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

TITLE = "🆕 v2.6 업데이트 — 성격 시스템 + 퀴즈 이벤트"

CONTENT = '''같은 포켓몬이라도 개성이 달라야 재밌잖아요.
이제 포켓몬마다 고유한 성격이 부여됩니다. 같은 리자몽이라도 『무쌍』이 붙으면 화력이 다릅니다.
배틀, 던전, 랭전, 토너먼트 — 모든 전투에 성격 보너스가 적용됩니다.

🎭 <b>성격 시스템</b>

<b style="color:#fca5a5;">⚔️ 공격형</b> — 주력 공격스탯 부스트 (공격 or 특공 중 높은 쪽)
<span style="color:#888;">소심</span> → <span style="color:#93c5fd;">·난폭·</span> → <span style="color:#fde68a;">「사나움」</span> → <span style="color:#86efac;font-weight:800;">『무쌍』</span>
<span style="color:#aaa;">주력 공격:</span> <span style="color:#888;">+0%</span> / <span style="color:#93c5fd;font-weight:800;">+3%</span> / <span style="color:#fde68a;font-weight:800;">+5%</span> / <span style="color:#86efac;font-weight:800;">+8%</span>

<b style="color:#93c5fd;">🛡️ 방어형</b> — 방어 & 특방 & HP 부스트
<span style="color:#888;">유리몸</span> → <span style="color:#93c5fd;">·단단·</span> → <span style="color:#fde68a;">「억센」</span> → <span style="color:#86efac;font-weight:800;">『철벽』</span>
<span style="color:#aaa;">방어·특방:</span> <span style="color:#888;">+0%</span> / <span style="color:#93c5fd;font-weight:800;">+3%</span> / <span style="color:#fde68a;font-weight:800;">+5%</span> / <span style="color:#86efac;font-weight:800;">+8%</span>
<span style="color:#aaa;">HP:</span> <span style="color:#888;">+0%</span> / <span style="color:#93c5fd;font-weight:800;">+1.5%</span> / <span style="color:#fde68a;font-weight:800;">+2.5%</span> / <span style="color:#86efac;font-weight:800;">+4%</span>

<b style="color:#fde68a;">⚡ 스피드형</b> — 스피드 + 부공격 부스트
<span style="color:#888;">굼뜸</span> → <span style="color:#93c5fd;">·재빠름·</span> → <span style="color:#fde68a;">「질풍」</span> → <span style="color:#86efac;font-weight:800;">『신속』</span>
<span style="color:#aaa;">스피드:</span> <span style="color:#888;">+0%</span> / <span style="color:#93c5fd;font-weight:800;">+3.6%</span> / <span style="color:#fde68a;font-weight:800;">+6%</span> / <span style="color:#86efac;font-weight:800;">+9.6%</span>
<span style="color:#aaa;">주력 공격:</span> <span style="color:#888;">+0%</span> / <span style="color:#93c5fd;font-weight:800;">+1.2%</span> / <span style="color:#fde68a;font-weight:800;">+2%</span> / <span style="color:#86efac;font-weight:800;">+3.2%</span>

<b style="color:#86efac;">⚖️ 밸런스형</b> — 전 스탯 균등 부스트
<span style="color:#888;">변덕</span> → <span style="color:#93c5fd;">·냉철·</span> → <span style="color:#fde68a;">「명석」</span> → <span style="color:#86efac;font-weight:800;">『완벽』</span>
<span style="color:#aaa;">전 스탯:</span> <span style="color:#888;">+0%</span> / <span style="color:#93c5fd;font-weight:800;">각+0.9%</span> / <span style="color:#fde68a;font-weight:800;">각+1.5%</span> / <span style="color:#86efac;font-weight:800;">각+2.4%</span>

💡 <b>알아두면 좋은 것</b>
• 기존 포켓몬 전부 성격 자동 부여 완료
• <b>이로치</b>는 최소 2등급 이상 보장
• <b>합성</b> 시 부모 성격을 50% 확률로 유전
• 스폰 카드 · 내포켓몬 · 감정 · 팀 편집에서 확인 가능

🧠 <b>매일 퀴즈 이벤트</b>
매일 밤 20:30~21:00 포켓몬 퀴즈!
• <b>채널장 구독권</b> 유저 → DM에서 "채널등록"
• 등록된 방 중 매일 랜덤 1곳 선정
• 정답: <code>ㄷ 포켓몬이름</code>
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
