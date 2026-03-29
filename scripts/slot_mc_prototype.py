"""슬롯 MC 실황 프로토타입 — 포켓TG가 실시간 중계."""
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

# 커스텀이모지 헬퍼
def _ce(eid, fb="?"):
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'

# 포켓몬 커스텀이모지
POKE_EMOJI = {
    "pikachu": _ce("6143424549074508692", "⚡"),
    "charmander": _ce("6142987961353903580", "🔥"),
    "squirtle": _ce("6143034596108803222", "💧"),
    "bulbasaur": _ce("6142953352507432594", "🌿"),
    "eevee": _ce("6143466343401268847", "🦊"),
    "mew": _ce("6143355370036274725", "🔮"),
    "jigglypuff": _ce("6143158604699540827", "🎀"),
    "psyduck": _ce("6143060400272317013", "🦆"),
    "snorlax": _ce("6143350078636563496", "😴"),
    "dratini": _ce("6143371373084417997", "🐉"),
}
CROWN = _ce("6143265588039916937", "👑")

# 이펙트 커스텀이모지
BOLT = _ce("6143251942928818741", "⚡")
SKULL = _ce("6143450305993382989", "💀")
CRYSTAL = _ce("6143120589944004477", "💎")
BATTLE = _ce("6143344370625026850", "⚔")
COIN = _ce("6143083713354801765", "💰")
STAR = _ce("6143322638090510138", "⭐")  # victini
FIRE = _ce("6142975986985081276", "🔥")  # moltres
CHECK = _ce("6143254176311811828", "✅")

SYMBOLS = list(POKE_EMOJI.values())
SYMBOL_NAMES = list(POKE_EMOJI.keys())

# MC 대사 풀
# ═══════════════════════════════════════════
# 문박사 MC 대사 풀 (총 200+ 대사)
# ═══════════════════════════════════════════

MC_START = [
    "자, 오늘의 도전자가 나섰군!",
    "허허, 또 왔나? 좋아 해보자고!",
    "음... 오늘은 느낌이 좋은데?",
    "오? 눈빛이 다르군. 해보자!",
    "자 재료 투입! 제련 시작이다!",
    "중꺽마 정신으로 가보자고!",
    "오늘은 뭔가 될 것 같은 느낌적 느낌...",
    "좋아, GMG? 가면 간다!",
    "제련로가 달궈졌어. 준비됐나?",
    "허허, 오늘도 과학의 힘을 믿어보지!",
    "자 재료 확인 완료! 시작한다!",
    "아, 용기 있는 트레이너로군!",
]

MC_SPIN = [
    "자 돌아간다~!",
    "운명의 슬롯이 회전 중!",
    "어디 한번 보자꾸나~",
    "두근두근...",
    "HMH!! 하면 해!",
    "자 집중...!",
    "돌아라 돌아라~",
]

MC_FIRST_STOP = [
    "오, 첫 번째 멈췄군!",
    "허허, {sym} 나왔어!",
    "음음, 첫 번째는 {sym}이로군!",
    "오호~ {sym}! 시작이 좋은데?",
    "{sym}! 일단 하나 확인!",
    "좋아, {sym}! 다음은...?",
    "첫 번째! {sym} 고정!",
]

MC_SECOND_MATCH = [
    "헉?! 두 개 일치!!!",
    "잠깐... 이거 두 개 같은데?!",
    "오오?! {sym}{sym} 연속이야!!!",
    "이왜진?! 두 개 맞았어!!!",
    "난리자베스!! 두 개 일치!!!",
    "홀리몰리?! 이거 되는 건가?!",
    "심장 떨려... 두 개 같다!!!",
    "ㅁ...뭐?! 두 개?!?!",
    "아 잠깐 잠깐 잠깐!!!",
    "이거 실화냐?! 두 개 일치!!!",
]

MC_SECOND_NOMATCH = [
    "음... 두 번째는 다르군~",
    "두 번째는 {sym}! 마지막 가보자!",
    "다르긴 한데... 마지막이 있으니까!",
    "아직 끝난 게 아니야! 마지막!",
    "흠, {sym}이로군. 마지막 승부!",
]

