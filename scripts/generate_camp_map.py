"""
캠프 맵 생성 — Tiny Swords 에셋 기반
Level 1: 모닥불 + 작은 텐트 (빈 터)
"""
from PIL import Image, ImageDraw, ImageFilter
import os, math

ASSET = r"C:\Users\Administrator\Desktop\game asset"
TS_FREE = os.path.join(ASSET, "Tiny Swords (Free Pack)")
TS_UPD = os.path.join(ASSET, "Tiny Swords (Update 010)")
OUT = r"C:\Users\Administrator\Desktop\pokemon-bot\assets\camp"

W, H = 960, 540
TILE = 64

def load(path):
    return Image.open(path).convert("RGBA")

def tile_region(sheet, x, y, w, h):
    """시트에서 특정 영역 잘라내기 (pixel coords)"""
    return sheet.crop((x, y, x+w, y+h))

def paste_center(canvas, sprite, cx, cy):
    """스프라이트를 중심점 기준으로 붙이기"""
    x = cx - sprite.width // 2
    y = cy - sprite.height // 2
    canvas.paste(sprite, (x, y), sprite)

def fill_tile(canvas, tile_img, x, y, w, h):
    """타일을 반복해서 영역 채우기"""
    tw, th = tile_img.size
    for ty in range(y, y+h, th):
        for tx in range(x, x+w, tw):
            canvas.paste(tile_img, (tx, ty), tile_img)

