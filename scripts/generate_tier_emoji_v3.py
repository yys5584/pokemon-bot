"""
랭크전 티어 이모지 v3 — 깔끔한 계급장 스타일
블러/글로우 없음, 선명한 도형만 사용
100x100 RGBA PNG
"""
from PIL import Image, ImageDraw, ImageFont
import math, os

SIZE = 100
OUT = r"C:\Users\Administrator\Desktop\pokemon-bot\assets\tier_emoji_v3"

TIERS = {
    "bronze": {
        "top": (180, 120, 70), "bottom": (220, 170, 110),
        "band": (140, 90, 50), "btn_out": (140, 90, 50), "btn_in": (200, 140, 80),
        "outline": (100, 60, 30), "accent": (160, 110, 60),
        "star": (220, 175, 100), "star_outline": (140, 90, 50),
    },
    "silver": {
        "top": (175, 182, 195), "bottom": (215, 220, 232),
        "band": (140, 148, 162), "btn_out": (140, 148, 162), "btn_in": (195, 200, 218),
        "outline": (105, 115, 130), "accent": (160, 168, 185),
        "star": (220, 225, 240), "star_outline": (140, 148, 162),
    },
    "gold": {
        "top": (235, 190, 35), "bottom": (255, 232, 130),
        "band": (195, 155, 20), "btn_out": (195, 155, 20), "btn_in": (240, 200, 50),
        "outline": (150, 110, 10), "accent": (210, 170, 25),
        "star": (255, 230, 70), "star_outline": (180, 140, 15),
    },
    "platinum": {
        "top": (50, 190, 205), "bottom": (155, 225, 235),
        "band": (30, 150, 170), "btn_out": (30, 150, 170), "btn_in": (70, 200, 215),
        "outline": (20, 110, 130), "accent": (50, 175, 195),
        "star": (130, 235, 248), "star_outline": (30, 150, 170),
    },
    "diamond": {
        "top": (70, 130, 235), "bottom": (150, 192, 255),
        "band": (40, 90, 195), "btn_out": (40, 90, 195), "btn_in": (90, 150, 248),
        "outline": (30, 65, 160), "accent": (60, 115, 215),
        "star": (155, 198, 255), "star_outline": (40, 90, 195),
    },
    "master": {
        "top": (150, 70, 195), "bottom": (195, 140, 225),
        "band": (110, 40, 165), "btn_out": (110, 40, 165), "btn_in": (160, 90, 205),
        "outline": (80, 25, 130), "accent": (135, 60, 180),
        "star": (215, 165, 255), "star_outline": (110, 40, 165),
    },
    "challenger": {
        "top": (25, 25, 55), "bottom": (45, 45, 85),
        "band": (215, 165, 25), "btn_out": (215, 95, 25), "btn_in": (250, 155, 45),
        "outline": (180, 130, 10), "accent": (230, 175, 30),
        "star": (255, 215, 70), "star_outline": (200, 150, 15),
    },
}


def draw_star_5(draw, cx, cy, outer_r, inner_r, fill, outline, width=1):
    """깔끔한 5꼭지 별"""
    pts = []
    for i in range(10):
        angle = math.radians(-90 + i * 36)
        r = outer_r if i % 2 == 0 else inner_r
        pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    draw.polygon(pts, fill=fill, outline=outline, width=width)


