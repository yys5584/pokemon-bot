"""주간보스 크래시 게임 프로토타입 — DM에서 테스트용."""
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, ContextTypes, MessageHandler, CallbackQueryHandler,
    filters,
)
from dotenv import load_dotenv
import os

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = 1832746512

# 보스 상태 (in-memory)
_boss = {
    "name": "레쿠쟈",
    "types": ["dragon", "flying"],
    "max_hp": 500_000,
    "hp": 500_000,
}

# 유저 세션
_sessions = {}  # user_id -> {pokemon_idx, total_damage, pokemon: [...], dead: [...]}

TEAM = [
    {"name": "피카츄", "emoji": "⚡", "base_dmg": 800},
    {"name": "리자몽", "emoji": "🔥", "base_dmg": 1200},
    {"name": "갸라도스", "emoji": "💧", "base_dmg": 1000},
    {"name": "뮤츠", "emoji": "🔮", "base_dmg": 1500},
    {"name": "라프라스", "emoji": "❄️", "base_dmg": 900},
    {"name": "망나뇽", "emoji": "🐉", "base_dmg": 1100},
]

DART_RESULT = {
    1: ("💀 대실패!", 0, True),      # miss + 영혼
    2: ("😤 빗나감...", 0.3, False),
    3: ("🤏 약타", 0.8, False),
    4: ("⚔️ 명중!", 1.5, False),
    5: ("💥 강타!", 2.0, False),
    6: ("🔥🔥 크리티컬!", 3.0, False),
}


def _hp_bar(hp, max_hp, length=10):
    pct = max(0, hp / max_hp) if max_hp > 0 else 0
    filled = round(pct * length)
    return "█" * filled + "░" * (length - filled)


