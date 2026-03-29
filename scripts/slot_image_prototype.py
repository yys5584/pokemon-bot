"""슬롯 이미지 프로토타입 — PIL로 슬롯 이미지 생성 + edit_media 애니메이션."""
import asyncio
import random
import logging
import os
import sys
import io

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    ApplicationBuilder, ContextTypes, MessageHandler, CallbackQueryHandler,
    filters,
)
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = "8616848852:AAEEboGyiQ9vUq_8NpzPxlzZEWF0jhNr7iU"
ADMIN_ID = 1832746512

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "pokemon")

# 슬롯 포켓몬 (id, 이름)
SLOT_POOL = [
    (25, "피카츄"), (6, "리자몽"), (9, "거북왕"), (3, "이상해꽃"),
    (131, "라프라스"), (149, "망나뇽"), (150, "뮤츠"),
]
JACKPOT_IMG = (150, "뮤츠")  # 잭팟 심볼

# 색상
BG_COLOR = (18, 18, 32)
SLOT_BG = (30, 30, 55)
REEL_BG = (22, 22, 40)
GOLD = (255, 215, 0)
RED = (255, 80, 80)
GREEN = (80, 255, 120)
WHITE = (255, 255, 255)
DIM_WHITE = (180, 180, 200)

try:
    FONT_TITLE = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 32)
    FONT_SUB = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 22)
    FONT_RESULT = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 36)
    FONT_SM = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 18)
except Exception:
    FONT_TITLE = FONT_SUB = FONT_RESULT = FONT_SM = ImageFont.load_default()

IMG_W, IMG_H = 800, 500
REEL_SIZE = 140  # 포켓몬 이미지 크기
REEL_Y = 160
REEL_GAP = 30
REEL_START_X = (IMG_W - (REEL_SIZE * 3 + REEL_GAP * 2)) // 2


def _load_pokemon_img(pid: int, size: int = REEL_SIZE) -> Image.Image:
    path = os.path.join(ASSETS, f"{pid}.png")
    if os.path.exists(path):
        img = Image.open(path).convert("RGBA")
        img = img.resize((size, size), Image.LANCZOS)
        return img
    # fallback: 빈 이미지
    img = Image.new("RGBA", (size, size), (60, 60, 80, 255))
    return img


