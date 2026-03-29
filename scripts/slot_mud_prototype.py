"""이로치 제련소 — 머드게임 스타일 프로토타입.

특징:
- 박스 프레임 테두리 (═══)
- 프레임마다 테두리 패턴 변화 (빛이 흐르는 효과)
- 릴 스피닝 (포켓몬 커스텀이모지 돌아감)
- 머드 MC 문박사 실황
- 고정 레이아웃 (줄 수 일정)
- 카지노 97% 회수율 (소당첨 포함)
"""
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

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = "8616848852:AAEEboGyiQ9vUq_8NpzPxlzZEWF0jhNr7iU"

# ═══════════════════════════════════════════
# 커스텀이모지
# ═══════════════════════════════════════════

def _ce(eid, fb="?"):
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'

POKE = {
    "pikachu":    _ce("6143424549074508692", "⚡"),
    "charmander": _ce("6142987961353903580", "🔥"),
    "squirtle":   _ce("6143034596108803222", "💧"),
    "bulbasaur":  _ce("6142953352507432594", "🌿"),
    "eevee":      _ce("6143466343401268847", "🦊"),
    "mew":        _ce("6143355370036274725", "🔮"),
    "jigglypuff": _ce("6143158604699540827", "🎀"),
    "psyduck":    _ce("6143060400272317013", "🦆"),
    "snorlax":    _ce("6143350078636563496", "😴"),
    "dratini":    _ce("6143371373084417997", "🐉"),
}

CROWN   = _ce("6143265588039916937", "👑")
BOLT    = _ce("6143251942928818741", "⚡")
SKULL   = _ce("6143450305993382989", "💀")
CRYSTAL = _ce("6143120589944004477", "💎")
STAR    = _ce("6143322638090510138", "⭐")
FIRE    = _ce("6142975986985081276", "🔥")

SYMBOLS = list(POKE.values())


# ═══════════════════════════════════════════
# 머드 스타일 박스 프레임
# ═══════════════════════════════════════════

# 테두리 패턴 (프레임마다 순환 → 빛이 흐르는 효과)
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


def _box(slot_line, mc_line, border_idx=0, borders=BORDER_NORMAL, gauge=""):
    """머드 스타일 프레임 (고정 줄 수)."""
    border = borders[border_idx % len(borders)]
    return (
        f"{border}\n"
        f"  <b>◈ 이로치 제련소 ◈</b>\n"
        f"{border}\n"
        f"\n"
        f"  {slot_line}\n"
        f"\n"
        f"{mc_line}\n"
        f"{gauge}\n"
        f"{border}"
    )


def _result_box(title, slot_line, mc_line, detail, borders=BORDER_GOLD, border_idx=0):
    """결과 전용 프레임."""
    border = borders[border_idx % len(borders)]
    return (
        f"{border}\n"
        f"  <b>{title}</b>\n"
        f"{border}\n"
        f"\n"
        f"  {slot_line}\n"
        f"\n"
        f"{mc_line}\n"
        f"\n"
        f"{detail}\n"
        f"{border}"
    )


def _slot(a, b, c):
    return f"[ {a} ┃ {b} ┃ {c} ]"


def _gauge(pct):
    total = 10
    filled = round(pct / 100 * total)
    bar = "▓" * filled + "░" * (total - filled)
    return f"🔧 게이지 {bar} {pct}%"


# ═══════════════════════════════════════════
# 문박사 대사
# ═══════════════════════════════════════════

MC_COMMIT = [
    "자, 재료 투입 완료! 가보자고!",
    "허허, 오늘의 도전이 시작됐군!",
    "좋아, 제련로에 불꽃이 타오른다!",
    "음... 오늘은 느낌이 좋은데?",
    "GMG? 가면 간다!",
    "중꺽마 정신으로!",
    "자 용기 있는 트레이너!",
    "HMH!! 하면 해!",
    "제련로가 달궈졌어. 시작한다!",
    "오늘은 뭔가 될 것 같은 느낌적 느낌...",
]

