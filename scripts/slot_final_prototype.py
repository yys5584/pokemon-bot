"""이로치 제련소 최종 프로토타입.

리서치 기반 최적화:
- MUD 텍스트 연출 + 가챠 5단계 감정 곡선
- 감속 패턴 (빠름→느림)
- 결과 등급별 애니메이션 길이 차등
- 니어미스 오버슈트 기법
- 한국어 의성어 이펙트
- 고정 레이아웃 (화면 떨림 방지)
- 커스텀이모지 포켓몬 + 이펙트
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
# 커스텀이모지 정의
# ═══════════════════════════════════════════

def _ce(eid, fb="?"):
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'

# 포켓몬 릴 심볼
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

# 이펙트 이모지
CROWN   = _ce("6143265588039916937", "👑")
BOLT    = _ce("6143251942928818741", "⚡")
SKULL   = _ce("6143450305993382989", "💀")
CRYSTAL = _ce("6143120589944004477", "💎")
BATTLE  = _ce("6143344370625026850", "⚔")
STAR    = _ce("6143322638090510138", "⭐")
FIRE    = _ce("6142975986985081276", "🔥")
CHECK   = _ce("6143254176311811828", "✅")
GOTCHA  = _ce("6143385318843227267", "🎯")
COIN    = _ce("6143083713354801765", "💰")

SYMBOLS = list(POKE.values())
SYMBOL_NAMES = list(POKE.keys())

# ═══════════════════════════════════════════
# 문박사 MC 대사 (총 200+)
# ═══════════════════════════════════════════

# ── 1단계: 투입 ──
MC_COMMIT = [
    "자, 재료 투입 완료! 가보자고!",
    "허허, 오늘의 도전이 시작됐군!",
    "좋아, 제련로에 불꽃이 타오른다!",
    "음... 오늘은 느낌이 좋은데?",
    "오? 눈빛이 다르군. 해보자!",
    "GMG? 가면 간다!",
    "중꺽마 정신으로!",
    "허허, 과학의 힘을 믿어보지!",
    "자 용기 있는 트레이너! 시작이다!",
    "HMH!! 하면 해!",
    "오늘은 뭔가 될 것 같은 느낌적 느낌...",
    "자, 운명의 제련을 시작하지!",
]

# ── 2단계: 첫 번째 릴 ──
MC_FIRST = [
    "오, {sym} 나왔어!",
    "첫 번째는 {sym}!",
    "음음, {sym}이로군!",
    "오호~ {sym}! 시작이 좋은데?",
    "{sym}! 하나 확인!",
    "좋아 {sym}! 다음은...?",
]

# ── 3단계: 두 번째 릴 (일치) ──
MC_MATCH = [
    "헉?! 두 개 일치!!!",
    "잠깐... 두 개 같은데?!",
    "이왜진?! 두 개 맞았어!!!",
    "난리자베스!! 두 개 일치!!!",
    "홀리몰리?! 이거 되는 건가?!",
    "심장 떨려... 두 개 같다!!!",
    "ㅁ...뭐?! 두 개?!?!",
    "아 잠깐 잠깐 잠깐!!!",
    "이거 실화냐?! 두 개 일치!!!",
    "오오오?! {sym}{sym} 연속이야!!!",
]

# ── 3단계: 두 번째 릴 (불일치) ──
MC_NOMATCH = [
    "음... 다르군~",
    "두 번째는 {sym}! 마지막 가보자!",
    "다르긴 한데... 마지막이 있으니까!",
    "흠, {sym}이로군. 마지막 승부!",
    "아직 끝나지 않았어!",
]

# ── 4단계: 서스펜스 (2개 일치 시) ──
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

# ── 5단계: 잭팟 리액션 ──
MC_JACKPOT = [
    "잠깐... 이거...",
    "이게 진짜...?",
    "메...메가스톤?!?!?!",
    "ㄹㅇ 미쳤다!!!!",
]

# ── 5단계: 성공 즉각 반응 ──
MC_SUCCESS_1 = [
    "!!!",
    "나왔다!!!",
    "오오오!!!",
    "빠밤!!!",
]

# ── 5단계: 성공 축하 ──
MC_SUCCESS_2 = [
    "허허! 축하하네! 이로치 확정이야!",
    "개꿀!! 이로치 떴다!!!",
    "난리자베스!! 성공이야!!",
    "이건 학술적으로도 레전드야...",
    "느좋!! 최고야 축하한다!",
    "떡상!! 이로치 탄생이다!",
    "GOAT!! 오늘의 주인공이로군!",
    "킹왕짱!! 대단하다 진짜!",
    "역시 될 놈은 된다!!",
    "내 연구 인생에서 이런 건 처음이야!",
    "축하한다! 오늘 로또도 사봐!",
]

# ── 5단계: 니어미스 즉각 ──
MC_NEAR_1 = [
    "아이고...",
    "에이~ 아깝다 ㅋㅋ",
    "킹받네... 거의 다 왔는데!",
    "어 왜 거기서 멈춰...!",
    "억까당했다... 이건 너무한데",
    "할많하않...",
    "니어미스자베스...",
    "아 이거 살짝 빡친다 나도",
    "헐... 하나만 맞았으면!!",
    "이게 안 된다고?! 말이 돼?!",
    "아까워서 내가 다 속상하다",
    "99%에서 멈추는 느낌이군...",
]

# ── 5단계: 니어미스 위로 (결과창) ──
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

# ── 5단계: 실패 즉각 ──
MC_FAIL_1 = [
    "허허...",
    "음... 이번엔 인연이 아니었나보군",
    "산으로 갔다...",
    "하... 그냥 웃기다 ㅋㅋ",
    "스불재... 인가?",
    "괜찮아 딩딩딩~",
    "음... 쿨하게 넘어가자",
    "이건 뭐 어쩔 수 없지",
    "포켓몬들이 안 맞는 날이군",
    "와르르... 무너졌다",
]

# ── 5단계: 실패 티배깅 (결과창) ──
MC_FAIL_2 = [
    "원래 한 번에 되면 재미없지 않나?",
    "포기는 금물! 게이지 쌓이고 있으니까!",
    "이런 날도 있는 거지 뭐~",
    "다음엔 분명 될 거야! ...아마도!",
    "라면 먹으러... 아니 한 판 더 가자!",
    "GMG? 갈 거면 가는 거야!",
    "존버하면 된다! 존버 실패는 없어!",
    "테무인간 아니잖아? 진짜를 노려봐!",
    "한 판만 더... 한 판만...",
    "알잘딱깔센으로 한 번 더!",
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
    "다음 판은 좀 다를 거야!",
    "여기서 멈추면 진짜 아까운 건데...?",
    "어차피 할 거잖아? ㅋㅋ 솔직해져봐",
    "다음에 되면 이 실패가 빛나는 거야!",
    "참을 인 세 번이면 이로치가 온다!",
    "연성 게이지가 널 기다리고 있다고!",
    "이건 실패가 아니야. 투자야!",
    "감이 안 좋은 게 아니라 타이밍이야!",
    "오늘의 실패가 내일의 이로치다!",
    "슬롯 마스터는 하루아침에 안 돼!",
    "흐음... 다음엔 넉넉히 재료 넣어봐!",
]


# ═══════════════════════════════════════════
# MC 포맷 + 유틸
# ═══════════════════════════════════════════

def _mc(text):
    return f"🧑‍🔬 <b>문박사</b>: {text}"

# 고정 8줄 레이아웃 (화면 떨림 방지)
# Line 1: 타이틀
# Line 2: 구분선
# Line 3: (빈줄)
# Line 4: 슬롯 or 에너지바
# Line 5: 이펙트 라인
# Line 6: (빈줄)
# Line 7: MC 멘트
# Line 8: 패딩

def _frame(slot_line, effect_line, mc_line, title="🔥 <b>이로치 제련소</b>"):
    """고정 8줄 프레임 생성."""
    return (
        f"{title}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"\n"
        f"{slot_line}\n"
        f"{effect_line}\n"
        f"\n"
        f"{mc_line}\n"
        f"‎"  # 보이지 않는 문자 (줄 수 고정)
    )

def _result_frame(content):
    """결과 전용 프레임 (레이아웃 다름)."""
    return content

# 슬롯 표시 (여백 넓힘)
SP = "  "
def _slot(a, b, c):
    return f"[  {a}  ┃  {b}  ┃  {c}  ]"

# 에너지바 (유니코드 블록)
def _energy_bar(pct, style="normal"):
    total = 10
    filled = round(pct / 100 * total)
    if style == "gold":
        return f"{'▰' * filled}{'▱' * (total - filled)}  ✦"
    elif style == "rainbow":
        return f"{'█' * filled}{'░' * (total - filled)}  ★"
    return f"{'▓' * filled}{'░' * (total - filled)}"


# ═══════════════════════════════════════════
# 메인 핸들러
# ═══════════════════════════════════════════

async def slot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    buttons = [[InlineKeyboardButton("🎰 제련 시작!", callback_data=f"fs_{uid}")]]
    text = _frame(
        _slot("❓", "❓", "❓"),
        _energy_bar(0),
        _mc("어서오게! 오늘도 도전하는 건가?"),
    )
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")


async def slot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    if not query.data.startswith("fs_"):
        return

    target_uid = int(query.data.split("_")[1])
    if uid != target_uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    await query.answer("🎰 시작!")

    # ── 결과 결정 ──
    roll = random.random()
    if roll < 0.015:
        result_type = "jackpot"
        final = [CROWN, CROWN, CROWN]
    elif roll < 0.065:
        result_type = "shiny"
        sym_idx = random.randrange(len(SYMBOLS))
        final = [SYMBOLS[sym_idx]] * 3
    elif roll < 0.30:
        result_type = "near"
        sym_idx = random.randrange(len(SYMBOLS))
        other_idx = random.choice([i for i in range(len(SYMBOLS)) if i != sym_idx])
        final = [SYMBOLS[sym_idx], SYMBOLS[sym_idx], SYMBOLS[other_idx]]
    else:
        result_type = "fail"
        idxs = random.sample(range(len(SYMBOLS)), 3)
        final = [SYMBOLS[i] for i in idxs]

    retry_btn = [[InlineKeyboardButton("🎰 다시 도전!", callback_data=f"fs_{uid}")]]
    is_match_2 = (final[0] == final[1])

    # ═══════════════════════════════════════
    # 등급별 애니메이션 분기
    # 실패: 빠르게 (~4초, 5프레임)
    # 니어미스: 중간 (~7초, 8프레임)
    # 성공: 길게 (~9초, 9프레임)
    # 잭팟: 최대 (~12초, 12프레임)
    # ═══════════════════════════════════════

    if result_type == "fail":
        await _animate_fail(query, uid, final, retry_btn)
    elif result_type == "near":
        await _animate_near(query, uid, final, retry_btn)
    elif result_type == "shiny":
        await _animate_success(query, uid, final, retry_btn)
    else:
        await _animate_jackpot(query, uid, final, retry_btn)


# ═══════════════════════════════════════════
# 실패 애니메이션 (~4초, 빠르게)
# ═══════════════════════════════════════════

async def _animate_fail(query, uid, final, retry_btn):
    # F1: 투입 (0.8s)
    await _safe_edit(query, _frame(
        _slot("❓", "❓", "❓"),
        _energy_bar(20),
        _mc(random.choice(MC_COMMIT)),
    ))
    await asyncio.sleep(0.8)

    # F2: 첫 번째 릴 (0.6s)
    await _safe_edit(query, _frame(
        _slot(final[0], "❓", "❓"),
        _energy_bar(40),
        _mc(random.choice(MC_FIRST).format(sym=final[0])),
    ))
    await asyncio.sleep(0.6)

    # F3: 두 번째 릴 (0.6s)
    await _safe_edit(query, _frame(
        _slot(final[0], final[1], "❓"),
        _energy_bar(60),
        _mc(random.choice(MC_NOMATCH).format(sym=final[1])),
    ))
    await asyncio.sleep(0.6)

    # F4: 세 번째 릴 + MC 리액션 (1.2s)
    slot_final = _slot(final[0], final[1], final[2])
    await _safe_edit(query, _frame(
        slot_final,
        _energy_bar(30),
        _mc(random.choice(MC_FAIL_1)),
    ))
    await asyncio.sleep(1.5)

    # F5: 결과창 전환
    await _safe_edit(query, _result_frame(
        f"💨 <b>실패</b>\n\n"
        f"{slot_final}\n\n"
        f"{_mc(random.choice(MC_FAIL_2))}\n\n"
        f"재료 소멸 💨\n"
        f"🔧 연성 게이지 +10%\n"
        f"▓▓▓▓▓▓░░░░ 60%"
    ), retry_btn)


# ═══════════════════════════════════════════
# 니어미스 애니메이션 (~7초)
# ═══════════════════════════════════════════

async def _animate_near(query, uid, final, retry_btn):
    # F1: 투입 (1.0s)
    await _safe_edit(query, _frame(
        _slot("❓", "❓", "❓"),
        _energy_bar(15),
        _mc(random.choice(MC_COMMIT)),
    ))
    await asyncio.sleep(1.0)

    # F2: 첫 번째 릴 (0.8s)
    await _safe_edit(query, _frame(
        _slot(final[0], "❓", "❓"),
        _energy_bar(35),
        _mc(random.choice(MC_FIRST).format(sym=final[0])),
    ))
    await asyncio.sleep(0.8)

    # F3: 두 번째 릴 — 일치! (1.0s)
    await _safe_edit(query, _frame(
        _slot(final[0], final[1], "❓"),
        _energy_bar(70, "gold"),
        _mc(random.choice(MC_MATCH).format(sym=final[0])),
    ))
    await asyncio.sleep(1.0)

    # F4: 서스펜스 (1.2s)
    await _safe_edit(query, _frame(
        _slot(final[0], final[1], "❓"),
        f"{BOLT}{BOLT}{BOLT}{BOLT}{BOLT}{BOLT}{BOLT}{BOLT}",
        _mc(random.choice(MC_SUSPENSE)),
    ))
    await asyncio.sleep(1.2)

    # F5: 극적 멈춤 — 두근두근 (1.5s)
    await _safe_edit(query, _frame(
        _slot(final[0], final[1], "🫣"),
        f"{CRYSTAL}  ❓  {SKULL}  ❓  {CRYSTAL}",
        _mc(random.choice(MC_SUSPENSE)),
    ))
    await asyncio.sleep(1.5)

    # F6: 니어미스 오버슈트! — 잠깐 3개 일치 보여주고...
    await _safe_edit(query, _frame(
        _slot(final[0], final[1], final[0]),  # 잠깐 일치!
        f"{STAR}{STAR}{STAR}{STAR}{STAR}{STAR}{STAR}{STAR}",
        _mc("!!!"),
    ))
    await asyncio.sleep(0.3)

    # F7: ...빗나감 (실제 결과)
    slot_final = _slot(final[0], final[1], final[2])
    await _safe_edit(query, _frame(
        slot_final,
        _energy_bar(85),
        _mc(random.choice(MC_NEAR_1)),
    ))
    await asyncio.sleep(2.0)

    # F8: 결과창
    await _safe_edit(query, _result_frame(
        f"😱 <b>아깝다!</b>\n\n"
        f"{slot_final}\n\n"
        f"{_mc(random.choice(MC_NEAR_2))}\n\n"
        f"재료 소멸 💨\n"
        f"🔧 연성 게이지 +15%\n"
        f"▓▓▓▓▓▓▓▓░░ 80%"
    ), retry_btn)


# ═══════════════════════════════════════════
# 성공 애니메이션 (~9초)
# ═══════════════════════════════════════════

async def _animate_success(query, uid, final, retry_btn):
    # F1: 투입 (1.0s)
    await _safe_edit(query, _frame(
        _slot("❓", "❓", "❓"),
        _energy_bar(10),
        _mc(random.choice(MC_COMMIT)),
    ))
    await asyncio.sleep(1.0)

    # F2: 첫 번째 릴 (0.8s)
    await _safe_edit(query, _frame(
        _slot(final[0], "❓", "❓"),
        _energy_bar(30),
        _mc(random.choice(MC_FIRST).format(sym=final[0])),
    ))
    await asyncio.sleep(0.8)

    # F3: 두 번째 릴 — 일치! (1.0s)
    await _safe_edit(query, _frame(
        _slot(final[0], final[1], "❓"),
        _energy_bar(65, "gold"),
        _mc(random.choice(MC_MATCH).format(sym=final[0])),
    ))
    await asyncio.sleep(1.0)

    # F4: 서스펜스 (1.2s)
    await _safe_edit(query, _frame(
        _slot(final[0], final[1], "❓"),
        f"{BOLT}{BOLT}{BOLT}{BOLT}{BOLT}{BOLT}{BOLT}{BOLT}",
        _mc(random.choice(MC_SUSPENSE)),
    ))
    await asyncio.sleep(1.2)

    # F5: 극적 멈춤 (1.5s)
    await _safe_edit(query, _frame(
        _slot(final[0], final[1], "🫣"),
        f"{CRYSTAL}  ❓  {CRYSTAL}  ❓  {CRYSTAL}",
        _mc("두근두근..."),
    ))
    await asyncio.sleep(1.5)

    # F6: 시그널! — 에너지바가 골드로 가득 참 (0.5s)
    await _safe_edit(query, _frame(
        _slot(final[0], final[1], "🫣"),
        _energy_bar(100, "gold"),
        _mc("...!!!"),
    ))
    await asyncio.sleep(0.5)

    # F7: 리빌! 3개 일치! (0.8s)
    slot_final = _slot(final[0], final[1], final[2])
    await _safe_edit(query, _frame(
        slot_final,
        f"{STAR}{CRYSTAL}{STAR}{CRYSTAL}{STAR}{CRYSTAL}{STAR}{CRYSTAL}",
        _mc(random.choice(MC_SUCCESS_1)),
    ))
    await asyncio.sleep(0.8)

    # F8: 축하 MC (2.0s)
    await _safe_edit(query, _frame(
        slot_final,
        f"{CRYSTAL}{STAR}{CRYSTAL}{STAR}{CRYSTAL}{STAR}{CRYSTAL}{STAR}",
        _mc(random.choice(MC_SUCCESS_2)),
    ))
    await asyncio.sleep(2.0)

    # F9: 결과창
    await _safe_edit(query, _result_frame(
        f"{STAR}{STAR}{STAR}{STAR}{STAR}{STAR}{STAR}{STAR}{STAR}{STAR}\n\n"
        f"  {CRYSTAL} <b>이로치 제련 성공!</b> {CRYSTAL}\n\n"
        f"{STAR}{STAR}{STAR}{STAR}{STAR}{STAR}{STAR}{STAR}{STAR}{STAR}\n\n"
        f"{slot_final}\n\n"
        f"{_mc(random.choice(MC_SUCCESS_2))}\n\n"
        f"🔥 리자몽이 빛나기 시작한다!\n"
        f"✨ <b>이로치 리자몽</b> 획득!"
    ), retry_btn)


# ═══════════════════════════════════════════
# 잭팟 애니메이션 (~12초, 최대 드라마)
# ═══════════════════════════════════════════

async def _animate_jackpot(query, uid, final, retry_btn):
    # F1: 투입 (1.0s)
    await _safe_edit(query, _frame(
        _slot("❓", "❓", "❓"),
        _energy_bar(10),
        _mc(random.choice(MC_COMMIT)),
    ))
    await asyncio.sleep(1.0)

    # F2: 첫 번째 릴 (0.8s) — 왕관!
    await _safe_edit(query, _frame(
        _slot(CROWN, "❓", "❓"),
        _energy_bar(30),
        _mc("오...? 이건...?!"),
    ))
    await asyncio.sleep(0.8)

    # F3: 두 번째 릴 — 왕관 2개! (1.0s)
    await _safe_edit(query, _frame(
        _slot(CROWN, CROWN, "❓"),
        _energy_bar(70, "gold"),
        _mc("잠깐?! 두 개?!?!"),
    ))
    await asyncio.sleep(1.0)

    # F4: 서스펜스 1 (1.2s)
    await _safe_edit(query, _frame(
        _slot(CROWN, CROWN, "❓"),
        f"{BOLT}{BOLT}{BOLT}{BOLT}{BOLT}{BOLT}{BOLT}{BOLT}",
        _mc("이거... 설마...?!"),
    ))
    await asyncio.sleep(1.2)

    # F5: 서스펜스 2 — 화면 어두워지는 느낌 (1.5s)
    await _safe_edit(query, _frame(
        _slot(CROWN, CROWN, "🫣"),
        f"{SKULL}  ❓  {CRYSTAL}  ❓  {SKULL}",
        _mc("..."),
        title="◈ ◈ ◈ ◈ ◈ ◈ ◈ ◈ ◈ ◈",
    ))
    await asyncio.sleep(1.5)

    # F6: 서스펜스 3 — 교대 (1.0s)
    await _safe_edit(query, _frame(
        _slot(CROWN, CROWN, "🫣"),
        f"{CRYSTAL}  ❓  {SKULL}  ❓  {CRYSTAL}",
        _mc("......"),
        title="✦ ✦ ✦ ✦ ✦ ✦ ✦ ✦ ✦ ✦",
    ))
    await asyncio.sleep(1.0)

    # F7: 시그널! 에너지바 레인보우! (0.5s)
    await _safe_edit(query, _frame(
        _slot(CROWN, CROWN, "🫣"),
        _energy_bar(100, "rainbow"),
        _mc("...!!!!!!"),
        title="★ ✦ ★ ✦ ★ ✦ ★ ✦ ★ ✦",
    ))
    await asyncio.sleep(0.5)

    # F8: 리빌! (0.8s)
    jp_slot = _slot(CROWN, CROWN, CROWN)
    await _safe_edit(query, _frame(
        jp_slot,
        f"{FIRE}{CRYSTAL}{FIRE}{CRYSTAL}{FIRE}{CRYSTAL}{FIRE}{CRYSTAL}",
        _mc(MC_JACKPOT[0]),
    ))
    await asyncio.sleep(0.8)

    # F9: 리액션 2 (0.8s)
    await _safe_edit(query, _frame(
        jp_slot,
        f"{CRYSTAL}{FIRE}{CRYSTAL}{FIRE}{CRYSTAL}{FIRE}{CRYSTAL}{FIRE}",
        _mc(MC_JACKPOT[1]),
    ))
    await asyncio.sleep(0.8)

    # F10: 리액션 3 (0.8s)
    await _safe_edit(query, _frame(
        jp_slot,
        f"{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}",
        _mc(MC_JACKPOT[2]),
    ))
    await asyncio.sleep(0.8)

    # F11: 리액션 4 (2.0s)
    await _safe_edit(query, _frame(
        jp_slot,
        f"{STAR}{FIRE}{CRYSTAL}{STAR}{FIRE}{CRYSTAL}{STAR}{FIRE}",
        _mc(MC_JACKPOT[3]),
    ))
    await asyncio.sleep(2.0)

    # F12: 결과창
    await _safe_edit(query, _result_frame(
        f"{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}\n\n"
        f"   {CRYSTAL} <b>MEGA JACKPOT</b> {CRYSTAL}\n\n"
        f"{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}{FIRE}\n\n"
        f"{jp_slot}\n\n"
        f"{_mc('이건 역사에 남을 순간이야...')}\n\n"
        f"{CRYSTAL} 메가스톤 획득!\n"
        f"{FIRE} 리자몽 → ✨ <b>메가리자몽</b>"
    ), retry_btn)


# ═══════════════════════════════════════════
# 유틸
# ═══════════════════════════════════════════

async def _safe_edit(query, text, buttons=None):
    """안전한 메시지 편집."""
    markup = InlineKeyboardMarkup(buttons) if buttons else None
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        if "not modified" not in str(e).lower():
            logging.warning(f"edit failed: {e}")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r"^슬롯$"), slot_cmd))
    app.add_handler(CallbackQueryHandler(slot_callback, pattern=r"^fs_"))
    logging.info("Final slot prototype running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