MC_SUSPENSE = [
    "자... 마지막이야...",
    "마지막 릴... 제발 떠라!!",
    "이거 되면 내가 더 흥분하겠는데...",
    "중꺽마... 꺾이지 않는 마음...",
    "이번엔 된다 이번엔...",
    "손이 떨린다 진짜...",
    "잠깐 숨 좀 고르고...",
    "제발... 제발...!!!",
    "여기서 되면 전설인데...",
    "나도 긴장된다 솔직히...",
]

MC_DOTS = [
    "...",
    ". . .",
    "......",
]

MC_JACKPOT = [
    "잠깐... 이거...",
    "이게 진짜...?",
    "메...메가스톤?!?!?!",
    "🔥🔥🔥 ㄹㅇ 미쳤다!!!! 🔥🔥🔥",
]

MC_SUCCESS = [
    # 즉각 반응 (첫 멘트)
    "!!!",
    "나왔다!!!",
    "오오오!!!",
    # 축하 멘트 (두번째 멘트)
    "허허! 축하하네! 이로치 확정이야!",
    "개꿀!! 이로치 떴다!!!",
    "난리자베스!! 성공이야!!",
    "이건 학술적으로도 레전드야...",
    "느좋!! 최고야 축하한다!",
    "떡상!! 이로치 탄생이다!",
    "GOAT!! 오늘의 주인공이로군!",
    "킹왕짱!! 대단하다 진짜!",
    "갓겜이다 이거!! ㅋㅋㅋ",
    "역시 될 놈은 된다!!",
    "내 연구 인생에서 이런 건 처음이야!",
    "축하한다! 오늘 로또도 사봐!",
]

MC_NEAR = [
    "아이고...",
    "에이~ 아깝다 ㅋㅋ",
    "킹받네... 거의 다 왔는데!",
    "어 왜 거기서 멈춰...!",
    "억까당했다... 이건 너무한데",
    "할많하않...",
    "니어미스자베스... 아쉽다 진짜",
    "아 이거 살짝 빡친다 나도",
    "헐... 하나만 맞았으면!!",
    "이게 안 된다고?! 말이 돼?!",
    "아까워서 내가 다 속상하다",
    "99%에서 멈추는 느낌이군...",
]

MC_NEAR_2 = [
    "게이지는 찼으니까 다음엔 기대해봐 👀",
    "공부 많이 된다~ 다음엔 될 거야!",
    "아까 거의 됐잖아! 한 판만 더!",
    "찐텐 나올 때까지 가는 거야!",
    "이 정도면 거의 다 온 거야!",
    "다음 판이 진짜야... 느낌 온다!",
    "아쉽지만 게이지가 꽤 찼어!",
    "이렇게 아까울 수가... 한 번만 더!",
    "운이 모이고 있어! 곧 터진다!",
    "슬롯의 신이 장난치는 거야 ㅋㅋ",
]

MC_FAIL = [
    "허허...",
    "음... 이번엔 인연이 아니었나보군",
    "산으로 갔다...",
    "하... 그냥 웃기다 ㅋㅋ",
    "스불재... 인가?",
    "괜찮아 딩딩딩~",
    "음... 쿨하게 넘어가자",
    "제련로가 삐뚤어졌나...",
    "이건 뭐 어쩔 수 없지",
    "허허... 과학도 가끔 실패하는 법이야",
    "포켓몬들이 안 맞는 날이군",
    "이런 날도 있는 거야...",
]

