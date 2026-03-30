"""성격 시스템 패치노트 — 텔레그램 DM + 대시보드 공지사항 등록."""

import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── 텔레그램 DM 공지 (짧고 압축적) ──

TELEGRAM_PATCH_NOTE = """
🆕 <b>성격 시스템 업데이트!</b>

포켓몬마다 <b>성격</b>이 붙습니다

🎴 스폰 카드에 성격 뱃지가 표시돼요
ㄴ 좋은 성격일수록 카드가 화려해집니다

⚔️ 성격이 좋으면 <b>배틀에서 더 강해요</b>
ㄴ 공격형, 방어형, 스피드형, 밸런스형 4종
ㄴ 등급 높을수록 보너스↑

📋 성격 등급 (16종)
<code>공격  소심 → 난폭 → 사나움 → 『무쌍』
방어  유리몸 → 단단 → 억센 → 『철벽』
속도  굼뜸 → 재빠름 → 질풍 → 『신속』
밸런스 변덕 → 냉철 → 명석 → 『완벽』</code>

💡 『 』가 붙은 포켓몬을 노려보세요!
ㄴ 이로치는 최소 2등급 이상 보장
ㄴ 합성 시 부모 성격을 50% 확률로 물려받아요
""".strip()


# ── 대시보드 공지사항 (HTML 디자인) ──

DASHBOARD_PATCH_NOTE_TITLE = "🆕 v2.6 업데이트 — 성격 시스템 + 퀴즈 이벤트"

