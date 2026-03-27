"""이로치 제련소 프로토타입 — 포켓몬 투입 연출 + 문박사 MC."""
import asyncio
import random
import logging
import os
import sys

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, ContextTypes, MessageHandler, CallbackQueryHandler,
    filters,
)
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from data.smelting_lines import SMELTING_LINES, TYPE_SMELTING_LINES, GENERIC_LINES, REPEAT_LINES

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = "8616848852:AAEEboGyiQ9vUq_8NpzPxlzZEWF0jhNr7iU"


# ═══════════════════════════════════════════
# 커스텀이모지
# ═══════════════════════════════════════════

def _ce(eid, fb="?"):
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'

BOLT    = _ce("6143251942928818741", "⚡")
CRYSTAL = _ce("6143120589944004477", "💎")
STAR    = _ce("6143322638090510138", "⭐")
FIRE    = _ce("6142975986985081276", "🔥")
CROWN   = _ce("6143265588039916937", "👑")
SKULL   = _ce("6143450305993382989", "💀")


# ═══════════════════════════════════════════
# 테스트용 포켓몬 데이터
# ═══════════════════════════════════════════

TEST_POKEMON = [
    {"id": 25, "name": "피카츄", "type": "electric", "emoji": "⚡"},
    {"id": 6, "name": "리자몽", "type": "fire", "emoji": "🔥"},
    {"id": 131, "name": "라프라스", "type": "water", "emoji": "💧"},
    {"id": 150, "name": "뮤츠", "type": "psychic", "emoji": "🔮"},
    {"id": 143, "name": "잠만보", "type": "normal", "emoji": "😴"},
    {"id": 94, "name": "겐가", "type": "ghost", "emoji": "👻"},
    {"id": 130, "name": "갸라도스", "type": "water", "emoji": "💧"},
    {"id": 149, "name": "망나뇽", "type": "dragon", "emoji": "🐉"},
]


# ═══════════════════════════════════════════
# 묘사 선택 로직
# ═══════════════════════════════════════════

def get_smelting_line(pokemon_id: int, pokemon_name: str, pokemon_type: str, nth: int) -> tuple[str, str]:
    """포켓몬 투입 묘사를 선택한다.

    nth: 이 제련에서 몇 번째 투입인지 (0-indexed)
    Returns: (포켓몬 행동 묘사, 문박사 대사)
    """
    # 1순위: 개별 묘사
    individual = SMELTING_LINES.get(pokemon_id, [])
    if nth < len(individual):
        action, mc = individual[nth]
        return action.format(name=pokemon_name), mc

    # 2순위: 반복 투입 (2번째 이상이면)
    if nth >= 1 and REPEAT_LINES:
        action, mc = REPEAT_LINES[nth % len(REPEAT_LINES)]
        return action.format(name=pokemon_name), mc

    # 3순위: 속성별 범용 + 범용 섞어서
    pool = []
    type_lines = TYPE_SMELTING_LINES.get(pokemon_type, [])
    pool.extend(type_lines)
    pool.extend(GENERIC_LINES)

    if pool:
        action, mc = random.choice(pool)
        return action.format(name=pokemon_name), mc

    # 최후 fallback
    return f"{pokemon_name}(이)가 용광로에 들어갔다", "...미안"


# ═══════════════════════════════════════════
# 테두리 패턴
# ═══════════════════════════════════════════

BORDER_NORMAL = [
    "━═══════════════════━",
    "━══✦═══════════✦══━",
    "━════✦═══════✦════━",
    "━═══════✦═══════━━━",
    "━════✦═══════✦════━",
    "━══✦═══════════✦══━",
]
BORDER_GOLD = [
    "✦═✦═✦═✦═✦═✦═✦═✦═✦",
    "═✦═✦═✦═✦═✦═✦═✦═✦═",
]
BORDER_JACKPOT = [
    "★═★═★═★═★═★═★═★═★",
    "═★═★═★═★═★═★═★═★═",
]


def _mc(text):
    return f"🧑‍🔬 <b>문박사</b>: {text}"


def _gauge(pct):
    total = 10
    filled = round(pct / 100 * total)
    return f"🔧 게이지 {'▓' * filled}{'░' * (total - filled)} {pct}%"


