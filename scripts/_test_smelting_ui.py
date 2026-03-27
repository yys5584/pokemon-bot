"""제련소 UI 미리보기 — 관리자 DM으로 전송."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
import config

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = 1832746512

async def main():
    bot = Bot(token=BOT_TOKEN)

    user_id = ADMIN_ID
    # 메인 메뉴
    border = "✦═══════════════════✦"
    menu = "\n".join([
        "🔥 <b>이로치 제련소</b>",
        "",
        border,
        "  📊 게이지: ▓▓▓▓░░░░░░ 42.3%",
        "  ✨ 이로치 확률: 7%",
        "  💎 메가스톤 확률: 2.6%",
        border,
        "",
        "💰 보유 BP: 15,200",
        "🎫 제련 비용: 200 BP",
        "👤 구독: 베이직 (x1.2)",
        "",
        "포켓몬 10마리를 투입하여 이로치 또는",
        "메가스톤 제련권을 노려보세요!",
        "",
        "💡 높은 등급 포켓몬 = 더 많은 게이지",
        "💡 게이지가 높을수록 확률 UP",
    ])
    menu_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 제련 시작", callback_data="demo_1")],
    ])
    await bot.send_message(ADMIN_ID, menu, reply_markup=menu_kb, parse_mode="HTML")

    # 선택 화면
    select = "\n".join([
        "🔥 <b>제련 포켓몬 선택</b>",
        "",
        "선택: <b>3/10</b>",
        "필터: 일반 (312마리)",
        "",
    ])
    rows = []
    # 필터
    rows.append([
        InlineKeyboardButton("▪전체", callback_data="demo"),
        InlineKeyboardButton("일반", callback_data="demo"),
        InlineKeyboardButton("레어", callback_data="demo"),
    ])
    rows.append([
        InlineKeyboardButton("에픽", callback_data="demo"),
        InlineKeyboardButton("전설", callback_data="demo"),
        InlineKeyboardButton("초전설", callback_data="demo"),
        InlineKeyboardButton("✨이로치", callback_data="demo"),
    ])
    # 포켓몬 목록
    pokemon_samples = [
        ("✅", "🟢", "피카츄", "A"),
        ("✅", "🟢", "피카츄", "B"),
        ("✅", "🟢", "꼬부기", "S"),
        ("⬜", "🟢", "파이리", "A"),
        ("⬜", "🟢", "이상해씨", "B"),
        ("⬜", "🔵", "또가스", "A"),
        ("⬜", "🔵", "야도란", "S"),
        ("⬜", "🟣", "마자용", "A"),
    ]
    for check, emoji, name, grade in pokemon_samples:
        rows.append([InlineKeyboardButton(
            f"{check} {emoji} {name} [{grade}]",
            callback_data="demo",
        )])
    # 페이지네이션
    rows.append([
        InlineKeyboardButton("◀", callback_data="demo"),
        InlineKeyboardButton("1/39", callback_data="demo"),
        InlineKeyboardButton("▶", callback_data="demo"),
    ])
    # 하단
    rows.append([
        InlineKeyboardButton("🗑 초기화", callback_data="demo"),
        InlineKeyboardButton("🔙 돌아가기", callback_data="demo"),
    ])

    await bot.send_message(ADMIN_ID, select, reply_markup=InlineKeyboardMarkup(rows), parse_mode="HTML")

    await bot.close()

asyncio.run(main())
