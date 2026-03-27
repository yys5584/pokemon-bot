"""패치노트 DM 테스트 발송."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from utils.helpers import icon_emoji, ball_emoji, shiny_emoji

async def main():
    import httpx

    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_ID = 1832746512

    _bt = icon_emoji("battle")
    _cr = icon_emoji("crown")
    _se = shiny_emoji()
    _mb = ball_emoji("masterball")
    _ck = icon_emoji("check")
    _sk = icon_emoji("skill")
    _co = icon_emoji("coin")

    text = (
        f"{_bt} <b>v2.9 패치노트</b>\n"
        f"\n"
        f"{_bt} <b>타입 제한 → 코스트 제한으로 전환</b>\n"
        f"- 이번 시즌: 6마리 팀 코스트 12 이하\n"
        f"- 예: 에픽1(4)+레어3(6)+일반2(2)=12\n"
        f"- 랭크전 / 토너먼트 동일 적용\n"
        f"- 랭크전 쿨다운 삭제\n"
        f"\n"
        f"{_sk} <b>던전</b>\n"
        f"- 100층 확장 + 자동배틀 롤백\n"
        f"- 저주/회복룰렛 발동 표시\n"
        f"- 버프 표시 버그 수정\n"
        f"\n"
        f"{_co} <b>뽑기</b>\n"
        f"- {_mb}마볼 6%, 재설정 5%, 잭팟 3.5% (소폭 상향)\n"
        f"\n"
        f"{_cr} <b>토너먼트</b>\n"
        f"- 시즌 코스트 룰 적용\n"
        f"- 1·2등: 일반이로치 → 💎IV+3 스톤\n"
        f"\n"
        f"🌙 <b>대시보드</b>\n"
        f"- 다크모드 추가\n"
        f"- 비행 등 서브타입 필터 수정\n"
        f"\n"
        f"{_ck} <b>기타</b>\n"
        f"- 캡차 미응답 시 포획 차단\n"
        f"- 도감 누락 보정"
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json={
            "chat_id": ADMIN_ID,
            "text": text,
            "parse_mode": "HTML",
        })
        print(f"Status: {resp.status_code}")
        if resp.status_code != 200:
            print(resp.text[:500])
        else:
            print("DM 발송 완료!")

asyncio.run(main())
