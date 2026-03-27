"""슬롯 GIF 프로토타입 — 휙휙 돌아가는 릴 + 팡팡 이펙트."""
import asyncio
import random
import logging
import math
import os
import sys
import io

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaAnimation, InputMediaPhoto
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

SLOT_POOL = [
    (25, "pikachu"), (6, "charizard"), (9, "blastoise"), (3, "venusaur"),
    (131, "lapras"), (149, "dragonite"), (150, "mewtwo"), (130, "gyarados"),
    (248, "tyranitar"), (376, "metagross"),
]

BG_COLOR = (18, 18, 32)
SLOT_BG = (30, 30, 55)
REEL_BG = (22, 22, 40)
GOLD = (255, 215, 0)
RED = (255, 80, 80)
GREEN = (80, 255, 120)
CYAN = (80, 220, 255)
WHITE = (255, 255, 255)
DIM = (120, 120, 140)

try:
    FONT_TITLE = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 30)
    FONT_SUB = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 22)
    FONT_BIG = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 38)
    FONT_SM = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 16)
except Exception:
    FONT_TITLE = FONT_SUB = FONT_BIG = FONT_SM = ImageFont.load_default()

IMG_W, IMG_H = 700, 420
REEL_SIZE = 120
REEL_Y = 130
REEL_GAP = 25
REEL_START_X = (IMG_W - (REEL_SIZE * 3 + REEL_GAP * 2)) // 2

# 포켓몬 이미지 캐시
_img_cache = {}


def _load_pokemon(pid, size=REEL_SIZE):
    if (pid, size) in _img_cache:
        return _img_cache[(pid, size)]
    path = os.path.join(ASSETS, f"{pid}.png")
    if os.path.exists(path):
        img = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
    else:
        img = Image.new("RGBA", (size, size), (60, 60, 80, 255))
    _img_cache[(pid, size)] = img
    return img


def _paste_pokemon(base, poke_img, x, y):
    """RGBA 포켓몬을 RGB 베이스에 붙이기."""
    temp = Image.new("RGB", poke_img.size, REEL_BG)
    temp.paste(poke_img, mask=poke_img.split()[3])
    base.paste(temp, (x, y))


def _draw_sparkles(draw, cx, cy, radius, count, frame, color=GOLD):
    """프레임에 따라 반짝이는 별 효과."""
    for i in range(count):
        angle = (360 / count) * i + frame * 15
        r = radius + math.sin(frame * 0.5 + i) * 15
        sx = int(cx + r * math.cos(math.radians(angle)))
        sy = int(cy + r * math.sin(math.radians(angle)))
        size = random.randint(2, 5)
        draw.ellipse((sx - size, sy - size, sx + size, sy + size), fill=color)


def _draw_confetti(draw, w, h, frame, count=30):
    """컨페티/파티클 효과."""
    random.seed(42 + frame)  # 프레임별 다른 위치
    colors = [GOLD, RED, GREEN, CYAN, (255, 100, 200), (255, 165, 0)]
    for i in range(count):
        x = random.randint(0, w)
        y = (random.randint(-50, h) + frame * 8 + i * 13) % (h + 50) - 25
        c = colors[i % len(colors)]
        size = random.randint(3, 7)
        if i % 3 == 0:
            draw.rectangle((x, y, x + size, y + size * 2), fill=c)
        elif i % 3 == 1:
            draw.ellipse((x, y, x + size, y + size), fill=c)
        else:
            draw.polygon([(x, y - size), (x - size, y + size), (x + size, y + size)], fill=c)


def _draw_speed_lines(draw, reel_x, reel_y, reel_size, direction="down"):
    """스피닝 속도감 라인."""
    for _ in range(5):
        lx = reel_x + random.randint(5, reel_size - 5)
        if direction == "down":
            ly = reel_y + random.randint(0, reel_size)
            draw.line((lx, ly, lx, ly + random.randint(15, 40)), fill=(100, 100, 150, 128), width=2)
        else:
            ly = reel_y + random.randint(0, reel_size)
            draw.line((lx, ly, lx, ly - random.randint(15, 40)), fill=(100, 100, 150, 128), width=2)


