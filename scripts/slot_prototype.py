"""슬롯 연출 프로토타입 — 텍스트 편집 애니메이션 + 텔레그램 빌트인 🎰 비교."""
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
BOT_TOKEN = os.environ.get("TEST_BOT_TOKEN", "8616848852:AAEEboGyiQ9vUq_8NpzPxlzZEWF0jhNr7iU")
ADMIN_ID = 1832746512

# 슬롯 심볼 — 커스텀이모지
def _ce(eid, fb="?"):
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'

SLOT_POKEMON = {
    "pikachu":    _ce("6143424549074508692", "⚡"),
    "charmander": _ce("6142987961353903580", "🔥"),
    "squirtle":   _ce("6143034596108803222", "💧"),
    "bulbasaur":  _ce("6142953352507432594", "🌿"),
    "eevee":      _ce("6143466343401268847", "🦊"),
    "mew":        _ce("6143355370036274725", "🔮"),
    "jigglypuff": _ce("6143158604699540827", "🎀"),
}
SLOT_JACKPOT = _ce("6143265588039916937", "👑")  # crown

SYMBOLS = list(SLOT_POKEMON.values())
SPINNING = "❓"


async def slot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """DM: 슬롯 → 두 가지 방식 비교."""
    uid = update.effective_user.id
    buttons = [
        [InlineKeyboardButton("🎰 방법1: 텔레그램 빌트인", callback_data=f"slot_builtin_{uid}")],
        [InlineKeyboardButton("✨ 방법2: 텍스트 연출", callback_data=f"slot_text_{uid}")],
        [InlineKeyboardButton("🔥 방법3: 텍스트+빌트인 콤보", callback_data=f"slot_combo_{uid}")],
    ]
    await update.message.reply_text(
        "🎰 <b>이로치 제련소 프로토타입</b>\n\n어떤 연출을 볼래?",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
    )


async def slot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data

    if data.startswith("slot_builtin_"):
        await query.answer()
        await _demo_builtin(context, uid)
    elif data.startswith("slot_text_"):
        await query.answer()
        await _demo_text(context, uid)
    elif data.startswith("slot_combo_"):
        await query.answer()
        await _demo_combo(context, uid)


async def _demo_builtin(context, uid):
    """방법1: 텔레그램 빌트인 🎰."""
    await context.bot.send_message(uid, "🔥 <b>리자몽</b>을(를) 제련합니다...\n재료: 리자몽 x3 + 500BP", parse_mode="HTML")
    await asyncio.sleep(1)

    msg = await context.bot.send_dice(chat_id=uid, emoji="🎰")
    value = msg.dice.value

    await asyncio.sleep(3)  # 애니메이션 대기

    if value == 64:
        result = "🔥🔥🔥 <b>잭팟!!! 메가스톤 획득!!!</b>\n🔥리자몽 → 메가리자몽으로 진화! 🐉"
    elif value in (1, 22, 43):
        result = "✨✨✨ <b>이로치 성공!!!</b>\n🔥리자몽이 빛나기 시작한다!"
    elif value in (16, 32, 48):
        result = "😱 <b>아깝다!!!</b> 2개 일치!\n재료 소멸... 게이지 +15%"
    else:
        result = "💨 <b>실패...</b>\n재료 소멸. 게이지 +10%"

    await context.bot.send_message(uid, result, parse_mode="HTML")


