"""패치노트 업데이트 스크립트."""
import asyncio, asyncpg, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

CONTENT = '''<b style="color:#3498db;font-size:15px">■ 던전 100층 확장</b>
기존 50층 한도를 <b>100층</b>으로 확장하였습니다.
50층 이후 보상이 대폭 강화되며, 90~100층은 최상위 난이도로 설계되었습니다.

<table style="border-collapse:collapse;width:100%;max-width:420px;margin:6px 0 12px;font-size:12px"><tr style="background:#3498db18"><th style="border:1px solid #3498db44;padding:5px 10px;text-align:center">층</th><th style="border:1px solid #3498db44;padding:5px 10px;text-align:center">BP</th><th style="border:1px solid #3498db44;padding:5px 10px;text-align:left">보상</th></tr><tr><td style="border:1px solid #3498db44;padding:5px 10px;text-align:center">10F</td><td style="border:1px solid #3498db44;padding:5px 10px;text-align:center">+20</td><td style="border:1px solid #3498db44;padding:5px 10px">조각 ×1</td></tr><tr><td style="border:1px solid #3498db44;padding:5px 10px;text-align:center">20F</td><td style="border:1px solid #3498db44;padding:5px 10px;text-align:center">+30</td><td style="border:1px solid #3498db44;padding:5px 10px">부적 ×1</td></tr><tr><td style="border:1px solid #3498db44;padding:5px 10px;text-align:center">30F</td><td style="border:1px solid #3498db44;padding:5px 10px;text-align:center">+50</td><td style="border:1px solid #3498db44;padding:5px 10px">결정 ×1</td></tr><tr><td style="border:1px solid #3498db44;padding:5px 10px;text-align:center">40F</td><td style="border:1px solid #3498db44;padding:5px 10px;text-align:center">+80</td><td style="border:1px solid #3498db44;padding:5px 10px">개체값 재설정</td></tr><tr><td style="border:1px solid #3498db44;padding:5px 10px;text-align:center">50F</td><td style="border:1px solid #3498db44;padding:5px 10px;text-align:center">+120</td><td style="border:1px solid #3498db44;padding:5px 10px">조각 ×3</td></tr><tr style="background:#e74c3c08"><td style="border:1px solid #3498db44;padding:5px 10px;text-align:center;color:#e74c3c;font-weight:700">60F</td><td style="border:1px solid #3498db44;padding:5px 10px;text-align:center">+200</td><td style="border:1px solid #3498db44;padding:5px 10px">결정 ×2</td></tr><tr style="background:#e74c3c08"><td style="border:1px solid #3498db44;padding:5px 10px;text-align:center;color:#e74c3c;font-weight:700">70F</td><td style="border:1px solid #3498db44;padding:5px 10px;text-align:center">+350</td><td style="border:1px solid #3498db44;padding:5px 10px">IV 선택 리롤</td></tr><tr style="background:#e74c3c08"><td style="border:1px solid #3498db44;padding:5px 10px;text-align:center;color:#e74c3c;font-weight:700">80F</td><td style="border:1px solid #3498db44;padding:5px 10px;text-align:center">+500</td><td style="border:1px solid #3498db44;padding:5px 10px">이로치 알</td></tr><tr style="background:#f1c40f18"><td style="border:1px solid #3498db44;padding:5px 10px;text-align:center;color:#f1c40f;font-weight:700">90F</td><td style="border:1px solid #3498db44;padding:5px 10px;text-align:center">+700</td><td style="border:1px solid #3498db44;padding:5px 10px">무지개 ×2 + IV스톤 ×1</td></tr><tr style="background:#f1c40f18"><td style="border:1px solid #3498db44;padding:5px 10px;text-align:center;color:#f1c40f;font-weight:700">100F</td><td style="border:1px solid #3498db44;padding:5px 10px;text-align:center">+1000</td><td style="border:1px solid #3498db44;padding:5px 10px">무지개 ×1 + IV스톤 ×2</td></tr></table>

* 기존 50층이 사실상 최종 벽으로 작용하여 도전 의욕이 떨어지는 문제가 있었습니다.
* 100층으로 확장하면서 난이도 커브를 재설계하였고, 90~100층은 최상위 유저를 위한 도전 구간으로 설정하였습니다.

<b style="color:#2ecc71;font-size:15px">■ 자동배틀 복귀</b>
턴제 수동배틀을 <b>자동배틀</b>로 되돌렸습니다.

텔레그램 특성상 버튼 클릭마다 서버 응답 딜레이가 발생하여, 턴제 배틀이 체감상 매우 느렸습니다.
특히 고층에서 턴 수가 늘어나면 한 판에 수 분이 소요되는 문제가 있었습니다.

변경 후 전투는 자동으로 처리되며, <b>버프 선택만 직접</b> 하는 방식으로 운영됩니다.

<b style="color:#e74c3c;font-size:15px">■ 뽑기 확률 조정</b>
상위 아이템 획득 확률을 <b>50% 하향</b>하였습니다.

최근 이로치 전환 조각, 전환 티켓, 우선포획볼, 무지개 결정 등 고급 아이템이 의도보다 과도하게 풀리면서 이로치 인플레이션이 심화되었습니다.
이로치 전설~초전설은 최종 컨텐츠로서 인당 보유 수를 제한적으로 유지하려는 설계 의도에 맞춰 조정하였습니다.

<b style="color:#95a5a6;font-size:13px">■ 버그 수정</b>
• 던전 버프 목록에 내부 데이터(? Lv.0)가 표시되던 문제 수정
• 던전 전 화면에 활성 시너지가 표시되지 않던 문제 수정
• 프리미엄 상점 마스터볼 구매 횟수가 1회로 제한되던 문제 수정
• 토너먼트 결과가 패치노트 게시판에 잘못 분류되던 문제 수정'''

async def main():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"), statement_cache_size=0)

    # 가장 최근 notice 패치노트 업데이트
    last_id = await conn.fetchval(
        "SELECT MAX(id) FROM board_posts WHERE board_type = 'notice'"
    )
    if last_id:
        await conn.execute(
            "UPDATE board_posts SET content = $1, title = $2 WHERE id = $3",
            CONTENT, "v2.9 던전 100층 확장 & 자동배틀 롤백", last_id,
        )
        print(f"패치노트 id={last_id} 업데이트 완료")
    else:
        print("notice 게시물 없음")

    await conn.close()

asyncio.run(main())