def draw_shield_badge(draw, cx, cy, w, h, fill, outline):
    """방패형 배경 (하단 뾰족)"""
    pts = [
        (cx - w//2, cy - h//2),       # 좌상
        (cx + w//2, cy - h//2),       # 우상
        (cx + w//2, cy + h//4),       # 우중
        (cx, cy + h//2),              # 하단 꼭지
        (cx - w//2, cy + h//4),       # 좌중
    ]
    draw.polygon(pts, fill=fill, outline=outline, width=2)


def draw_wing(draw, cx, cy, side, color, outline_c):
    """날개 한쪽 (side: -1=좌, 1=우)"""
    # 3개 깃털 — 위가 길고 아래가 짧음
    feathers = [
        (0, -8, 18, 5),   # 위 깃털 (dy, dx_len, feather_h)
        (0, 0, 14, 5),    # 중간
        (0, 8, 10, 4),    # 아래
    ]
    for dy_off, dy, length, fh in feathers:
        if side == 1:
            pts = [
                (cx, cy + dy),
                (cx + length, cy + dy - fh),
                (cx + length + 3, cy + dy),
                (cx + length, cy + dy + fh - 1),
            ]
        else:
            pts = [
                (cx, cy + dy),
                (cx - length, cy + dy - fh),
                (cx - length - 3, cy + dy),
                (cx - length, cy + dy + fh - 1),
            ]
        draw.polygon(pts, fill=color, outline=outline_c)


def draw_laurel_leaf(draw, cx, cy, side, color, outline_c):
    """월계관 잎 한쪽"""
    for i in range(4):
        angle = math.radians(30 + i * 30)
        dist = 5 + i * 5
        lx = cx + side * dist * math.cos(angle) * 0.6
        ly = cy - dist * math.sin(angle) + 10

        # 잎 = 마름모
        leaf_size = 5
        la = math.radians(45 + i * 10) if side == 1 else math.radians(135 - i * 10)
        pts = [
            (lx, ly - leaf_size),
            (lx + side * leaf_size * 0.6, ly),
            (lx, ly + leaf_size * 0.5),
            (lx - side * leaf_size * 0.3, ly - leaf_size * 0.3),
        ]
        draw.polygon(pts, fill=color, outline=outline_c)


def draw_crown(draw, cx, cy, color, gem_colors):
    """왕관"""
    pts = [
        (cx - 15, cy + 10),
        (cx - 17, cy - 1),
        (cx - 9, cy + 5),
        (cx, cy - 6),
        (cx + 9, cy + 5),
        (cx + 17, cy - 1),
        (cx + 15, cy + 10),
    ]
    draw.polygon(pts, fill=color, outline=(min(255, color[0]+30), min(255, color[1]+30), min(255, color[2]+30)))
    # 보석 3개
    draw.ellipse([cx-2, cy, cx+2, cy+4], fill=gem_colors[0])
    draw.ellipse([cx-11, cy+3, cx-8, cy+6], fill=gem_colors[1])
    draw.ellipse([cx+8, cy+3, cx+11, cy+6], fill=gem_colors[1])


def draw_flame(draw, cx, cy, ball_r):
    """불꽃 (챌린저) — 선명한 삼각형"""
    flame_color = (255, 95, 15)
    flame_inner = (255, 195, 45)

    positions = [
        # (offset_x, offset_y, size)
        (-ball_r - 4, -6, 9),
        (-ball_r + 1, -16, 6),
        (-ball_r - 1, 5, 7),
        (ball_r + 4, -6, 9),
        (ball_r - 1, -16, 6),
        (ball_r + 1, 5, 7),
    ]
    for fx, fy, fs in positions:
        x, y = cx + fx, cy + fy
        draw.polygon([(x, y), (x - fs//2, y + fs), (x + fs//2, y + fs)], fill=flame_color)
        s2 = fs * 2 // 3
        draw.polygon([(x, y + 2), (x - s2//2, y + fs - 1), (x + s2//2, y + fs - 1)], fill=flame_inner)


def generate_tier(tier_key, division):
    t = TIERS[tier_key]
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = SIZE // 2, SIZE // 2
    ball_r = 26
    has_crown = tier_key in ("master", "challenger")
    has_flame = tier_key == "challenger"
    has_wings = tier_key in ("platinum", "diamond", "master", "challenger")
    has_laurel = tier_key in ("gold", "diamond", "master", "challenger")

    if has_crown:
        cy += 5
    if division > 0:
        cy -= 3

    # ── 불꽃 (챌린저, 볼 뒤) ──
    if has_flame:
        draw_flame(draw, cx, cy, ball_r)

    # ── 날개 ──
    if has_wings:
        draw_wing(draw, cx - ball_r - 2, cy, -1, t["accent"], t["outline"])
        draw_wing(draw, cx + ball_r + 2, cy, 1, t["accent"], t["outline"])

    # ── 월계관 ──
    if has_laurel:
        draw_laurel_leaf(draw, cx, cy + ball_r - 5, -1, t["accent"], t["outline"])
        draw_laurel_leaf(draw, cx, cy + ball_r - 5, 1, t["accent"], t["outline"])

    # ── 포켓볼 ──
    # 외곽
    draw.ellipse([cx-ball_r-2, cy-ball_r-2, cx+ball_r+2, cy+ball_r+2], fill=t["outline"])
    # 상단
    draw.pieslice([cx-ball_r, cy-ball_r, cx+ball_r, cy+ball_r], 180, 360, fill=t["top"])
    # 하단
    draw.pieslice([cx-ball_r, cy-ball_r, cx+ball_r, cy+ball_r], 0, 180, fill=t["bottom"])
    # 밴드
    draw.rectangle([cx-ball_r, cy-3, cx+ball_r, cy+3], fill=t["band"])
    # 버튼
    draw.ellipse([cx-8, cy-8, cx+8, cy+8], fill=t["btn_out"])
    draw.ellipse([cx-5, cy-5, cx+5, cy+5], fill=t["btn_in"])
    # 버튼 하이라이트
    draw.ellipse([cx-3, cy-3, cx-1, cy-1], fill=(255, 255, 255, 160))

    # 볼 하이라이트 (작은 원 2개)
    draw.ellipse([cx-14, cy-ball_r+6, cx-7, cy-ball_r+12], fill=(255, 255, 255, 100))
    draw.ellipse([cx-5, cy-ball_r+11, cx-2, cy-ball_r+14], fill=(255, 255, 255, 70))

    # ── 왕관 ──
    if has_crown:
        crown_color = (255, 200, 50) if tier_key == "master" else (255, 170, 30)
        gems = [(255, 50, 50), (50, 200, 255)] if tier_key == "master" else [(255, 80, 30), (255, 220, 60)]
        draw_crown(draw, cx, cy - ball_r - 5, crown_color, gems)

    # ── 디비전 별 ──
    if division > 0:
        star_y = cy + ball_r + 10
        sr, sir = 6, 2.5
        if division == 2:
            draw_star_5(draw, cx, star_y, sr, sir, t["star"], t["star_outline"])
        elif division == 1:
            draw_star_5(draw, cx - 9, star_y, sr, sir, t["star"], t["star_outline"])
            draw_star_5(draw, cx + 9, star_y, sr, sir, t["star"], t["star_outline"])

    return img


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)

    all_imgs = []
    labels = []
    name_kr = {
        "bronze": "브론즈", "silver": "실버", "gold": "골드",
        "platinum": "플래티넘", "diamond": "다이아",
        "master": "마스터", "challenger": "챌린저",
    }

    div_tiers = ["bronze", "silver", "gold", "platinum", "diamond"]
    no_div_tiers = ["master", "challenger"]

    for tk in div_tiers:
        for div in [2, 1]:
            img = generate_tier(tk, div)
            dn = "II" if div == 2 else "I"
            fname = f"tier_{tk}_{dn.lower()}.png"
            img.save(os.path.join(OUT, fname), "PNG")
            all_imgs.append(img)
            labels.append(f"{name_kr[tk]} {dn}")
            print(f"  {tk} {dn}")

    for tk in no_div_tiers:
        img = generate_tier(tk, 0)
        fname = f"tier_{tk}.png"
        img.save(os.path.join(OUT, fname), "PNG")
        all_imgs.append(img)
        labels.append(name_kr[tk])
        print(f"  {tk}")

    # ── 프리뷰 시트 ──
    cols = 6
    rows = math.ceil(len(all_imgs) / cols)
    pad = 10
    cell_w, cell_h = SIZE + pad, SIZE + 28
    sheet = Image.new("RGBA", (cols * cell_w + pad, rows * cell_h + pad), (30, 30, 50, 255))
    sd = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("malgun.ttf", 11)
    except:
        font = ImageFont.load_default()

    for idx, (im, label) in enumerate(zip(all_imgs, labels)):
        c, r = idx % cols, idx // cols
        x, y = pad + c * cell_w, pad + r * cell_h
        sheet.paste(im, (x, y), im)
        bb = sd.textbbox((0, 0), label, font=font)
        sd.text((x + SIZE//2 - (bb[2]-bb[0])//2, y + SIZE + 2), label,
                fill=(255, 255, 255), font=font)

    sheet.save(os.path.join(OUT, "_preview.png"), "PNG")
    print(f"\n  Preview -> {OUT}\\_preview.png")