def _frame(border_idx, title_line, content, mc_line, gauge_line="", borders=BORDER_NORMAL):
    """고정 레이아웃 프레임."""
    border = borders[border_idx % len(borders)]
    return (
        f"{border}\n"
        f"  <b>◈ 이로치 제련소 ◈</b>\n"
        f"{border}\n"
        f"\n"
        f"{title_line}\n"
        f"\n"
        f"{content}\n"
        f"\n"
        f"{mc_line}\n"
        f"{gauge_line}\n"
        f"{border}"
    )


def _result_frame(border_idx, title, content, mc_line, detail, borders=BORDER_GOLD):
    border = borders[border_idx % len(borders)]
    return (
        f"{border}\n"
        f"  <b>{title}</b>\n"
        f"{border}\n"
        f"\n"
        f"{content}\n"
        f"\n"
        f"{mc_line}\n"
        f"\n"
        f"{detail}\n"
        f"{border}"
    )


# ═══════════════════════════════════════════
# MC 대사
# ═══════════════════════════════════════════

MC_START = [
    "자, 재료 투입 시작한다!",
    "허허, 오늘의 도전이 시작됐군!",
    "좋아, 제련로에 불꽃을 올려라!",
    "GMG? 가면 간다!",
    "중꺽마 정신으로!",
    "HMH!! 하면 해!",
]

MC_PROGRESS = [
    "반응이 오고 있어...!",
    "에너지가 쌓이고 있다!",
    "온도가 올라간다...!",
    "좋아, 계속 가자!",
    "뭔가 느껴져...!",
]

MC_CLIMAX = [
    "이 에너지... 심상치 않아!!!",
    "제련로가 요동치고 있어!!!",
    "뭔가 거대한 반응이...!!!",
    "온도 한계 돌파!!!",
]

MC_SUCCESS = [
    "나왔다!!!",
    "난리자베스!! 성공이야!!",
    "개꿀!! 이로치 떴다!!!",
    "이건 학술적으로도 레전드야...!",
    "GOAT!! 축하한다!",
    "느좋!! 최고야!",
    "떡상!! 이로치 탄생!",
    "역시 될 놈은 된다!!",
]

MC_JACKPOT_REACT = [
    "잠깐... 이거...",
    "이게 진짜...?",
    "메...메가스톤?!?!",
    "ㄹㅇ 미쳤다!!!!",
]

MC_FAIL = [
    "원래 한 번에 되면 재미없지 않나?",
    "포기는 금물! 게이지 쌓이고 있으니까!",
    "다음엔 분명 될 거야! ...아마도!",
    "라면 먹으러... 아니 한 판 더!",
    "GMG? 갈 거면 가는 거야!",
    "존버하면 된다!",
    "한 판만 더... 한 판만...",
    "게이지 보이지? 쌓이고 있다고!",
    "괜찮아, 이로치는 도망 안 가!",
    "이건 실패가 아니야. 투자야!",
    "오늘의 실패가 내일의 이로치다!",
    "넌 할 수 있어. 문박사가 보장한다!",
]

MC_NEAR = [
    "아까 거의 됐잖아! 한 판만 더!",
    "운이 모이고 있어! 곧 터진다!",
    "찐텐 나올 때까지 가는 거야!",
    "게이지는 찼으니까 다음엔 기대해봐 👀",
]

MC_SMALL = [
    "오, 조각이 나왔네! 빈손은 아니야!",
    "작은 수확! 이것도 쌓이면 큰 거야!",
    "허허, 빈손은 아니니 됐지 뭐~",
    "제련의 부산물이 나왔군!",
]


# ═══════════════════════════════════════════
# 핸들러
# ═══════════════════════════════════════════

async def slot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    # 투입 수 선택
    buttons = [
        [
            InlineKeyboardButton("5마리 (3%)", callback_data=f"smelt_{uid}_5"),
            InlineKeyboardButton("7마리 (8%)", callback_data=f"smelt_{uid}_7"),
        ],
        [
            InlineKeyboardButton("10마리 (25%)", callback_data=f"smelt_{uid}_10"),
        ],
    ]

    text = _frame(0,
        "🔥 리자몽을 이로치로 제련!",
        "투입할 리자몽 수를 선택하세요\n\n"
        "  5마리 → 확률  3%\n"
        "  7마리 → 확률  8%\n"
        "  10마리 → 확률 25%",
        _mc("많이 넣을수록 확률이 올라가지!\n  ...대신 그만큼 잃는 거야"),
        _gauge(60),
    )
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")


