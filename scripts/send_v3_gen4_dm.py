"""v3.0 Gen4 DM 공지 브로드캐스트 — 커스텀이모지 포함."""
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from database.connection import get_db

# --- 커스텀이모지 헬퍼 ---
def te(type_key, fallback=""):
    """타입 커스텀이모지 태그."""
    from config import TYPE_CUSTOM_EMOJI, TYPE_EMOJI
    eid = TYPE_CUSTOM_EMOJI.get(type_key, "")
    fb = fallback or TYPE_EMOJI.get(type_key, "")
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>' if eid else fb

def re(rarity_key, fallback=""):
    """레어리티 커스텀이모지 태그."""
    from config import RARITY_CUSTOM_EMOJI, RARITY_EMOJI
    eid = RARITY_CUSTOM_EMOJI.get(rarity_key, "")
    fb = fallback or RARITY_EMOJI.get(rarity_key, "")
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>' if eid else fb

# --- 타입 조합 ---
dragon_ground = f"{te('dragon')}{te('ground')}"
fire_fight = f"{te('fire')}{te('fighting')}"
water_steel = f"{te('water')}{te('steel')}"
fight_steel = f"{te('fighting')}{te('steel')}"
steel_dragon = f"{te('steel')}{te('dragon')}"
water_dragon = f"{te('water')}{te('dragon')}"
ghost_dragon = f"{te('ghost')}{te('dragon')}"
fairy_fly = f"{te('fairy')}{te('flying')}"
ice_ghost = f"{te('ice')}{te('ghost')}"
dark_ice = f"{te('dark')}{te('ice')}"
electric_steel = f"{te('electric')}{te('steel')}"
psychic = te('psychic')
grass = te('grass')
fire = te('fire')
water = te('water')
dark = te('dark')
normal = te('normal')

# --- 레어리티 뱃지 ---
epic = re('epic')
legend = re('legendary')
ultra = re('ultra_legendary')

DM_TEXT = f"""\
📢 <b>v3.0 — 4세대(신오) 대형 업데이트!</b>

안녕하세요, 문박사입니다.

<b>4세대 107종</b>이 추가되었습니다!
387번 모부기부터 493번 아르세우스까지, <b>총 493종</b>의 포켓몬을 만나보세요.

━━━━━━━━━━━━━━━━━━━━

<b>🌟 신규 포켓몬 107종</b>

{grass} 모부기 라인 / {fire_fight} 불꽃숭이 라인 / {water_steel} 엠페르트 라인
{dragon_ground} <b>한카리아스</b> — 4세대 600족, 시로나의 에이스
{fight_steel} <b>루카리오</b> — 파동의 용사
{fairy_fly} <b>토게키스</b> / {dark_ice} <b>포푸니라</b> / {electric_steel} <b>자포코일</b>

{legend} <b>전설</b> — 유크시/엠라이트/아그놈, 히드런, 크레세리아
{ultra} <b>초전설</b> — 디아루가{steel_dragon} 펄기아{water_dragon} 기라티나{ghost_dragon}
　　　　마나피 / 다크라이{dark} / 쉐이미{grass} / 아르세우스{normal}

━━━━━━━━━━━━━━━━━━━━

<b>🔀 분기 진화 시스템</b>

친밀도 MAX 후 진화 시 <b>랜덤으로 2종 중 하나</b>로!

• {psychic} 킬리아 → 가디안 또는 엘레이드
• {te('ice')} 눈꼬마 → 얼음귀신 또는 {ice_ghost} 눈여아

━━━━━━━━━━━━━━━━━━━━

<b>🔄 크로스세대 진화 18종</b>

기존 포켓몬 중 18종이 4세대 진화형을 얻었습니다!

{electric_steel} 자포코일 / {te('ground')}{te('rock')} 거대코뿌리 / {te('electric')} 에레키블
{fire} 마그마번 / {fairy_fly} 토게키스 / {dark_ice} 포푸니라
{grass} 리피아·글레이시아{te('ice')} — 이브이 진화 <b>7종</b> 달성!

━━━━━━━━━━━━━━━━━━━━

<b>⚔️ 밸런스 조정</b>

• {dragon_ground} 한카리아스 / {normal} 레지기가스 → {epic} epic (코스트 4)
• 전체 스킬 파워 Gen1-3 기준 정밀 보정
• {grass} 리피아 / {te('ice')} 글레이시아 → {epic} epic (이브이 라인 통일)

━━━━━━━━━━━━━━━━━━━━

<b>📖 도감 386종 → 493종</b>

• 도감/마이포켓 <b>4세대 필터</b> 추가
• 4세대 칭호 추가 + <b>107종 트리비아</b>

━━━━━━━━━━━━━━━━━━━━

<b>🛡️ 어뷰징 챌린지 5분 → 3분</b>

━━━━━━━━━━━━━━━━━━━━

비버니교 신도 여러분, 아르세우스를 잡으러 가봅시다! 🐹
— 문박사 드림 🧑‍🔬"""


async def main():
    from telegram import Bot
    bot = Bot(token=os.environ["BOT_TOKEN"])
    pool = await get_db()

    # 최근 7일 활성 유저
    rows = await pool.fetch(
        "SELECT DISTINCT user_id FROM user_pokemon WHERE caught_at > NOW() - INTERVAL '7 days'"
    )
    user_ids = [r["user_id"] for r in rows]
    print(f"📤 {len(user_ids)}명에게 DM 발송 시작...")

    success = 0
    fail = 0
    for uid in user_ids:
        try:
            await bot.send_message(chat_id=uid, text=DM_TEXT, parse_mode="HTML")
            success += 1
        except Exception as e:
            fail += 1
            if "bot was blocked" not in str(e).lower():
                print(f"  ❌ {uid}: {e}")
        await asyncio.sleep(0.05)  # rate limit

    print(f"✅ 완료: {success}명 성공, {fail}명 실패")

    # 대시보드 공지도 등록
    await pool.execute(
        "INSERT INTO board_posts (board_type, user_id, display_name, tag, title, content) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        "notice", 1832746512, "TG포켓", "패치노트",
        "v3.0 패치노트 — 4세대(신오) 107종 대형 업데이트", DM_TEXT,
    )
    print("OK: 대시보드 공지도 등록 완료")


if __name__ == "__main__":
    asyncio.run(main())