MC_FAIL_TEASE = [
    "원래 한 번에 되면 재미없지 않나?",
    "포기는 금물! 게이지 쌓이고 있으니까!",
    "이런 날도 있는 거지 뭐~",
    "다음엔 분명 될 거야! ...아마도!",
    "라면 먹으러... 아니 한 판 더 가자!",
    "GMG? 갈 거면 가는 거야!",
    "존버하면 된다! 존버 실패는 없어!",
    "테무인간 아니잖아? 진짜를 노려봐!",
    "한 판만 더... 한 판만...",
    "알잘딱깔센으로 한 번 더 가봅시다!",
    "실패는 성공의 어머니라고 했어!",
    "이건 연습이었어. 진짜는 다음 판!",
    "게이지 보이지? 쌓이고 있다고!",
    "내가 30년 연구한 경험에 의하면... 곧 돼!",
    "확률적으로 다음엔 더 높아진다니까!",
    "아직 재료 있지? 그럼 된 거야!",
    "오늘 안에 될 수도 있어! 아마!",
    "허허, 슬롯이란 원래 이런 거야~",
    "나도 처음엔 50번 실패했다고!",
    "이게 나중에 추억이 되는 거야 ㅋㅋ",
    "다음 거는 내가 봐도 될 것 같은데?",
    "실패도 데이터야! 연구에 도움이 돼!",
    "괜찮아, 이로치는 도망 안 가!",
    "지금 포기하면 게이지가 아까워!",
    "슬롯의 여신이 지금 잠깐 쉬는 거야!",
    "나를 믿어! 다음엔 된다!!",
    "아 이거 거의 다 왔는데... 한 번만?",
    "포켓몬 세계에 공짜는 없지 ㅋㅋ",
    "넌 할 수 있어. 문박사가 보장한다!",
    "흐음... 다음 판은 좀 다를 거야!",
    "여기서 멈추면 진짜 아까운 건데...?",
    "어차피 할 거잖아? ㅋㅋ 솔직해져봐",
    "다음에 되면 이 실패가 빛나는 거야!",
    "참을 인 세 번이면 이로치가 온다!",
    "연성 게이지가 널 기다리고 있다고!",
    "이건 실패가 아니야. 투자야!",
    "감이 안 좋은 게 아니라 타이밍이야!",
    "재료가 좀 부족했나? 다음엔 넉넉히!",
    "오늘의 실패가 내일의 이로치다!",
    "슬롯 마스터는 하루아침에 안 돼!",
]


def _mc(text):
    """MC 포맷."""
    return f"🧑‍🔬 <b>문박사</b>: {text}"


async def slot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    buttons = [[InlineKeyboardButton("🎰 제련 시작!", callback_data=f"mc_{uid}")]]
    await update.message.reply_text(
        "🔥 <b>이로치 제련소</b>\n"
        "━━━━━━━━━━━━━━━\n"
        "대상: 🔥 리자몽\n"
        "재료: 🔥리자몽 x3 + 500BP\n\n"
        f"{_mc('어서오게! 오늘도 도전하는 건가?')}",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
    )


