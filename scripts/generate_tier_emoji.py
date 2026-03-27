"""
랭크전 티어 커스텀 이모지 생성 — 포켓볼 변형 (화려한 버전)
100x100 RGBA PNG, 텔레그램 커스텀 이모지용
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math, os

SIZE = 100
CENTER = SIZE // 2
OUT = r"C:\Users\Administrator\Desktop\pokemon-bot\assets\tier_emoji"

TIERS = {
    "bronze": {
        "top": (180, 120, 70),
        "bottom": (220, 170, 110),
        "band": (140, 90, 50),
        "button_outer": (140, 90, 50),
        "button_inner": (200, 140, 80),
        "outline": (120, 75, 40),
        "glow": None,
        "crown": False,
        "sparkle": False,
        "label": None,
    },
    "silver": {
        "top": (180, 185, 195),
        "bottom": (210, 215, 225),
        "band": (140, 148, 160),
        "button_outer": (140, 148, 160),
        "button_inner": (190, 195, 205),
        "outline": (120, 128, 140),
        "glow": None,
        "crown": False,
        "sparkle": False,
        "label": None,
    },
    "gold": {
        "top": (240, 200, 50),
        "bottom": (255, 235, 150),
        "band": (200, 160, 30),
        "button_outer": (200, 160, 30),
        "button_inner": (240, 200, 50),
        "outline": (170, 130, 20),
        "glow": None,
        "crown": False,
        "sparkle": True,
        "label": None,
    },
    "platinum": {
        "top": (60, 200, 210),
        "bottom": (170, 230, 240),
        "band": (40, 160, 180),
        "button_outer": (40, 160, 180),
        "button_inner": (80, 210, 220),
        "outline": (30, 130, 150),
        "glow": (100, 220, 240, 40),
        "crown": False,
        "sparkle": True,
        "label": None,
    },
    "diamond": {
        "top": (80, 140, 240),
        "bottom": (160, 200, 255),
        "band": (50, 100, 200),
        "button_outer": (50, 100, 200),
        "button_inner": (100, 160, 255),
        "outline": (40, 80, 180),
        "glow": (100, 160, 255, 50),
        "crown": False,
        "sparkle": True,
        "label": None,
    },
    "master": {
        "top": (160, 80, 200),
        "bottom": (200, 150, 230),
        "band": (120, 50, 170),
        "button_outer": (120, 50, 170),
        "button_inner": (170, 100, 210),
        "outline": (100, 40, 150),
        "glow": (180, 100, 255, 60),
        "crown": True,
        "sparkle": True,
        "label": "M",
    },
    "challenger": {
        "top": (30, 30, 60),
        "bottom": (50, 50, 90),
        "band": (220, 170, 30),
        "button_outer": (220, 100, 30),
        "button_inner": (255, 160, 50),
        "outline": (200, 150, 20),
        "glow": (255, 180, 50, 70),
        "crown": True,
        "sparkle": True,
        "label": None,
        "flame": True,
    },
}


def draw_pokeball(t, tier_key):
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = CENTER, CENTER + 2  # 약간 아래로 (왕관 공간)
    r = 38  # 볼 반지름

    # ── 글로우 (있으면) ──
    if t.get("glow"):
        glow_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow_layer)
        gc = t["glow"]
        for gr in range(r+15, r+5, -1):
            alpha = int(gc[3] * (1 - (gr - r - 5) / 10))
            gd.ellipse([cx-gr, cy-gr, cx+gr, cy+gr], fill=(gc[0], gc[1], gc[2], alpha))
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(4))
        img = Image.alpha_composite(img, glow_layer)
        draw = ImageDraw.Draw(img)

    # ── 외곽선 ──
    ol = t["outline"]
    draw.ellipse([cx-r-2, cy-r-2, cx+r+2, cy+r+2], fill=ol)

    # ── 상단 반구 ──
    draw.pieslice([cx-r, cy-r, cx+r, cy+r], 180, 360, fill=t["top"])

    # ── 하단 반구 ──
    draw.pieslice([cx-r, cy-r, cx+r, cy+r], 0, 180, fill=t["bottom"])

    # ── 중앙 밴드 ──
    band_h = 7
    draw.rectangle([cx-r-1, cy-band_h//2, cx+r+1, cy+band_h//2], fill=t["band"])

    # ── 중앙 버튼 ──
    btn_r = 10
    draw.ellipse([cx-btn_r, cy-btn_r, cx+btn_r, cy+btn_r], fill=t["button_outer"])
    btn_inner = 6
    draw.ellipse([cx-btn_inner, cy-btn_inner, cx+btn_inner, cy+btn_inner], fill=t["button_inner"])

    # ── 하이라이트 (상단 반사) ──
    hl_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hl_layer)
    # 큰 반사
    hd.ellipse([cx-18, cy-r+6, cx-6, cy-r+16], fill=(255, 255, 255, 120))
    # 작은 반사
    hd.ellipse([cx-5, cy-r+14, cx, cy-r+19], fill=(255, 255, 255, 80))
    img = Image.alpha_composite(img, hl_layer)
    draw = ImageDraw.Draw(img)

    # ── 상단 그라데이션 (입체감) ──
    grad_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    grd = ImageDraw.Draw(grad_layer)
    for i in range(r):
        alpha = int(30 * (i / r))
        grd.arc([cx-r+i//2, cy-r+i//2, cx+r-i//2, cy+r-i//2], 180, 360,
                fill=(255, 255, 255, alpha), width=1)
    img = Image.alpha_composite(img, grad_layer)
    draw = ImageDraw.Draw(img)

    # ── 라벨 (M 등) ──
    if t.get("label"):
        try:
            font = ImageFont.truetype("arial.ttf", 16)
        except:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), t["label"], font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((cx - tw//2, cy - r//2 - th//2 - 2), t["label"],
                  fill=(255, 255, 255, 230), font=font)

    # ── 왕관 (마스터/챌린저) ──
    if t.get("crown"):
        crown_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        cd = ImageDraw.Draw(crown_layer)
        crown_y = cy - r - 8
        crown_color = (255, 200, 50) if tier_key == "master" else (255, 160, 30)
        # 왕관 베이스
        pts = [
            (cx-14, crown_y+10),
            (cx-16, crown_y),
            (cx-8, crown_y+5),
            (cx, crown_y-4),
            (cx+8, crown_y+5),
            (cx+16, crown_y),
            (cx+14, crown_y+10),
        ]
        cd.polygon(pts, fill=crown_color)
        # 보석
        cd.ellipse([cx-2, crown_y-1, cx+2, crown_y+3], fill=(255, 50, 50))
        cd.ellipse([cx-10, crown_y+2, cx-7, crown_y+5], fill=(50, 200, 255))
        cd.ellipse([cx+7, crown_y+2, cx+10, crown_y+5], fill=(50, 200, 255))
        img = Image.alpha_composite(img, crown_layer)
        draw = ImageDraw.Draw(img)

    # ── 불꽃 (챌린저) ──
    if t.get("flame"):
        flame_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        fd = ImageDraw.Draw(flame_layer)
        # 좌측 불꽃
        for fx, fy, fs in [(-r-5, -5, 12), (-r-2, -15, 8), (-r, 8, 10),
                           (r+5, -5, 12), (r+2, -15, 8), (r, 8, 10)]:
            flame_pts = [
                (cx+fx, cy+fy),
                (cx+fx-fs//2, cy+fy+fs),
                (cx+fx+fs//2, cy+fy+fs),
            ]
            fd.polygon(flame_pts, fill=(255, 100, 20, 150))
            inner_pts = [
                (cx+fx, cy+fy+3),
                (cx+fx-fs//3, cy+fy+fs-2),
                (cx+fx+fs//3, cy+fy+fs-2),
            ]
            fd.polygon(inner_pts, fill=(255, 200, 50, 180))
        flame_layer = flame_layer.filter(ImageFilter.GaussianBlur(1))
        img = Image.alpha_composite(img, flame_layer)
        draw = ImageDraw.Draw(img)

    # ── 스파클 ──
    if t.get("sparkle"):
        spark_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        sd = ImageDraw.Draw(spark_layer)
        import random
        random.seed(hash(tier_key))
        sparkle_positions = [(cx+random.randint(-r-8, r+8), cy+random.randint(-r-8, r+8))
                            for _ in range(5)]
        for sx, sy in sparkle_positions:
            # 4꼭지 별
            slen = random.randint(3, 5)
            sd.line([(sx-slen, sy), (sx+slen, sy)], fill=(255, 255, 255, 200), width=1)
            sd.line([(sx, sy-slen), (sx, sy+slen)], fill=(255, 255, 255, 200), width=1)
            sd.point((sx, sy), fill=(255, 255, 255, 255))
        img = Image.alpha_composite(img, spark_layer)

    return img


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)

    for tier_key, t in TIERS.items():
        img = draw_pokeball(t, tier_key)
        path = os.path.join(OUT, f"tier_{tier_key}.png")
        img.save(path, "PNG")
        print(f"  {tier_key:12s} -> {path}")

    # 프리뷰 시트 생성
    cols = len(TIERS)
    sheet_w = cols * (SIZE + 10) + 10
    sheet_h = SIZE + 40
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (30, 30, 50, 255))
    sd = ImageDraw.Draw(sheet)

    try:
        font = ImageFont.truetype("malgun.ttf", 12)
    except:
        font = ImageFont.load_default()

    names = ["브론즈", "실버", "골드", "플래티넘", "다이아", "마스터", "챌린저"]
    for i, (tier_key, t) in enumerate(TIERS.items()):
        x = 10 + i * (SIZE + 10)
        img = draw_pokeball(t, tier_key)
        sheet.paste(img, (x, 5), img)
        # 라벨
        bbox = sd.textbbox((0, 0), names[i], font=font)
        tw = bbox[2] - bbox[0]
        sd.text((x + SIZE//2 - tw//2, SIZE + 10), names[i], fill=(255, 255, 255), font=font)

    sheet_path = os.path.join(OUT, "_preview_sheet.png")
    sheet.save(sheet_path, "PNG")
    print(f"\n  Preview -> {sheet_path}")
    print("Done!")
