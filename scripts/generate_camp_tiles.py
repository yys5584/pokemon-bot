"""Generate atmospheric camp field background tiles (400×180 PNG).

각 필드 타입별로 분위기 있는 배경 타일을 PIL로 생성.
assets/camp_tiles/{field_type}.png 에 저장.
"""

import math
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

TILE_W = 400
TILE_H = 180
OUT_DIR = Path(__file__).parent.parent / "assets" / "camp_tiles"


def _gradient(w, h, top, bot):
    """수직 그라디언트 이미지."""
    img = Image.new("RGBA", (w, h))
    for y in range(h):
        r = y / h
        c = tuple(int(top[i] + (bot[i] - top[i]) * r) for i in range(3))
        ImageDraw.Draw(img).line([(0, y), (w, y)], fill=(*c, 255))
    return img


def _add_noise(img, intensity=15, seed=42):
    """미세한 노이즈 텍스처 추가."""
    rng = random.Random(seed)
    pixels = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            n = rng.randint(-intensity, intensity)
            pixels[x, y] = (
                max(0, min(255, r + n)),
                max(0, min(255, g + n)),
                max(0, min(255, b + n)),
                a,
            )


def generate_forest():
    """숲 — 짙은 초록, 나무 실루엣, 빛줄기."""
    img = _gradient(TILE_W, TILE_H, (20, 65, 25), (8, 35, 12))
    draw = ImageDraw.Draw(img)
    rng = random.Random(1)

    # 먼 산/언덕 실루엣
    points = [(0, 100)]
    for x in range(0, TILE_W + 20, 20):
        y = 90 + int(15 * math.sin(x * 0.02)) + rng.randint(-8, 8)
        points.append((x, y))
    points.append((TILE_W, TILE_H))
    points.append((0, TILE_H))
    draw.polygon(points, fill=(15, 50, 18, 200))

    # 나무 실루엣 (뒷줄)
    for i in range(12):
        x = rng.randint(0, TILE_W)
        trunk_h = rng.randint(40, 70)
        trunk_y = TILE_H - trunk_h + rng.randint(-10, 20)
        # 줄기
        draw.rectangle([x - 2, trunk_y, x + 2, TILE_H], fill=(12, 38, 15, 180))
        # 수관
        crown_r = rng.randint(15, 28)
        draw.ellipse([x - crown_r, trunk_y - crown_r, x + crown_r, trunk_y + crown_r // 2],
                     fill=(18, 55 + rng.randint(-10, 10), 22, 160))

    # 나무 실루엣 (앞줄, 더 크고 어두움)
    for i in range(6):
        x = rng.randint(0, TILE_W)
        trunk_h = rng.randint(60, 100)
        trunk_y = TILE_H - trunk_h + 30
        draw.rectangle([x - 3, trunk_y, x + 3, TILE_H], fill=(8, 28, 10, 220))
        crown_r = rng.randint(22, 38)
        draw.ellipse([x - crown_r, trunk_y - crown_r, x + crown_r, trunk_y + crown_r // 3],
                     fill=(12, 42 + rng.randint(-8, 8), 16, 200))

    # 빛줄기 (대각선)
    light_layer = Image.new("RGBA", (TILE_W, TILE_H), (0, 0, 0, 0))
    light_draw = ImageDraw.Draw(light_layer)
    for i in range(4):
        bx = 80 + i * 90 + rng.randint(-20, 20)
        alpha = rng.randint(15, 30)
        light_draw.polygon(
            [(bx, 0), (bx + 15, 0), (bx + 50, TILE_H), (bx + 25, TILE_H)],
            fill=(180, 220, 100, alpha),
        )
    img = Image.alpha_composite(img, light_layer)

    # 바닥 풀
    draw = ImageDraw.Draw(img)
    for x in range(0, TILE_W, 3):
        gh = rng.randint(3, 10)
        gc = (40 + rng.randint(-10, 20), 100 + rng.randint(-20, 30), 30, 160)
        draw.line([(x, TILE_H), (x + rng.randint(-2, 2), TILE_H - gh)], fill=gc, width=1)

    # 반딧불이
    for _ in range(15):
        fx = rng.randint(0, TILE_W)
        fy = rng.randint(30, TILE_H - 20)
        fs = rng.randint(2, 4)
        fa = rng.randint(80, 180)
        draw.ellipse([fx - fs, fy - fs, fx + fs, fy + fs], fill=(160, 230, 80, fa))

    _add_noise(img, 8, seed=10)
    return img


def generate_volcano():
    """화산 — 붉은 하늘, 용암, 연기."""
    img = _gradient(TILE_W, TILE_H, (80, 25, 10), (40, 12, 5))
    draw = ImageDraw.Draw(img)
    rng = random.Random(2)

    # 화산 실루엣
    volcano_peak = TILE_W // 2 + rng.randint(-30, 30)
    peak_y = 30
    draw.polygon(
        [(volcano_peak - 120, TILE_H), (volcano_peak - 20, peak_y),
         (volcano_peak + 20, peak_y), (volcano_peak + 120, TILE_H)],
        fill=(35, 12, 8, 220),
    )
    # 분화구 빛
    draw.ellipse(
        [volcano_peak - 15, peak_y - 5, volcano_peak + 15, peak_y + 10],
        fill=(255, 120, 30, 200),
    )

    # 용암 흐름
    lava_layer = Image.new("RGBA", (TILE_W, TILE_H), (0, 0, 0, 0))
    lava_draw = ImageDraw.Draw(lava_layer)
    for i in range(3):
        lx = volcano_peak + rng.randint(-25, 25)
        points = [(lx, peak_y + 10)]
        for j in range(5):
            lx += rng.randint(-10, 10)
            ly = peak_y + 10 + j * 30 + rng.randint(0, 15)
            points.append((lx, ly))
        for j in range(len(points) - 1):
            alpha = 200 - j * 30
            lava_draw.line(
                [points[j], points[j + 1]],
                fill=(255, 100 + j * 20, 20, max(50, alpha)),
                width=3 - min(j, 2),
            )
    img = Image.alpha_composite(img, lava_layer)

    # 바위/돌
    draw = ImageDraw.Draw(img)
    for _ in range(20):
        rx = rng.randint(0, TILE_W)
        ry = rng.randint(TILE_H // 2, TILE_H)
        rs = rng.randint(4, 12)
        rc = rng.randint(20, 40)
        draw.ellipse([rx - rs, ry - rs // 2, rx + rs, ry + rs // 2],
                     fill=(rc, rc - 5, rc - 8, 180))

    # 불씨 파티클
    for _ in range(30):
        px = rng.randint(0, TILE_W)
        py = rng.randint(0, TILE_H)
        ps = rng.randint(1, 3)
        pa = rng.randint(60, 200)
        color = rng.choice([(255, 140, 30), (255, 80, 20), (255, 200, 60)])
        draw.ellipse([px - ps, py - ps, px + ps, py + ps], fill=(*color, pa))

    # 연기 (상단)
    smoke = Image.new("RGBA", (TILE_W, TILE_H), (0, 0, 0, 0))
    smoke_draw = ImageDraw.Draw(smoke)
    for _ in range(8):
        sx = volcano_peak + rng.randint(-50, 50)
        sy = rng.randint(0, 40)
        sr = rng.randint(20, 45)
        smoke_draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr],
                           fill=(60, 40, 30, rng.randint(20, 50)))
    smoke = smoke.filter(ImageFilter.GaussianBlur(8))
    img = Image.alpha_composite(img, smoke)

    _add_noise(img, 10, seed=20)
    return img


def generate_lake():
    """호수 — 푸른 물, 반사, 잔물결."""
    img = _gradient(TILE_W, TILE_H, (15, 40, 80), (8, 22, 50))
    draw = ImageDraw.Draw(img)
    rng = random.Random(3)

    # 하늘 부분 (상단 1/3)
    for y in range(TILE_H // 3):
        r = y / (TILE_H // 3)
        c = (int(25 + 15 * r), int(50 + 20 * r), int(100 - 10 * r))
        draw.line([(0, y), (TILE_W, y)], fill=(*c, 255))

    # 수평선
    horizon_y = TILE_H // 3
    draw.line([(0, horizon_y), (TILE_W, horizon_y)], fill=(40, 80, 130, 150), width=1)

    # 물결 패턴
    water_layer = Image.new("RGBA", (TILE_W, TILE_H), (0, 0, 0, 0))
    water_draw = ImageDraw.Draw(water_layer)
    for y in range(horizon_y, TILE_H, 6):
        alpha = 20 + int(15 * (y - horizon_y) / (TILE_H - horizon_y))
        phase = y * 0.15
        for x in range(0, TILE_W, 2):
            offset = int(3 * math.sin(x * 0.03 + phase))
            water_draw.point((x, y + offset), fill=(80, 160, 220, alpha))
    img = Image.alpha_composite(img, water_layer)

    # 달/태양 반사
    draw = ImageDraw.Draw(img)
    reflect_x = TILE_W * 2 // 3
    for i in range(20, 0, -1):
        alpha = int(25 * i / 20)
        r = int(30 * i / 20)
        draw.ellipse(
            [reflect_x - r, 15 - r // 2, reflect_x + r, 15 + r // 2],
            fill=(200, 220, 255, alpha),
        )
    # 물 위 반사 줄
    for y in range(horizon_y + 5, TILE_H, 8):
        w_half = 3 + (y - horizon_y) // 4
        alpha = 40 - (y - horizon_y) // 5
        if alpha > 0:
            draw.line(
                [(reflect_x - w_half, y), (reflect_x + w_half, y)],
                fill=(180, 210, 255, max(10, alpha)), width=1,
            )

    # 수초/갈대 (하단 양쪽)
    for _ in range(12):
        gx = rng.choice([rng.randint(0, 60), rng.randint(TILE_W - 60, TILE_W)])
        gy = TILE_H
        gh = rng.randint(15, 35)
        bend = rng.randint(-5, 5)
        draw.line([(gx, gy), (gx + bend, gy - gh)],
                  fill=(30, 70 + rng.randint(0, 30), 40, 180), width=1)

    # 잔잔한 파동 원
    for _ in range(5):
        cx = rng.randint(50, TILE_W - 50)
        cy = rng.randint(horizon_y + 20, TILE_H - 20)
        for r in range(8, 20, 4):
            draw.arc([cx - r, cy - r // 3, cx + r, cy + r // 3],
                     start=0, end=360, fill=(100, 180, 240, 40), width=1)

    _add_noise(img, 6, seed=30)
    return img


def generate_city():
    """도시 — 밤하늘, 빌딩 스카이라인, 네온."""
    img = _gradient(TILE_W, TILE_H, (18, 20, 35), (10, 12, 22))
    draw = ImageDraw.Draw(img)
    rng = random.Random(4)

    # 별
    for _ in range(30):
        sx = rng.randint(0, TILE_W)
        sy = rng.randint(0, TILE_H // 3)
        sa = rng.randint(80, 200)
        draw.point((sx, sy), fill=(255, 255, 255, sa))

    # 빌딩 스카이라인
    buildings = []
    x = 0
    while x < TILE_W:
        bw = rng.randint(20, 50)
        bh = rng.randint(40, 120)
        buildings.append((x, bh, bw))
        x += bw + rng.randint(2, 8)

    for bx, bh, bw in buildings:
        by = TILE_H - bh
        # 빌딩 본체
        shade = rng.randint(18, 35)
        draw.rectangle([bx, by, bx + bw, TILE_H], fill=(shade, shade, shade + 5, 230))
        # 테두리
        draw.rectangle([bx, by, bx + bw, TILE_H], outline=(40, 42, 50, 150), width=1)

        # 창문
        for wy in range(by + 5, TILE_H - 8, 12):
            for wx in range(bx + 4, bx + bw - 4, 8):
                if rng.random() < 0.6:  # 60% 켜진 창
                    wc = rng.choice([
                        (255, 230, 150),  # 따뜻한 빛
                        (200, 220, 255),  # 차가운 빛
                        (255, 200, 100),  # 노란 빛
                    ])
                    wa = rng.randint(100, 220)
                    draw.rectangle([wx, wy, wx + 4, wy + 6], fill=(*wc, wa))

    # 네온 사인 (일부 빌딩 꼭대기)
    neon_colors = [(255, 50, 80), (50, 200, 255), (255, 200, 50), (100, 255, 100)]
    for bx, bh, bw in buildings[:5]:
        if rng.random() < 0.3:
            by = TILE_H - bh
            nc = rng.choice(neon_colors)
            na = rng.randint(60, 120)
            # 글로우
            for step in range(6, 0, -1):
                r = step * 3
                draw.ellipse(
                    [bx + bw // 2 - r, by - r - 3, bx + bw // 2 + r, by + r - 3],
                    fill=(*nc, na * step // 6),
                )

    # 도로 (하단)
    draw.rectangle([0, TILE_H - 10, TILE_W, TILE_H], fill=(25, 25, 28, 255))
    # 도로 줄
    for x in range(0, TILE_W, 20):
        draw.rectangle([x, TILE_H - 6, x + 10, TILE_H - 5], fill=(180, 180, 50, 150))

    _add_noise(img, 5, seed=40)
    return img


def generate_cave():
    """동굴 — 어두운 갈색, 종유석, 수정."""
    img = _gradient(TILE_W, TILE_H, (38, 28, 18), (20, 14, 8))
    draw = ImageDraw.Draw(img)
    rng = random.Random(5)

    # 동굴 벽면 텍스처
    for _ in range(100):
        rx = rng.randint(0, TILE_W)
        ry = rng.randint(0, TILE_H)
        rs = rng.randint(10, 40)
        shade = rng.randint(25, 45)
        alpha = rng.randint(30, 80)
        draw.ellipse([rx - rs, ry - rs // 2, rx + rs, ry + rs // 2],
                     fill=(shade, shade - 3, shade - 8, alpha))

    # 종유석 (상단)
    for i in range(15):
        sx = rng.randint(0, TILE_W)
        sh = rng.randint(15, 50)
        sw = rng.randint(4, 12)
        base_y = rng.randint(-5, 5)
        shade = rng.randint(35, 55)
        draw.polygon(
            [(sx - sw, base_y), (sx + sw, base_y), (sx + rng.randint(-2, 2), base_y + sh)],
            fill=(shade, shade - 2, shade - 6, 200),
        )

    # 석순 (하단)
    for i in range(10):
        sx = rng.randint(0, TILE_W)
        sh = rng.randint(10, 35)
        sw = rng.randint(3, 10)
        shade = rng.randint(30, 50)
        draw.polygon(
            [(sx - sw, TILE_H), (sx + sw, TILE_H), (sx + rng.randint(-2, 2), TILE_H - sh)],
            fill=(shade, shade - 2, shade - 5, 200),
        )

    # 빛나는 수정
    crystal_colors = [(120, 200, 255), (180, 140, 255), (100, 255, 180)]
    for _ in range(8):
        cx = rng.randint(30, TILE_W - 30)
        cy = rng.randint(30, TILE_H - 30)
        cc = rng.choice(crystal_colors)
        cs = rng.randint(4, 8)
        # 글로우
        for step in range(8, 0, -1):
            r = cs + step * 2
            alpha = int(20 * step / 8)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*cc, alpha))
        # 수정 본체 (다이아몬드)
        draw.polygon(
            [(cx, cy - cs * 2), (cx + cs, cy), (cx, cy + cs), (cx - cs, cy)],
            fill=(*cc, 200),
        )

    # 동굴 개구부 빛 (좌상단에서 들어옴)
    light = Image.new("RGBA", (TILE_W, TILE_H), (0, 0, 0, 0))
    light_draw = ImageDraw.Draw(light)
    for step in range(30, 0, -1):
        r = step * 8
        alpha = int(15 * step / 30)
        light_draw.ellipse([-r // 2, -r // 2, r, r], fill=(180, 160, 120, alpha))
    light = light.filter(ImageFilter.GaussianBlur(12))
    img = Image.alpha_composite(img, light)

    _add_noise(img, 8, seed=50)
    return img


def generate_temple():
    """신전 — 보라빛, 신비한 룬, 에너지."""
    img = _gradient(TILE_W, TILE_H, (35, 15, 55), (18, 8, 30))
    draw = ImageDraw.Draw(img)
    rng = random.Random(6)

    # 별/반짝이
    for _ in range(40):
        sx = rng.randint(0, TILE_W)
        sy = rng.randint(0, TILE_H)
        sa = rng.randint(40, 160)
        sc = rng.choice([(200, 150, 255), (255, 200, 255), (150, 100, 255)])
        draw.point((sx, sy), fill=(*sc, sa))

    # 기둥 실루엣
    pillar_positions = [50, 130, 270, 350]
    for px in pillar_positions:
        pw = rng.randint(14, 22)
        ph = rng.randint(80, 140)
        py = TILE_H - ph
        shade = rng.randint(22, 35)
        draw.rectangle([px - pw // 2, py, px + pw // 2, TILE_H],
                       fill=(shade, shade - 3, shade + 8, 200))
        # 기둥 상단 장식
        draw.rectangle([px - pw // 2 - 3, py - 4, px + pw // 2 + 3, py + 2],
                       fill=(shade + 5, shade, shade + 12, 200))

    # 에너지 오브 (중앙)
    orb_layer = Image.new("RGBA", (TILE_W, TILE_H), (0, 0, 0, 0))
    orb_draw = ImageDraw.Draw(orb_layer)
    ocx, ocy = TILE_W // 2, TILE_H // 2 - 10
    for step in range(25, 0, -1):
        r = step * 5
        alpha = int(20 * step / 25)
        orb_draw.ellipse([ocx - r, ocy - r, ocx + r, ocy + r],
                         fill=(140, 80, 220, alpha))
    orb_draw.ellipse([ocx - 8, ocy - 8, ocx + 8, ocy + 8], fill=(200, 160, 255, 180))
    orb = orb_layer.filter(ImageFilter.GaussianBlur(3))
    img = Image.alpha_composite(img, orb)

    # 룬 기호 (원형 배치)
    draw = ImageDraw.Draw(img)
    rune_r = 50
    for i in range(6):
        angle = i * math.pi / 3
        rx = int(ocx + rune_r * math.cos(angle))
        ry = int(ocy + rune_r * math.sin(angle))
        ra = rng.randint(40, 100)
        # 작은 다이아몬드
        s = 4
        draw.polygon([(rx, ry - s), (rx + s, ry), (rx, ry + s), (rx - s, ry)],
                     fill=(180, 120, 255, ra))

    # 에너지 파티클
    for _ in range(20):
        px = rng.randint(0, TILE_W)
        py = rng.randint(0, TILE_H)
        ps = rng.randint(1, 3)
        pa = rng.randint(60, 180)
        pc = rng.choice([(180, 100, 255), (220, 160, 255), (140, 80, 200)])
        draw.ellipse([px - ps, py - ps, px + ps, py + ps], fill=(*pc, pa))

    # 바닥 무늬
    for x in range(0, TILE_W, 40):
        draw.line([(x, TILE_H - 3), (x + 20, TILE_H - 3)],
                  fill=(60, 30, 80, 80), width=1)

    _add_noise(img, 6, seed=60)
    return img


def generate_locked():
    """잠긴 필드 배경 (사용하지 않지만 참고용)."""
    img = Image.new("RGBA", (TILE_W, TILE_H), (25, 25, 30, 255))
    return img


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    generators = {
        "forest": generate_forest,
        "volcano": generate_volcano,
        "lake": generate_lake,
        "city": generate_city,
        "cave": generate_cave,
        "temple": generate_temple,
    }

    for name, gen_func in generators.items():
        print(f"Generating {name}...", end=" ")
        tile = gen_func()
        path = OUT_DIR / f"{name}.png"
        tile.save(path, "PNG")
        print(f"saved → {path}")

    print("\nDone! All tiles saved to", OUT_DIR)


if __name__ == "__main__":
    main()
