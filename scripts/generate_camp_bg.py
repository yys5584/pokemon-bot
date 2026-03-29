"""
캠프 구역 배경 이미지 생성 — 도트풍 (Pillow)
960x540 (16:9), 타일 기반 픽셀아트
"""
from PIL import Image, ImageDraw, ImageFont
import random, os

W, H = 960, 540
TILE = 12  # 픽셀아트 느낌의 타일 사이즈

# ── 색상 팔레트 (도트풍) ──────────────────────────
PAL = {
    # 풀숲
    "grass_dark":   "#2d5a1e",
    "grass_mid":    "#3e7a2a",
    "grass_light":  "#5aad36",
    "grass_bright": "#7ecc55",
    "tree_trunk":   "#5c3a1e",
    "tree_dark":    "#1e4a0f",
    "tree_mid":     "#2d6b1a",
    "tree_light":   "#4a8f2e",
    "flower_r":     "#e84040",
    "flower_y":     "#f0d040",
    "flower_w":     "#f0eee0",
    "path":         "#c4a86a",
    "path_dark":    "#a08850",
    "sky_top":      "#4a90d9",
    "sky_mid":      "#6ab4f0",
    "sky_bot":      "#a0d8ff",
    "cloud":        "#f0f4ff",
    "cloud_shadow": "#d0dcea",
    "sun":          "#ffe070",
    "sun_glow":     "#fff4b0",
    # 호수
    "water_deep":   "#1a5276",
    "water_mid":    "#2980b9",
    "water_light":  "#5dade2",
    "water_shine":  "#aed6f1",
    "sand":         "#f0d9a0",
    "sand_dark":    "#d4b870",
    "rock":         "#7f8c8d",
    "rock_dark":    "#5d6d7e",
    "lily_pad":     "#27ae60",
    "lily_flower":  "#ff69b4",
    # 모닥불
    "night_top":    "#0a0a2e",
    "night_mid":    "#141450",
    "night_bot":    "#1e1e5a",
    "fire_core":    "#fff4a0",
    "fire_mid":     "#ff9020",
    "fire_out":     "#e84040",
    "fire_glow":    "#ff6a0030",
    "log":          "#5c3a1e",
    "log_dark":     "#3a2010",
    "star":         "#ffe070",
    "tent":         "#c0392b",
    "tent_dark":    "#962d22",
    "ground_night": "#1a1a0a",
    "ground_n2":    "#2a2a1a",
}

def hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 8:
        return tuple(int(h[i:i+2], 16) for i in (0,2,4,6))
    return tuple(int(h[i:i+2], 16) for i in (0,2,4))

def fill_tile(draw, tx, ty, color, t=TILE):
    x, y = tx * t, ty * t
    draw.rectangle([x, y, x+t-1, y+t-1], fill=color)

def rand_shade(base_hex, var=15):
    r, g, b = hex_to_rgb(base_hex)
    return (
        max(0, min(255, r + random.randint(-var, var))),
        max(0, min(255, g + random.randint(-var, var))),
        max(0, min(255, b + random.randint(-var, var))),
    )