def _make_question_mark(size: int = REEL_SIZE) -> Image.Image:
    img = Image.new("RGBA", (size, size), (40, 40, 60, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", size // 2)
    except Exception:
        font = ImageFont.load_default()
    draw.text((size // 2, size // 2), "?", fill=GOLD, font=font, anchor="mm")
    return img


def render_slot(reels, title="이로치 제련소", subtitle="", phase="spin", glow_color=None):
    """슬롯 이미지 렌더링.
    reels: [pid_or_None, pid_or_None, pid_or_None] — None이면 ? 표시
    """
    img = Image.new("RGB", (IMG_W, IMG_H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # 타이틀
    draw.text((IMG_W // 2, 30), "🔥 " + title, fill=GOLD, font=FONT_TITLE, anchor="mt")

    # 슬롯 배경
    slot_pad = 20
    slot_rect = (
        REEL_START_X - slot_pad,
        REEL_Y - slot_pad,
        REEL_START_X + REEL_SIZE * 3 + REEL_GAP * 2 + slot_pad,
        REEL_Y + REEL_SIZE + slot_pad,
    )
    draw.rounded_rectangle(slot_rect, radius=20, fill=SLOT_BG, outline=(60, 60, 90), width=2)

    if glow_color:
        draw.rounded_rectangle(slot_rect, radius=20, outline=glow_color, width=4)

    # 릴
    qmark = _make_question_mark()
    for i, pid in enumerate(reels):
        rx = REEL_START_X + i * (REEL_SIZE + REEL_GAP)
        ry = REEL_Y

        # 릴 배경
        draw.rounded_rectangle(
            (rx - 5, ry - 5, rx + REEL_SIZE + 5, ry + REEL_SIZE + 5),
            radius=12, fill=REEL_BG
        )

        # 포켓몬 이미지 or ?
        if pid == "spin":
            # 스피닝: 랜덤 포켓몬 블러
            rand_pid = random.choice(SLOT_POOL)[0]
            poke_img = _load_pokemon_img(rand_pid)
            poke_img_rgb = Image.new("RGB", poke_img.size, REEL_BG)
            poke_img_rgb.paste(poke_img, mask=poke_img.split()[3])
            poke_img_rgb = poke_img_rgb.filter(ImageFilter.GaussianBlur(radius=6))
            img.paste(poke_img_rgb, (rx, ry))
        elif pid == "?":
            qmark_rgb = Image.new("RGB", qmark.size, REEL_BG)
            qmark_rgb.paste(qmark, mask=qmark.split()[3])
            img.paste(qmark_rgb, (rx, ry))
        elif pid is not None:
            poke_img = _load_pokemon_img(pid)
            poke_img_rgb = Image.new("RGB", poke_img.size, REEL_BG)
            poke_img_rgb.paste(poke_img, mask=poke_img.split()[3])
            img.paste(poke_img_rgb, (rx, ry))

    # 구분선
    for i in range(1, 3):
        lx = REEL_START_X + i * (REEL_SIZE + REEL_GAP) - REEL_GAP // 2
        draw.line((lx, REEL_Y - 10, lx, REEL_Y + REEL_SIZE + 10), fill=(50, 50, 70), width=2)

    # 서브타이틀
    if subtitle:
        draw.text((IMG_W // 2, REEL_Y + REEL_SIZE + 50), subtitle, fill=DIM_WHITE, font=FONT_SUB, anchor="mt")

    # 하단 결과 텍스트 (phase별)
    if phase == "success":
        draw.text((IMG_W // 2, IMG_H - 60), "✨ 이로치 제련 성공! ✨", fill=GREEN, font=FONT_RESULT, anchor="mm")
    elif phase == "jackpot":
        draw.text((IMG_W // 2, IMG_H - 60), "💎 MEGA JACKPOT 💎", fill=GOLD, font=FONT_RESULT, anchor="mm")
    elif phase == "near":
        draw.text((IMG_W // 2, IMG_H - 60), "😱 아깝다...!!!", fill=RED, font=FONT_RESULT, anchor="mm")
    elif phase == "fail":
        draw.text((IMG_W // 2, IMG_H - 60), "💨 실패...", fill=DIM_WHITE, font=FONT_RESULT, anchor="mm")

    return img


def img_to_bytes(img: Image.Image) -> io.BytesIO:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    return buf


async def slot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    buttons = [[InlineKeyboardButton("🎰 슬롯 돌리기!", callback_data=f"imgslot_{uid}")]]
    # 초기 이미지
    init_img = render_slot(["?", "?", "?"], subtitle="재료를 넣고 슬롯을 돌려보세요!")
    await update.message.reply_photo(
        photo=img_to_bytes(init_img),
        caption="🔥 <b>이로치 제련소</b>\n대상: 🔥 리자몽\n재료: 리자몽 x3 + 500BP",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
    )


async def slot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id

    if not query.data.startswith("imgslot_"):
        return
    await query.answer("🎰 제련 시작!")

    # 결과 미리 결정
    roll = random.random()
    if roll < 0.02:
        result_type = "jackpot"
        final_pids = [JACKPOT_IMG[0]] * 3
    elif roll < 0.08:
        result_type = "shiny"
        sym = random.choice(SLOT_POOL)
        final_pids = [sym[0]] * 3
    elif roll < 0.35:
        result_type = "near"
        sym = random.choice(SLOT_POOL)
        other = random.choice([s for s in SLOT_POOL if s[0] != sym[0]])
        final_pids = [sym[0], sym[0], other[0]]
        random.shuffle(final_pids)
    else:
        result_type = "fail"
        picks = random.sample(SLOT_POOL, 3)
        final_pids = [p[0] for p in picks]

    # Phase 1: 스피닝 (2회)
    for i in range(2):
        spin_img = render_slot(["spin", "spin", "spin"], subtitle="회전 중...")
        try:
            await query.edit_message_media(
                media=InputMediaPhoto(img_to_bytes(spin_img)),
            )
        except Exception:
            pass
        await asyncio.sleep(0.6)

    # Phase 2: 1번 릴 멈춤
    img2 = render_slot([final_pids[0], "spin", "spin"], subtitle="🔒 첫 번째!")
    try:
        await query.edit_message_media(media=InputMediaPhoto(img_to_bytes(img2)))
    except Exception:
        pass
    await asyncio.sleep(0.8)

    # Phase 3: 2번 릴 멈춤
    if final_pids[0] == final_pids[1]:
        sub3 = "😳 두 개 일치...!"
    else:
        sub3 = "🔒🔒 두 번째!"
    img3 = render_slot([final_pids[0], final_pids[1], "spin"], subtitle=sub3)
    try:
        await query.edit_message_media(media=InputMediaPhoto(img_to_bytes(img3)))
    except Exception:
        pass
    await asyncio.sleep(0.8)

    # Phase 4: 극적 멈춤 (2개 일치 시)
    if final_pids[0] == final_pids[1]:
        img_sus = render_slot([final_pids[0], final_pids[1], "?"], subtitle="🫣 . . .")
        try:
            await query.edit_message_media(media=InputMediaPhoto(img_to_bytes(img_sus)))
        except Exception:
            pass
        await asyncio.sleep(1.5)

    # Phase 5: 최종 결과
    glow = None
    if result_type == "jackpot":
        glow = GOLD
        phase = "jackpot"
        caption = "🔥🔥🔥 <b>MEGA JACKPOT!!!</b> 🔥🔥🔥\n\n💎 메가스톤 획득!\n🔥 리자몽 → ✨ <b>메가리자몽</b>"
    elif result_type == "shiny":
        glow = GREEN
        phase = "success"
        caption = "✨✨✨ <b>이로치 제련 성공!!!</b>\n\n🔥 리자몽이 빛나기 시작한다!\n✨ <b>이로치 리자몽</b> 획득!"
    elif result_type == "near":
        phase = "near"
        caption = "😱 <b>아깝다!!!</b>\n\n빛이 거의 나타났다가... 사라졌다\n재료 소멸 💨\n\n🔧 연성 게이지 +15%\n▓▓▓▓▓▓▓▓░░ 80%"
    else:
        phase = "fail"
        caption = "💨 <b>실패...</b>\n\n제련로의 불꽃이 꺼졌다\n재료 소멸 💨\n\n🔧 연성 게이지 +10%\n▓▓▓▓▓▓░░░░ 60%"

    final_img = render_slot(final_pids, phase=phase, glow_color=glow)

    buttons = [[InlineKeyboardButton("🎰 다시 돌리기!", callback_data=f"imgslot_{uid}")]]
    try:
        await query.edit_message_media(
            media=InputMediaPhoto(img_to_bytes(final_img), caption=caption, parse_mode="HTML"),
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    except Exception as e:
        logging.error(f"edit error: {e}")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r"^슬롯$"), slot_cmd))
    app.add_handler(CallbackQueryHandler(slot_callback, pattern=r"^imgslot_"))
    logging.info("Image slot prototype running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
