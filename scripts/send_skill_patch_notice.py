"""One-time script: post v2.4 skill effects + rarity balance patch notice."""
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from database.connection import get_db

ADMIN_USER_ID = 1832746512

NOTICE_TITLE = "v2.4 스킬 효과 시스템 + 밸런스 조정"
NOTICE_CONTENT = (
    '<b style="color:#ff6b6b;font-size:15px">■ 스킬 특수 효과 활성화</b>\n'
    '배틀 스킬에 <b>특수 효과</b>가 추가되었습니다!\n'
    '스킬 발동(30%) 시 효과가 함께 적용됩니다.\n\n'

    '<b style="color:#f39c12">💢 반동기</b> — 고위력 + 자기피해\n'
    '<table style="border-collapse:collapse;width:100%;max-width:380px;margin:6px 0 12px;font-size:12px">'
    '<tr style="background:#f39c1218">'
    '<th style="border:1px solid #f39c1244;padding:5px 10px;text-align:left">스킬</th>'
    '<th style="border:1px solid #f39c1244;padding:5px 10px;text-align:left">효과</th></tr>'
    '<tr><td style="border:1px solid #f39c1244;padding:5px 10px">역린</td>'
    '<td style="border:1px solid #f39c1244;padding:5px 10px"><b>x2.0</b> 데미지, 25% 자해</td></tr>'
    '<tr><td style="border:1px solid #f39c1244;padding:5px 10px">인파이트</td>'
    '<td style="border:1px solid #f39c1244;padding:5px 10px"><b>x2.0</b> 데미지, 25% 자해</td></tr>'
    '<tr><td style="border:1px solid #f39c1244;padding:5px 10px">브레이브버드</td>'
    '<td style="border:1px solid #f39c1244;padding:5px 10px"><b>x2.0</b> 데미지, 25% 자해</td></tr>'
    '<tr><td style="border:1px solid #f39c1244;padding:5px 10px">하이점프킥</td>'
    '<td style="border:1px solid #f39c1244;padding:5px 10px"><b>x2.0</b> 데미지, 25% 자해</td></tr>'
    '</table>\n'

    '<b style="color:#2ecc71">🌿 흡수기</b> — 데미지 + HP 회복\n'
    '<table style="border-collapse:collapse;width:100%;max-width:380px;margin:6px 0 12px;font-size:12px">'
    '<tr style="background:#2ecc7118">'
    '<th style="border:1px solid #2ecc7144;padding:5px 10px;text-align:left">스킬</th>'
    '<th style="border:1px solid #2ecc7144;padding:5px 10px;text-align:left">효과</th></tr>'
    '<tr><td style="border:1px solid #2ecc7144;padding:5px 10px">흡수</td>'
    '<td style="border:1px solid #2ecc7144;padding:5px 10px">데미지의 <b>25%</b> 회복</td></tr>'
    '<tr><td style="border:1px solid #2ecc7144;padding:5px 10px">메가드레인</td>'
    '<td style="border:1px solid #2ecc7144;padding:5px 10px">데미지의 <b>35%</b> 회복</td></tr>'
    '<tr><td style="border:1px solid #2ecc7144;padding:5px 10px">기가드레인</td>'
    '<td style="border:1px solid #2ecc7144;padding:5px 10px">데미지의 <b>50%</b> 회복</td></tr>'
    '</table>\n'

    '<b style="color:#f1c40f">⚡ 선제기</b> — 발동 시 선공\n'
    '<table style="border-collapse:collapse;width:100%;max-width:380px;margin:6px 0 12px;font-size:12px">'
    '<tr style="background:#f1c40f18">'
    '<th style="border:1px solid #f1c40f44;padding:5px 10px;text-align:left">스킬</th>'
    '<th style="border:1px solid #f1c40f44;padding:5px 10px;text-align:left">효과</th></tr>'
    '<tr><td style="border:1px solid #f1c40f44;padding:5px 10px">신속</td>'
    '<td style="border:1px solid #f1c40f44;padding:5px 10px">30% 확률 선공</td></tr>'
    '<tr><td style="border:1px solid #f1c40f44;padding:5px 10px">전광석화</td>'
    '<td style="border:1px solid #f1c40f44;padding:5px 10px">30% 확률 선공</td></tr>'
    '<tr><td style="border:1px solid #f1c40f44;padding:5px 10px">불릿펀치</td>'
    '<td style="border:1px solid #f1c40f44;padding:5px 10px">30% 확률 선공</td></tr>'
    '<tr><td style="border:1px solid #f1c40f44;padding:5px 10px">마하펀치</td>'
    '<td style="border:1px solid #f1c40f44;padding:5px 10px">30% 확률 선공</td></tr>'
    '</table>\n'

    '<b style="color:#3498db">기타 효과</b>\n'
    '<table style="border-collapse:collapse;width:100%;max-width:380px;margin:6px 0 12px;font-size:12px">'
    '<tr style="background:#3498db18">'
    '<th style="border:1px solid #3498db44;padding:5px 10px;text-align:left">스킬</th>'
    '<th style="border:1px solid #3498db44;padding:5px 10px;text-align:left">효과</th></tr>'
    '<tr><td style="border:1px solid #3498db44;padding:5px 10px">💤 잠자기</td>'
    '<td style="border:1px solid #3498db44;padding:5px 10px">공격 대신 <b>최대HP 35%</b> 회복</td></tr>'
    '<tr><td style="border:1px solid #3498db44;padding:5px 10px">🔄 반격</td>'
    '<td style="border:1px solid #3498db44;padding:5px 10px">받은 데미지 <b>x1.5</b> 반사</td></tr>'
    '<tr><td style="border:1px solid #3498db44;padding:5px 10px">🎲 손가락흔들기</td>'
    '<td style="border:1px solid #3498db44;padding:5px 10px"><b>x0.5~2.5</b> 랜덤 데미지</td></tr>'
    '<tr><td style="border:1px solid #3498db44;padding:5px 10px">💦 튀어오르기</td>'
    '<td style="border:1px solid #3498db44;padding:5px 10px">데미지 0 (잉어킹 전용)</td></tr>'
    '<tr><td style="border:1px solid #3498db44;padding:5px 10px">💥 자폭/대폭발</td>'
    '<td style="border:1px solid #3498db44;padding:5px 10px">기존과 동일</td></tr>'
    '</table>\n'

    '─────────────────────────\n\n'

    '<b style="color:#9b59b6;font-size:15px">■ 등급 밸런스 조정</b>\n'
    '일부 포켓몬의 등급이 조정되었습니다.\n\n'

    '<table style="border-collapse:collapse;width:100%;max-width:420px;margin:6px 0 12px;font-size:12px">'
    '<tr style="background:#e74c3c18">'
    '<th style="border:1px solid #e74c3c44;padding:5px 10px;text-align:left">변경</th>'
    '<th style="border:1px solid #e74c3c44;padding:5px 10px;text-align:left">포켓몬</th></tr>'
    '<tr><td style="border:1px solid #e74c3c44;padding:5px 10px;color:#e74c3c;font-weight:700">에픽 → 레어</td>'
    '<td style="border:1px solid #e74c3c44;padding:5px 10px">나인테일 / 골덕 / 날쌩마 / 점토도리</td></tr>'
    '<tr><td style="border:1px solid #e74c3c44;padding:5px 10px;color:#3498db;font-weight:700">레어 → 일반</td>'
    '<td style="border:1px solid #e74c3c44;padding:5px 10px">토게틱 / 코산호 / 마이농</td></tr>'
    '</table>\n'

    '<span style="color:#95a5a6;font-size:11px">'
    '※ 하향된 포켓몬은 배틀 보정치(일반 x1.15, 레어 x1.05)가 적용되어\n'
    '실제 배틀 성능 차이는 크지 않습니다.</span>\n\n'

    '─────────────────────────\n\n'

    '<b style="color:#e67e22;font-size:15px">■ 인기 포켓몬 영향 분석</b>\n'
    '배틀 상위권 포켓몬 중 변화가 있는 포켓몬입니다.\n\n'

    '<table style="border-collapse:collapse;width:100%;max-width:480px;margin:6px 0 12px;font-size:12px">'
    '<tr style="background:#e67e2218">'
    '<th style="border:1px solid #e67e2244;padding:5px 10px;text-align:left">포켓몬</th>'
    '<th style="border:1px solid #e67e2244;padding:5px 10px;text-align:left">변화</th>'
    '<th style="border:1px solid #e67e2244;padding:5px 10px;text-align:left">영향</th></tr>'
    '<tr><td style="border:1px solid #e67e2244;padding:5px 10px">🐉 망나뇽 <span style="color:#f39c12">(75.1%)</span></td>'
    '<td style="border:1px solid #e67e2244;padding:5px 10px">역린: x2.0 + 25% 자해</td>'
    '<td style="border:1px solid #e67e2244;padding:5px 10px;color:#95a5a6">±0.0% (동일)</td></tr>'
    '<tr><td style="border:1px solid #e67e2244;padding:5px 10px">🪲 헤라크로스 <span style="color:#f39c12">(81.8%)</span></td>'
    '<td style="border:1px solid #e67e2244;padding:5px 10px">인파이트: x2.0 + 25% 자해</td>'
    '<td style="border:1px solid #e67e2244;padding:5px 10px;color:#e74c3c">-3.0% (너프)</td></tr>'
    '<tr><td style="border:1px solid #e67e2244;padding:5px 10px">😴 잠만보 <span style="color:#f39c12">(52.6%)</span></td>'
    '<td style="border:1px solid #e67e2244;padding:5px 10px">잠자기: 최대HP 35% 회복</td>'
    '<td style="border:1px solid #e67e2244;padding:5px 10px;color:#2ecc71">생존력 ↑ (버프)</td></tr>'
    '<tr><td style="border:1px solid #e67e2244;padding:5px 10px">🦇 핫삼</td>'
    '<td style="border:1px solid #e67e2244;padding:5px 10px">불릿펀치: 30% 선공 추가</td>'
    '<td style="border:1px solid #e67e2244;padding:5px 10px;color:#2ecc71">선제 효과 추가</td></tr>'
    '<tr><td style="border:1px solid #e67e2244;padding:5px 10px">🔥 윈디</td>'
    '<td style="border:1px solid #e67e2244;padding:5px 10px">신속: 30% 선공 추가</td>'
    '<td style="border:1px solid #e67e2244;padding:5px 10px;color:#2ecc71">선제 효과 추가</td></tr>'
    '</table>\n'

    '<span style="color:#95a5a6;font-size:11px">'
    '※ 마기라스, 뮤츠, 라이코, 가이오가 등 대부분의\n'
    '고티어 포켓몬은 영향 없습니다.</span>\n\n'

    '─────────────────────────\n\n'

    '<b style="color:#1abc9c;font-size:15px">■ 대시보드 업데이트</b>\n'
    '• 티어표 스킬 컬럼에 <b>효과 태그</b> 표시\n'
    '• 스킬 호버 시 <b>상세 툴팁</b> 확인 가능\n'
    '• 모바일 반응형 개선 (스탯 그래프 자동 숨김)\n\n'

    '즐거운 배틀 되세요! ⚔️🎮'
)


async def main():
    pool = await get_db()

    # Update existing notice (id=17)
    result = await pool.execute(
        "UPDATE board_posts SET content=$1 WHERE id=17",
        NOTICE_CONTENT,
    )
    print("✅ 공지사항 수정 완료:", result)


if __name__ == "__main__":
    asyncio.run(main())