DASHBOARD_PATCH_NOTE = """
<div style="font-family:'Noto Sans KR',sans-serif;line-height:1.8;color:#e0e0e0;font-size:14px;">

<div style="background:linear-gradient(135deg,#1a1c2e,#0f1923);border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:24px;margin-bottom:20px;">
  <h2 style="margin:0 0 6px;font-size:22px;color:#fff;">🎭 성격 시스템</h2>
  <p style="margin:0;color:#aaa;font-size:14px;">포켓몬마다 고유한 성격이 부여됩니다. 성격이 좋을수록 배틀에서 강해집니다.</p>
</div>

<div style="padding:0 4px;">

<b style="color:#fca5a5;">⚔️ 공격형</b> — 주력 공격스탯 부스트 (공격 or 특공 중 높은 쪽)<br>
<span style="margin-left:16px;"><span style="color:#888;">소심</span> → <span style="color:#93c5fd;">난폭</span> → <span style="color:#fde68a;">사나움</span> → <span style="color:#86efac;font-weight:800;">『무쌍』</span></span><br>
<span style="margin-left:16px;color:#aaa;">주력 공격: </span><span style="color:#888;">+0%</span> / <span style="color:#93c5fd;font-weight:800;">+3%</span> / <span style="color:#fde68a;font-weight:800;">+5%</span> / <span style="color:#86efac;font-weight:800;">+8%</span>
<br><br>

<b style="color:#93c5fd;">🛡️ 방어형</b> — 방어 & 특방 & HP 부스트<br>
<span style="margin-left:16px;"><span style="color:#888;">유리몸</span> → <span style="color:#93c5fd;">단단</span> → <span style="color:#fde68a;">억센</span> → <span style="color:#86efac;font-weight:800;">『철벽』</span></span><br>
<span style="margin-left:16px;color:#aaa;">방어·특방: </span><span style="color:#888;">+0%</span> / <span style="color:#93c5fd;font-weight:800;">+3%</span> / <span style="color:#fde68a;font-weight:800;">+5%</span> / <span style="color:#86efac;font-weight:800;">+8%</span><br>
<span style="margin-left:16px;color:#aaa;">HP: </span><span style="color:#888;">+0%</span> / <span style="color:#93c5fd;font-weight:800;">+1.5%</span> / <span style="color:#fde68a;font-weight:800;">+2.5%</span> / <span style="color:#86efac;font-weight:800;">+4%</span>
<br><br>

<b style="color:#fde68a;">⚡ 스피드형</b> — 스피드 + 부공격 부스트<br>
<span style="margin-left:16px;"><span style="color:#888;">굼뜸</span> → <span style="color:#93c5fd;">재빠름</span> → <span style="color:#fde68a;">질풍</span> → <span style="color:#86efac;font-weight:800;">『신속』</span></span><br>
<span style="margin-left:16px;color:#aaa;">스피드: </span><span style="color:#888;">+0%</span> / <span style="color:#93c5fd;font-weight:800;">+3.6%</span> / <span style="color:#fde68a;font-weight:800;">+6%</span> / <span style="color:#86efac;font-weight:800;">+9.6%</span><br>
<span style="margin-left:16px;color:#aaa;">주력 공격: </span><span style="color:#888;">+0%</span> / <span style="color:#93c5fd;font-weight:800;">+1.2%</span> / <span style="color:#fde68a;font-weight:800;">+2%</span> / <span style="color:#86efac;font-weight:800;">+3.2%</span>
<br><br>

<b style="color:#86efac;">⚖️ 밸런스형</b> — 전 스탯 균등 부스트<br>
<span style="margin-left:16px;"><span style="color:#888;">변덕</span> → <span style="color:#93c5fd;">냉철</span> → <span style="color:#fde68a;">명석</span> → <span style="color:#86efac;font-weight:800;">『완벽』</span></span><br>
<span style="margin-left:16px;color:#aaa;">전 스탯: </span><span style="color:#888;">+0%</span> / <span style="color:#93c5fd;font-weight:800;">각+0.9%</span> / <span style="color:#fde68a;font-weight:800;">각+1.5%</span> / <span style="color:#86efac;font-weight:800;">각+2.4%</span>

<br><br>
<div style="border-top:1px solid rgba(255,255,255,0.08);margin:8px 0 12px;"></div>

<b style="color:#fff;font-size:15px;">💡 기타</b><br><br>

• 기존 포켓몬 전부 성격 자동 부여 완료<br>
• <b>이로치</b>는 최소 2등급 이상 보장<br>
• <b>합성</b> 시 부모 성격을 50% 확률로 유전<br>
• 배틀 · 던전 · 토너먼트 · 랭크전 전부 적용<br>
• 스폰 카드 · 내포켓몬 · 감정 · 팀 편집에서 확인 가능

</div>

<div style="background:linear-gradient(135deg,rgba(34,197,94,0.1),rgba(15,18,28,0.9));border:1px solid rgba(34,197,94,0.3);border-radius:10px;padding:16px;text-align:center;margin-top:16px;margin-bottom:24px;">
  <div style="font-size:16px;font-weight:900;color:#86efac;">『 』가 붙은 포켓몬을 노려보세요!</div>
</div>

<div style="background:linear-gradient(135deg,#1a1c2e,#0f1923);border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:24px;margin-bottom:20px;">
  <h2 style="margin:0 0 6px;font-size:22px;color:#fff;">🧠 매일 퀴즈 이벤트</h2>
  <p style="margin:0;color:#aaa;font-size:14px;">매일 밤 포켓몬 퀴즈가 열립니다!</p>
</div>

<div style="padding:0 4px;">

• 매일 <b>20:30 ~ 21:00 (KST)</b> 자동 진행<br>
• <b>채널장 구독권</b> 보유자가 자신의 채팅방을 퀴즈방으로 등록 가능<br>
• 등록 방법: 봇 DM에서 <b>"채널등록"</b> 입력 → 초대링크 입력<br>
• 등록된 방 중 매일 <b>랜덤 1곳</b>에서 퀴즈 진행<br>
• 정답자에게 <b>BP + 랜덤 상자</b> 보상<br>
• 등수별 차등 보상 지급

</div>

</div>
""".strip()


async def main():
    """패치노트를 대시보드 공지사항에 등록."""
    from database.connection import get_db

    pool = await get_db()

    # 대시보드 공지사항 등록
    post_id = await pool.fetchval(
        "INSERT INTO board_posts (board_type, user_id, display_name, tag, title, content, is_pinned) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id",
        "notice", 1832746512, "TG포켓", "업데이트",
        DASHBOARD_PATCH_NOTE_TITLE, DASHBOARD_PATCH_NOTE, 1,
    )
    logger.info(f"Dashboard notice posted: id={post_id}")

    print("\n=== 텔레그램 DM 공지 (복사용) ===\n")
    print(TELEGRAM_PATCH_NOTE)
    print(f"\n=== 대시보드 공지 등록 완료: post_id={post_id} ===")


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(main())