# ── 풀숲 생성 ──────────────────────────
def generate_grass_zone(seed=42):
    random.seed(seed)
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    cols, rows = W // TILE, H // TILE  # 80x45

    # 1) 하늘 그라데이션 (상단 40%)
    sky_rows = int(rows * 0.4)
    for ty in range(sky_rows):
        ratio = ty / sky_rows
        if ratio < 0.5:
            r1, g1, b1 = hex_to_rgb(PAL["sky_top"])
            r2, g2, b2 = hex_to_rgb(PAL["sky_mid"])
            t = ratio * 2
        else:
            r1, g1, b1 = hex_to_rgb(PAL["sky_mid"])
            r2, g2, b2 = hex_to_rgb(PAL["sky_bot"])
            t = (ratio - 0.5) * 2
        r = int(r1 + (r2-r1)*t)
        g = int(g1 + (g2-g1)*t)
        b = int(b1 + (b2-b1)*t)
        for tx in range(cols):
            fill_tile(draw, tx, ty, rand_shade(f"#{r:02x}{g:02x}{b:02x}", 3))

    # 2) 구름
    clouds = [(8,3,12), (25,5,8), (50,2,14), (65,6,10)]
    for cx, cy, cw in clouds:
        for dx in range(cw):
            for dy in range(-1, 2):
                if dy == 0 or (dx > 1 and dx < cw-1):
                    px, py = cx+dx, cy+dy
                    if 0 <= px < cols and 0 <= py < rows:
                        c = PAL["cloud"] if dy <= 0 else PAL["cloud_shadow"]
                        fill_tile(draw, px, py, rand_shade(c, 5))

    # 3) 원경 나무 (하늘-풀 경계)
    tree_line_y = sky_rows - 2
    for tx in range(cols):
        h = random.choice([3, 4, 5, 4, 3, 5, 6, 4])
        for dy in range(h):
            ty = tree_line_y - dy
            if 0 <= ty < rows:
                shade = PAL["tree_dark"] if dy < 2 else PAL["tree_mid"]
                fill_tile(draw, tx, ty, rand_shade(shade, 8))

    # 4) 풀밭 (하단 60%)
    for ty in range(sky_rows, rows):
        for tx in range(cols):
            depth = (ty - sky_rows) / (rows - sky_rows)
            if depth < 0.3:
                base = PAL["grass_light"]
            elif depth < 0.7:
                base = PAL["grass_mid"]
            else:
                base = PAL["grass_dark"]
            fill_tile(draw, tx, ty, rand_shade(base, 10))

    # 5) 오솔길 (곡선)
    import math
    path_center_x = cols // 2
    for ty in range(sky_rows + 2, rows):
        depth = (ty - sky_rows) / (rows - sky_rows)
        cx = path_center_x + int(math.sin(depth * 3) * 8)
        pw = int(2 + depth * 3)
        for dx in range(-pw, pw+1):
            tx = cx + dx
            if 0 <= tx < cols:
                c = PAL["path"] if abs(dx) < pw-1 else PAL["path_dark"]
                fill_tile(draw, tx, ty, rand_shade(c, 5))

    # 6) 나무 (중경/전경)
    trees = [(5, sky_rows+4, 7), (15, sky_rows+8, 9),
             (68, sky_rows+3, 8), (72, sky_rows+10, 10),
             (22, sky_rows+15, 11), (55, sky_rows+12, 9)]
    for tree_x, tree_base, tree_h in trees:
        # 줄기
        for dy in range(tree_h//3):
            ty = tree_base - dy
            fill_tile(draw, tree_x, ty, rand_shade(PAL["tree_trunk"], 8))
            fill_tile(draw, tree_x+1, ty, rand_shade(PAL["tree_trunk"], 8))
        # 잎 (원형)
        leaf_center_y = tree_base - tree_h//3
        leaf_r = tree_h // 2
        for dy in range(-leaf_r, leaf_r+1):
            for dx in range(-leaf_r, leaf_r+1):
                if dx*dx + dy*dy <= leaf_r*leaf_r + random.randint(-2,2):
                    px, py = tree_x + dx, leaf_center_y + dy
                    if 0 <= px < cols and 0 <= py < rows:
                        if dy < -leaf_r//2:
                            c = PAL["tree_light"]
                        elif dy < 0:
                            c = PAL["tree_mid"]
                        else:
                            c = PAL["tree_dark"]
                        fill_tile(draw, px, py, rand_shade(c, 12))

    # 7) 꽃/풀 디테일
    for _ in range(60):
        tx = random.randint(0, cols-1)
        ty = random.randint(sky_rows+2, rows-1)
        c = random.choice([PAL["flower_r"], PAL["flower_y"], PAL["flower_w"], PAL["grass_bright"]])
        fill_tile(draw, tx, ty, hex_to_rgb(c))

    # 8) 풀 터프트 (밝은 포인트)
    for _ in range(40):
        tx = random.randint(0, cols-1)
        ty = random.randint(sky_rows, rows-2)
        for dx in range(random.randint(1,3)):
            if tx+dx < cols:
                fill_tile(draw, tx+dx, ty, rand_shade(PAL["grass_bright"], 15))

    return img


# ── 호수 생성 ──────────────────────────
def generate_lake_zone(seed=42):
    random.seed(seed)
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    cols, rows = W // TILE, H // TILE

    # 1) 하늘 (상단 30%)
    sky_rows = int(rows * 0.3)
    for ty in range(sky_rows):
        ratio = ty / sky_rows
        r1, g1, b1 = hex_to_rgb(PAL["sky_top"])
        r2, g2, b2 = hex_to_rgb(PAL["sky_bot"])
        r = int(r1 + (r2-r1)*ratio)
        g = int(g1 + (g2-g1)*ratio)
        b = int(b1 + (b2-b1)*ratio)
        for tx in range(cols):
            fill_tile(draw, tx, ty, rand_shade(f"#{r:02x}{g:02x}{b:02x}", 3))

    # 구름
    for cx, cy, cw in [(10,2,10), (40,4,12), (60,1,8)]:
        for dx in range(cw):
            for dy in range(-1, 1):
                px, py = cx+dx, cy+dy
                if 0 <= px < cols and 0 <= py < rows:
                    fill_tile(draw, px, py, rand_shade(PAL["cloud"], 5))

    # 2) 풀밭 (양쪽 + 뒤)
    shore_top = sky_rows
    for ty in range(shore_top, rows):
        for tx in range(cols):
            fill_tile(draw, tx, ty, rand_shade(PAL["grass_mid"], 10))

    # 3) 호수 (중앙 타원형)
    lake_cx, lake_cy = cols//2, int(rows*0.6)
    lake_rx, lake_ry = cols//3, int(rows*0.2)
    for ty in range(rows):
        for tx in range(cols):
            dx = (tx - lake_cx) / lake_rx
            dy = (ty - lake_cy) / lake_ry
            dist = dx*dx + dy*dy
            if dist < 1.0:
                if dist < 0.3:
                    c = PAL["water_deep"]
                elif dist < 0.6:
                    c = PAL["water_mid"]
                elif dist < 0.85:
                    c = PAL["water_light"]
                else:
                    c = PAL["water_shine"]
                fill_tile(draw, tx, ty, rand_shade(c, 5))

    # 4) 모래 해변 (호수 테두리)
    for ty in range(rows):
        for tx in range(cols):
            dx = (tx - lake_cx) / lake_rx
            dy = (ty - lake_cy) / lake_ry
            dist = dx*dx + dy*dy
            if 1.0 <= dist < 1.15:
                c = PAL["sand"] if dist < 1.08 else PAL["sand_dark"]
                fill_tile(draw, tx, ty, rand_shade(c, 8))

    # 5) 수련잎
    for _ in range(8):
        angle = random.uniform(0, 6.28)
        r_ratio = random.uniform(0.4, 0.8)
        lx = int(lake_cx + lake_rx * r_ratio * 0.7 * __import__('math').cos(angle))
        ly = int(lake_cy + lake_ry * r_ratio * 0.7 * __import__('math').sin(angle))
        if 0 <= lx < cols and 0 <= ly < rows:
            for ddx in range(-1, 2):
                for ddy in range(-1, 1):
                    px, py = lx+ddx, ly+ddy
                    if 0 <= px < cols and 0 <= py < rows:
                        fill_tile(draw, px, py, rand_shade(PAL["lily_pad"], 10))
            if random.random() < 0.5:
                fill_tile(draw, lx, ly-1, hex_to_rgb(PAL["lily_flower"]))

    # 6) 바위
    rocks = [(lake_cx-lake_rx-3, lake_cy-2), (lake_cx+lake_rx+1, lake_cy+3)]
    for rx, ry in rocks:
        for ddx in range(3):
            for ddy in range(2):
                px, py = rx+ddx, ry+ddy
                if 0 <= px < cols and 0 <= py < rows:
                    c = PAL["rock"] if ddy == 0 else PAL["rock_dark"]
                    fill_tile(draw, px, py, rand_shade(c, 8))

    # 7) 나무 (좌우)
    for tree_x, tree_base, tree_h in [(3, shore_top+6, 8), (8, shore_top+10, 7),
                                        (70, shore_top+5, 9), (75, shore_top+8, 7)]:
        for dy in range(tree_h//3):
            ty = tree_base - dy
            fill_tile(draw, tree_x, ty, rand_shade(PAL["tree_trunk"], 8))
        leaf_cy = tree_base - tree_h//3
        lr = tree_h//2
        for dy in range(-lr, lr+1):
            for dx in range(-lr, lr+1):
                if dx*dx + dy*dy <= lr*lr:
                    px, py = tree_x+dx, leaf_cy+dy
                    if 0 <= px < cols and 0 <= py < rows:
                        c = PAL["tree_mid"] if dy < 0 else PAL["tree_dark"]
                        fill_tile(draw, px, py, rand_shade(c, 12))

    # 8) 물 반짝임
    for _ in range(15):
        angle = random.uniform(0, 6.28)
        r_ratio = random.uniform(0.1, 0.6)
        sx = int(lake_cx + lake_rx * r_ratio * __import__('math').cos(angle))
        sy = int(lake_cy + lake_ry * r_ratio * __import__('math').sin(angle))
        if 0 <= sx < cols and 0 <= sy < rows:
            fill_tile(draw, sx, sy, (255, 255, 255))

    return img


# ── 모닥불 생성 (밤) ──────────────────────────
def generate_campfire_zone(seed=42):
    random.seed(seed)
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    cols, rows = W // TILE, H // TILE
    fire_cx, fire_cy = cols//2, int(rows*0.65)

    # 1) 밤하늘
    sky_rows = int(rows * 0.45)
    for ty in range(sky_rows):
        ratio = ty / sky_rows
        r1, g1, b1 = hex_to_rgb(PAL["night_top"])
        r2, g2, b2 = hex_to_rgb(PAL["night_mid"])
        r = int(r1 + (r2-r1)*ratio)
        g = int(g1 + (g2-g1)*ratio)
        b = int(b1 + (b2-b1)*ratio)
        for tx in range(cols):
            fill_tile(draw, tx, ty, rand_shade(f"#{r:02x}{g:02x}{b:02x}", 3))

    # 2) 별
    for _ in range(40):
        sx, sy = random.randint(0, cols-1), random.randint(0, sky_rows-1)
        brightness = random.randint(200, 255)
        fill_tile(draw, sx, sy, (brightness, brightness, random.randint(180, 255)))

    # 3) 어두운 땅
    for ty in range(sky_rows, rows):
        for tx in range(cols):
            # 모닥불 근처는 따뜻한 색
            dist = ((tx-fire_cx)**2 + (ty-fire_cy)**2) ** 0.5
            max_glow = 25
            if dist < max_glow:
                glow = 1 - dist/max_glow
                base_r = int(30 + glow * 80)
                base_g = int(25 + glow * 40)
                base_b = int(10 + glow * 10)
            else:
                base_r, base_g, base_b = 25, 22, 10
            fill_tile(draw, tx, ty, rand_shade(f"#{base_r:02x}{base_g:02x}{base_b:02x}", 5))

    # 4) 원경 나무 실루엣
    for tx in range(cols):
        h = random.choice([5, 6, 7, 8, 6, 7, 9, 7])
        for dy in range(h):
            ty = sky_rows - dy
            if 0 <= ty < rows:
                fill_tile(draw, tx, ty, rand_shade("#0a1a05", 3))

    # 5) 통나무 (불 아래)
    for dx in range(-4, 5):
        fill_tile(draw, fire_cx+dx, fire_cy+2, rand_shade(PAL["log"], 8))
        fill_tile(draw, fire_cx+dx, fire_cy+3, rand_shade(PAL["log_dark"], 8))
    # 교차 통나무
    for dx in range(-3, 4):
        fill_tile(draw, fire_cx+dx, fire_cy+1, rand_shade(PAL["log"], 10))

    # 6) 불꽃
    import math
    for dx in range(-3, 4):
        flame_h = int(6 - abs(dx) * 1.2 + random.randint(-1, 1))
        for dy in range(max(1, flame_h)):
            ty = fire_cy - dy
            if dy < 2:
                c = PAL["fire_core"]
            elif dy < 4:
                c = PAL["fire_mid"]
            else:
                c = PAL["fire_out"]
            fill_tile(draw, fire_cx+dx, ty, rand_shade(c, 15))

    # 불꽃 입자
    for _ in range(12):
        px = fire_cx + random.randint(-5, 5)
        py = fire_cy - random.randint(5, 12)
        if 0 <= px < cols and 0 <= py < rows:
            fill_tile(draw, px, py, rand_shade(PAL["fire_mid"], 20))

    # 7) 텐트 (좌측)
    tent_x, tent_base = fire_cx - 15, fire_cy + 1
    for row in range(6):
        y = tent_base - row
        w = 6 - row
        for dx in range(-w, w+1):
            px = tent_x + dx
            if 0 <= px < cols and 0 <= y < rows:
                c = PAL["tent"] if dx < 0 else PAL["tent_dark"]
                fill_tile(draw, px, y, rand_shade(c, 8))

    # 8) 앉을 자리 (돌)
    for angle_deg in [30, 150, 210, 330]:
        rad = math.radians(angle_deg)
        sx = int(fire_cx + 8 * math.cos(rad))
        sy = int(fire_cy + 4 * math.sin(rad))
        for ddx in range(2):
            for ddy in range(1):
                px, py = sx+ddx, sy+ddy
                if 0 <= px < cols and 0 <= py < rows:
                    fill_tile(draw, px, py, rand_shade(PAL["rock"], 10))

    return img


if __name__ == "__main__":
    out_dir = "assets/camp/zones"
    os.makedirs(out_dir, exist_ok=True)

    print("🌿 풀숲 생성중...")
    img = generate_grass_zone()
    img.save(f"{out_dir}/grass.png")
    print(f"   → {out_dir}/grass.png ({img.size})")

    print("💧 호수 생성중...")
    img = generate_lake_zone()
    img.save(f"{out_dir}/lake.png")
    print(f"   → {out_dir}/lake.png ({img.size})")

    print("🔥 모닥불 생성중...")
    img = generate_campfire_zone()
    img.save(f"{out_dir}/campfire.png")
    print(f"   → {out_dir}/campfire.png ({img.size})")

    print("\n✅ 완료! 3개 구역 배경 생성됨")