async def slot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    if not query.data.startswith("smelt_"):
        return

    parts = query.data.split("_")
    target_uid = int(parts[1])
    count = int(parts[2])

    if uid != target_uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    await query.answer("🔥 제련 시작!")

    # 확률 결정
    rates = {5: 0.03, 7: 0.08, 10: 0.25}
    rate = rates.get(count, 0.05)

    roll = random.random()
    if roll < rate * 0.06:  # 잭팟: 성공의 6%
        result_type = "jackpot"
    elif roll < rate:
        result_type = "shiny"
    elif roll < rate + 0.25:
        result_type = "near"
    elif roll < rate + 0.25 + 0.50:
        result_type = "small"
    else:
        result_type = "fail"

    # 투입 포켓몬 선택 (테스트용: 랜덤)
    pokemon_pool = TEST_POKEMON.copy()
    random.shuffle(pokemon_pool)
    # 리자몽으로 통일 (같은 종 제련)
    base_poke = {"id": 6, "name": "리자몽", "type": "fire", "emoji": "🔥"}
    selected = [base_poke.copy() for _ in range(count)]

    retry_btn = [[InlineKeyboardButton("🎰 다시 도전!", callback_data=f"smelt_{uid}_{count}")]]
    frame_i = 0

    # ═══ Phase 1: 제련 시작 ═══
    await _safe_edit(query, _frame(frame_i,
        f"🔥 리자몽 x{count} 투입!",
        f"  {'🔥 ' * min(count, 5)}\n  {'🔥 ' * max(0, count - 5)}",
        _mc(random.choice(MC_START)),
        _gauge(60),
    ))
    frame_i += 1
    await asyncio.sleep(1.5)

    # ═══ Phase 2: 한 마리씩 투입 ═══
    gauge_start = 60
    gauge_per = 30 // count  # 총 30% 증가를 투입 수로 분배

    for i, poke in enumerate(selected):
        gauge = gauge_start + (i + 1) * gauge_per

        # 묘사 가져오기
        action, mc_response = get_smelting_line(
            poke["id"], poke["name"], poke["type"], i
        )

        # 남은 포켓몬 표시
        remaining = count - i - 1
        remaining_display = f"🔥 x{remaining}" if remaining > 0 else "없음"

        # 중간 MC 코멘트 (3마리마다)
        if i > 0 and i % 3 == 0:
            progress_mc = random.choice(MC_PROGRESS)
            await _safe_edit(query, _frame(frame_i,
                f"🔥 제련 진행 중... ({i+1}/{count})",
                f"  {action}",
                _mc(progress_mc),
                _gauge(gauge),
            ))
            frame_i += 1
            await asyncio.sleep(1.0)

        # 투입 연출
        await _safe_edit(query, _frame(frame_i,
            f"🔥 {i+1}번째 투입! (남은: {remaining_display})",
            f"  {action}",
            _mc(mc_response),
            _gauge(gauge),
        ))
        frame_i += 1

        # 감속 패턴: 뒤로 갈수록 느리게 (긴장감 상승)
        if i == count - 1:
            await asyncio.sleep(3.0)   # 마지막: 3초
        elif i >= count - 3:
            await asyncio.sleep(2.5)   # 마지막 3마리: 2.5초
        elif i >= count - 5:
            await asyncio.sleep(2.0)   # 중반: 2초
        else:
            await asyncio.sleep(1.8)   # 초반: 1.8초

    # ═══ Phase 3: 클라이맥스 ═══
    await _safe_edit(query, _frame(frame_i,
        "🔥🔥🔥 전원 투입 완료! 🔥🔥🔥",
        f"  제련로가 요동친다...!",
        _mc(random.choice(MC_CLIMAX)),
        _gauge(95),
    ))
    frame_i += 1
    await asyncio.sleep(2.0)

    # 극적 멈춤
    await _safe_edit(query, _frame(frame_i,
        "🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥",
        "  ......",
        _mc("......!!!"),
        _gauge(99),
    ))
    frame_i += 1
    await asyncio.sleep(2.5)

    # ═══ Phase 4: 암전 ═══
    border = BORDER_NORMAL[frame_i % len(BORDER_NORMAL)]
    await _safe_edit(query, f"{border}\n\n\n\n      ...\n\n\n\n{border}")
    await asyncio.sleep(1.2)

    # ═══ Phase 5: 결과 ═══
    if result_type == "jackpot":
        # 잭팟: MC 4단 리액션
        for i, mc_line in enumerate(MC_JACKPOT_REACT):
            await _safe_edit(query, _frame(i,
                f"  {CROWN} {CROWN} {CROWN}",
                "",
                _mc(mc_line),
                "★ ★ ★ ★ ★ ★ ★ ★ ★ ★",
                borders=BORDER_JACKPOT,
            ))
            await asyncio.sleep(0.8)
        await asyncio.sleep(1.5)

        await _safe_edit(query, _result_frame(0,
            f"{CRYSTAL} MEGA JACKPOT {CRYSTAL}",
            f"  {CROWN} {CROWN} {CROWN}",
            _mc("이건 역사에 남을 순간이야..."),
            f"{CRYSTAL} 메가스톤 획득!\n{FIRE} 리자몽 → ✨ <b>메가리자몽</b>",
            borders=BORDER_JACKPOT,
        ), retry_btn)

    elif result_type == "shiny":
        await _safe_edit(query, _frame(0,
            "✨✨✨✨✨✨✨✨✨✨",
            "  빛이... 빛이 나고 있어!!!",
            _mc(random.choice(MC_SUCCESS)),
            "✦ ✦ ✦ SUCCESS ✦ ✦ ✦",
            borders=BORDER_GOLD,
        ))
        await asyncio.sleep(2.0)

        await _safe_edit(query, _result_frame(0,
            f"{STAR} 이로치 제련 성공! {STAR}",
            "  ✨ 리자몽이 빛나기 시작한다!",
            _mc(random.choice(MC_SUCCESS)),
            "✨ <b>이로치 리자몽</b> 획득!",
            borders=BORDER_GOLD,
        ), retry_btn)

    elif result_type == "near":
        await _safe_edit(query, _frame(0,
            "  빛이 거의 나타났다가...",
            "  ...사라졌다 💨",
            _mc("킹받네... 거의 다 왔는데!"),
            _gauge(80),
        ))
        await asyncio.sleep(2.0)

        await _safe_edit(query, _result_frame(0,
            "😱 아깝다!",
            "  빛이 잠깐 나타났다가 사라졌다",
            _mc(random.choice(MC_NEAR)),
            f"재료 소멸 💨\n{_gauge(80)} (+15%)",
            borders=BORDER_NORMAL,
        ), retry_btn)

    elif result_type == "small":
        frag = random.randint(1, 3)
        bp = random.choice([10, 20, 30])

        await _safe_edit(query, _frame(0,
            "  제련로에서 무언가 나왔다...",
            f"  🧩 조각 {frag}개 + 💰 {bp}BP",
            _mc(random.choice(MC_SMALL)),
            _gauge(68),
        ))
        await asyncio.sleep(2.0)

        await _safe_edit(query, _result_frame(0,
            "🧩 소당첨!",
            f"  🧩 조각 {frag}개 + 💰 {bp}BP 획득!",
            _mc(random.choice(MC_SMALL)),
            f"이로치는 아니지만 빈손은 아니야!\n{_gauge(68)} (+8%)",
            borders=BORDER_NORMAL,
        ), retry_btn)

    else:
        await _safe_edit(query, _frame(0,
            "  제련로의 불꽃이 꺼졌다...",
            "  💨 아무것도 남지 않았다",
            _mc(random.choice(MC_FAIL)),
            _gauge(63),
        ))
        await asyncio.sleep(2.0)

        await _safe_edit(query, _result_frame(0,
            "💨 실패",
            "  재료가 소멸했다",
            _mc(random.choice(MC_FAIL)),
            f"재료 소멸 💨\n{_gauge(63)} (+3%)",
            borders=BORDER_NORMAL,
        ), retry_btn)


async def _safe_edit(query, text, buttons=None):
    markup = InlineKeyboardMarkup(buttons) if buttons else None
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        if "not modified" not in str(e).lower():
            logging.warning(f"edit failed: {e}")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r"^(슬롯|제련)$"), slot_cmd))
    app.add_handler(CallbackQueryHandler(slot_callback, pattern=r"^smelt_"))
    logging.info("Smelting prototype running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