async def boss_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """DM: 보스 → 보스 정보 + 공격 버튼."""
    uid = update.effective_user.id
    pct = _boss["hp"] / _boss["max_hp"] * 100

    text = (
        f"🐉 <b>주간보스: {_boss['name']}</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"❤️ HP: {_boss['hp']:,} / {_boss['max_hp']:,} ({pct:.1f}%)\n"
        f"{_hp_bar(_boss['hp'], _boss['max_hp'])}\n\n"
        f"💡 약점: 얼음, 드래곤, 바위, 페어리\n\n"
        f"포켓몬 6마리로 보스를 공격!\n"
        f"🎯 다트로 공격 판정 → 대성공/성공/실패\n"
        f"💀 대실패 시 포켓몬 영혼...\n"
        f"매턴 GO/STOP 선택!"
    )
    buttons = [[InlineKeyboardButton("⚔️ 공격 시작!", callback_data=f"bp_start_{uid}")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")


async def boss_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data

    if data.startswith("bp_start_"):
        # 세션 초기화
        _sessions[uid] = {
            "idx": 0,
            "total_dmg": 0,
            "team": [dict(p) for p in TEAM],
            "dead": [],
        }
        await query.answer("⚔️ 보스전 시작!")
        await _show_turn(query, context, uid)

    elif data.startswith("bp_go_"):
        await query.answer()
        await _do_attack(query, context, uid)

    elif data.startswith("bp_stop_"):
        await query.answer("💰 STOP!")
        await _finish(query, context, uid)


async def _show_turn(query, context, uid):
    """현재 포켓몬 턴 표시."""
    s = _sessions.get(uid)
    if not s or s["idx"] >= len(s["team"]):
        await _finish(query, context, uid)
        return

    poke = s["team"][s["idx"]]
    remaining = len(s["team"]) - s["idx"]
    dead_names = ", ".join(f"💀{d}" for d in s["dead"]) if s["dead"] else "없음"

    text = (
        f"🐉 <b>vs {_boss['name']}</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"❤️ 보스 HP: {_boss['hp']:,} / {_boss['max_hp']:,}\n"
        f"{_hp_bar(_boss['hp'], _boss['max_hp'])}\n\n"
        f"🎯 현재: {poke['emoji']} <b>{poke['name']}</b> (기본딜 {poke['base_dmg']})\n"
        f"💥 누적 딜: <b>{s['total_dmg']:,}</b>\n"
        f"🧑‍🤝‍🧑 남은 포켓몬: {remaining}마리\n"
        f"💀 영혼: {dead_names}\n\n"
        f"🎯 다트를 던져 공격!\n"
        f"GO = 공격 / STOP = 딜 확정"
    )
    buttons = [
        [
            InlineKeyboardButton(f"🔥 GO! ({poke['emoji']}{poke['name']})", callback_data=f"bp_go_{uid}"),
            InlineKeyboardButton("💰 STOP", callback_data=f"bp_stop_{uid}"),
        ]
    ]
    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    except Exception:
        await context.bot.send_message(uid, text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")


async def _do_attack(query, context, uid):
    """다트 던지기 → 결과."""
    s = _sessions.get(uid)
    if not s:
        return

    poke = s["team"][s["idx"]]

    # 다트 애니메이션 전 연출
    await context.bot.send_message(
        uid,
        f"{poke['emoji']} <b>{poke['name']}</b>이(가) 공격을 준비한다...!",
        parse_mode="HTML",
    )

    # 다트 전송
    msg = await context.bot.send_dice(chat_id=uid, emoji="🎯")
    value = msg.dice.value

    # 애니메이션 대기
    await asyncio.sleep(3)

    # 결과 판정
    label, mult, is_dead = DART_RESULT[value]
    dmg = int(poke["base_dmg"] * mult)

    if is_dead:
        # 대실패 → 영혼
        s["dead"].append(poke["name"])
        s["idx"] += 1

        text = (
            f"{label}\n\n"
            f"💀 <b>{poke['emoji']}{poke['name']}</b>의 영혼이 빠져나갔다...\n\n"
            f"💥 누적 딜: {s['total_dmg']:,}"
        )

        if s["idx"] >= len(s["team"]):
            text += "\n\n⚠️ 팀 전멸!"
            await context.bot.send_message(uid, text, parse_mode="HTML")
            await asyncio.sleep(1)
            await _finish_msg(context, uid, s)
            return
        else:
            next_poke = s["team"][s["idx"]]
            text += f"\n\n▶ 다음: {next_poke['emoji']} {next_poke['name']} 투입!"

        buttons = [
            [
                InlineKeyboardButton(f"🔥 GO! ({next_poke['emoji']}{next_poke['name']})", callback_data=f"bp_go_{uid}"),
                InlineKeyboardButton("💰 STOP", callback_data=f"bp_stop_{uid}"),
            ]
        ]
        await context.bot.send_message(uid, text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")

    else:
        # 성공 → 딜 적립
        s["total_dmg"] += dmg
        _boss["hp"] = max(0, _boss["hp"] - dmg)

        text = (
            f"{label}\n\n"
            f"{poke['emoji']} {poke['name']} → 💥 <b>{dmg:,}</b> 데미지! (x{mult})\n\n"
            f"💥 누적 딜: <b>{s['total_dmg']:,}</b>\n"
            f"❤️ 보스 HP: {_boss['hp']:,}\n\n"
            f"계속할까?"
        )

        # 같은 포켓몬으로 계속 GO 가능
        buttons = [
            [
                InlineKeyboardButton(f"🔥 GO! ({poke['emoji']}{poke['name']})", callback_data=f"bp_go_{uid}"),
                InlineKeyboardButton("💰 STOP", callback_data=f"bp_stop_{uid}"),
            ]
        ]
        await context.bot.send_message(uid, text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")


async def _finish(query, context, uid):
    s = _sessions.get(uid)
    if not s:
        return
    try:
        await query.edit_message_reply_markup(None)
    except Exception:
        pass
    await _finish_msg(context, uid, s)


async def _finish_msg(context, uid, s):
    dead_names = ", ".join(f"💀{d}" for d in s["dead"]) if s["dead"] else "없음"

    text = (
        f"💰 <b>보스전 종료!</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💥 최종 딜량: <b>{s['total_dmg']:,}</b>\n"
        f"❤️ 보스 HP: {_boss['hp']:,} / {_boss['max_hp']:,}\n"
        f"{_hp_bar(_boss['hp'], _boss['max_hp'])}\n\n"
        f"💀 영혼: {dead_names}\n\n"
        f"🎁 보상: (딜량 기반 마일스톤)\n"
    )

    if s["dead"]:
        text += f"\n⚠️ 영혼 포켓몬은 대시보드 방문으로 부활!"

    await context.bot.send_message(uid, text, parse_mode="HTML")
    _sessions.pop(uid, None)


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r"^보스$"), boss_cmd))
    app.add_handler(CallbackQueryHandler(boss_callback, pattern=r"^bp_"))
    logger.info("Boss prototype running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
