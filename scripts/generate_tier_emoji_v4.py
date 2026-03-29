"""
랭크전 티어 이모지 v4 — 레퍼런스 스타일 재현
포켓볼 크게, 날개/월계관 디테일, M마크, 챌린저 광선
100x100 RGBA PNG
"""
from PIL import Image, ImageDraw, ImageFont
import math, os

SIZE = 100
CX, CY_BASE = 50, 50
OUT = r"C:\Users\Administrator\Desktop\pokemon-bot\assets\tier_emoji_v4"

# ── 색상 정의 ──
TIERS = {
    "bronze": {
        "top": [(190, 130, 75), (160, 100, 55), (140, 80, 40)],
        "bottom": [(230, 180, 120), (210, 160, 100), (190, 140, 85)],
        "band": (150, 100, 55),
        "btn_out": (150, 100, 55), "btn_in": (210, 155, 90),
        "outline": (110, 70, 35),
        "star_c": (210, 165, 90), "star_ol": (150, 100, 55),
        "accent": (170, 120, 65),
        "wing": False, "laurel": True, "crown": False, "mark": None, "rays": False,
    },
    "silver": {
        "top": [(190, 195, 210), (170, 175, 190), (150, 158, 175)],
        "bottom": [(225, 230, 240), (205, 210, 222), (185, 192, 208)],
        "band": (155, 162, 178),
        "btn_out": (155, 162, 178), "btn_in": (200, 208, 225),
        "outline": (115, 125, 145),
        "star_c": (215, 222, 238), "star_ol": (155, 162, 178),
        "accent": (170, 178, 198),
        "wing": False, "laurel": True, "crown": False, "mark": None, "rays": False,
    },
    "gold": {
        "top": [(245, 205, 50), (225, 180, 30), (200, 155, 15)],
        "bottom": [(255, 240, 150), (245, 225, 120), (230, 205, 95)],
        "band": (205, 165, 25),
        "btn_out": (205, 165, 25), "btn_in": (245, 210, 60),
        "outline": (160, 120, 10),
        "star_c": (255, 230, 70), "star_ol": (190, 150, 15),
        "accent": (220, 180, 35),
        "wing": False, "laurel": True, "crown": False, "mark": None, "rays": False,
    },
    "platinum": {
        "top": [(60, 195, 195), (40, 165, 170), (25, 140, 148)],
        "bottom": [(130, 215, 210), (100, 190, 188), (80, 168, 168)],
        "band": (35, 145, 155),
        "btn_out": (35, 145, 155), "btn_in": (80, 195, 200),
        "outline": (20, 110, 120),
        "star_c": (120, 225, 228), "star_ol": (35, 145, 155),
        "accent": (55, 170, 178),
        "wing": True, "laurel": False, "crown": False, "mark": None, "rays": False,
        "wing_c": [(65, 180, 180), (45, 155, 158), (30, 130, 135)],
    },
    "diamond": {
        "top": [(75, 135, 235), (55, 110, 210), (40, 88, 185)],
        "bottom": [(155, 195, 255), (130, 170, 240), (110, 148, 218)],
        "band": (48, 98, 200),
        "btn_out": (48, 98, 200), "btn_in": (100, 158, 248),
        "outline": (32, 68, 165),
        "star_c": [(160, 200, 255), (120, 170, 240)], "star_ol": (48, 98, 200),
        "accent": (65, 120, 220),
        "wing": True, "laurel": True, "crown": False, "mark": None, "rays": False,
        "wing_c": [(80, 140, 230), (55, 110, 205), (38, 85, 178)],
    },
    "master": {
        "top": [(180, 90, 210), (155, 65, 190), (130, 45, 165)],
        "bottom": [(210, 155, 235), (190, 130, 215), (168, 108, 195)],
        "band": (125, 50, 170),
        "btn_out": (125, 50, 170), "btn_in": (175, 105, 215),
        "outline": (90, 30, 135),
        "star_c": (220, 170, 252), "star_ol": (125, 50, 170),
        "accent": (150, 70, 190),
        "wing": True, "laurel": True, "crown": True, "mark": "M", "rays": False,
        "wing_c": [(165, 85, 200), (140, 60, 178), (118, 42, 155)],
        "crown_c": (255, 210, 60),
    },
    "challenger": {
        "top": [(35, 30, 65), (25, 20, 50), (18, 15, 38)],
        "bottom": [(55, 50, 95), (42, 38, 78), (32, 28, 62)],
        "band": (225, 175, 30),
        "btn_out": (225, 110, 30), "btn_in": (255, 165, 55),
        "outline": (190, 145, 15),
        "star_c": (255, 218, 75), "star_ol": (205, 155, 20),
        "accent": (235, 185, 35),
        "wing": True, "laurel": True, "crown": True, "mark": "M", "rays": True,
        "wing_c": [(225, 185, 45), (200, 158, 28), (175, 135, 18)],
        "crown_c": (255, 200, 45),
    },
}


