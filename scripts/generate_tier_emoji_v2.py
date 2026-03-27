"""
랭크전 티어 커스텀 이모지 v2 — 포켓볼 + 계급장 스타일
디비전 II(★1) / I(★★) 구분
100x100 RGBA PNG
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math, os

SIZE = 100
CENTER = SIZE // 2
OUT = r"C:\Users\Administrator\Desktop\pokemon-bot\assets\tier_emoji_v2"

TIERS = {
    "bronze": {
        "top": (180, 120, 70),
        "bottom": (220, 170, 110),
        "band": (140, 90, 50),
        "btn_out": (140, 90, 50),
        "btn_in": (200, 140, 80),
        "outline": (120, 75, 40),
        "star_color": (200, 150, 90),
        "chevron_color": (160, 110, 60),
        "glow": None,
        "wings": False,
        "laurel": False,
    },
    "silver": {
        "top": (180, 185, 195),
        "bottom": (215, 220, 230),
        "band": (145, 150, 165),
        "btn_out": (145, 150, 165),
        "btn_in": (195, 200, 215),
        "outline": (120, 128, 140),
        "star_color": (210, 215, 230),
        "chevron_color": (160, 168, 185),
        "glow": None,
        "wings": False,
        "laurel": False,
    },
    "gold": {
        "top": (240, 195, 40),
        "bottom": (255, 235, 140),
        "band": (200, 160, 25),
        "btn_out": (200, 160, 25),
        "btn_in": (245, 205, 55),
        "outline": (170, 130, 15),
        "star_color": (255, 220, 60),
        "chevron_color": (210, 170, 30),
        "glow": None,
        "wings": False,
        "laurel": True,
    },
    "platinum": {
        "top": (55, 195, 210),
        "bottom": (165, 228, 238),
        "band": (35, 155, 175),
        "btn_out": (35, 155, 175),
        "btn_in": (75, 205, 218),
        "outline": (25, 125, 145),
        "star_color": (140, 235, 250),
        "chevron_color": (60, 180, 200),
        "glow": (100, 220, 240, 30),
        "wings": True,
        "laurel": False,
    },
    "diamond": {
        "top": (75, 135, 238),
        "bottom": (155, 195, 255),
        "band": (45, 95, 198),
        "btn_out": (45, 95, 198),
        "btn_in": (95, 155, 250),
        "outline": (35, 75, 175),
        "star_color": (160, 200, 255),
        "chevron_color": (80, 130, 220),
        "glow": (100, 160, 255, 40),
        "wings": True,
        "laurel": True,
    },
    "master": {
        "top": (155, 75, 198),
        "bottom": (198, 145, 228),
        "band": (115, 45, 168),
        "btn_out": (115, 45, 168),
        "btn_in": (165, 95, 208),
        "outline": (95, 35, 148),
        "star_color": (220, 170, 255),
        "chevron_color": (140, 70, 190),
        "glow": (180, 100, 255, 50),
        "wings": True,
        "laurel": True,
        "crown": True,
    },
    "challenger": {
        "top": (28, 28, 58),
        "bottom": (48, 48, 88),
        "band": (218, 168, 28),
        "btn_out": (218, 98, 28),
        "btn_in": (252, 158, 48),
        "outline": (198, 148, 18),
        "star_color": (255, 210, 80),
        "chevron_color": (220, 160, 30),
        "glow": (255, 180, 50, 60),
        "wings": True,
        "laurel": True,
        "crown": True,
        "flame": True,
    },
}


def draw_star(draw, cx, cy, r, color, outline=None):
    """5꼭지 별"""
    pts = []
    for i in range(10):
        angle = math.radians(-90 + i * 36)
        rad = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rad * math.cos(angle), cy + rad * math.sin(angle)))
    draw.polygon(pts, fill=color, outline=outline)


def draw_chevron(draw, cx, cy, w, h, color, thickness=3):
    """V자 셰브론 (계급장)"""
    pts = [
        (cx - w//2, cy - h//3),
        (cx, cy + h//3),
        (cx + w//2, cy - h//3),
    ]
    draw.line(pts, fill=color, width=thickness, joint="curve")


def draw_laurel(img, cx, cy, r, color):
    """월계관 (좌우 잎)"""
    layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    for side in [-1, 1]:
        for i in range(5):
            angle = math.radians(-60 + i * 25)
            lx = cx + side * (r + 4) * math.cos(angle)
            ly = cy - 5 + (r - 5) * math.sin(angle) - i * 2
            # 잎 모양 (작은 타원)
            leaf_angle = -30 + i * 10 if side == -1 else 30 - i * 10
            leaf_w, leaf_h = 6, 3
            bbox = [lx - leaf_w, ly - leaf_h, lx + leaf_w, ly + leaf_h]
            d.ellipse(bbox, fill=(*color, 180))

    return Image.alpha_composite(img, layer)


def draw_wings(img, cx, cy, r, color):
    """작은 날개 (좌우)"""
    layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    for side in [-1, 1]:
        wing_x = cx + side * (r + 8)
        # 3개의 깃털
        for i in range(3):
            fy = cy - 5 + i * 6
            fw = 8 + (2 - i) * 3  # 위가 더 길게
            fh = 3
            x1 = wing_x if side == 1 else wing_x - fw
            x2 = wing_x + fw if side == 1 else wing_x
            d.ellipse([x1, fy - fh, x2, fy + fh], fill=(*color, 160))

    return Image.alpha_composite(img, layer)


def generate_tier(tier_key, division):
    """
    tier_key: bronze~challenger
    division: 2 (하위=II), 1 (상위=I), 0 (마스터/챌린저=디비전 없음)
    """
    t = TIERS[tier_key]
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = CENTER, CENTER
    ball_r = 28

    # 왕관/불꽃 있으면 볼 위치 조정
    has_crown = t.get("crown", False)
    has_flame = t.get("flame", False)
    if has_crown:
        cy += 4

    # ── 글로우 ──
    if t.get("glow"):
        glow_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow_layer)
        gc = t["glow"]
        for gr in range(ball_r + 18, ball_r + 6, -1):
            alpha = int(gc[3] * (1 - (gr - ball_r - 6) / 12))
            gd.ellipse([cx-gr, cy-gr, cx+gr, cy+gr], fill=(gc[0], gc[1], gc[2], alpha))
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(5))
        img = Image.alpha_composite(img, glow_layer)
        draw = ImageDraw.Draw(img)

    # ── 날개 ──
    if t.get("wings"):
        img = draw_wings(img, cx, cy, ball_r, t["chevron_color"])
        draw = ImageDraw.Draw(img)

    # ── 월계관 ──
    if t.get("laurel"):
        img = draw_laurel(img, cx, cy, ball_r, t["chevron_color"])
        draw = ImageDraw.Draw(img)

    # ── 포켓볼 본체 ──
    # 외곽선
    draw.ellipse([cx-ball_r-2, cy-ball_r-2, cx+ball_r+2, cy+ball_r+2], fill=t["outline"])
    # 상단
    draw.pieslice([cx-ball_r, cy-ball_r, cx+ball_r, cy+ball_r], 180, 360, fill=t["top"])
    # 하단
    draw.pieslice([cx-ball_r, cy-ball_r, cx+ball_r, cy+ball_r], 0, 180, fill=t["bottom"])
    # 밴드
    band_h = 6
    draw.rectangle([cx-ball_r-1, cy-band_h//2, cx+ball_r+1, cy+band_h//2], fill=t["band"])
    # 버튼
    draw.ellipse([cx-9, cy-9, cx+9, cy+9], fill=t["btn_out"])
    draw.ellipse([cx-5, cy-5, cx+5, cy+5], fill=t["btn_in"])

    # ── 하이라이트 ──
    hl = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hl)
    hd.ellipse([cx-15, cy-ball_r+5, cx-6, cy-ball_r+13], fill=(255, 255, 255, 110))
    hd.ellipse([cx-4, cy-ball_r+12, cx, cy-ball_r+16], fill=(255, 255, 255, 70))
    img = Image.alpha_composite(img, hl)
    draw = ImageDraw.Draw(img)

    # ── 셰브론 + 별 (디비전 표시) ──
    if division > 0:
        star_y = cy + ball_r + 10
        star_size = 5
        sc = t["star_color"]

        if division == 2:  # II — 별 1개
            draw_star(draw, cx, star_y, star_size, sc, outline=t["outline"])
        elif division == 1:  # I — 별 2개
            draw_star(draw, cx - 8, star_y, star_size, sc, outline=t["outline"])
            draw_star(draw, cx + 8, star_y, star_size, sc, outline=t["outline"])

    # ── 왕관 ──
    if has_crown:
        crown_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        cd = ImageDraw.Draw(crown_layer)
        crown_y = cy - ball_r - 6
        cc = (255, 200, 50) if tier_key == "master" else (255, 170, 30)
        pts = [
            (cx - 16, crown_y + 12),
            (cx - 18, crown_y),
            (cx - 9, crown_y + 6),
            (cx, crown_y - 5),
            (cx + 9, crown_y + 6),
            (cx + 18, crown_y),
            (cx + 16, crown_y + 12),
        ]
        cd.polygon(pts, fill=cc)
        # 왕관 보석
        cd.ellipse([cx-2, crown_y+1, cx+2, crown_y+5], fill=(255, 50, 50))
        cd.ellipse([cx-11, crown_y+3, cx-8, crown_y+6], fill=(50, 200, 255))
        cd.ellipse([cx+8, crown_y+3, cx+11, crown_y+6], fill=(50, 200, 255))
        img = Image.alpha_composite(img, crown_layer)
        draw = ImageDraw.Draw(img)

    # ── 불꽃 (챌린저) ──
    if has_flame:
        fl = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        fd = ImageDraw.Draw(fl)
        flames = [
            (-ball_r - 6, -8, 10), (-ball_r - 2, -18, 7), (-ball_r + 2, 5, 8),
            (ball_r + 6, -8, 10), (ball_r + 2, -18, 7), (ball_r - 2, 5, 8),
            (0, -ball_r - 14, 8), (-10, -ball_r - 10, 6), (10, -ball_r - 10, 6),
        ]
        for fx, fy, fs in flames:
            p = [(cx+fx, cy+fy), (cx+fx-fs//2, cy+fy+fs), (cx+fx+fs//2, cy+fy+fs)]
            fd.polygon(p, fill=(255, 100, 20, 140))
            p2 = [(cx+fx, cy+fy+2), (cx+fx-fs//3, cy+fy+fs-1), (cx+fx+fs//3, cy+fy+fs-1)]
            fd.polygon(p2, fill=(255, 200, 50, 170))
        fl = fl.filter(ImageFilter.GaussianBlur(1))
        img = Image.alpha_composite(img, fl)
        draw = ImageDraw.Draw(img)

    # ── 스파클 (골드 이상) ──
    if tier_key in ("gold", "platinum", "diamond", "master", "challenger"):
        sp = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sp)
        import random
        random.seed(hash(tier_key) + division)
        for _ in range(4):
            sx = cx + random.randint(-ball_r - 5, ball_r + 5)
            sy = cy + random.randint(-ball_r - 5, ball_r + 5)
            slen = random.randint(2, 4)
            sd.line([(sx-slen, sy), (sx+slen, sy)], fill=(255, 255, 255, 200), width=1)
            sd.line([(sx, sy-slen), (sx, sy+slen)], fill=(255, 255, 255, 200), width=1)
        img = Image.alpha_composite(img, sp)

    return img


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)

    all_imgs = []
    labels = []

    div_tiers = ["bronze", "silver", "gold", "platinum", "diamond"]
    no_div_tiers = ["master", "challenger"]

    # 디비전 있는 티어: II, I
    for tier_key in div_tiers:
        for div in [2, 1]:
            img = generate_tier(tier_key, div)
            div_name = "II" if div == 2 else "I"
            fname = f"tier_{tier_key}_{div_name.lower()}.png"
            img.save(os.path.join(OUT, fname), "PNG")
            all_imgs.append(img)
            name_kr = {"bronze":"브론즈","silver":"실버","gold":"골드",
                       "platinum":"플래티넘","diamond":"다이아"}[tier_key]
            labels.append(f"{name_kr} {div_name}")
            print(f"  {tier_key} {div_name:3s} -> {fname}")

    # 디비전 없는 티어
    for tier_key in no_div_tiers:
        img = generate_tier(tier_key, 0)
        fname = f"tier_{tier_key}.png"
        img.save(os.path.join(OUT, fname), "PNG")
        all_imgs.append(img)
        name_kr = {"master":"마스터","challenger":"챌린저"}[tier_key]
        labels.append(name_kr)
        print(f"  {tier_key:12s} -> {fname}")

    # ── 프리뷰 시트 (2줄) ──
    cols = 6
    rows_count = math.ceil(len(all_imgs) / cols)
    pad = 8
    cell_w = SIZE + pad
    cell_h = SIZE + 28
    sheet_w = cols * cell_w + pad
    sheet_h = rows_count * cell_h + pad
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (30, 30, 50, 255))
    sd = ImageDraw.Draw(sheet)

    try:
        font = ImageFont.truetype("malgun.ttf", 11)
    except:
        font = ImageFont.load_default()

    for idx, (im, label) in enumerate(zip(all_imgs, labels)):
        col = idx % cols
        row = idx // cols
        x = pad + col * cell_w
        y = pad + row * cell_h
        sheet.paste(im, (x, y), im)
        bbox = sd.textbbox((0, 0), label, font=font)
        tw = bbox[2] - bbox[0]
        sd.text((x + SIZE//2 - tw//2, y + SIZE + 2), label,
                fill=(255, 255, 255), font=font)

    sheet_path = os.path.join(OUT, "_preview_sheet.png")
    sheet.save(sheet_path, "PNG")
    print(f"\n  Preview -> {sheet_path}")
    print("Done!")
