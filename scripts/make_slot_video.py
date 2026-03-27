"""슬롯 애니메이션 동영상 노트 생성."""
import os
import sys
import random
import asyncio
from PIL import Image, ImageDraw, ImageFont
import imageio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 설정
SIZE = 480  # 동영상 노트는 정사각형
FPS = 15
BG_COLOR = (15, 15, 30)
SLOT_BG = (30, 30, 50)
REEL_BG = (20, 20, 35)
GOLD = (255, 215, 0)
RED = (255, 80, 80)
GREEN = (80, 255, 120)
WHITE = (255, 255, 255)
DIM = (120, 120, 140)

SYMBOLS = ["⚡", "🔥", "💧", "🌿", "❄️", "🔮", "7️"]
RESULT = ["🔥", "🔥", "🔥"]  # 3개 일치 = 성공!

try:
    FONT_BIG = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 52)
    FONT_MED = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 28)
    FONT_SM = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 20)
    FONT_EMOJI = ImageFont.truetype("C:/Windows/Fonts/seguiemj.ttf", 48)
    FONT_EMOJI_SM = ImageFont.truetype("C:/Windows/Fonts/seguiemj.ttf", 36)
except Exception:
    FONT_BIG = ImageFont.load_default()
    FONT_MED = ImageFont.load_default()
    FONT_SM = ImageFont.load_default()
    FONT_EMOJI = ImageFont.load_default()
    FONT_EMOJI_SM = ImageFont.load_default()


def draw_circle_mask(size):
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse((0, 0, size-1, size-1), fill=255)
    return mask


def make_frame(reel_values, title="이로치 제련소", subtitle="", phase="spin", glow=False):
    """프레임 하나 생성."""
    img = Image.new("RGB", (SIZE, SIZE), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # 원형 마스크용 배경 테두리
    if glow:
        draw.ellipse((2, 2, SIZE-3, SIZE-3), outline=GOLD, width=4)

    # 제목
    draw.text((SIZE//2, 40), title, fill=GOLD, font=FONT_MED, anchor="mt")

    # 슬롯 배경 박스
    slot_y = 140
    slot_h = 100
    margin = 30
    draw.rounded_rectangle(
        (margin, slot_y, SIZE - margin, slot_y + slot_h),
        radius=15, fill=SLOT_BG, outline=(60, 60, 80), width=2
    )

    # 3개 릴
    reel_w = (SIZE - margin*2 - 20) // 3
    for i, val in enumerate(reel_values):
        rx = margin + 10 + i * (reel_w + 5)
        ry = slot_y + 10
        # 릴 배경
        draw.rounded_rectangle(
            (rx, ry, rx + reel_w - 10, ry + slot_h - 20),
            radius=8, fill=REEL_BG
        )
        # 심볼 (텍스트로)
        cx = rx + (reel_w - 10) // 2
        cy = ry + (slot_h - 20) // 2
        try:
            draw.text((cx, cy), val, fill=WHITE, font=FONT_EMOJI, anchor="mm")
        except Exception:
            draw.text((cx, cy), val, fill=WHITE, font=FONT_BIG, anchor="mm")

    # 구분선
    for i in range(1, 3):
        lx = margin + 10 + i * (reel_w + 5) - 3
        draw.line((lx, slot_y + 5, lx, slot_y + slot_h - 5), fill=(60, 60, 80), width=2)

    # 하단 텍스트
    if subtitle:
        draw.text((SIZE//2, slot_y + slot_h + 30), subtitle, fill=WHITE, font=FONT_MED, anchor="mt")

    # 추가 장식
    if phase == "result_success":
        for _ in range(8):
            sx = random.randint(20, SIZE-20)
            sy = random.randint(280, SIZE-20)
            draw.text((sx, sy), random.choice(["✨", "⭐", "🌟"]), fill=GOLD, font=FONT_EMOJI_SM)
    elif phase == "result_jackpot":
        for _ in range(12):
            sx = random.randint(20, SIZE-20)
            sy = random.randint(280, SIZE-20)
            draw.text((sx, sy), random.choice(["🔥", "💎", "⭐", "🎊"]), fill=GOLD, font=FONT_EMOJI_SM)
        draw.text((SIZE//2, SIZE - 60), "MEGA JACKPOT", fill=RED, font=FONT_BIG, anchor="mm")

    # 원형 마스크 적용
    mask = draw_circle_mask(SIZE)
    bg = Image.new("RGB", (SIZE, SIZE), (0, 0, 0))
    img = Image.composite(img, bg, mask)
    return img


def generate_video(output_path="scripts/slot_demo.mp4"):
    frames = []

    # Phase 1: 제련 시작 (1초)
    for _ in range(FPS):
        f = make_frame(["", "", ""], title="이로치 제련소", subtitle="🔥 리자몽 제련 시작!")
        frames.append(f)

    # Phase 2: 스피닝 (2초)
    for _ in range(FPS * 2):
        syms = [random.choice(SYMBOLS) for _ in range(3)]
        f = make_frame(syms, title="이로치 제련소", subtitle="회전 중...", phase="spin")
        frames.append(f)

    # Phase 3: 1번 멈춤 (0.8초)
    for _ in range(int(FPS * 0.8)):
        syms = [RESULT[0], random.choice(SYMBOLS), random.choice(SYMBOLS)]
        f = make_frame(syms, title="이로치 제련소", subtitle="🔒 첫 번째!")
        frames.append(f)

    # Phase 4: 2번 멈춤 (0.8초)
    for _ in range(int(FPS * 0.8)):
        syms = [RESULT[0], RESULT[1], random.choice(SYMBOLS)]
        f = make_frame(syms, title="이로치 제련소", subtitle="😳 두 개 일치...!")
        frames.append(f)

    # Phase 5: 극적 멈춤 (1.5초)
    for _ in range(int(FPS * 1.5)):
        f = make_frame([RESULT[0], RESULT[1], "❓"], title="이로치 제련소", subtitle="🫣 . . .")
        frames.append(f)

    # Phase 6: 결과! (2초)
    for _ in range(FPS * 2):
        f = make_frame(RESULT, title="✨ SUCCESS ✨", subtitle="이로치 리자몽 획득!", phase="result_success", glow=True)
        frames.append(f)

    # numpy 배열로 변환
    import numpy as np
    np_frames = [np.array(f) for f in frames]

    writer = imageio.get_writer(output_path, fps=FPS, codec="libx264",
                                 output_params=["-pix_fmt", "yuv420p"])
    for nf in np_frames:
        writer.append_data(nf)
    writer.close()
    print(f"Done: {output_path} ({len(frames)} frames, {len(frames)/FPS:.1f}s)")
    return output_path


if __name__ == "__main__":
    path = generate_video()