MC_SPIN = [
    "돌아간다~!",
    "운명의 슬롯이 회전 중!",
    "어디 한번 보자꾸나~",
    "두근두근...",
    "자 집중...!",
]

MC_FIRST = [
    "오, {sym} 나왔어!",
    "첫 번째는 {sym}!",
    "{sym}! 시작이 좋은데?",
    "오호~ {sym}! 다음은...?",
]

MC_MATCH = [
    "헉?! 두 개 일치!!!",
    "이왜진?! 두 개 맞았어!!!",
    "난리자베스!! 두 개 일치!!!",
    "홀리몰리?! 이거 되는 건가?!",
    "심장 떨려... 두 개 같다!!!",
    "아 잠깐 잠깐 잠깐!!!",
    "오오오?! {sym}{sym} 연속!!!",
]

MC_NOMATCH = [
    "음... 다르군~ 마지막 가보자!",
    "다르긴 한데... 마지막이 있으니까!",
    "아직 끝나지 않았어!",
]

MC_SUSPENSE = [
    "마지막이야... 제발 떠라!!",
    "이거 되면 내가 더 흥분하겠는데...",
    "이번엔 된다 이번엔...",
    "손이 떨린다 진짜...",
    "제발... 제발...!!!",
    "나도 긴장된다 솔직히...",
]

MC_JACKPOT = ["잠깐... 이거...", "이게 진짜...?", "메...메가스톤?!?!", "ㄹㅇ 미쳤다!!!!"]
MC_SUCCESS_1 = ["!!!", "나왔다!!!", "오오오!!!", "빠밤!!!"]
MC_SUCCESS_2 = [
    "축하하네! 이로치 확정이야!",
    "개꿀!! 이로치 떴다!!!",
    "난리자베스!! 성공이야!!",
    "이건 학술적으로도 레전드야...",
    "느좋!! 최고야 축하한다!",
    "GOAT!! 오늘의 주인공이로군!",
    "내 연구 인생에서 이런 건 처음이야!",
]

MC_NEAR_1 = [
    "아이고...", "에이~ 아깝다 ㅋㅋ", "킹받네...",
    "어 왜 거기서 멈춰...!", "억까당했다...",
    "할많하않...", "니어미스자베스...",
]
MC_NEAR_2 = [
    "게이지는 찼으니까 다음엔 기대해봐 👀",
    "아까 거의 됐잖아! 한 판만 더!",
    "운이 모이고 있어! 곧 터진다!",
    "찐텐 나올 때까지 가는 거야!",
]

MC_SMALL_WIN = [
    "오, 조각이 나왔네! 아쉽지만 본전!",
    "허허, 작은 수확이라도 있으니 다행이군!",
    "조각이라도 건졌다! 다음엔 더 클 거야!",
    "나쁘지 않아! 이것도 쌓이면 큰 거야!",
    "허허, 빈손은 아니니 됐지 뭐~",
    "제련의 부산물이 나왔군! 아깝진 않아!",
]

MC_FAIL_1 = [
    "허허...", "이번엔 인연이 아니었나보군",
    "산으로 갔다...", "하... 웃기다 ㅋㅋ",
    "괜찮아 딩딩딩~", "와르르...",
]
MC_FAIL_2 = [
    "원래 한 번에 되면 재미없지 않나?",
    "포기는 금물! 게이지 쌓이고 있으니까!",
    "다음엔 분명 될 거야! ...아마도!",
    "라면 먹으러... 아니 한 판 더!",
    "GMG? 갈 거면 가는 거야!",
    "존버하면 된다!",
    "테무인간 아니잖아? 진짜를 노려봐!",
    "한 판만 더... 한 판만...",
    "실패는 성공의 어머니라고 했어!",
    "게이지 보이지? 쌓이고 있다고!",
    "확률적으로 다음엔 더 높아진다니까!",
    "나도 처음엔 50번 실패했다고!",
    "괜찮아, 이로치는 도망 안 가!",
    "슬롯의 여신이 잠깐 쉬는 거야!",
    "넌 할 수 있어. 문박사가 보장한다!",
    "어차피 할 거잖아? ㅋㅋ 솔직해져봐",
    "이건 실패가 아니야. 투자야!",
    "오늘의 실패가 내일의 이로치다!",
]


