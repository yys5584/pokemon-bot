"""시즌 보상 공지 테스트 발송 (관리자 DM)."""
import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import httpx

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 1832746512

TEXT = (
    '<tg-emoji emoji-id="6143344370625026850">⚔️</tg-emoji> <b>시즌 1 &amp; 1.5 보상 지급!</b>\n'
    '\n'
    '지난 두 시즌 보상이 지급되었습니다.\n'
    '상위권 트레이너분들 축하합니다!\n'
    '\n'
    '<tg-emoji emoji-id="6143344370625026850">⚔️</tg-emoji> <b>보상 기준</b>\n'
    'ㄴ 1위 → <tg-emoji emoji-id="6143120589944004477">💎</tg-emoji>이로치 초전설\n'
    'ㄴ 2~3위 → <tg-emoji emoji-id="6143120589944004477">💎</tg-emoji>이로치 전설\n'
    'ㄴ 마스터 → <tg-emoji emoji-id="6143120589944004477">💎</tg-emoji>이로치 에픽\n'
    'ㄴ 다이아 → IV+3 ×2\n'
    'ㄴ 플래 → IV+3 ×1\n'
    '\n'
    '<tg-emoji emoji-id="6143254176311811828">✅</tg-emoji> <b>최근 패치</b>\n'
    'ㄴ <b>던전 100층 확장</b> + 자동배틀 롤백\n'
    'ㄴ 뽑기 상위템 확률 하향\n'
    'ㄴ 랭크전 룰 검증 강화 (전설 우회 차단)\n'
    'ㄴ 진화 버튼 무반응 수정\n'
    'ㄴ 캡차 미응답 시 포획 완전 차단\n'
    'ㄴ DM에서 캠프 필드 추가/변경 가능\n'
    '\n'
    '다음 시즌도 파이팅! <tg-emoji emoji-id="6143344370625026850">⚔️</tg-emoji>'
)


async def main():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json={
            "chat_id": ADMIN_ID,
            "text": TEXT,
            "parse_mode": "HTML",
        })
        print(resp.status_code, resp.text[:300])


asyncio.run(main())