async def _demo_text(context, uid):
    """방법2: 텍스트 편집으로 슬롯 연출."""
    # 결과 미리 결정
    normal_syms = [v for v in SYMBOLS]  # 커스텀이모지 포켓몬들
    roll = random.random()
    if roll < 0.015:
        final = [SLOT_JACKPOT, SLOT_JACKPOT, SLOT_JACKPOT]
        result_type = "jackpot"
    elif roll < 0.065:
        sym = random.choice(normal_syms)
        final = [sym, sym, sym]
        result_type = "shiny"
    elif roll < 0.30:
        sym = random.choice(normal_syms)
        other = random.choice([s for s in normal_syms if s != sym])
        final = [sym, sym, other]
        random.shuffle(final)
        result_type = "near"
    else:
        syms = random.sample(normal_syms, 3)
        result_type = "fail"
        final = syms

    # 랜덤 심볼 스피닝 연출용
    def rand_sym():
        return random.choice(SYMBOLS)

    # === 1단계: 제련로 점화 ===
    msg = await context.bot.send_message(
        uid,
        "🔥 <b>이로치 제련소</b>\n"
        "━━━━━━━━━━━━━━━\n"
        "대상: 🔥 <b>리자몽</b>\n"
        "재료: 🔥리자몽 x3 투입!\n\n"
        "<i>제련로에 불꽃이 타오른다...</i>",
        parse_mode="HTML",
    )
    await asyncio.sleep(1.5)

    # === 2단계: 슬롯 회전 시작 (빠른 스피닝) ===
    for i in range(3):
        await msg.edit_text(
            "🔥 <b>이로치 제련소</b>\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"  [ {rand_sym()} | {rand_sym()} | {rand_sym()} ]\n\n"
            "🔄🔄🔄 <i>회전 중...</i>",
            parse_mode="HTML",
        )
        await asyncio.sleep(0.5)

    # === 3단계: 1번 릴 멈춤 ===
    for i in range(2):
        await msg.edit_text(
            "🔥 <b>이로치 제련소</b>\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"  [ {final[0]} | {rand_sym()} | {rand_sym()} ]\n\n"
            "🔒🔄🔄 <i>첫 번째 멈춤!</i>",
            parse_mode="HTML",
        )
        await asyncio.sleep(0.5)

    # === 4단계: 2번 릴 멈춤 ===
    # 2개 일치면 긴장감 연출
    if final[0] == final[1]:
        suspense = "😳 <i>두 개 일치...! 마지막은...?!</i>"
    else:
        suspense = "🔒🔒🔄 <i>마지막 릴 회전 중...</i>"

    for i in range(2):
        await msg.edit_text(
            "🔥 <b>이로치 제련소</b>\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"  [ {final[0]} | {final[1]} | {rand_sym()} ]\n\n"
            f"{suspense}",
            parse_mode="HTML",
        )
        await asyncio.sleep(0.5)

    # === 5단계: 최종 릴 멈추기 전 극적 멈춤 ===
    if final[0] == final[1]:
        await msg.edit_text(
            "🔥 <b>이로치 제련소</b>\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"  [ {final[0]} | {final[1]} | ❓ ]\n\n"
            "🫣🫣🫣 <b>. . .</b>",
            parse_mode="HTML",
        )
        await asyncio.sleep(1.5)
    else:
        await asyncio.sleep(0.8)

    # === 6단계: 결과! ===
    if result_type == "jackpot":
        # 잭팟 연출 (여러 단계)
        jp = SLOT_JACKPOT
        await msg.edit_text(
            "🔥 <b>이로치 제련소</b>\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"  [ {jp} | {jp} | {jp} ]\n\n"
            "⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡",
            parse_mode="HTML",
        )
        await asyncio.sleep(0.5)
        await msg.edit_text(
            "🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥\n"
            "🔥\n"
            f"🔥  <b>★ MEGA JACKPOT ★</b>\n"
            "🔥\n"
            "🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥\n\n"
            f"  [ {jp} | {jp} | {jp} ]\n\n"
            "💎 <b>메가스톤 획득!!!</b>\n"
            "🔥 리자몽 → ✨ <b>메가리자몽</b> 진화!\n\n"
            "🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊",
            parse_mode="HTML",
        )
    elif result_type == "shiny":
        await msg.edit_text(
            "✨✨✨✨✨✨✨✨✨✨\n"
            "✨                                    ✨\n"
            "✨  <b>★ SUCCESS ★</b>          ✨\n"
            "✨                                    ✨\n"
            "✨✨✨✨✨✨✨✨✨✨\n\n"
            f"  [ {final[0]} | {final[1]} | {final[2]} ]\n\n"
            "🔥 리자몽이 눈부시게 빛난다!\n"
            "✨ <b>이로치 리자몽</b> 획득!",
            parse_mode="HTML",
        )
    elif result_type == "near":
        await msg.edit_text(
            "🔥 <b>이로치 제련소</b>\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"  [ {final[0]} | {final[1]} | {final[2]} ]\n\n"
            "😱😱😱 <b>아깝다!!!</b>\n\n"
            "빛이 거의 나타났다가... 사라졌다\n"
            "재료 소멸 💨\n\n"
            "🔧 연성 게이지 +15%\n"
            "▓▓▓▓▓▓▓▓░░ 80%\n\n"
            "<i>한 번만 더 하면...</i> 🤔",
            parse_mode="HTML",
        )
    else:
        await msg.edit_text(
            "🔥 <b>이로치 제련소</b>\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"  [ {final[0]} | {final[1]} | {final[2]} ]\n\n"
            "💨 <b>실패...</b>\n\n"
            "제련로의 불꽃이 꺼졌다\n"
            "재료 소멸 💨\n\n"
            "🔧 연성 게이지 +10%\n"
            "▓▓▓▓▓▓░░░░ 60%",
            parse_mode="HTML",
        )