async def slot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    if not query.data.startswith("mc_"):
        return
    await query.answer("🎰 시작!")

    # 결과 미리 결정
    roll = random.random()
    if roll < 0.015:
        result_type = "jackpot"
        sym_idx = random.randrange(len(SYMBOLS))
        final = [CROWN, CROWN, CROWN]
        final_names = ["👑", "👑", "👑"]
    elif roll < 0.065:
        result_type = "shiny"
        sym_idx = random.randrange(len(SYMBOLS))
        final = [SYMBOLS[sym_idx]] * 3
        final_names = [SYMBOL_NAMES[sym_idx]] * 3
    elif roll < 0.30:
        result_type = "near"
        sym_idx = random.randrange(len(SYMBOLS))
        other_idx = random.choice([i for i in range(len(SYMBOLS)) if i != sym_idx])
        final = [SYMBOLS[sym_idx], SYMBOLS[sym_idx], SYMBOLS[other_idx]]
        final_names = [SYMBOL_NAMES[sym_idx], SYMBOL_NAMES[sym_idx], SYMBOL_NAMES[other_idx]]
        # 셔플 (마지막이 다른 게 더 극적)
        # 일부러 셔플 안 함 — 앞 2개 일치 + 마지막 다름이 가장 극적
    else:
        result_type = "fail"
        idxs = random.sample(range(len(SYMBOLS)), 3)
        final = [SYMBOLS[i] for i in idxs]
        final_names = [SYMBOL_NAMES[i] for i in idxs]

    Q = "❓"
    SP = "  "  # 여백으로 이모지 강조
    SLOT = lambda a, b, c: f"[ {SP}{a}{SP} | {SP}{b}{SP} | {SP}{c}{SP} ]"
    retry_btn = [[InlineKeyboardButton("🎰 다시 도전!", callback_data=f"mc_{uid}")]]

    # 스피닝 이펙트 프레임 (커스텀이모지)
    SPIN_FRAMES = [BOLT, STAR, CRYSTAL, BOLT, STAR]
    STOP_FLASH = [BOLT, BATTLE, CRYSTAL]

    # ═══ 1단계: 시작 ═══
    await _edit(query, _mc(random.choice(MC_START)), SLOT(Q, Q, Q))
    await asyncio.sleep(1.5)

    # ═══ 2단계: 첫 번째 멈춤 ═══
    flash = random.choice(STOP_FLASH)
    mc_first = random.choice(MC_FIRST_STOP).format(sym=final[0])
    await _edit(query, _mc(mc_first), f"{SLOT(final[0], Q, Q)}\n{flash} 첫 번째!")
    await asyncio.sleep(1.0)

    # 2,3번 릴 계속 스피닝
    for i in range(2):
        r2, r3 = random.choice(SYMBOLS), random.choice(SYMBOLS)
        frame = SPIN_FRAMES[i % len(SPIN_FRAMES)]
        await _edit(query, _mc(f"{frame} ..."), SLOT(final[0], r2, r3))
        await asyncio.sleep(0.4)

    # ═══ 4단계: 두 번째 멈춤 ═══
    is_match_2 = (final[0] == final[1])
    flash = random.choice(STOP_FLASH)
    if is_match_2:
        mc_second = random.choice(MC_SECOND_MATCH).format(sym=final[0])
        await _edit(query, _mc(mc_second), f"{SLOT(final[0], final[1], Q)}\n{flash}{flash} 두 개 일치!!")
    else:
        mc_second = random.choice(MC_SECOND_NOMATCH).format(sym=final[1])
        await _edit(query, _mc(mc_second), f"{SLOT(final[0], final[1], Q)}\n{flash} 두 번째!")
    await asyncio.sleep(1.2)

    # ═══ 5단계: 2개 일치 시 극적 연출 ═══
    if is_match_2:
        await _edit(query, _mc(random.choice(MC_SUSPENSE)), f"{SLOT(final[0], final[1], '❓')}\n{BOLT}{BOLT}{BOLT}{BOLT}{BOLT}{BOLT}")
        await asyncio.sleep(1.5)

        # 떨림 효과 (커스텀이모지 교대)
        await _edit(query, _mc(random.choice(MC_DOTS)), f"{SLOT(final[0], final[1], '🫣')}\n{SKULL}  ❓  {CRYSTAL}  ❓  {SKULL}")
        await asyncio.sleep(1.0)
        await _edit(query, _mc("...!!!"), f"{SLOT(final[0], final[1], '🫣')}\n{CRYSTAL}  ❓  {SKULL}  ❓  {CRYSTAL}")
        await asyncio.sleep(1.0)

    # ═══ 6단계: 3번째 릴 결과 + MC 리액션 ═══
    slot_final = SLOT(final[0], final[1], final[2])

    if result_type == "jackpot":
        # 3번째 멈춤 — MC 연속 리액션 + 플래시
        jp_slot = SLOT(CROWN, CROWN, CROWN)
        await _edit(query, _mc(MC_JACKPOT[0]), f"{jp_slot}\n{BOLT}{BOLT}{BOLT}{BOLT}{BOLT}{BOLT}")
        await asyncio.sleep(0.8)
        await _edit(query, _mc(MC_JACKPOT[1]), f"{jp_slot}\n{FIRE}{CRYSTAL}{FIRE}{CRYSTAL}{FIRE}{CRYSTAL}")
        await asyncio.sleep(0.8)
        await _edit(query, _mc(MC_JACKPOT[2]), f"{jp_slot}\n{CRYSTAL}{FIRE}{CRYSTAL}{FIRE}{CRYSTAL}{FIRE}")
        await asyncio.sleep(0.8)
        await _edit(query, _mc(MC_JACKPOT[3]), f"{jp_slot}\n{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}")
        await asyncio.sleep(2.0)
        # 결과창 전환
        await _edit(query, "", "",
            f"{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}\n\n"
            f"   {CRYSTAL} <b>MEGA JACKPOT</b> {CRYSTAL}\n\n"
            f"{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}\n\n"
            f"{jp_slot}\n\n"
            f"{_mc('이건 역사에 남을 순간이야...')}\n\n"
            f"{CRYSTAL} 메가스톤 획득!\n"
            f"{FIRE} 리자몽 → ✨ <b>메가리자몽</b>",
            retry_btn)

    elif result_type == "shiny":
        # 3번째 멈춤 — 플래시 연출
        await _edit(query, _mc(random.choice(MC_SUCCESS[:3])), f"{slot_final}\n{STAR}{CRYSTAL}{STAR}{CRYSTAL}{STAR}{CRYSTAL}")
        await asyncio.sleep(0.7)
        await _edit(query, _mc(random.choice(MC_SUCCESS[3:])), f"{slot_final}\n{CRYSTAL}{STAR}{CRYSTAL}{STAR}{CRYSTAL}{STAR}")
        await asyncio.sleep(2.0)
        # 결과창 전환
        await _edit(query, "", "",
            f"{STAR}{STAR}{STAR}{STAR}{STAR}{STAR}{STAR}{STAR}{STAR}{STAR}\n\n"
            f"  {CRYSTAL} <b>이로치 제련 성공!</b> {CRYSTAL}\n\n"
            f"{STAR}{STAR}{STAR}{STAR}{STAR}{STAR}{STAR}{STAR}{STAR}{STAR}\n\n"
            f"{slot_final}\n\n"
            f"{_mc(random.choice(MC_SUCCESS[3:]))}\n\n"
            f"🔥 리자몽이 빛나기 시작한다!\n"
            f"✨ <b>이로치 리자몽</b> 획득!",
            retry_btn)

    elif result_type == "near":
        # 3번째 멈춤 — MC 리액션
        await _edit(query, _mc(random.choice(MC_NEAR)), slot_final)
        await asyncio.sleep(1.2)
        await _edit(query, _mc(random.choice(MC_NEAR_2)), slot_final)
        await asyncio.sleep(2.0)
        # 결과창 전환
        teabag = random.choice(MC_NEAR_2)
        await _edit(query, "", "",
            "💨 <b>아깝다!</b>\n\n"
            f"{slot_final}\n\n"
            f"{_mc(teabag)}\n\n"
            "재료 소멸 💨\n"
            "🔧 연성 게이지 +15%\n"
            "▓▓▓▓▓▓▓▓░░ 80%",
            retry_btn)

    else:
        # 3번째 멈춤 — MC 리액션
        await _edit(query, _mc(random.choice(MC_FAIL)), slot_final)
        await asyncio.sleep(1.2)
        await _edit(query, _mc(random.choice(MC_FAIL_TEASE)), slot_final)
        await asyncio.sleep(2.0)
        # 결과창 전환
        teabag = random.choice(MC_FAIL_TEASE)
        await _edit(query, "", "",
            "💨 <b>실패</b>\n\n"
            f"{slot_final}\n\n"
            f"{_mc(teabag)}\n\n"
            "재료 소멸 💨\n"
            "🔧 연성 게이지 +10%\n"
            "▓▓▓▓▓▓░░░░ 60%",
            retry_btn)


async def _edit(query, mc_line, slot_display, bottom="", buttons=None):
    """메시지 업데이트 — 고정 레이아웃, MC 한 줄만."""
    if mc_line and slot_display:
        # 진행 중: 타이틀 + 슬롯 + MC
        text = (
            "🔥 <b>이로치 제련소</b>\n"
            "━━━━━━━━━━━━━━━\n"
            "\n"
            f"{slot_display}\n"
            "\n"
            f"{mc_line}"
        )
    else:
        # 결과창: bottom만
        text = bottom

    markup = InlineKeyboardMarkup(buttons) if buttons else None
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r"^슬롯$"), slot_cmd))
    app.add_handler(CallbackQueryHandler(slot_callback, pattern=r"^mc_"))
    logging.info("MC slot prototype running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
