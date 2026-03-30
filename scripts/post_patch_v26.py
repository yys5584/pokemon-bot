"""v2.6 패치노트 압축 버전 — 원페이지."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

TITLE = "🆕 v2.6 업데이트 — 성격 시스템 + 퀴즈 이벤트"

CONTENT = '''<div style="font-family:'Noto Sans KR',sans-serif;color:#e5e7eb;font-size:14px;line-height:1.7;">

<div style="background:linear-gradient(135deg,#101826,#172033);border:1px solid rgba(255,255,255,0.08);border-radius:16px;padding:22px;margin-bottom:14px;">
  <span style="display:inline-block;padding:4px 10px;border-radius:999px;font-size:11px;font-weight:800;color:#86efac;background:rgba(134,239,172,0.12);border:1px solid rgba(134,239,172,0.18);">NEW</span>
  <h1 style="margin:8px 0 4px;font-size:24px;color:#fff;">성격 시스템 + 퀴즈 이벤트</h1>
  <p style="margin:0;color:#94a3b8;font-size:13px;">포켓몬마다 성격이 붙고, 성격이 좋을수록 배틀에서 강해집니다.</p>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px;">
  <div style="background:rgba(20,29,46,0.96);border:1px solid rgba(252,165,165,0.2);border-radius:14px;padding:14px;">
    <b style="color:#fca5a5;font-size:15px;">⚔️ 공격형</b><br>
    <span style="color:#94a3b8;font-size:12px;">주력 공격 +8%</span><br>
    <span style="font-size:12px;color:#64748b;">소심 → ·<span style="color:#93c5fd;">난폭</span>· → 「<span style="color:#fde68a;">사나움</span>」 → <span style="color:#86efac;font-weight:800;">『무쌍』</span></span>
  </div>
  <div style="background:rgba(20,29,46,0.96);border:1px solid rgba(147,197,253,0.2);border-radius:14px;padding:14px;">
    <b style="color:#93c5fd;font-size:15px;">🛡️ 방어형</b><br>
    <span style="color:#94a3b8;font-size:12px;">HP+4% 방어+8% 특방+4%</span><br>
    <span style="font-size:12px;color:#64748b;">유리몸 → ·<span style="color:#93c5fd;">단단</span>· → 「<span style="color:#fde68a;">억센</span>」 → <span style="color:#86efac;font-weight:800;">『철벽』</span></span>
  </div>
  <div style="background:rgba(20,29,46,0.96);border:1px solid rgba(253,230,138,0.2);border-radius:14px;padding:14px;">
    <b style="color:#fde68a;font-size:15px;">⚡ 스피드형</b><br>
    <span style="color:#94a3b8;font-size:12px;">스피드+10% 부공격+3%</span><br>
    <span style="font-size:12px;color:#64748b;">굼뜸 → ·<span style="color:#93c5fd;">재빠름</span>· → 「<span style="color:#fde68a;">질풍</span>」 → <span style="color:#86efac;font-weight:800;">『신속』</span></span>
  </div>
  <div style="background:rgba(20,29,46,0.96);border:1px solid rgba(134,239,172,0.2);border-radius:14px;padding:14px;">
    <b style="color:#86efac;font-size:15px;">⚖️ 밸런스형</b><br>
    <span style="color:#94a3b8;font-size:12px;">전스탯 각+2.4%</span><br>
    <span style="font-size:12px;color:#64748b;">변덕 → ·<span style="color:#93c5fd;">냉철</span>· → 「<span style="color:#fde68a;">명석</span>」 → <span style="color:#86efac;font-weight:800;">『완벽』</span></span>
  </div>
</div>

<div style="background:rgba(16,24,39,0.96);border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:14px;margin-bottom:14px;font-size:13px;color:#d1d5db;">
  • 기존 포켓몬 전부 자동 부여 &nbsp;• 이로치 2등급+ 보장 &nbsp;• 합성 시 50% 유전<br>
  • 배틀·던전·토너·랭전 전부 적용 &nbsp;• 카드·내포켓몬·감정에서 확인
</div>

<div style="background:linear-gradient(135deg,#101826,#172033);border:1px solid rgba(253,230,138,0.15);border-radius:16px;padding:22px;">
  <span style="display:inline-block;padding:4px 10px;border-radius:999px;font-size:11px;font-weight:800;color:#fde68a;background:rgba(253,230,138,0.12);border:1px solid rgba(253,230,138,0.18);">EVENT</span>
  <b style="display:block;margin-top:8px;font-size:18px;color:#fff;">🧠 매일 퀴즈 이벤트</b>
  <div style="margin-top:8px;font-size:13px;color:#d1d5db;line-height:1.7;">
    • 매일 <b style="color:#fff;">20:30~21:00</b> 자동 진행<br>
    • <b style="color:#fde68a;">채널장 구독권</b> 유저 → DM에서 "채널등록"<br>
    • 등록된 방 중 매일 랜덤 1곳 선정<br>
    • 정답: <code>ㄷ 포켓몬이름</code> → BP + 랜덤 상자 보상
  </div>
</div>

</div>'''


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
