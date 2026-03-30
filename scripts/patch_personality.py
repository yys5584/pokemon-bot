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

DASHBOARD_PATCH_NOTE_TITLE = "🆕 성격 시스템 업데이트"

DASHBOARD_PATCH_NOTE = """
<div style="font-family:'Noto Sans KR',sans-serif;line-height:1.7;color:#e0e0e0;">

<div style="background:linear-gradient(135deg,#1a1c2e,#0f1923);border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:24px;margin-bottom:20px;">
  <h2 style="margin:0 0 8px;font-size:22px;color:#fff;">🎭 성격 시스템</h2>
  <p style="margin:0;color:#aaa;font-size:14px;">포켓몬마다 고유한 성격이 부여됩니다. 성격에 따라 배틀 능력이 달라집니다.</p>
</div>

<div style="background:rgba(15,18,28,0.8);border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:20px;margin-bottom:16px;">
  <h3 style="margin:0 0 14px;font-size:16px;color:#93c5fd;">📋 성격 종류 (4유형 × 4등급 = 16종)</h3>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
    <div style="background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.2);border-radius:8px;padding:14px;">
      <div style="font-weight:800;color:#fca5a5;margin-bottom:8px;">⚔️ 공격형</div>
      <div style="font-size:13px;color:#aaa;">공격·특공 보너스</div>
      <div style="margin-top:8px;font-size:13px;">
        <span style="color:rgba(160,160,160,0.5);">소심</span> →
        <span style="color:#93c5fd;">난폭</span> →
        <span style="color:#fde68a;">사나움</span> →
        <span style="color:#86efac;font-weight:900;">『무쌍』</span>
      </div>
    </div>
    <div style="background:rgba(59,130,246,0.08);border:1px solid rgba(59,130,246,0.2);border-radius:8px;padding:14px;">
      <div style="font-weight:800;color:#93c5fd;margin-bottom:8px;">🛡️ 방어형</div>
      <div style="font-size:13px;color:#aaa;">방어·특방·HP 보너스</div>
      <div style="margin-top:8px;font-size:13px;">
        <span style="color:rgba(160,160,160,0.5);">유리몸</span> →
        <span style="color:#93c5fd;">단단</span> →
        <span style="color:#fde68a;">억센</span> →
        <span style="color:#86efac;font-weight:900;">『철벽』</span>
      </div>
    </div>
    <div style="background:rgba(234,179,8,0.08);border:1px solid rgba(234,179,8,0.2);border-radius:8px;padding:14px;">
      <div style="font-weight:800;color:#fde68a;margin-bottom:8px;">⚡ 스피드형</div>
      <div style="font-size:13px;color:#aaa;">스피드 집중 보너스</div>
      <div style="margin-top:8px;font-size:13px;">
        <span style="color:rgba(160,160,160,0.5);">굼뜸</span> →
        <span style="color:#93c5fd;">재빠름</span> →
        <span style="color:#fde68a;">질풍</span> →
        <span style="color:#86efac;font-weight:900;">『신속』</span>
      </div>
    </div>
    <div style="background:rgba(34,197,94,0.08);border:1px solid rgba(34,197,94,0.2);border-radius:8px;padding:14px;">
      <div style="font-weight:800;color:#86efac;margin-bottom:8px;">⚖️ 밸런스형</div>
      <div style="font-size:13px;color:#aaa;">전 스탯 균등 보너스</div>
      <div style="margin-top:8px;font-size:13px;">
        <span style="color:rgba(160,160,160,0.5);">변덕</span> →
        <span style="color:#93c5fd;">냉철</span> →
        <span style="color:#fde68a;">명석</span> →
        <span style="color:#86efac;font-weight:900;">『완벽』</span>
      </div>
    </div>
  </div>
</div>

<div style="background:rgba(15,18,28,0.8);border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:20px;margin-bottom:16px;">
  <h3 style="margin:0 0 14px;font-size:16px;color:#fde68a;">📊 등급별 보너스</h3>
  <table style="width:100%;border-collapse:collapse;font-size:14px;">
    <tr style="border-bottom:1px solid rgba(255,255,255,0.08);">
      <th style="text-align:left;padding:8px;color:#888;">등급</th>
      <th style="text-align:center;padding:8px;color:#888;">확률</th>
      <th style="text-align:center;padding:8px;color:#888;">유형 보너스</th>
      <th style="text-align:left;padding:8px;color:#888;">표시</th>
    </tr>
    <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
      <td style="padding:8px;color:rgba(160,160,160,0.6);">1등급</td>
      <td style="text-align:center;padding:8px;color:#888;">45%</td>
      <td style="text-align:center;padding:8px;color:#888;">없음</td>
      <td style="padding:8px;color:rgba(160,160,160,0.5);">소심</td>
    </tr>
    <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
      <td style="padding:8px;color:#93c5fd;">2등급</td>
      <td style="text-align:center;padding:8px;color:#888;">30%</td>
      <td style="text-align:center;padding:8px;color:#93c5fd;">+3%</td>
      <td style="padding:8px;color:#93c5fd;">▫난폭</td>
    </tr>
    <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
      <td style="padding:8px;color:#fde68a;">3등급</td>
      <td style="text-align:center;padding:8px;color:#888;">15%</td>
      <td style="text-align:center;padding:8px;color:#fde68a;">+5%</td>
      <td style="padding:8px;color:#fde68a;">▫사나움▫</td>
    </tr>
    <tr>
      <td style="padding:8px;color:#86efac;font-weight:800;">4등급</td>
      <td style="text-align:center;padding:8px;color:#888;">10%</td>
      <td style="text-align:center;padding:8px;color:#86efac;font-weight:800;">+8%</td>
      <td style="padding:8px;color:#86efac;font-weight:800;">『무쌍』</td>
    </tr>
  </table>
</div>

<div style="background:rgba(15,18,28,0.8);border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:20px;margin-bottom:16px;">
  <h3 style="margin:0 0 14px;font-size:16px;color:#86efac;">💡 알아두면 좋은 것</h3>
  <ul style="margin:0;padding-left:20px;font-size:14px;color:#ccc;">
    <li style="margin-bottom:6px;">모든 포켓몬에 성격이 자동 부여됩니다 (기존 포켓몬 포함)</li>
    <li style="margin-bottom:6px;"><b>이로치</b>는 최소 2등급 이상 보장!</li>
    <li style="margin-bottom:6px;">성격은 <b>배틀·던전·토너먼트·랭크전</b> 모두 적용</li>
    <li style="margin-bottom:6px;">같은 IV라도 성격에 따라 배틀 스탯이 달라집니다</li>
    <li style="margin-bottom:6px;">스폰 카드에서 성격 등급을 한눈에 확인할 수 있어요</li>
    <li><b>합성</b> 시 부모 성격을 50% 확률로 물려받습니다</li>
    <li>내포켓몬, 감정, 팀 편집 등 모든 곳에서 성격 확인 가능</li>
  </ul>
</div>

<div style="background:linear-gradient(135deg,rgba(34,197,94,0.1),rgba(15,18,28,0.9));border:1px solid rgba(34,197,94,0.3);border-radius:10px;padding:16px;text-align:center;">
  <div style="font-size:18px;font-weight:900;color:#86efac;margin-bottom:4px;">『 』가 붙은 포켓몬을 노려보세요!</div>
  <div style="font-size:13px;color:#888;">공격형 포켓몬에 『무쌍』이 붙으면 최고의 조합입니다</div>
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