async def _demo_combo(context, uid):
    """방법3: 텍스트 연출 + 빌트인 🎰 콤보."""
    # 준비 연출
    msg = await context.bot.send_message(
        uid,
        "🔥 <b>이로치 제련소</b>\n"
        "━━━━━━━━━━━━━━━\n"
        "대상: 🔥 <b>리자몽</b>\n"
        "재료: 🔥리자몽 x3 투입!\n"
        "비용: 💰 500 BP\n\n"
        "<i>제련로에 불꽃이 타오른다...</i> 🔥🔥🔥",
        parse_mode="HTML",
    )
    await asyncio.sleep(2)

    # 빌트인 슬롯
    dice_msg = await context.bot.send_dice(chat_id=uid, emoji="🎰")
    value = dice_msg.dice.value
    await asyncio.sleep(3)

    # 결과 판정
    if value == 64:
        lines = [
            "🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥",
            "",
            "💎 <b>MEGA JACKPOT!!!</b> 💎",
            "",
            "메가스톤이 제련로에서 나타났다!",
            "🔥 리자몽 → ✨ <b>메가리자몽</b> 진화!",
            "",
            "🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥",
        ]
    elif value in (1, 22, 43):
        lines = [
            "✨✨✨✨✨✨✨✨✨✨",
            "",
            "⭐ <b>이로치 제련 성공!!!</b> ⭐",
            "",
            "🔥 리자몽이 눈부시게 빛난다!",
            "✨ <b>이로치 리자몽</b> 획득!",
            "",
            "✨✨✨✨✨✨✨✨✨✨",
        ]
    elif value in (16, 32, 48):
        lines = [
            "😱😱😱",
            "",
            "빛이 거의 나타났다가... 사라졌다",
            "",
            f"<b>아깝다!!!</b>",
            "재료 소멸... 💨",
            "",
            "🔧 연성 게이지: ████████░░ 80% (+15%)",
            "",
            "<i>다음엔 반드시...</i>",
        ]
    else:
        lines = [
            "💨",
            "",
            "제련로의 불꽃이 꺼졌다...",
            "",
            "<b>실패</b>",
            "재료 소멸 💨",
            "",
            "🔧 연성 게이지: ██████░░░░ 60% (+10%)",
        ]

    await context.bot.send_message(uid, "\n".join(lines), parse_mode="HTML")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r"^슬롯$"), slot_cmd))
    app.add_handler(CallbackQueryHandler(slot_callback, pattern=r"^slot_"))
    logging.info("Slot prototype running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