def render_frame(reels, title, subtitle="", phase="spin", frame_idx=0, glow=None):
    """단일 프레임 렌더링.
    reels: [(pid, state), ...] state='spin'|'stop'|'question'
    """
    img = Image.new("RGB", (IMG_W, IMG_H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # 결과 이펙트 (배경)
    if phase in ("success", "jackpot"):
        _draw_confetti(draw, IMG_W, IMG_H, frame_idx, count=25 if phase == "jackpot" else 15)

    # 타이틀
    draw.text((IMG_W // 2, 25), title, fill=GOLD, font=FONT_TITLE, anchor="mt")

    # 슬롯 박스
    pad = 18
    box = (
        REEL_START_X - pad, REEL_Y - pad,
        REEL_START_X + REEL_SIZE * 3 + REEL_GAP * 2 + pad,
        REEL_Y + REEL_SIZE + pad,
    )
    draw.rounded_rectangle(box, radius=18, fill=SLOT_BG, outline=(60, 60, 90), width=2)
    if glow:
        for g in range(3):
            draw.rounded_rectangle(
                (box[0] - g*2, box[1] - g*2, box[2] + g*2, box[3] + g*2),
                radius=18, outline=(*glow, 150 - g*40), width=2
            )

    # 릴 그리기
    for i, (pid, state) in enumerate(reels):
        rx = REEL_START_X + i * (REEL_SIZE + REEL_GAP)
        ry = REEL_Y

        draw.rounded_rectangle(
            (rx - 4, ry - 4, rx + REEL_SIZE + 4, ry + REEL_SIZE + 4),
            radius=10, fill=REEL_BG
        )

        if state == "spin":
            # 스피닝: 여러 포켓몬이 빠르게 지나가는 느낌
            # 현재 + 다음 포켓몬을 y 오프셋으로 표시
            offset = (frame_idx * 37 + i * 17) % (REEL_SIZE + 20)
            p1 = SLOT_POOL[(frame_idx * 3 + i * 7) % len(SLOT_POOL)][0]
            p2 = SLOT_POOL[(frame_idx * 3 + i * 7 + 1) % len(SLOT_POOL)][0]

            # 클리핑 영역
            clip_img = Image.new("RGB", (REEL_SIZE, REEL_SIZE), REEL_BG)
            poke1 = _load_pokemon(p1)
            poke2 = _load_pokemon(p2)
            temp1 = Image.new("RGB", poke1.size, REEL_BG)
            temp1.paste(poke1, mask=poke1.split()[3])
            temp2 = Image.new("RGB", poke2.size, REEL_BG)
            temp2.paste(poke2, mask=poke2.split()[3])

            # 모션 블러 효과
            temp1 = temp1.filter(ImageFilter.GaussianBlur(radius=3))
            temp2 = temp2.filter(ImageFilter.GaussianBlur(radius=3))

            y1 = offset - REEL_SIZE - 10
            y2 = offset

            clip_img.paste(temp1, (0, y1))
            clip_img.paste(temp2, (0, y2))
            img.paste(clip_img, (rx, ry))

            # 속도 라인
            _draw_speed_lines(draw, rx, ry, REEL_SIZE)

        elif state == "stop":
            poke = _load_pokemon(pid)
            _paste_pokemon(img, poke, rx, ry)
            # 멈출 때 반짝
            if phase == "stopping":
                _draw_sparkles(draw, rx + REEL_SIZE // 2, ry + REEL_SIZE // 2, 20, 4, frame_idx, WHITE)

        elif state == "question":
            # 물음표
            draw.rounded_rectangle((rx, ry, rx + REEL_SIZE, ry + REEL_SIZE), radius=8, fill=(35, 35, 55))
            draw.text((rx + REEL_SIZE // 2, ry + REEL_SIZE // 2), "?",
                       fill=GOLD, font=FONT_BIG, anchor="mm")
            # 떨림 효과
            if frame_idx % 2:
                draw.text((rx + REEL_SIZE // 2 + 2, ry + REEL_SIZE // 2 + 1), "?",
                           fill=(200, 180, 0), font=FONT_BIG, anchor="mm")

    # 구분선
    for i in range(1, 3):
        lx = REEL_START_X + i * (REEL_SIZE + REEL_GAP) - REEL_GAP // 2
        draw.line((lx, REEL_Y - 10, lx, REEL_Y + REEL_SIZE + 10), fill=(50, 50, 70), width=2)

    # 서브타이틀
    if subtitle:
        draw.text((IMG_W // 2, REEL_Y + REEL_SIZE + 40), subtitle, fill=DIM, font=FONT_SUB, anchor="mt")

    # 결과 텍스트
    if phase == "success":
        _draw_sparkles(draw, IMG_W // 2, IMG_H - 55, 60, 8, frame_idx, GREEN)
        draw.text((IMG_W // 2, IMG_H - 55), "✨ SUCCESS ✨", fill=GREEN, font=FONT_BIG, anchor="mm")
    elif phase == "jackpot":
        _draw_sparkles(draw, IMG_W // 2, IMG_H - 55, 80, 12, frame_idx, GOLD)
        draw.text((IMG_W // 2, IMG_H - 55), "💎 MEGA JACKPOT 💎", fill=GOLD, font=FONT_BIG, anchor="mm")
    elif phase == "near":
        draw.text((IMG_W // 2, IMG_H - 55), "😱 아깝다...!!!", fill=RED, font=FONT_BIG, anchor="mm")
    elif phase == "fail":
        draw.text((IMG_W // 2, IMG_H - 55), "💨 실패...", fill=DIM, font=FONT_BIG, anchor="mm")

    return img


def generate_slot_gif(final_pids, result_type):
    """슬롯 GIF 전체 생성. returns bytes."""
    frames = []
    durations = []

    # Phase 1: 스피닝 (8프레임, 빠르게)
    for f in range(8):
        reels = [(0, "spin"), (0, "spin"), (0, "spin")]
        frame = render_frame(reels, "🔥 이로치 제련소", "회전 중...", "spin", f)
        frames.append(frame)
        durations.append(120)  # 120ms

    # Phase 2: 1번 멈춤 (3프레임)
    for f in range(3):
        reels = [(final_pids[0], "stop"), (0, "spin"), (0, "spin")]
        frame = render_frame(reels, "🔥 이로치 제련소", "🔒 첫 번째!", "stopping", f + 8)
        frames.append(frame)
        durations.append(250)

    # Phase 3: 2번 멈춤 (3프레임)
    if final_pids[0] == final_pids[1]:
        sub = "😳 두 개 일치...!"
    else:
        sub = "🔒🔒 두 번째!"
    for f in range(3):
        reels = [(final_pids[0], "stop"), (final_pids[1], "stop"), (0, "spin")]
        frame = render_frame(reels, "🔥 이로치 제련소", sub, "stopping", f + 11)
        frames.append(frame)
        durations.append(300)

    # Phase 4: 극적 멈춤 (2개 일치 시 물음표 떨림)
    if final_pids[0] == final_pids[1]:
        for f in range(6):
            reels = [(final_pids[0], "stop"), (final_pids[1], "stop"), (0, "question")]
            frame = render_frame(reels, "🔥 이로치 제련소", "🫣 . . .", "stopping", f + 14)
            frames.append(frame)
            durations.append(300)

    # Phase 5: 결과 (6프레임, 이펙트)
    phase = {"jackpot": "jackpot", "shiny": "success", "near": "near", "fail": "fail"}[result_type]
    glow = {"jackpot": GOLD, "shiny": GREEN}.get(result_type)
    for f in range(6):
        reels = [(final_pids[0], "stop"), (final_pids[1], "stop"), (final_pids[2], "stop")]
        frame = render_frame(reels, "🔥 이로치 제련소", "", phase, f + 20, glow)
        frames.append(frame)
        durations.append(400 if f < 3 else 600)

    # GIF로 저장
    buf = io.BytesIO()
    frames[0].save(
        buf, format="GIF", save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
    )
    buf.seek(0)
    return buf


async def slot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    buttons = [[InlineKeyboardButton("🎰 슬롯 돌리기!", callback_data=f"gslot_{uid}")]]
    # 초기 이미지
    init = render_frame(
        [(0, "question"), (0, "question"), (0, "question")],
        "🔥 이로치 제련소", "재료를 넣고 돌려보세요!", "idle", 0
    )
    buf = io.BytesIO()
    init.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    await update.message.reply_photo(
        photo=buf,
        caption="🔥 <b>이로치 제련소</b>\n대상: 🔥 리자몽\n재료: 리자몽 x3 + 500BP",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
    )


async def slot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    if not query.data.startswith("gslot_"):
        return
    await query.answer("🎰 제련 시작!")

    # 결과 결정
    roll = random.random()
    if roll < 0.02:
        result_type = "jackpot"
        sym = random.choice(SLOT_POOL)
        final_pids = [sym[0]] * 3
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

    # GIF 생성
    gif_buf = generate_slot_gif(final_pids, result_type)

    # 캡션
    if result_type == "jackpot":
        caption = "🔥🔥🔥 <b>MEGA JACKPOT!!!</b> 🔥🔥🔥\n\n💎 메가스톤 획득!\n🔥 리자몽 → ✨ <b>메가리자몽</b>"
    elif result_type == "shiny":
        caption = "✨✨✨ <b>이로치 제련 성공!!!</b>\n\n🔥 리자몽이 빛나기 시작한다!\n✨ <b>이로치 리자몽</b> 획득!"
    elif result_type == "near":
        caption = "😱 <b>아깝다!!!</b>\n\n빛이 거의 나타났다가... 사라졌다\n재료 소멸 💨\n\n🔧 연성 게이지 +15%\n▓▓▓▓▓▓▓▓░░ 80%"
    else:
        caption = "💨 <b>실패...</b>\n\n제련로의 불꽃이 꺼졌다\n재료 소멸 💨\n\n🔧 연성 게이지 +10%\n▓▓▓▓▓▓░░░░ 60%"

    buttons = [[InlineKeyboardButton("🎰 다시 돌리기!", callback_data=f"gslot_{uid}")]]

    try:
        gif_buf.name = "slot.gif"
        await query.edit_message_media(
            media=InputMediaAnimation(gif_buf, filename="slot.gif", caption=caption, parse_mode="HTML"),
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    except Exception as e:
        logging.error(f"edit error: {e}")
        gif_buf.seek(0)
        gif_buf.name = "slot.gif"
        await context.bot.send_animation(
            uid, gif_buf, caption=caption, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r"^슬롯$"), slot_cmd))
    app.add_handler(CallbackQueryHandler(slot_callback, pattern=r"^gslot_"))
    logging.info("GIF slot prototype running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