def draw_gradient_circle_half(draw, cx, cy, r, colors, is_top=True):
    """반원에 그라데이션 (3단계 밴드)"""
    if is_top:
        for i, band_h in enumerate(range(r, 0, -r // 3)):
            c = colors[min(i, len(colors) - 1)]
            y_start = cy - band_h
            draw.pieslice([cx - r, cy - r, cx + r, cy + r], 180, 360, fill=c)
    else:
        draw.pieslice([cx - r, cy - r, cx + r, cy + r], 0, 180, fill=colors[0])
        # 하단 밝은 부분
        inner_r = r * 2 // 3
        draw.pieslice([cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r],
                      0, 180, fill=colors[1])


def draw_star(draw, cx, cy, r_out, r_in, fill, outline):
    pts = []
    for i in range(10):
        a = math.radians(-90 + i * 36)
        rad = r_out if i % 2 == 0 else r_in
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    draw.polygon(pts, fill=fill, outline=outline)


def draw_wing_detailed(draw, cx, cy, side, colors):
    """디테일한 날개 — 3겹 깃털"""
    feathers = [
        # (angle_offset, length, width, color_idx)
        (-25, 22, 6, 0),
        (-10, 20, 6, 0),
        (5, 17, 5, 1),
        (18, 14, 5, 1),
        (30, 10, 4, 2),
    ]
    for angle_off, length, width, ci in feathers:
        a = math.radians(angle_off)
        # 깃털 시작점
        sx = cx
        sy = cy
        # 깃털 끝점
        ex = cx + side * length
        ey = cy + length * math.sin(a) * 0.3

        # 깃털 = 길쭉한 다각형
        perp_x = -math.sin(a) * width * 0.3
        perp_y = math.cos(a) * width * 0.5

        pts = [
            (sx, sy - 1),
            (ex + side * 2, ey - perp_y),
            (ex + side * 4, ey),
            (ex + side * 2, ey + perp_y),
            (sx, sy + 1),
        ]
        c = colors[min(ci, len(colors) - 1)]
        draw.polygon(pts, fill=c)

    # 날개 루트 (볼과 연결)
    draw.ellipse([cx - 3, cy - 5, cx + 3, cy + 5], fill=colors[0])


def draw_laurel(draw, cx, cy, r, color, outline_c):
    """월계관 — 양쪽 잎"""
    for side in [-1, 1]:
        for i in range(5):
            angle = math.radians(40 + i * 25)
            dist = r - 5 + i * 3
            lx = cx + side * (12 + i * 3) * math.cos(angle) * 0.4
            ly = cy + r - 8 - i * 5

            # 잎 모양 (뾰족한 타원)
            leaf_w = 5
            leaf_h = 3
            pts = [
                (lx, ly - leaf_h - 1),
                (lx + side * leaf_w, ly),
                (lx, ly + leaf_h - 1),
                (lx - side * (leaf_w * 0.3), ly - 1),
            ]
            draw.polygon(pts, fill=color, outline=outline_c)


def draw_crown_detailed(draw, cx, cy, color):
    """디테일한 왕관"""
    # 왕관 몸체
    body = [
        (cx - 18, cy + 12),
        (cx - 20, cy - 2),
        (cx - 11, cy + 4),
        (cx - 5, cy - 6),
        (cx, cy - 1),
        (cx + 5, cy - 6),
        (cx + 11, cy + 4),
        (cx + 20, cy - 2),
        (cx + 18, cy + 12),
    ]
    # 어두운 테두리
    draw.polygon(body, fill=color,
                 outline=(max(0, color[0] - 40), max(0, color[1] - 40), max(0, color[2] - 20)))

    # 밴드 (왕관 하단)
    draw.rectangle([cx - 17, cy + 9, cx + 17, cy + 12],
                   fill=(max(0, color[0] - 30), max(0, color[1] - 30), max(0, color[2] - 10)))

    # 보석
    draw.ellipse([cx - 3, cy + 1, cx + 3, cy + 7], fill=(255, 55, 55))
    draw.ellipse([cx - 13, cy + 3, cx - 9, cy + 7], fill=(55, 200, 255))
    draw.ellipse([cx + 9, cy + 3, cx + 13, cy + 7], fill=(55, 200, 255))
    # 꼭대기 점
    for px in [cx - 20, cx - 5, cx + 5, cx + 20]:
        draw.ellipse([px - 2, cy - 7, px + 2, cy - 3], fill=(255, 230, 100))


def draw_rays(draw, cx, cy, r):
    """챌린저 금빛 광선"""
    ray_color = (255, 210, 60, 200)
    ray_color2 = (255, 180, 30, 150)
    for angle_deg in range(0, 360, 30):
        a = math.radians(angle_deg)
        # 광선 = 가느다란 삼각형
        inner_r = r + 5
        outer_r = r + 18
        half_w = math.radians(4)

        pts = [
            (cx + inner_r * math.cos(a), cy + inner_r * math.sin(a)),
            (cx + outer_r * math.cos(a - half_w), cy + outer_r * math.sin(a - half_w)),
            (cx + outer_r * math.cos(a + half_w), cy + outer_r * math.sin(a + half_w)),
        ]
        c = ray_color if angle_deg % 60 == 0 else ray_color2
        draw.polygon(pts, fill=c[:3])


def generate(tier_key, division):
    t = TIERS[tier_key]
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = CX, CY_BASE
    ball_r = 30  # 큰 포켓볼

    has_crown = t.get("crown", False)
    has_wings = t.get("wing", False)
    has_laurel = t.get("laurel", False)
    has_rays = t.get("rays", False)

    # 위치 조정
    if has_crown:
        cy += 6
        ball_r = 27
    if division > 0:
        cy -= 4

    # ── 광선 (챌린저, 가장 뒤) ──
    if has_rays:
        draw_rays(draw, cx, cy, ball_r)

    # ── 날개 ──
    if has_wings:
        wc = t.get("wing_c", [(150, 150, 150)] * 3)
        draw_wing_detailed(draw, cx - ball_r + 2, cy, -1, wc)
        draw_wing_detailed(draw, cx + ball_r - 2, cy, 1, wc)

    # ── 월계관 ──
    if has_laurel and not has_wings:
        draw_laurel(draw, cx, cy, ball_r, t["accent"], t["outline"])

    # ── 포켓볼 본체 ──
    # 외곽 (두꺼운 테두리)
    draw.ellipse([cx-ball_r-3, cy-ball_r-3, cx+ball_r+3, cy+ball_r+3], fill=t["outline"])

    # 상단 반구
    draw.pieslice([cx-ball_r, cy-ball_r, cx+ball_r, cy+ball_r], 180, 360, fill=t["top"][0])
    # 상단 어두운 가장자리
    draw.arc([cx-ball_r, cy-ball_r, cx+ball_r, cy+ball_r], 180, 360,
             fill=t["top"][2], width=3)

    # 하단 반구
    draw.pieslice([cx-ball_r, cy-ball_r, cx+ball_r, cy+ball_r], 0, 180, fill=t["bottom"][0])
    # 하단 밝은 중심
    draw.pieslice([cx-ball_r+8, cy-ball_r+8, cx+ball_r-8, cy+ball_r-8],
                  0, 180, fill=t["bottom"][1])

    # 밴드
    band_h = 4
    draw.rectangle([cx-ball_r-1, cy-band_h, cx+ball_r+1, cy+band_h], fill=t["band"])

    # 버튼
    draw.ellipse([cx-10, cy-10, cx+10, cy+10], fill=t["btn_out"])
    draw.ellipse([cx-7, cy-7, cx+7, cy+7], fill=t["btn_in"])
    draw.ellipse([cx-4, cy-4, cx+4, cy+4], fill=t["btn_out"])
    # 버튼 하이라이트
    draw.ellipse([cx-3, cy-4, cx, cy-1], fill=(255, 255, 255, 140))

    # 볼 하이라이트 (큰 반사광)
    hl_x, hl_y = cx - ball_r // 3, cy - ball_r // 2
    draw.ellipse([hl_x - 6, hl_y - 4, hl_x + 2, hl_y + 2], fill=(255, 255, 255, 130))
    draw.ellipse([hl_x + 3, hl_y + 1, hl_x + 6, hl_y + 4], fill=(255, 255, 255, 80))

    # ── M 마크 (마스터/챌린저) ──
    if t.get("mark"):
        try:
            font = ImageFont.truetype("arial.ttf", 18)
        except:
            try:
                font = ImageFont.truetype("arialbd.ttf", 18)
            except:
                font = ImageFont.load_default()
        m = t["mark"]
        bb = draw.textbbox((0, 0), m, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        # 상단 반구 중앙에
        draw.text((cx - tw // 2, cy - ball_r // 2 - th // 2 - 1), m,
                  fill=(255, 255, 255, 220), font=font)

    # ── 왕관 ──
    if has_crown:
        crown_c = t.get("crown_c", (255, 200, 50))
        draw_crown_detailed(draw, cx, cy - ball_r - 4, crown_c)

    # ── 월계관 (날개 있는 경우, 볼 위에 오버레이) ──
    if has_laurel and has_wings:
        draw_laurel(draw, cx, cy, ball_r, t["accent"], t["outline"])

    # ── 디비전 별 ──
    if division > 0:
        star_y = cy + ball_r + 11
        sr, sir = 6, 2.8
        sc = t["star_c"]
        if isinstance(sc, list):
            sc = sc[0]
        sol = t["star_ol"]

        if division == 2:
            draw_star(draw, cx, star_y, sr, sir, sc, sol)
        elif division == 1:
            draw_star(draw, cx - 10, star_y, sr, sir, sc, sol)
            draw_star(draw, cx + 10, star_y, sr, sir, sc, sol)

    return img


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)

    all_imgs, labels = [], []
    name_kr = {
        "bronze": "브론즈", "silver": "실버", "gold": "골드",
        "platinum": "플래티넘", "diamond": "다이아",
        "master": "마스터", "challenger": "챌린저",
    }

    div_tiers = ["bronze", "silver", "gold", "platinum", "diamond"]
    for tk in div_tiers:
        for div in [2, 1]:
            img = generate(tk, div)
            dn = "II" if div == 2 else "I"
            img.save(os.path.join(OUT, f"tier_{tk}_{dn.lower()}.png"), "PNG")
            all_imgs.append(img)
            labels.append(f"{name_kr[tk]} {dn}")
            print(f"  {tk} {dn}")

    for tk in ["master", "challenger"]:
        img = generate(tk, 0)
        img.save(os.path.join(OUT, f"tier_{tk}.png"), "PNG")
        all_imgs.append(img)
        labels.append(name_kr[tk])
        print(f"  {tk}")

    # 프리뷰
    cols = 6
    rows = math.ceil(len(all_imgs) / cols)
    pad = 10
    cell_w, cell_h = SIZE + pad, SIZE + 30
    sw, sh = cols * (SIZE + 10) + 10, rows * (SIZE + 30) + 10
    sheet = Image.new("RGBA", (sw, sh), (30, 30, 50, 255))
    sd = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("malgun.ttf", 12)
    except:
        font = ImageFont.load_default()

    for i, (im, lb) in enumerate(zip(all_imgs, labels)):
        c, r = i % cols, i // cols
        x, y = 10 + c * (SIZE + 10), 10 + r * (SIZE + 30)
        sheet.paste(im, (x, y), im)
        bb = sd.textbbox((0, 0), lb, font=font)
        sd.text((x + SIZE // 2 - (bb[2] - bb[0]) // 2, y + SIZE + 3), lb,
                fill=(255, 255, 255), font=font)

    sheet.save(os.path.join(OUT, "_preview.png"), "PNG")
    print(f"\n  Preview → {OUT}\\_preview.png")
