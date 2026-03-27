"""Send v2.4 patch note DM to admin with custom emoji."""
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import aiohttp

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_USER_ID = 1832746512

# Custom emoji helper
def ce(emoji_id, fallback="⭐"):
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

# Custom emoji IDs
E_BATTLE = ce("6143344370625026850", "⚔️")
E_SKILL = ce("6143088085631507366", "💫")
E_BOLT = ce("6143251942928818741", "⚡")
E_FIRE = ce("6143060735279766934", "🔥")
E_DRAGON = ce("6143316101150283963", "🐉")
E_BUG = ce("6141032312420180456", "🪲")
E_STEEL = ce("6142980178873162454", "🦇")
E_SNORLAX = ce("6143350078636563496", "😴")
E_CHECK = ce("6143254176311811828", "✅")
E_SKULL = ce("6143450305993382989", "💀")
E_CRYSTAL = ce("6143120589944004477", "💎")
E_EPIC = ce("6141022159117492116", "🟣")
E_RARE = ce("6140797725601438152", "🔵")
E_COMMON = ce("6140791433474351151", "⚪")
E_POKECENTER = ce("6142954550803307680", "🏥")

MSG = (
    f"{E_BATTLE} <b>v2.4 스킬 효과 시스템 + 밸런스 조정</b>\n"
    "━━━━━━━━━━━━━━━\n\n"

    f"{E_SKILL} <b>스킬 특수 효과 활성화</b>\n"
    "배틀 스킬에 특수 효과가 추가되었습니다!\n"
    "스킬 발동(30%) 시 효과가 함께 적용됩니다.\n\n"

    f"{E_SKULL} <b>반동기</b> — 고위력 + 자기피해\n"
    "• 역린: <b>x2.0</b> 데미지, 25% 자해\n"
    "• 인파이트: <b>x2.0</b> 데미지, 25% 자해\n"
    "• 브레이브버드: <b>x2.0</b> 데미지, 25% 자해\n"
    "• 하이점프킥: <b>x2.0</b> 데미지, 25% 자해\n\n"

    "🌿 <b>흡수기</b> — 데미지 + HP 회복\n"
    "• 흡수: 데미지의 <b>25%</b> 회복\n"
    "• 메가드레인: 데미지의 <b>35%</b> 회복\n"
    "• 기가드레인: 데미지의 <b>50%</b> 회복\n\n"

    f"{E_BOLT} <b>선제기</b> — 발동 시 선공\n"
    "• 신속 / 전광석화 / 불릿펀치 / 마하펀치\n"
    "• 스킬 발동 시 <b>30% 확률 선공</b>\n\n"

    f"{E_POKECENTER} <b>기타 효과</b>\n"
    "• 잠자기: 공격 대신 <b>최대HP 35%</b> 회복\n"
    "• 반격: 받은 데미지 <b>x1.5</b> 반사\n"
    "• 손가락흔들기: <b>x0.5~2.5</b> 랜덤 데미지\n"
    "• 튀어오르기: 데미지 0 (잉어킹 전용)\n"
    "• 자폭/대폭발: 기존과 동일\n\n"

    "━━━━━━━━━━━━━━━\n\n"

    f"{E_CRYSTAL} <b>등급 밸런스 조정</b>\n\n"

    f"{E_EPIC} → {E_RARE} <b>에픽 → 레어 하향</b>\n"
    "• 나인테일 / 골덕 / 날쌩마 / 점토도리\n\n"

    f"{E_RARE} → {E_COMMON} <b>레어 → 일반 하향</b>\n"
    "• 토게틱 / 코산호 / 마이농\n\n"

    "<i>※ 배틀 보정치(일반 x1.15, 레어 x1.05) 적용으로\n"
    "실제 배틀 성능 차이는 크지 않습니다.</i>\n\n"

    "━━━━━━━━━━━━━━━\n\n"

    f"{E_BATTLE} <b>인기 포켓몬 영향 분석</b>\n\n"

    f"{E_DRAGON} <b>망나뇽</b> (승률 75.1%)\n"
    "• 역린: x2.0 + 25% 자해\n"
    "• 기대딜 변화: ±0.0% (동일)\n\n"

    f"{E_BUG} <b>헤라크로스</b> (승률 81.8%)\n"
    "• 인파이트: x2.0 + 25% 자해\n"
    "• 기대딜 변화: <b>-3.0%</b> (너프)\n\n"

    f"{E_SNORLAX} <b>잠만보</b> (승률 52.6%)\n"
    "• 잠자기: 최대HP 35% 회복\n"
    "• 생존력 상승 (버프)\n\n"

    f"{E_STEEL} <b>핫삼</b>\n"
    "• 불릿펀치: 30% 선공 효과 추가\n\n"

    f"{E_FIRE} <b>윈디</b>\n"
    "• 신속: 30% 선공 효과 추가\n\n"

    "<i>※ 마기라스, 뮤츠, 라이코, 가이오가 등\n"
    "대부분의 고티어 포켓몬은 영향 없습니다.</i>\n\n"

    "━━━━━━━━━━━━━━━\n\n"

    f"{E_CHECK} <b>대시보드 업데이트</b>\n"
    "• 티어표 스킬 컬럼에 <b>효과 태그</b> 표시\n"
    "• 스킬 호버 시 <b>상세 툴팁</b> 확인 가능\n"
    "• 모바일 반응형 개선 (스탯 그래프 자동 숨김)\n\n"

    "즐거운 배틀 되세요! ⚔️🎮"
)


async def main():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json={
            "chat_id": ADMIN_USER_ID,
            "text": MSG,
            "parse_mode": "HTML",
        }) as resp:
            data = await resp.json()
            if data.get("ok"):
                print("✅ DM 전송 성공!")
            else:
                print(f"❌ 실패: {data}")


if __name__ == "__main__":
    asyncio.run(main())