def generate_level1():
    """Level 1: 빈 터 — 모닥불 + 작은 집"""
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # ── 1. 배경: 물 ──
    water_bg = load(os.path.join(TS_FREE, "Terrain", "Tileset", "Water Background color.png"))
    fill_tile(canvas, water_bg, 0, 0, W, H)

    # 물 위에 약간의 변형 (어둡게/밝게 랜덤 패치)
    water_overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_w = ImageDraw.Draw(water_overlay)
    import random
    random.seed(42)
    for _ in range(30):
        rx, ry = random.randint(0, W), random.randint(0, H)
        rw, rh = random.randint(40, 120), random.randint(30, 80)
        alpha = random.randint(10, 30)
        color = random.choice([(255,255,255,alpha), (0,0,0,alpha)])
        draw_w.ellipse([rx, ry, rx+rw, ry+rh], fill=color)
    water_overlay = water_overlay.filter(ImageFilter.GaussianBlur(8))
    canvas = Image.alpha_composite(canvas, water_overlay)

    # ── 2. 잔디 섬 (중앙) ──
    tilemap = load(os.path.join(TS_FREE, "Terrain", "Tileset", "Tilemap_color1.png"))

    # 큰 잔디 fill 타일 (tilemap 좌상단 큰 블록: 0,0 ~ 192,128)
    grass_fill = tile_region(tilemap, 0, 0, 192, 128)

    # 섬 영역 정의 (중앙에 큰 플랫폼)
    island_x, island_y = 120, 80
    island_w, island_h = 720, 400

    # 잔디 채우기
    island_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for ty in range(island_y, island_y + island_h, grass_fill.height):
        for tx in range(island_x, island_x + island_w, grass_fill.width):
            island_layer.paste(grass_fill, (tx, ty), grass_fill)

    # 섬 마스크 (둥근 직사각형)
    mask = Image.new("L", (W, H), 0)
    mask_draw = ImageDraw.Draw(mask)
    r = 60  # 코너 라운드
    mask_draw.rounded_rectangle(
        [island_x, island_y, island_x+island_w, island_y+island_h],
        radius=r, fill=255
    )
    island_layer.putalpha(mask)
    canvas = Image.alpha_composite(canvas, island_layer)

    # ── 3. 절벽 테두리 ──
    # cliff 타일 (tilemap 우하단: elevation)
    cliff_tile = tile_region(tilemap, 320, 192, 64, 64)
    cliff_narrow = tile_region(tilemap, 384, 192, 64, 64)

    # 하단 절벽 (그림자 느낌)
    cliff_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cliff_h = 48
    for tx in range(island_x + r, island_x + island_w - r, 64):
        cliff_layer.paste(cliff_tile, (tx, island_y + island_h - 8), cliff_tile)
    canvas = Image.alpha_composite(canvas, cliff_layer)

    # ── 4. 흙길 (중앙 십자) ──
    tilemap_sand = load(os.path.join(TS_FREE, "Terrain", "Tileset", "Tilemap_color2.png"))
    sand_fill = tile_region(tilemap_sand, 0, 0, 64, 64)

    path_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # 가로 길
    path_y = island_y + island_h // 2 - 24
    for tx in range(island_x + 60, island_x + island_w - 60, 64):
        path_layer.paste(sand_fill, (tx, path_y), sand_fill)
    # 세로 길
    path_x = island_x + island_w // 2 - 24
    for ty in range(island_y + 40, island_y + island_h - 40, 64):
        path_layer.paste(sand_fill, (path_x, ty), sand_fill)

    # 길 마스크 (섬 안쪽만)
    path_mask = Image.new("L", (W, H), 0)
    pm_draw = ImageDraw.Draw(path_mask)
    # 가로
    pm_draw.rounded_rectangle(
        [island_x+80, path_y, island_x+island_w-80, path_y+48],
        radius=15, fill=255
    )
    # 세로
    pm_draw.rounded_rectangle(
        [path_x, island_y+60, path_x+48, island_y+island_h-60],
        radius=15, fill=255
    )
    path_layer.putalpha(path_mask)
    canvas = Image.alpha_composite(canvas, path_layer)

    # ── 5. 건물: 작은 집 (좌상) ──
    house = load(os.path.join(TS_FREE, "Buildings", "Red Buildings", "House1.png"))
    house = house.resize((int(house.width*0.8), int(house.height*0.8)), Image.LANCZOS)
    paste_center(canvas, house, island_x + 200, island_y + 150)

    # ── 6. 나무들 ──
    tree_sheet = load(os.path.join(TS_UPD, "Resources", "Trees", "Tree.png"))
    # 나무 시트에서 개별 나무 추출 (첫번째 줄, 4개)
    tree1 = tile_region(tree_sheet, 0, 0, 192, 192)
    tree2 = tile_region(tree_sheet, 192, 0, 192, 192)
    tree3 = tile_region(tree_sheet, 384, 0, 192, 192)

    # 나무 작게 조정
    tree_s = 0.55
    trees_small = [t.resize((int(192*tree_s), int(192*tree_s)), Image.LANCZOS) for t in [tree1, tree2, tree3]]

    # 나무 배치 (섬 테두리쪽)
    tree_positions = [
        (island_x + 80, island_y + 60),
        (island_x + 30, island_y + 220),
        (island_x + island_w - 100, island_y + 50),
        (island_x + island_w - 60, island_y + 180),
        (island_x + island_w - 120, island_y + island_h - 120),
        (island_x + 60, island_y + island_h - 100),
        (island_x + island_w - 40, island_y + 300),
    ]
    for i, (tx, ty) in enumerate(tree_positions):
        t = trees_small[i % len(trees_small)]
        paste_center(canvas, t, tx, ty)

    # ── 7. 바위 ──
    rock1 = load(os.path.join(TS_FREE, "Terrain", "Decorations", "Rocks", "Rock1.png"))
    rock2 = load(os.path.join(TS_FREE, "Terrain", "Decorations", "Rocks", "Rock2.png"))
    rock3 = load(os.path.join(TS_FREE, "Terrain", "Decorations", "Rocks", "Rock3.png"))

    paste_center(canvas, rock1, island_x + island_w - 200, island_y + 120)
    paste_center(canvas, rock2, island_x + 140, island_y + island_h - 80)
    paste_center(canvas, rock3, island_x + island_w - 150, island_y + island_h - 60)

    # ── 8. 덤불 ──
    bush1 = load(os.path.join(TS_FREE, "Terrain", "Decorations", "Bushes", "Bushe1.png"))
    # 덤불 시트에서 프레임 1개만 (애니메이션 스트립)
    bush_frame = tile_region(bush1, 0, 0, bush1.width // 8, bush1.height)
    bush_positions = [
        (island_x + 300, island_y + 100),
        (island_x + island_w - 250, island_y + island_h - 100),
        (island_x + 150, island_y + 300),
        (island_x + island_w - 300, island_y + 280),
    ]
    for bx, by in bush_positions:
        paste_center(canvas, bush_frame, bx, by)

    # ── 9. 모닥불 (중앙) — 수동 그리기 ──
    fire_cx, fire_cy = W // 2, H // 2 + 10
    fire_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fire_layer)

    # 돌 원형 (화덕)
    stone_r = 28
    for angle in range(0, 360, 30):
        sx = fire_cx + int(stone_r * math.cos(math.radians(angle)))
        sy = fire_cy + int(stone_r * math.sin(math.radians(angle))) + 5
        fd.ellipse([sx-7, sy-5, sx+7, sy+5], fill=(100, 110, 120, 255))
        fd.ellipse([sx-6, sy-4, sx+6, sy+3], fill=(130, 140, 150, 255))

    # 나무 장작
    fd.rounded_rectangle([fire_cx-18, fire_cy-2, fire_cx+18, fire_cy+8], radius=3,
                         fill=(101, 67, 33, 255))
    fd.rounded_rectangle([fire_cx-14, fire_cy-8, fire_cx+14, fire_cy+2], radius=3,
                         fill=(120, 80, 40, 255))

    # 불꽃
    # 외부 (빨강/주황)
    flame_pts_outer = [
        (fire_cx, fire_cy - 30),
        (fire_cx - 15, fire_cy - 5),
        (fire_cx - 10, fire_cy + 2),
        (fire_cx + 10, fire_cy + 2),
        (fire_cx + 15, fire_cy - 5),
    ]
    fd.polygon(flame_pts_outer, fill=(255, 100, 30, 220))
    # 중간 (주황/노랑)
    flame_pts_mid = [
        (fire_cx, fire_cy - 22),
        (fire_cx - 10, fire_cy - 5),
        (fire_cx - 7, fire_cy),
        (fire_cx + 7, fire_cy),
        (fire_cx + 10, fire_cy - 5),
    ]
    fd.polygon(flame_pts_mid, fill=(255, 180, 50, 230))
    # 코어 (노랑/흰)
    flame_pts_core = [
        (fire_cx, fire_cy - 15),
        (fire_cx - 5, fire_cy - 3),
        (fire_cx + 5, fire_cy - 3),
    ]
    fd.polygon(flame_pts_core, fill=(255, 240, 150, 255))

    # 불빛 글로우
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for r_size in [80, 60, 40]:
        alpha = 15 if r_size == 80 else 25 if r_size == 60 else 35
        gd.ellipse([fire_cx-r_size, fire_cy-r_size, fire_cx+r_size, fire_cy+r_size],
                   fill=(255, 150, 50, alpha))
    glow = glow.filter(ImageFilter.GaussianBlur(10))
    canvas = Image.alpha_composite(canvas, glow)
    canvas = Image.alpha_composite(canvas, fire_layer)

    # ── 10. 텐트 (모닥불 좌측) — 수동 그리기 ──
    tent_cx, tent_cy = fire_cx - 120, fire_cy + 20
    tent_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    td = ImageDraw.Draw(tent_layer)

    # 텐트 본체 (삼각형)
    tent_w, tent_h = 70, 55
    tent_pts = [
        (tent_cx, tent_cy - tent_h),          # 꼭대기
        (tent_cx - tent_w//2, tent_cy + 5),   # 좌하
        (tent_cx + tent_w//2, tent_cy + 5),   # 우하
    ]
    td.polygon(tent_pts, fill=(180, 60, 50, 255))  # 빨간 텐트

    # 텐트 밝은 면
    tent_light = [
        (tent_cx, tent_cy - tent_h),
        (tent_cx + tent_w//2, tent_cy + 5),
        (tent_cx + 5, tent_cy + 5),
    ]
    td.polygon(tent_light, fill=(200, 80, 60, 255))

    # 텐트 입구 (어두운 삼각형)
    door_pts = [
        (tent_cx, tent_cy - 15),
        (tent_cx - 15, tent_cy + 5),
        (tent_cx + 15, tent_cy + 5),
    ]
    td.polygon(door_pts, fill=(80, 25, 20, 255))

    # 텐트 막대기
    td.line([(tent_cx, tent_cy - tent_h - 5), (tent_cx, tent_cy - tent_h + 3)],
            fill=(139, 90, 43, 255), width=3)

    canvas = Image.alpha_composite(canvas, tent_layer)

    # ── 11. 구름 (상단) ──
    for cloud_file in ["Clouds_01.png", "Clouds_03.png", "Clouds_05.png"]:
        cloud = load(os.path.join(TS_FREE, "Terrain", "Decorations", "Clouds", cloud_file))
        cloud = cloud.resize((int(cloud.width*0.5), int(cloud.height*0.5)), Image.LANCZOS)
        # 반투명
        cloud_data = cloud.split()
        alpha = cloud_data[3].point(lambda p: int(p * 0.6))
        cloud.putalpha(alpha)

    cloud1 = load(os.path.join(TS_FREE, "Terrain", "Decorations", "Clouds", "Clouds_01.png"))
    cloud1 = cloud1.resize((int(cloud1.width*0.4), int(cloud1.height*0.4)), Image.LANCZOS)
    paste_center(canvas, cloud1, 120, 50)

    cloud2 = load(os.path.join(TS_FREE, "Terrain", "Decorations", "Clouds", "Clouds_03.png"))
    cloud2 = cloud2.resize((int(cloud2.width*0.35), int(cloud2.height*0.35)), Image.LANCZOS)
    paste_center(canvas, cloud2, 780, 35)

    cloud3 = load(os.path.join(TS_FREE, "Terrain", "Decorations", "Clouds", "Clouds_06.png"))
    cloud3 = cloud3.resize((int(cloud3.width*0.3), int(cloud3.height*0.3)), Image.LANCZOS)
    paste_center(canvas, cloud3, 500, 25)

    # ── 12. 최종 합성 (RGB) ──
    bg = Image.new("RGB", (W, H), (90, 180, 200))
    bg.paste(canvas, (0, 0), canvas)

    return bg


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    print("Generating Level 1 camp map...")
    img = generate_level1()
    out_path = os.path.join(OUT, "camp_level1.png")
    img.save(out_path, "PNG")
    print(f"Done! → {out_path} ({img.size})")
