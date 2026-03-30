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

DASHBOARD_PATCH_NOTE_OLD = """_unused"""

DASHBOARD_PATCH_NOTE = """
<div style="font-family:'Noto Sans KR',sans-serif;color:#e5e7eb;">

<div style="background:linear-gradient(135deg,#101826,#172033 58%,#0d1117);border:1px solid rgba(255,255,255,0.08);border-radius:22px;padding:28px;box-shadow:0 18px 60px rgba(0,0,0,0.35);">
  <span style="display:inline-block;padding:6px 11px;border-radius:999px;font-size:12px;font-weight:800;color:#86efac;background:rgba(134,239,172,0.12);border:1px solid rgba(134,239,172,0.18);">신규 시스템</span>
  <h1 style="margin:12px 0 8px;font-size:30px;line-height:1.2;color:#fff;">성격 시스템 업데이트</h1>
  <p style="margin:0;color:#94a3b8;font-size:15px;line-height:1.65;">이제 포켓몬마다 고유한 성격이 부여됩니다.<br>성격이 좋을수록 전투 스타일이 더 선명해지고, 같은 포켓몬도 다른 전투 감각을 갖게 됩니다.</p>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:16px;">

  <div style="background:linear-gradient(180deg,rgba(20,29,46,0.96),rgba(16,24,39,0.98));border:1px solid rgba(252,165,165,0.22);border-radius:18px;padding:18px;">
    <div style="font-size:19px;font-weight:900;color:#fca5a5;">공격형</div>
    <div style="margin-top:5px;color:#cbd5e1;font-size:14px;">주력 공격 스탯에 몰아주는 딜 특화 성격</div>
    <div style="margin-top:12px;padding:10px 12px;border-radius:12px;color:#fff;font-size:14px;font-weight:800;background:rgba(252,165,165,0.10);">주력 공격 +8%</div>
    <div style="margin-top:12px;font-size:13px;color:#94a3b8;">
      소심 &nbsp; ▫<span style="color:#93c5fd;">난폭</span> &nbsp; ▫<span style="color:#fde68a;">사나움</span>▫ &nbsp; <span style="color:#86efac;font-weight:800;">『무쌍』</span>
    </div>
    <div style="margin-top:8px;font-size:13px;color:#64748b;">공격 / 특공 중 더 높은 한 스탯만 강화됩니다.</div>
  </div>

  <div style="background:linear-gradient(180deg,rgba(20,29,46,0.96),rgba(16,24,39,0.98));border:1px solid rgba(147,197,253,0.22);border-radius:18px;padding:18px;">
    <div style="font-size:19px;font-weight:900;color:#93c5fd;">방어형</div>
    <div style="margin-top:5px;color:#cbd5e1;font-size:14px;">장기전과 안정적인 클리어에 강한 성격</div>
    <div style="margin-top:12px;padding:10px 12px;border-radius:12px;color:#fff;font-size:14px;font-weight:800;background:rgba(147,197,253,0.10);">HP +4% · 방어 +8% · 특방 +4%</div>
    <div style="margin-top:12px;font-size:13px;color:#94a3b8;">
      유리몸 &nbsp; ▫<span style="color:#93c5fd;">단단</span> &nbsp; ▫<span style="color:#fde68a;">억센</span>▫ &nbsp; <span style="color:#86efac;font-weight:800;">『철벽』</span>
    </div>
    <div style="margin-top:8px;font-size:13px;color:#64748b;">던전, 보스전, 유지력이 중요한 전투에서 강합니다.</div>
  </div>

  <div style="background:linear-gradient(180deg,rgba(20,29,46,0.96),rgba(16,24,39,0.98));border:1px solid rgba(253,230,138,0.22);border-radius:18px;padding:18px;">
    <div style="font-size:19px;font-weight:900;color:#fde68a;">스피드형</div>
    <div style="margin-top:5px;color:#cbd5e1;font-size:14px;">선공과 템포를 잡는 속도 특화 성격</div>
    <div style="margin-top:12px;padding:10px 12px;border-radius:12px;color:#fff;font-size:14px;font-weight:800;background:rgba(253,230,138,0.10);">스피드 +9.6% · 부공격 +3.2%</div>
    <div style="margin-top:12px;font-size:13px;color:#94a3b8;">
      굼뜸 &nbsp; ▫<span style="color:#93c5fd;">재빠름</span> &nbsp; ▫<span style="color:#fde68a;">질풍</span>▫ &nbsp; <span style="color:#86efac;font-weight:800;">『신속』</span>
    </div>
    <div style="margin-top:8px;font-size:13px;color:#64748b;">먼저 때리는 가치가 큰 콘텐츠일수록 체감이 커집니다.</div>
  </div>

  <div style="background:linear-gradient(180deg,rgba(20,29,46,0.96),rgba(16,24,39,0.98));border:1px solid rgba(134,239,172,0.22);border-radius:18px;padding:18px;">
    <div style="font-size:19px;font-weight:900;color:#86efac;">밸런스형</div>
    <div style="margin-top:5px;color:#cbd5e1;font-size:14px;">모든 스탯을 고르게 끌어올리는 만능형</div>
    <div style="margin-top:12px;padding:10px 12px;border-radius:12px;color:#fff;font-size:14px;font-weight:800;background:rgba(134,239,172,0.10);">전스탯 각 +2.4%</div>
    <div style="margin-top:12px;font-size:13px;color:#94a3b8;">
      변덕 &nbsp; ▫<span style="color:#93c5fd;">냉철</span> &nbsp; ▫<span style="color:#fde68a;">명석</span>▫ &nbsp; <span style="color:#86efac;font-weight:800;">『완벽』</span>
    </div>
    <div style="margin-top:8px;font-size:13px;color:#64748b;">어느 콘텐츠에서든 무난하게 좋은 안정형 성격입니다.</div>
  </div>

</div>

<div style="margin-top:16px;background:rgba(16,24,39,0.96);border:1px solid rgba(255,255,255,0.08);border-radius:18px;padding:18px;">
  <h2 style="margin:0 0 12px;font-size:18px;color:#fff;">핵심 변경점</h2>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px 16px;color:#d1d5db;font-size:14px;">
    <div style="padding:12px 13px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.04);border-radius:14px;">기존 포켓몬도 성격이 자동으로 부여됩니다.</div>
    <div style="padding:12px 13px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.04);border-radius:14px;">이로치는 최소 2등급 이상 성격이 보장됩니다.</div>
    <div style="padding:12px 13px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.04);border-radius:14px;">합성 시 부모 성격이 50% 확률로 유전됩니다.</div>
    <div style="padding:12px 13px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.04);border-radius:14px;">배틀, 랭전, 던전, 토너먼트에 모두 적용됩니다.</div>
  </div>
</div>

<div style="margin-top:16px;text-align:center;border-radius:18px;padding:18px;background:linear-gradient(135deg,rgba(134,239,172,0.12),rgba(59,130,246,0.10));border:1px solid rgba(134,239,172,0.24);">
  <strong style="display:block;font-size:18px;color:#fff;">더 강해진 파트너를 확인해보세요</strong>
  <span style="display:block;margin-top:6px;color:#a7f3d0;font-size:14px;">같은 포켓몬이라도 성격에 따라 전투 감각이 달라집니다.</span>
</div>

<div style="margin-top:24px;background:linear-gradient(135deg,#101826,#172033 58%,#0d1117);border:1px solid rgba(255,255,255,0.08);border-radius:22px;padding:28px;">
  <span style="display:inline-block;padding:6px 11px;border-radius:999px;font-size:12px;font-weight:800;color:#fde68a;background:rgba(253,230,138,0.12);border:1px solid rgba(253,230,138,0.18);">신규 이벤트</span>
  <h1 style="margin:12px 0 8px;font-size:26px;color:#fff;">🧠 매일 퀴즈 이벤트</h1>
  <p style="margin:0;color:#94a3b8;font-size:15px;line-height:1.65;">매일 밤 포켓몬 퀴즈가 열립니다!</p>
</div>

<div style="margin-top:16px;background:rgba(16,24,39,0.96);border:1px solid rgba(255,255,255,0.08);border-radius:18px;padding:18px;font-size:14px;color:#d1d5db;line-height:1.8;">
  • 매일 <b style="color:#fff;">20:30 ~ 21:00 (KST)</b> 자동 진행<br>
  • <b style="color:#fde68a;">채널장 구독권</b> 보유자가 자신의 채팅방을 퀴즈방으로 등록 가능<br>
  • 등록 방법: 봇 DM에서 <b style="color:#fff;">"채널등록"</b> 입력 → 초대링크 입력<br>
  • 등록된 방 중 매일 <b style="color:#fff;">랜덤 1곳</b>에서 퀴즈 진행<br>
  • 정답자에게 <b style="color:#86efac;">BP + 랜덤 상자</b> 보상<br>
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