def _mc(text):
    return f"🧑‍🔬 <b>문박사</b>: {text}"


# ═══════════════════════════════════════════
# 핸들러
# ═══════════════════════════════════════════

async def slot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    buttons = [[InlineKeyboardButton("🎰 제련 시작!", callback_data=f"mud_{uid}")]]
    text = _box(
        _slot("❓", "❓", "❓"),
        _mc("어서오게! 오늘도 도전하는 건가?"),
        gauge=_gauge(60),
    )
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")


async def slot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    if not query.data.startswith("mud_"):
        return
    target_uid = int(query.data.split("_")[1])
    if uid != target_uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return
    await query.answer("🎰 시작!")

    # ── 결과 결정 (카지노 97% 회수율) ──
    roll = random.random()
    if roll < 0.015:
        result_type = "jackpot"
        final = [CROWN, CROWN, CROWN]
    elif roll < 0.06:
        result_type = "shiny"
        idx = random.randrange(len(SYMBOLS))
        final = [SYMBOLS[idx]] * 3
    elif roll < 0.28:
        result_type = "near"
        idx = random.randrange(len(SYMBOLS))
        other = random.choice([i for i in range(len(SYMBOLS)) if i != idx])
        final = [SYMBOLS[idx], SYMBOLS[idx], SYMBOLS[other]]
    elif roll < 0.85:
        result_type = "small"  # 소당첨
        idxs = random.sample(range(len(SYMBOLS)), 3)
        final = [SYMBOLS[i] for i in idxs]
    else:
        result_type = "fail"  # 순수 꽝 15%
        idxs = random.sample(range(len(SYMBOLS)), 3)
        final = [SYMBOLS[i] for i in idxs]

    is_match_2 = (final[0] == final[1])
    retry_btn = [[InlineKeyboardButton("🎰 다시 도전!", callback_data=f"mud_{uid}")]]

    # ═══════════════════════════════════════
    # 공통 Phase 1~3: 스피닝 → 릴 멈춤
    # ═══════════════════════════════════════

    frame_i = 0

    # ── Phase 1: 투입 (테두리 빛 흐름 시작) ──
    await _safe_edit(query, _box(
        _slot("❓", "❓", "❓"),
        _mc(random.choice(MC_COMMIT)),
        border_idx=frame_i,
        gauge=_gauge(60),
    ))
    frame_i += 1
    await asyncio.sleep(1.0)

    # ── Phase 2: 스피닝 (릴 돌아감 + 테두리 빛 이동) ──
    for i in range(3):
        r1 = random.choice(SYMBOLS)
        r2 = random.choice(SYMBOLS)
        r3 = random.choice(SYMBOLS)
        await _safe_edit(query, _box(
            _slot(r1, r2, r3),
            _mc(random.choice(MC_SPIN)),
            border_idx=frame_i,
            gauge=_gauge(60),
        ))
        frame_i += 1
        await asyncio.sleep(0.5)

    # ── Phase 3a: 첫 번째 릴 멈춤 ──
    await _safe_edit(query, _box(
        _slot(final[0], "❓", "❓"),
        _mc(random.choice(MC_FIRST).format(sym=final[0])),
        border_idx=frame_i,
        gauge=_gauge(65),
    ))
    frame_i += 1
    await asyncio.sleep(0.8)

    # 2,3번 릴 계속 돌아감
    for i in range(2):
        r2 = random.choice(SYMBOLS)
        r3 = random.choice(SYMBOLS)
        await _safe_edit(query, _box(
            _slot(final[0], r2, r3),
            _mc("..."),
            border_idx=frame_i,
            gauge=_gauge(65),
        ))
        frame_i += 1
        await asyncio.sleep(0.4)

    # ── Phase 3b: 두 번째 릴 멈춤 ──
    if is_match_2:
        await _safe_edit(query, _box(
            _slot(final[0], final[1], "❓"),
            _mc(random.choice(MC_MATCH).format(sym=final[0])),
            border_idx=frame_i,
            gauge=_gauge(80),
        ))
    else:
        await _safe_edit(query, _box(
            _slot(final[0], final[1], "❓"),
            _mc(random.choice(MC_NOMATCH)),
            border_idx=frame_i,
            gauge=_gauge(65),
        ))
    frame_i += 1
    await asyncio.sleep(1.0)

    # ── Phase 4: 2개 일치 시 서스펜스 ──
    if is_match_2:
        # 3번째 릴 돌아감
        for i in range(2):
            r3 = random.choice(SYMBOLS)
            await _safe_edit(query, _box(
                _slot(final[0], final[1], r3),
                _mc(random.choice(MC_SUSPENSE)),
                border_idx=frame_i,
                gauge=_gauge(85),
            ))
            frame_i += 1
            await asyncio.sleep(0.5)

        # 극적 멈춤
        await _safe_edit(query, _box(
            _slot(final[0], final[1], "🫣"),
            _mc("......"),
            border_idx=frame_i,
            gauge=_gauge(90),
        ))
        frame_i += 1
        await asyncio.sleep(1.5)

        # 니어미스 오버슈트 (성공이 아닐 때만)
        if result_type == "near":
            await _safe_edit(query, _box(
                _slot(final[0], final[1], final[0]),  # 잠깐 일치!
                _mc("!!!"),
                border_idx=frame_i,
                borders=BORDER_GOLD,
                gauge=_gauge(95),
            ))
            frame_i += 1
            await asyncio.sleep(0.3)

    # ═══════════════════════════════════════
    # Phase 5: 3번째 릴 + MC 리액션 + 극적 전환
    # ═══════════════════════════════════════

    slot_final = _slot(final[0], final[1], final[2])

    if result_type == "jackpot":
        # ── 3번째 릴: 왕관! ──
        jp_slot = _slot(CROWN, CROWN, CROWN)
        await _safe_edit(query, _box(
            jp_slot, _mc(MC_JACKPOT[0]),
            border_idx=frame_i, gauge=_gauge(95),
        ))
        await asyncio.sleep(1.0)
        await _safe_edit(query, _box(
            jp_slot, _mc(MC_JACKPOT[1]),
            border_idx=frame_i+1, gauge=_gauge(98),
        ))
        await asyncio.sleep(1.0)
        await _safe_edit(query, _box(
            jp_slot, _mc(MC_JACKPOT[2]),
            border_idx=frame_i+2, borders=BORDER_JACKPOT,
            gauge="★ ★ ★ ★ ★ ★ ★ ★ ★ ★",
        ))
        await asyncio.sleep(0.8)
        await _safe_edit(query, _box(
            jp_slot, _mc(MC_JACKPOT[3]),
            border_idx=frame_i+3, borders=BORDER_JACKPOT,
            gauge="★ ★ ★ JACKPOT ★ ★ ★",
        ))
        await asyncio.sleep(1.0)

        # ── 깜빡 + 암전 ──
        await _safe_edit(query,
            f"{BORDER_JACKPOT[0]}\n\n\n\n\n\n\n\n{BORDER_JACKPOT[1]}")
        await asyncio.sleep(0.4)
        await _safe_edit(query,
            f"{BORDER_JACKPOT[1]}\n\n\n      ...\n\n\n\n{BORDER_JACKPOT[0]}")
        await asyncio.sleep(0.8)

        # ── 결과 팡! ──
        await _safe_edit(query, _result_box(
            f"{CRYSTAL} MEGA JACKPOT {CRYSTAL}",
            jp_slot,
            _mc("이건 역사에 남을 순간이야..."),
            f"{CRYSTAL} 메가스톤 획득!\n{FIRE} 리자몽 → ✨ <b>메가리자몽</b>",
            borders=BORDER_JACKPOT,
        ), retry_btn)

    elif result_type == "shiny":
        # ── 3번째 릴 + MC ──
        await _safe_edit(query, _box(
            slot_final, _mc(random.choice(MC_SUCCESS_1)),
            border_idx=0, borders=BORDER_GOLD,
            gauge="✦ ✦ ✦ ✦ ✦ ✦ ✦ ✦ ✦ ✦",
        ))
        await asyncio.sleep(0.8)
        mc_congrats = random.choice(MC_SUCCESS_2)
        await _safe_edit(query, _box(
            slot_final, _mc(mc_congrats),
            border_idx=1, borders=BORDER_GOLD,
            gauge="✦ ✦ ✦ SUCCESS ✦ ✦ ✦",
        ))
        await asyncio.sleep(1.2)

        # ── 깜빡 + 암전 ──
        await _safe_edit(query,
            f"{BORDER_GOLD[0]}\n\n\n\n\n\n\n\n{BORDER_GOLD[1]}")
        await asyncio.sleep(0.4)
        await _safe_edit(query,
            f"{BORDER_GOLD[1]}\n\n\n      ✨...✨\n\n\n\n{BORDER_GOLD[0]}")
        await asyncio.sleep(0.8)

        # ── 결과 팡! ──
        await _safe_edit(query, _result_box(
            f"{STAR} 이로치 제련 성공! {STAR}",
            slot_final,
            _mc(mc_congrats),
            "🔥 리자몽이 빛나기 시작한다!\n✨ <b>이로치 리자몽</b> 획득!",
            borders=BORDER_GOLD,
        ), retry_btn)

    elif result_type == "near":
        # ── 3번째 릴 + MC ──
        mc_near = random.choice(MC_NEAR_1)
        await _safe_edit(query, _box(
            slot_final, _mc(mc_near),
            border_idx=frame_i, gauge=_gauge(75),
        ))
        await asyncio.sleep(1.2)

        # ── 암전 ──
        await _safe_edit(query,
            f"━═══════════════════━\n\n\n      💨...\n\n\n\n━═══════════════════━")
        await asyncio.sleep(0.8)

        # ── 결과 ──
        await _safe_edit(query, _result_box(
            "😱 아깝다!",
            slot_final,
            _mc(random.choice(MC_NEAR_2)),
            f"재료 소멸 💨\n{_gauge(75)} (+15%)",
        ), retry_btn)

    elif result_type == "small":
        # ── 3번째 릴 + MC ──
        mc_sw = random.choice(MC_SMALL_WIN)
        await _safe_edit(query, _box(
            slot_final, _mc(mc_sw),
            border_idx=frame_i, gauge=_gauge(65),
        ))
        await asyncio.sleep(1.5)

        # ── 암전 ──
        await _safe_edit(query,
            f"━═══════════════════━\n\n\n      🧩...\n\n\n\n━═══════════════════━")
        await asyncio.sleep(0.8)

        # ── 결과 ──
        frag = random.randint(1, 3)
        bp = random.choice([10, 20, 30])
        await _safe_edit(query, _result_box(
            "🧩 소당첨!",
            slot_final,
            _mc(mc_sw),
            f"🧩 조각 {frag}개 + 💰 {bp}BP 획득!\n{_gauge(65)} (+10%)",
        ), retry_btn)

    else:
        # ── 3번째 릴 + MC ──
        await _safe_edit(query, _box(
            slot_final, _mc(random.choice(MC_FAIL_1)),
            border_idx=frame_i, gauge=_gauge(60),
        ))
        await asyncio.sleep(1.5)

        # ── 암전 ──
        await _safe_edit(query,
            f"━═══════════════════━\n\n\n      ...\n\n\n\n━═══════════════════━")
        await asyncio.sleep(0.8)

        # ── 결과 ──
        await _safe_edit(query, _result_box(
            "💨 실패",
            slot_final,
            _mc(random.choice(MC_FAIL_2)),
            f"재료 소멸 💨\n{_gauge(60)} (+5%)",
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
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r"^슬롯$"), slot_cmd))
    app.add_handler(CallbackQueryHandler(slot_callback, pattern=r"^mud_"))
    logging.info("MUD slot prototype running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
