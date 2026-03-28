"""Generate 16:9 Pokemon card images for spawn/pokedex display."""

import io
import math
import os
import random
from pathlib import Path
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

ASSETS_DIR = Path(__file__).parent.parent / "assets" / "pokemon"
BALL_DIR = Path(__file__).parent.parent / "assets" / "ball"
CARD_WIDTH = 960
CARD_HEIGHT = 540  # 16:9

# Font paths by style
_FONT_PATHS = [
    "C:/Windows/Fonts/malgun.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]
_FONT_BOLD_PATHS = [
    "C:/Windows/Fonts/malgunbd.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "C:/Windows/Fonts/malgun.ttf",
]
_FONT_IMPACT_PATHS = [
    "C:/Windows/Fonts/impact.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/malgunbd.ttf",
]

@lru_cache(maxsize=16)
def _get_font(size: int, style: str = "regular") -> ImageFont.FreeTypeFont:
    paths = {"regular": _FONT_PATHS, "bold": _FONT_BOLD_PATHS,
             "impact": _FONT_IMPACT_PATHS}.get(style, _FONT_PATHS)
    for path in paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

# Rarity → gradient colors (top, bottom)
RARITY_COLORS = {
    "common":         ((34, 49, 34),   (20, 30, 20)),
    "rare":           ((20, 40, 80),   (10, 20, 50)),
    "epic":           ((55, 20, 80),   (30, 10, 50)),
    "legendary":      ((80, 65, 10),   (50, 35, 5)),
    "ultra_legendary": ((100, 15, 15), (60, 5, 5)),
}

# Rarity → accent color for border/glow
RARITY_ACCENT = {
    "common":         (82, 183, 136),
    "rare":           (72, 149, 239),
    "epic":           (177, 133, 219),
    "legendary":      (255, 214, 10),
    "ultra_legendary": (255, 50, 50),
}


@lru_cache(maxsize=8)
def _make_gradient(width: int, height: int, top_color: tuple, bottom_color: tuple) -> Image.Image:
    """Create a vertical gradient image (cached per rarity, row-based)."""
    img = Image.new("RGB", (width, height))
    # Build flat pixel list row by row (avoids per-pixel x loop)
    pixels = []
    for y in range(height):
        ratio = y / height
        color = (
            int(top_color[0] + (bottom_color[0] - top_color[0]) * ratio),
            int(top_color[1] + (bottom_color[1] - top_color[1]) * ratio),
            int(top_color[2] + (bottom_color[2] - top_color[2]) * ratio),
        )
        pixels.extend([color] * width)
    img.putdata(pixels)
    return img


@lru_cache(maxsize=48)
def _load_sprite(pokemon_id: int) -> Image.Image | None:
    """Load and pre-scale a Pokemon sprite (cached)."""
    sprite_path = ASSETS_DIR / f"{pokemon_id}.png"
    if not sprite_path.exists():
        return None
    sprite = Image.open(sprite_path).convert("RGBA")
    max_size = 320
    ratio = min(max_size / sprite.width, max_size / sprite.height)
    new_w = int(sprite.width * ratio)
    new_h = int(sprite.height * ratio)
    return sprite.resize((new_w, new_h), Image.LANCZOS)


def _draw_glow(draw: ImageDraw.Draw, cx: int, cy: int, radius: int, color: tuple, steps: int = 20):
    """Draw a soft radial glow effect."""
    for i in range(steps, 0, -1):
        alpha = int(30 * (i / steps))
        r = int(radius * (i / steps))
        fill = (*color, alpha)
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill=fill,
        )


# Rainbow colors for shiny border
_RAINBOW = [
    (255, 0, 0), (255, 127, 0), (255, 255, 0),
    (0, 200, 0), (0, 150, 255), (100, 0, 255), (200, 0, 255),
]


def _rainbow_row_rgb(width: int) -> list[tuple]:
    """Generate a single row of rainbow RGB tuples (cached-friendly)."""
    n = len(_RAINBOW)
    row = []
    for x in range(width):
        t = x / width * n
        idx = int(t) % n
        nxt = (idx + 1) % n
        frac = t - int(t)
        c1, c2 = _RAINBOW[idx], _RAINBOW[nxt]
        row.append((
            int(c1[0] + (c2[0] - c1[0]) * frac),
            int(c1[1] + (c2[1] - c1[1]) * frac),
            int(c1[2] + (c2[2] - c1[2]) * frac),
        ))
    return row



def _draw_shiny_bottom_rainbow(card: Image.Image, band_height: int = 60) -> Image.Image:
    """Draw a horizontal rainbow gradient band at the bottom of the card."""
    w, h = card.size
    row_rgb = _rainbow_row_rgb(w)

    # Build RGBA band with alpha fade (row-based, avoids nested pixel loop)
    pixels = []
    for y_off in range(band_height):
        alpha = int(180 * (y_off / band_height))
        pixels.extend((*c, alpha) for c in row_rgb)

    band_img = Image.new("RGBA", (w, band_height))
    band_img.putdata(pixels)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    layer.paste(band_img, (0, h - band_height))
    return Image.alpha_composite(card, layer)


def _draw_shiny_glow(card: Image.Image, accent: tuple) -> Image.Image:
    """Draw enhanced shiny glow: brighter, larger, with sparkle particles."""
    import math
    import random
    w, h = card.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cx, cy = w // 2, h // 2 - 20

    bright = tuple(min(255, c + 80) for c in accent)
    white_accent = tuple(min(255, c + 160) for c in accent)

    # Bright outer glow (large)
    for i in range(30, 0, -1):
        alpha = int(50 * (i / 30))
        r = int(280 * (i / 30))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*bright, alpha))

    # Inner white-ish core
    for i in range(15, 0, -1):
        alpha = int(65 * (i / 15))
        r = int(120 * (i / 15))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*white_accent, alpha))

    # Diagonal shimmer rays
    for angle_deg in (30, 150, 210, 330):
        angle = math.radians(angle_deg)
        for dist in range(80, 260, 2):
            rx = int(cx + dist * math.cos(angle))
            ry = int(cy + dist * math.sin(angle))
            if 0 <= rx < w and 0 <= ry < h:
                fade = max(0, int(50 * (1 - (dist - 80) / 180)))
                draw.ellipse([rx - 2, ry - 2, rx + 2, ry + 2], fill=(*bright, fade))

    # Sparkle particles (반짝반짝) scattered around the glow area
    rng = random.Random(42)  # Fixed seed for consistent output
    for _ in range(55):
        angle = rng.uniform(0, 2 * math.pi)
        dist = rng.uniform(40, 250)
        sx = int(cx + dist * math.cos(angle))
        sy = int(cy + dist * math.sin(angle))
        if not (0 <= sx < w and 0 <= sy < h):
            continue
        size = rng.choice([2, 3, 4, 5])
        sparkle_alpha = rng.randint(120, 230)

        # Draw 4-pointed star shape
        arm = size * 2
        # Vertical line
        draw.line([(sx, sy - arm), (sx, sy + arm)], fill=(255, 255, 255, sparkle_alpha), width=1)
        # Horizontal line
        draw.line([(sx - arm, sy), (sx + arm, sy)], fill=(255, 255, 255, sparkle_alpha), width=1)
        # Center bright dot
        draw.ellipse([sx - size, sy - size, sx + size, sy + size],
                     fill=(255, 255, 255, sparkle_alpha))
        # Tiny color tinted halo
        draw.ellipse([sx - size - 1, sy - size - 1, sx + size + 1, sy + size + 1],
                     outline=(*bright, sparkle_alpha // 2))

    return Image.alpha_composite(card, layer)


# ── Mega Evolution card effects ──────────────────────────────

_MEGA_PURPLE = (160, 60, 220)
_MEGA_PINK = (255, 80, 180)

def _draw_mega_glow(card: Image.Image) -> Image.Image:
    """Draw mega evolution glow: purple-pink energy aura with DNA helix particles."""
    w, h = card.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cx, cy = w // 2, h // 2 - 20

    # Outer purple glow
    for i in range(30, 0, -1):
        alpha = int(45 * (i / 30))
        r = int(300 * (i / 30))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*_MEGA_PURPLE, alpha))

    # Inner pink core
    for i in range(18, 0, -1):
        alpha = int(55 * (i / 18))
        r = int(140 * (i / 18))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*_MEGA_PINK, alpha))

    # DNA helix-style double spiral particles
    rng = random.Random(77)
    for strand in (0, math.pi):
        for t in range(60):
            angle = t * 0.18 + strand
            dist = 60 + t * 3.2
            sx = int(cx + dist * math.cos(angle))
            sy = int(cy - 180 + t * 6)
            if not (0 <= sx < w and 0 <= sy < h):
                continue
            fade = max(0, 220 - t * 3)
            size = 3 if t % 3 == 0 else 2
            color = _MEGA_PURPLE if strand == 0 else _MEGA_PINK
            draw.ellipse([sx - size, sy - size, sx + size, sy + size],
                         fill=(*color, fade))

    # Scattered energy particles
    for _ in range(40):
        angle = rng.uniform(0, 2 * math.pi)
        dist = rng.uniform(50, 260)
        sx = int(cx + dist * math.cos(angle))
        sy = int(cy + dist * math.sin(angle))
        if not (0 <= sx < w and 0 <= sy < h):
            continue
        size = rng.choice([2, 3, 4])
        alpha = rng.randint(100, 200)
        color = rng.choice([_MEGA_PURPLE, _MEGA_PINK, (255, 255, 255)])
        # Diamond shape
        draw.polygon([(sx, sy - size * 2), (sx + size, sy),
                       (sx, sy + size * 2), (sx - size, sy)],
                     fill=(*color, alpha))

    return Image.alpha_composite(card, layer)


def _draw_mega_bottom_line(card: Image.Image, line_h: int = 6) -> Image.Image:
    """Draw a purple→pink gradient line at the bottom (replaces rarity line)."""
    w, h = card.size
    pixels = []
    for y_off in range(line_h):
        for x in range(w):
            t = x / w
            r = int(_MEGA_PURPLE[0] + (_MEGA_PINK[0] - _MEGA_PURPLE[0]) * t)
            g = int(_MEGA_PURPLE[1] + (_MEGA_PINK[1] - _MEGA_PURPLE[1]) * t)
            b = int(_MEGA_PURPLE[2] + (_MEGA_PINK[2] - _MEGA_PURPLE[2]) * t)
            pixels.append((r, g, b, 240))
    line_img = Image.new("RGBA", (w, line_h))
    line_img.putdata(pixels)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    layer.paste(line_img, (0, h - line_h))
    return Image.alpha_composite(card, layer)


# ── TCG Card Layout Constants ─────────────────────────────────

_FRAME_W = 8       # 외부 프레임 두께
_INNER_PAD = 4     # 이너 보더
_HEADER_H = 36     # 헤더 높이
_INFO_H = 70       # 인포바 높이

# 아트윈도우 영역 (프레임+이너패드+헤더 아래 ~ 인포바 위)
_ART_X = _FRAME_W + _INNER_PAD
_ART_Y = _FRAME_W + _INNER_PAD + _HEADER_H
_ART_W = CARD_WIDTH - 2 * (_FRAME_W + _INNER_PAD)
_ART_H = CARD_HEIGHT - 2 * (_FRAME_W + _INNER_PAD) - _HEADER_H - _INFO_H

# 프레임 색상 (main, accent/bevel)
_FRAME_COLORS = {
    "common":          ((100, 110, 105), (70, 80, 75)),
    "rare":            ((140, 165, 200), (100, 130, 170)),
    "epic":            ((170, 130, 210), (130, 90, 175)),
    "legendary":       ((230, 195, 55),  (180, 150, 30)),
    "ultra_legendary": ((220, 50, 50),   (180, 30, 30)),  # base; will be rainbow
}

# 타입별 색상 (도트용)
_TYPE_COLORS = {
    "normal": (168, 168, 120), "fire": (240, 80, 48), "water": (104, 144, 240),
    "grass": (120, 200, 80), "electric": (248, 208, 48), "ice": (152, 216, 216),
    "fighting": (192, 48, 40), "poison": (160, 64, 160), "ground": (224, 192, 104),
    "flying": (168, 144, 240), "psychic": (248, 88, 136), "bug": (168, 184, 32),
    "rock": (184, 160, 56), "ghost": (112, 88, 152), "dragon": (112, 56, 248),
    "dark": (112, 88, 72), "steel": (184, 184, 208), "fairy": (238, 153, 172),
}


def _draw_tcg_frame(card: Image.Image, rarity: str) -> Image.Image:
    """등급별 TCG 프레임 (8px 외부 테두리 + 4px 이너 보더)."""
    draw = ImageDraw.Draw(card)
    w, h = card.size
    main, bevel = _FRAME_COLORS.get(rarity, _FRAME_COLORS["common"])

    if rarity == "ultra_legendary":
        # 프리즘 레인보우 프레임
        row_rgb = _rainbow_row_rgb(w)
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        for y in range(h):
            for side in ("top", "bottom", "left", "right"):
                if side == "top" and y < _FRAME_W:
                    shift = y * 3
                    for x in range(w):
                        c = row_rgb[(x + shift) % w]
                        layer.putpixel((x, y), (*c, 255))
                elif side == "bottom" and y >= h - _FRAME_W:
                    shift = y * 3
                    for x in range(w):
                        c = row_rgb[(x + shift) % w]
                        layer.putpixel((x, y), (*c, 255))
                elif side == "left" and _FRAME_W <= y < h - _FRAME_W:
                    shift = y * 3
                    for x in range(_FRAME_W):
                        c = row_rgb[(x + shift) % w]
                        layer.putpixel((x, y), (*c, 255))
                elif side == "right" and _FRAME_W <= y < h - _FRAME_W:
                    shift = y * 3
                    for x in range(w - _FRAME_W, w):
                        c = row_rgb[(x + shift) % w]
                        layer.putpixel((x, y), (*c, 255))
        card = Image.alpha_composite(card, layer)
    else:
        # 외부 프레임 사각형
        draw.rectangle([0, 0, w - 1, h - 1], outline=(*main, 255), width=_FRAME_W)

        # 메탈릭 하이라이트 (rare 이상)
        if rarity in ("rare", "epic", "legendary"):
            highlight = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            hdraw = ImageDraw.Draw(highlight)
            # 상단 프레임에 밝은 줄
            for y in range(2, _FRAME_W - 1):
                alpha = int(60 * (1 - y / _FRAME_W))
                bright = tuple(min(255, c + 60) for c in main)
                hdraw.line([(0, y), (w, y)], fill=(*bright, alpha))
            card = Image.alpha_composite(card, highlight)

        # 골드 쉬머 (legendary)
        if rarity == "legendary":
            shimmer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            rng = random.Random(42)
            for _ in range(200):
                sx = rng.randint(0, w - 1)
                sy = rng.randint(0, h - 1)
                # 프레임 영역에만
                if sx < _FRAME_W or sx >= w - _FRAME_W or sy < _FRAME_W or sy >= h - _FRAME_W:
                    sdraw = ImageDraw.Draw(shimmer)
                    sdraw.point((sx, sy), fill=(255, 240, 150, rng.randint(40, 100)))
            card = Image.alpha_composite(card, shimmer)

    # 이너 보더 (어두운 라인)
    draw = ImageDraw.Draw(card)
    ix, iy = _FRAME_W, _FRAME_W
    iw, ih = w - _FRAME_W, h - _FRAME_W
    draw.rectangle([ix, iy, iw, ih], outline=(*bevel, 180), width=_INNER_PAD)

    return card


def _draw_tcg_art_bg(card: Image.Image, rarity: str) -> Image.Image:
    """아트윈도우 배경 그라데이션."""
    top_col, bot_col = RARITY_COLORS.get(rarity, RARITY_COLORS["common"])
    art_bg = _make_gradient(_ART_W, _ART_H, top_col, bot_col).convert("RGBA")
    card.paste(art_bg, (_ART_X, _ART_Y))
    return card


def _draw_holo_sparkles(card: Image.Image, iv_total: int) -> Image.Image:
    """IV 연동 홀로그래픽 스파클."""
    if iv_total is None or iv_total <= 60:
        return card
    intensity = min(1.0, (iv_total - 60) / 126)
    n_sparkles = int(intensity * 80)
    if n_sparkles <= 0:
        return card

    layer = Image.new("RGBA", card.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    rng = random.Random(iv_total)
    rainbow = _rainbow_row_rgb(_ART_W)

    for _ in range(n_sparkles):
        sx = rng.randint(_ART_X + 10, _ART_X + _ART_W - 10)
        sy = rng.randint(_ART_Y + 10, _ART_Y + _ART_H - 10)
        color = rainbow[(sx - _ART_X) % len(rainbow)]
        size = rng.choice([2, 3, 4])
        alpha = int(80 + intensity * 140)
        arm = size * 2
        # 4각 별
        draw.line([(sx, sy - arm), (sx, sy + arm)], fill=(*color, alpha), width=1)
        draw.line([(sx - arm, sy), (sx + arm, sy)], fill=(*color, alpha), width=1)
        draw.ellipse([sx - size, sy - size, sx + size, sy + size], fill=(*color, alpha))

    # S등급 (160+): 대각선 레인보우 쉰
    if iv_total >= 160:
        sheen = Image.new("RGBA", (_ART_W, _ART_H), (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(sheen)
        for y in range(_ART_H):
            for x in range(_ART_W):
                diag = (x + y) % _ART_W
                c = rainbow[diag % len(rainbow)]
                dist = abs(((x + y * 0.6) % 200) - 100) / 100  # 0~1 band
                if dist < 0.15:
                    a = int(35 * (1 - dist / 0.15))
                    sdraw.point((x, y), fill=(*c, a))
        sheen_layer = Image.new("RGBA", card.size, (0, 0, 0, 0))
        sheen_layer.paste(sheen, (_ART_X, _ART_Y))
        layer = Image.alpha_composite(layer, sheen_layer)

    return Image.alpha_composite(card, layer)


def _draw_tcg_shiny_border(card: Image.Image) -> Image.Image:
    """이로치 아트윈도우 내부 레인보우 보더 (3px)."""
    layer = Image.new("RGBA", card.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    bw = 3
    rainbow = _rainbow_row_rgb(_ART_W)

    # 상단/하단
    for y_off in range(bw):
        for x in range(_ART_W):
            c = rainbow[x]
            draw.point((_ART_X + x, _ART_Y + y_off), fill=(*c, 220))
            draw.point((_ART_X + x, _ART_Y + _ART_H - 1 - y_off), fill=(*c, 220))
    # 좌측/우측
    v_rainbow = _rainbow_row_rgb(_ART_H)
    for x_off in range(bw):
        for y in range(_ART_H):
            c = v_rainbow[y]
            draw.point((_ART_X + x_off, _ART_Y + y), fill=(*c, 220))
            draw.point((_ART_X + _ART_W - 1 - x_off, _ART_Y + y), fill=(*c, 220))

    return Image.alpha_composite(card, layer)


def _draw_tcg_header(draw: ImageDraw.Draw, pokemon_id: int, rarity: str,
                     is_shiny: bool, mega_key: str | None,
                     types: list[str] | None):
    """TCG 헤더바: ID 좌측, 타입 중앙, 뱃지 우측."""
    accent = RARITY_ACCENT.get(rarity, RARITY_ACCENT["common"])
    font_sm = _get_font(15)
    font_xs = _get_font(12)
    hx = _FRAME_W + _INNER_PAD + 8
    hy = _FRAME_W + _INNER_PAD + 8

    # 헤더 배경 (반투명 어두운 바)
    draw.rectangle(
        [_ART_X, _FRAME_W + _INNER_PAD, _ART_X + _ART_W, _ART_Y - 1],
        fill=(15, 15, 20, 220),
    )

    # ID 좌측
    id_text = f"#{pokemon_id:03d}"
    draw.text((hx, hy), id_text, fill=(200, 200, 200, 200), font=font_sm)

    # 타입 도트 (중앙)
    if types:
        total_w = len(types) * 50
        tx = CARD_WIDTH // 2 - total_w // 2
        for t in types:
            color = _TYPE_COLORS.get(t, (150, 150, 150))
            # 도트
            draw.ellipse([tx, hy + 2, tx + 14, hy + 16], fill=(*color, 255))
            # 타입명
            t_name = t[:3].upper()
            draw.text((tx + 18, hy + 1), t_name, fill=(200, 200, 200, 220), font=font_xs)
            tx += 50

    # 뱃지 우측 (등급 → MEGA → 이로치 순, 우→좌)
    rarity_labels = {"common": "일반", "rare": "레어", "epic": "에픽",
                     "legendary": "전설", "ultra_legendary": "초전설"}
    bx = _ART_X + _ART_W - 8  # 우측 끝

    # 등급 뱃지
    rt = rarity_labels.get(rarity, rarity)
    rbbox = draw.textbbox((0, 0), rt, font=font_sm)
    rw = rbbox[2] - rbbox[0]
    bx -= rw + 16
    draw.rounded_rectangle([bx, hy - 2, bx + rw + 16, hy + 20], radius=4, fill=(*accent, 210))
    draw.text((bx + 8, hy), rt, fill=(255, 255, 255), font=font_sm)

    # MEGA 뱃지
    if mega_key:
        bx -= 8
        mt = "MEGA"
        mbbox = draw.textbbox((0, 0), mt, font=font_sm)
        mw = mbbox[2] - mbbox[0]
        bx -= mw + 16
        draw.rounded_rectangle([bx, hy - 2, bx + mw + 16, hy + 20], radius=4, fill=(160, 60, 220, 220))
        draw.text((bx + 8, hy), mt, fill=(255, 255, 255), font=font_sm)

    # 이로치 뱃지
    if is_shiny:
        bx -= 8
        st = "✦SHINY"
        sbbox = draw.textbbox((0, 0), st, font=font_sm)
        sw = sbbox[2] - sbbox[0]
        bx -= sw + 16
        draw.rounded_rectangle([bx, hy - 2, bx + sw + 16, hy + 20], radius=4, fill=(205, 80, 80, 220))
        draw.text((bx + 8, hy), st, fill=(255, 255, 255), font=font_sm)


def _draw_tcg_info(draw: ImageDraw.Draw, name_ko: str, rarity: str,
                   iv_total: int | None, types: list[str] | None):
    """TCG 인포바: 이름 + 등급/IV/타입."""
    accent = RARITY_ACCENT.get(rarity, RARITY_ACCENT["common"])
    font_name = _get_font(28, "bold")
    font_detail = _get_font(14)

    info_y = _ART_Y + _ART_H
    info_x = _ART_X
    info_w = _ART_W

    # 인포바 배경
    draw.rectangle(
        [info_x, info_y, info_x + info_w, CARD_HEIGHT - _FRAME_W - _INNER_PAD],
        fill=(15, 15, 20, 230),
    )

    # 구분선 (accent)
    draw.line([(info_x + 12, info_y + 1), (info_x + info_w - 12, info_y + 1)],
              fill=(*accent, 180), width=2)

    # 이름 (좌측)
    nx = info_x + 20
    ny = info_y + 10
    draw.text((nx + 1, ny + 1), name_ko, fill=(0, 0, 0, 150), font=font_name)
    draw.text((nx, ny), name_ko, fill=(255, 255, 255), font=font_name)

    # 2줄째: 등급 + 타입 (좌측), IV 등급 (우측)
    rarity_labels = {"common": "일반", "rare": "레어", "epic": "에픽",
                     "legendary": "전설", "ultra_legendary": "초전설"}
    detail_y = ny + 36
    detail_parts = [rarity_labels.get(rarity, rarity)]
    if types:
        type_ko = {"normal": "노말", "fire": "불꽃", "water": "물", "grass": "풀",
                   "electric": "전기", "ice": "얼음", "fighting": "격투", "poison": "독",
                   "ground": "땅", "flying": "비행", "psychic": "에스퍼", "bug": "벌레",
                   "rock": "바위", "ghost": "고스트", "dragon": "드래곤", "dark": "악",
                   "steel": "강철", "fairy": "페어리"}
        type_str = " / ".join(type_ko.get(t, t) for t in types)
        detail_parts.append(type_str)
    detail_text = "  ·  ".join(detail_parts)
    draw.text((nx, detail_y), detail_text, fill=(180, 180, 190), font=font_detail)

    # IV 등급 뱃지 (우측)
    if iv_total is not None:
        grade_map = [(160, "S", (255, 215, 0)), (120, "A", (100, 200, 255)),
                     (93, "B", (140, 230, 140)), (62, "C", (200, 200, 200)),
                     (0, "D", (160, 160, 160))]
        grade_letter, grade_color = "D", (160, 160, 160)
        for threshold, letter, color in grade_map:
            if iv_total >= threshold:
                grade_letter, grade_color = letter, color
                break
        iv_text = f"IV: {grade_letter}"
        ivbbox = draw.textbbox((0, 0), iv_text, font=font_name)
        iv_w = ivbbox[2] - ivbbox[0]
        iv_x = info_x + info_w - iv_w - 20
        draw.text((iv_x, ny + 4), iv_text, fill=grade_color, font=_get_font(24, "bold"))


def generate_card(pokemon_id: int, name_ko: str, rarity: str, emoji: str = "",
                  is_shiny: bool = False, mega_key: str | None = None,
                  *, iv_total: int | None = None,
                  types: list[str] | None = None) -> io.BytesIO:
    """Generate a TCG-style 16:9 Pokemon card image.

    mega_key: 메가폼 키 (예: "mega_6_x"). 지정 시 메가폼 이미지+이펙트 사용.
    iv_total: IV 총합 (0~186). 홀로그래픽 효과 강도 결정.
    types: 타입 목록 (예: ["fire", "dragon"]). 헤더/인포에 표시.
    """
    accent = RARITY_ACCENT.get(rarity, RARITY_ACCENT["common"])

    # 1. 검정 배경 캔버스
    card = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (10, 10, 15, 255))

    # 2. TCG 프레임
    card = _draw_tcg_frame(card, rarity)

    # 3. 아트윈도우 배경
    card = _draw_tcg_art_bg(card, rarity)

    # 4. 기본 글로우
    glow_layer = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)
    cx = CARD_WIDTH // 2
    cy = _ART_Y + _ART_H // 2
    _draw_glow(glow_draw, cx, cy, 200, accent)
    card = Image.alpha_composite(card, glow_layer)

    # 5. 이로치/메가 이펙트
    if mega_key:
        card = _draw_mega_glow(card)
    elif is_shiny:
        card = _draw_shiny_glow(card, accent)

    if is_shiny:
        card = _draw_tcg_shiny_border(card)

    # 6. 홀로그래픽 (IV 연동)
    card = _draw_holo_sparkles(card, iv_total)

    # 7. 포켓몬 스프라이트
    if mega_key:
        sprite_path = ASSETS_DIR / f"{mega_key}.png"
        if sprite_path.exists():
            sprite = Image.open(sprite_path).convert("RGBA")
            max_size = 320
            ratio = min(max_size / sprite.width, max_size / sprite.height)
            sprite = sprite.resize((int(sprite.width * ratio), int(sprite.height * ratio)), Image.LANCZOS)
        else:
            sprite = _load_sprite(pokemon_id)
    else:
        sprite = _load_sprite(pokemon_id)
    if sprite:
        sx = (CARD_WIDTH - sprite.width) // 2
        sy = _ART_Y + (_ART_H - sprite.height) // 2
        card.paste(sprite, (sx, sy), sprite)

    # 8. 헤더바
    draw = ImageDraw.Draw(card)
    _draw_tcg_header(draw, pokemon_id, rarity, is_shiny, mega_key, types)

    # 9. 인포바
    _draw_tcg_info(draw, name_ko, rarity, iv_total, types)

    # 10. 하단 프레임 악센트 (메가/이로치)
    if mega_key:
        card = _draw_mega_bottom_line(card)
    elif is_shiny:
        line_h = 6
        row_rgb = _rainbow_row_rgb(CARD_WIDTH)
        line_pixels = [(*c, 240) for c in row_rgb] * line_h
        line_img = Image.new("RGBA", (CARD_WIDTH, line_h))
        line_img.putdata(line_pixels)
        rainbow_layer = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 0))
        rainbow_layer.paste(line_img, (0, CARD_HEIGHT - line_h))
        card = Image.alpha_composite(card, rainbow_layer)

    # Convert to bytes
    buf = io.BytesIO()
    card_rgb = card.convert("RGB")
    card_rgb.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    buf.name = "card.jpg"
    return buf


# ── Lineup Card (Finals VS image) ─────────────────────────────

# Smaller sprite loader for lineup card (160px)
@lru_cache(maxsize=48)
def _load_sprite_small(pokemon_id: int) -> Image.Image | None:
    """Load and scale a Pokemon sprite to 160px for lineup card."""
    sprite_path = ASSETS_DIR / f"{pokemon_id}.png"
    if not sprite_path.exists():
        return None
    sprite = Image.open(sprite_path).convert("RGBA")
    max_size = 160
    ratio = min(max_size / sprite.width, max_size / sprite.height)
    new_w = int(sprite.width * ratio)
    new_h = int(sprite.height * ratio)
    return sprite.resize((new_w, new_h), Image.LANCZOS)


def generate_lineup_card(
    p1_name: str,
    p1_team: list[dict],
    p2_name: str,
    p2_team: list[dict],
    date_str: str = "",
) -> io.BytesIO:
    """Generate a VS lineup card image for tournament finals.

    Each team entry: {"pokemon_id": int, "name": str, "rarity": str, "is_shiny": bool}
    Returns BytesIO (JPEG).
    """
    from datetime import datetime

    W, H = 1200, 680
    if not date_str:
        import config as _cfg
        date_str = _cfg.get_kst_now().strftime("%Y.%m.%d")

    # ── Background: bold red / black diagonal split ──
    card = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    draw = ImageDraw.Draw(card)

    # Red left half (solid, strong)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    ov_draw.polygon(
        [(0, 0), (W // 2 + 80, 0), (W // 2 - 80, H), (0, H)],
        fill=(190, 30, 30, 255),
    )
    card = Image.alpha_composite(card, overlay)

    # Subtle gradient shading on the diagonal edge
    edge_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    edge_draw = ImageDraw.Draw(edge_layer)
    for i in range(40):
        alpha = int(60 * (1 - i / 40))
        offset = i * 2
        edge_draw.polygon(
            [(W // 2 - 80 + offset, H), (W // 2 + 80 + offset, 0),
             (W // 2 + 82 + offset, 0), (W // 2 - 78 + offset, H)],
            fill=(0, 0, 0, alpha),
        )
    card = Image.alpha_composite(card, edge_layer)
    draw = ImageDraw.Draw(card)

    # Center point
    cx, cy = W // 2, H // 2

    # ── Fonts ──
    font_vs = _get_font(90, "impact")
    font_banner = _get_font(28, "bold")
    font_title = _get_font(30, "bold")
    font_name = _get_font(17, "bold")
    font_rarity = _get_font(12, "bold")
    font_date = _get_font(14, "bold")

    # ── "TG포켓 결승전" banner at very top ──
    banner_text = "TG포켓 결승전"
    b_bbox = draw.textbbox((0, 0), banner_text, font=font_banner)
    b_w = b_bbox[2] - b_bbox[0]
    bx = cx - b_w // 2
    by = 10
    draw.text((bx + 1, by + 1), banner_text, fill=(0, 0, 0, 180), font=font_banner)
    draw.text((bx, by), banner_text, fill=(255, 220, 80, 255), font=font_banner)

    # ── Trainer names below banner ──
    name_y = 48
    p1_bbox = draw.textbbox((0, 0), p1_name, font=font_title)
    p1_tw = p1_bbox[2] - p1_bbox[0]
    p1_tx = (W // 4) - p1_tw // 2
    draw.text((p1_tx + 2, name_y + 2), p1_name, fill=(0, 0, 0, 150), font=font_title)
    draw.text((p1_tx, name_y), p1_name, fill=(255, 255, 255, 255), font=font_title)

    p2_bbox = draw.textbbox((0, 0), p2_name, font=font_title)
    p2_tw = p2_bbox[2] - p2_bbox[0]
    p2_tx = (W * 3 // 4) - p2_tw // 2
    draw.text((p2_tx + 2, name_y + 2), p2_name, fill=(0, 0, 0, 150), font=font_title)
    draw.text((p2_tx, name_y), p2_name, fill=(255, 255, 255, 255), font=font_title)

    # Thin accent lines under names
    draw.line([(30, 86), (W // 2 - 50, 86)], fill=(255, 255, 255, 80), width=1)
    draw.line([(W // 2 + 50, 86), (W - 30, 86)], fill=(255, 255, 255, 80), width=1)

    # ── Draw team slots: 3x2 grid on each side ──
    def _draw_team(team: list[dict], base_x: int, base_y: int):
        slot_w, slot_h = 150, 175
        gap_x, gap_y = 10, 8
        cols = 3

        for i, mon in enumerate(team[:6]):
            col = i % cols
            row = i // cols
            sx = base_x + col * (slot_w + gap_x)
            sy = base_y + row * (slot_h + gap_y)

            pid = mon.get("pokemon_id", 0)
            name = mon.get("name", "???")
            rarity = mon.get("rarity", "common")
            is_shiny = mon.get("is_shiny", False)
            accent = RARITY_ACCENT.get(rarity, RARITY_ACCENT["common"])

            # Slot background (semi-transparent dark)
            draw.rounded_rectangle(
                [sx, sy, sx + slot_w, sy + slot_h],
                radius=8,
                fill=(10, 12, 18, 190),
                outline=(*accent, 120),
                width=2,
            )
            if is_shiny:
                draw.rounded_rectangle(
                    [sx - 1, sy - 1, sx + slot_w + 1, sy + slot_h + 1],
                    radius=9, outline=(255, 215, 0, 200), width=2,
                )

            # Mini glow
            gcx, gcy = sx + slot_w // 2, sy + 70
            for r in range(45, 0, -3):
                a = int(18 * (r / 45))
                draw.ellipse([gcx - r, gcy - r, gcx + r, gcy + r], fill=(*accent, a))

            # Sprite
            sprite = _load_sprite_small(pid)
            if sprite:
                spx = sx + (slot_w - sprite.width) // 2
                spy = sy + 8 + (120 - sprite.height) // 2
                card.paste(sprite, (spx, spy), sprite)

            # Pokemon name
            n_bbox = draw.textbbox((0, 0), name, font=font_name)
            n_w = n_bbox[2] - n_bbox[0]
            nx = sx + (slot_w - n_w) // 2
            ny = sy + slot_h - 30
            draw.text((nx + 1, ny + 1), name, fill=(0, 0, 0, 200), font=font_name)
            draw.text((nx, ny), name, fill=(255, 255, 255, 240), font=font_name)

            # Shiny sparkle indicator (top-right corner)
            if is_shiny:
                font_sparkle = _get_font(18, "bold")
                draw.text((sx + slot_w - 22, sy + 4), "*", fill=(255, 215, 0, 255), font=font_sparkle)
                draw.text((sx + slot_w - 14, sy + 12), "*", fill=(255, 255, 180, 200), font=_get_font(12, "bold"))

    _draw_team(p1_team, 25, 95)
    _draw_team(p2_team, W // 2 + 80, 95)

    # ── VS text LAST (drawn on top of everything) ──
    vs_text = "VS"
    vs_bbox = draw.textbbox((0, 0), vs_text, font=font_vs)
    vs_w = vs_bbox[2] - vs_bbox[0]
    vs_h = vs_bbox[3] - vs_bbox[1]
    vs_x = cx - vs_w // 2
    vs_y = cy - vs_h // 2 - 10

    # Dark backdrop behind VS for readability
    vs_pad = 20
    vs_bg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    vs_bg_draw = ImageDraw.Draw(vs_bg)
    vs_bg_draw.rounded_rectangle(
        [vs_x - vs_pad, vs_y - vs_pad // 2,
         vs_x + vs_w + vs_pad, vs_y + vs_h + 40],
        radius=12, fill=(0, 0, 0, 160),
    )
    card = Image.alpha_composite(card, vs_bg)
    draw = ImageDraw.Draw(card)

    # Shadow layers for depth
    for off in range(8, 0, -1):
        a = int(90 * (off / 8))
        draw.text((vs_x + off, vs_y + off), vs_text, fill=(0, 0, 0, a), font=font_vs)
    # Dark outline
    for dx in (-3, -2, -1, 0, 1, 2, 3):
        for dy in (-3, -2, -1, 0, 1, 2, 3):
            if dx or dy:
                draw.text((vs_x + dx, vs_y + dy), vs_text, fill=(30, 30, 30, 255), font=font_vs)
    # White fill
    draw.text((vs_x, vs_y), vs_text, fill=(255, 255, 255, 255), font=font_vs)

    # Date at bottom center
    d_bbox = draw.textbbox((0, 0), date_str, font=font_date)
    d_w = d_bbox[2] - d_bbox[0]
    dx = cx - d_w // 2
    dy = H - 28
    draw.text((dx + 1, dy + 1), date_str, fill=(0, 0, 0, 200), font=font_date)
    draw.text((dx, dy), date_str, fill=(200, 200, 200, 240), font=font_date)

    # Bottom accent bar
    draw.rectangle([0, H - 3, W, H], fill=(255, 255, 255, 100))

    # Output
    buf = io.BytesIO()
    card_rgb = card.convert("RGB")
    card_rgb.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    buf.name = "lineup.jpg"
    return buf


# ── Champion Card (우승자 팀 표시) ──────────────────────────────

def generate_champion_card(
    winner_name: str,
    team: list[dict],
    date_str: str = "",
) -> io.BytesIO:
    """Generate a champion card showing the winner's team.

    Each team entry: {"pokemon_id": int, "name": str, "rarity": str, "is_shiny": bool}
    Returns BytesIO (JPEG).
    """
    W, H = 1200, 500

    if not date_str:
        import config as _cfg
        date_str = _cfg.get_kst_now().strftime("%Y.%m.%d")

    # ── Background: dark with gold accents ──
    card = Image.new("RGBA", (W, H), (15, 15, 25, 255))
    draw = ImageDraw.Draw(card)

    # Gold gradient strip at top
    for y in range(6):
        alpha = int(200 * (1 - y / 6))
        draw.line([(0, y), (W, y)], fill=(255, 215, 0, alpha))

    # Subtle radial glow behind team
    cx, cy = W // 2, H // 2 + 30
    for r in range(280, 0, -4):
        a = int(15 * (r / 280))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 200, 50, a))

    # ── Fonts ──
    font_title = _get_font(40, "bold")
    font_name = _get_font(36, "bold")
    font_poke = _get_font(16, "bold")
    font_rarity = _get_font(12, "bold")
    font_date = _get_font(14, "bold")

    # ── "🏆 CHAMPION" title ──
    title_text = "CHAMPION"
    t_bbox = draw.textbbox((0, 0), title_text, font=font_title)
    t_w = t_bbox[2] - t_bbox[0]
    tx = cx - t_w // 2
    ty = 18
    # Gold outline
    for dx in (-2, -1, 0, 1, 2):
        for dy in (-2, -1, 0, 1, 2):
            if dx or dy:
                draw.text((tx + dx, ty + dy), title_text, fill=(120, 90, 0, 255), font=font_title)
    draw.text((tx, ty), title_text, fill=(255, 215, 0, 255), font=font_title)

    # ── Winner name ──
    n_bbox = draw.textbbox((0, 0), winner_name, font=font_name)
    n_w = n_bbox[2] - n_bbox[0]
    nx = cx - n_w // 2
    ny = 68
    draw.text((nx + 2, ny + 2), winner_name, fill=(0, 0, 0, 180), font=font_name)
    draw.text((nx, ny), winner_name, fill=(255, 255, 255, 255), font=font_name)

    # Gold line under name
    draw.line([(cx - 180, 115), (cx + 180, 115)], fill=(255, 215, 0, 150), width=2)

    # ── Draw 6 Pokemon in a row ──
    slot_w, slot_h = 170, 200
    gap = 12
    total_w = 6 * slot_w + 5 * gap
    start_x = (W - total_w) // 2
    start_y = 135

    for i, mon in enumerate(team[:6]):
        sx = start_x + i * (slot_w + gap)
        sy = start_y

        pid = mon.get("pokemon_id", 0)
        name = mon.get("name", "???")
        rarity = mon.get("rarity", "common")
        is_shiny = mon.get("is_shiny", False)
        accent = RARITY_ACCENT.get(rarity, RARITY_ACCENT["common"])

        # Slot background
        draw.rounded_rectangle(
            [sx, sy, sx + slot_w, sy + slot_h],
            radius=10,
            fill=(10, 12, 18, 210),
            outline=(*accent, 140),
            width=2,
        )

        # Shiny gold border
        if is_shiny:
            draw.rounded_rectangle(
                [sx - 1, sy - 1, sx + slot_w + 1, sy + slot_h + 1],
                radius=11, outline=(255, 215, 0, 220), width=2,
            )

        # Mini glow
        gcx, gcy = sx + slot_w // 2, sy + 80
        for r in range(50, 0, -3):
            a = int(20 * (r / 50))
            draw.ellipse([gcx - r, gcy - r, gcx + r, gcy + r], fill=(*accent, a))

        # Sprite
        sprite = _load_sprite_small(pid)
        if sprite:
            spx = sx + (slot_w - sprite.width) // 2
            spy = sy + 10 + (130 - sprite.height) // 2
            card.paste(sprite, (spx, spy), sprite)

        # Pokemon name
        p_bbox = draw.textbbox((0, 0), name, font=font_poke)
        p_w = p_bbox[2] - p_bbox[0]
        px = sx + (slot_w - p_w) // 2
        py = sy + slot_h - 35
        draw.text((px + 1, py + 1), name, fill=(0, 0, 0, 200), font=font_poke)
        draw.text((px, py), name, fill=(255, 255, 255, 240), font=font_poke)

        # Shiny sparkle
        if is_shiny:
            font_sparkle = _get_font(18, "bold")
            draw.text((sx + slot_w - 22, sy + 4), "*", fill=(255, 215, 0, 255), font=font_sparkle)
            draw.text((sx + slot_w - 14, sy + 12), "*", fill=(255, 255, 180, 200), font=_get_font(12, "bold"))

    # Date at bottom
    d_bbox = draw.textbbox((0, 0), date_str, font=font_date)
    d_w = d_bbox[2] - d_bbox[0]
    dx = cx - d_w // 2
    dy = H - 30
    draw.text((dx + 1, dy + 1), date_str, fill=(0, 0, 0, 200), font=font_date)
    draw.text((dx, dy), date_str, fill=(180, 180, 180, 240), font=font_date)

    # Bottom gold bar
    for y in range(H - 4, H):
        alpha = int(200 * ((H - y) / 4))
        draw.line([(0, y), (W, y)], fill=(255, 215, 0, alpha))

    # Output
    buf = io.BytesIO()
    card_rgb = card.convert("RGB")
    card_rgb.save(buf, format="JPEG", quality=92)
    buf.seek(0)
    buf.name = "champion.jpg"
    return buf


# ── Pokedex Device Card (도감 전용) ─────────────────────────────

# Rarity → circle glow color (brighter version of accent)
_RARITY_CIRCLE = {
    "common":         (100, 210, 160),
    "rare":           (90, 170, 255),
    "epic":           (200, 150, 255),
    "legendary":      (255, 230, 50),
    "ultra_legendary": (255, 80, 80),
}

_RARITY_LABEL_KO = {
    "common": "일반",
    "rare": "레어",
    "epic": "에픽",
    "legendary": "전설",
    "ultra_legendary": "초전설",
}


def generate_pokedex_card(
    pokemon_id: int,
    name_ko: str,
    rarity: str,
    emoji: str = "",
    pokemon_type: str = "",
    type_names: str = "",
    catch_rate: float = 0.0,
    owned: bool = False,
) -> io.BytesIO:
    """Generate a Pokedex-device-style card (960x540, 16:9).

    Features a device frame with screen area, circular rarity glow
    behind the Pokemon, and info panel on the right side.
    """
    W, H = 960, 540
    accent = RARITY_ACCENT.get(rarity, RARITY_ACCENT["common"])
    circle_color = _RARITY_CIRCLE.get(rarity, _RARITY_CIRCLE["common"])

    card = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # ── 1. Device outer body (red metallic frame) ──
    draw = ImageDraw.Draw(card)

    # Outer shell - dark red gradient feel
    draw.rounded_rectangle([0, 0, W - 1, H - 1], radius=24,
                           fill=(180, 35, 35, 255))
    # Inner darker band for depth
    draw.rounded_rectangle([4, 4, W - 5, H - 5], radius=22,
                           fill=(155, 28, 28, 255))
    # Highlight strip at top (glossy feel)
    highlight = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    h_draw = ImageDraw.Draw(highlight)
    h_draw.rounded_rectangle([6, 6, W - 7, 50], radius=20,
                             fill=(255, 255, 255, 25))
    card = Image.alpha_composite(card, highlight)
    draw = ImageDraw.Draw(card)

    # ── 2. Screen area (dark inset) ──
    scr_x, scr_y = 20, 20
    scr_w, scr_h = W - 40, H - 40  # 920 x 500
    # Screen bezel (dark border)
    draw.rounded_rectangle(
        [scr_x - 2, scr_y - 2, scr_x + scr_w + 2, scr_y + scr_h + 2],
        radius=14, fill=(30, 30, 30, 255),
    )
    # Screen background - dark blue-black
    draw.rounded_rectangle(
        [scr_x, scr_y, scr_x + scr_w, scr_y + scr_h],
        radius=12, fill=(12, 18, 30, 255),
    )

    # ── 3. Screen grid lines (subtle tech feel) ──
    for gx in range(scr_x + 40, scr_x + scr_w, 60):
        draw.line([(gx, scr_y + 10), (gx, scr_y + scr_h - 10)],
                  fill=(40, 55, 75, 40), width=1)
    for gy in range(scr_y + 40, scr_y + scr_h, 60):
        draw.line([(scr_x + 10, gy), (scr_x + scr_w - 10, gy)],
                  fill=(40, 55, 75, 40), width=1)

    # ── 4. Left section: Pokemon with circle glow ──
    left_cx = scr_x + 250  # center of pokemon area
    left_cy = scr_y + scr_h // 2 - 10

    # Circular rarity glow (large, soft)
    glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)

    # Outer soft glow
    for i in range(40, 0, -1):
        alpha = int(35 * (i / 40))
        r = int(170 * (i / 40))
        glow_draw.ellipse(
            [left_cx - r, left_cy - r, left_cx + r, left_cy + r],
            fill=(*circle_color, alpha),
        )
    card = Image.alpha_composite(card, glow_layer)
    draw = ImageDraw.Draw(card)

    # Solid circle behind pokemon (rarity color)
    draw.ellipse(
        [left_cx - 120, left_cy - 120, left_cx + 120, left_cy + 120],
        fill=(*accent, 60),
        outline=(*accent, 120),
        width=2,
    )

    # Pokemon sprite (centered on circle)
    sprite = _load_sprite(pokemon_id)
    if sprite:
        sx = left_cx - sprite.width // 2
        sy = left_cy - sprite.height // 2
        card.paste(sprite, (sx, sy), sprite)

    # ── 5. Right section: Info panel ──
    info_x = scr_x + 480
    info_y = scr_y + 30
    info_w = scr_w - 490
    font_id = _get_font(48, "impact")
    font_name = _get_font(34, "bold")
    font_info = _get_font(21, "regular")
    font_badge = _get_font(19, "bold")

    # Pokemon ID (large, top of info area)
    id_text = f"#{pokemon_id:03d}"
    draw.text((info_x + 2, info_y + 2), id_text,
              fill=(0, 0, 0, 180), font=font_id)
    draw.text((info_x, info_y), id_text,
              fill=(*accent, 255), font=font_id)

    # Pokemon name
    name_y = info_y + 62
    draw.text((info_x + 1, name_y + 1), name_ko,
              fill=(0, 0, 0, 180), font=font_name)
    draw.text((info_x, name_y), name_ko,
              fill=(255, 255, 255, 255), font=font_name)

    # Divider line
    div_y = name_y + 48
    draw.line([(info_x, div_y), (info_x + info_w, div_y)],
              fill=(*accent, 100), width=2)

    # Rarity badge - smart text color (dark text on bright backgrounds)
    rarity_label = _RARITY_LABEL_KO.get(rarity, rarity)
    badge_y = div_y + 16
    rbbox = draw.textbbox((0, 0), rarity_label, font=font_badge)
    rw = rbbox[2] - rbbox[0]
    draw.rounded_rectangle(
        [info_x, badge_y - 4, info_x + rw + 20, badge_y + 26],
        radius=5, fill=(*accent, 220),
    )
    # Use dark text on bright badges (legendary/common), white on dark
    badge_brightness = accent[0] * 0.299 + accent[1] * 0.587 + accent[2] * 0.114
    badge_text_color = (20, 20, 20, 255) if badge_brightness > 160 else (255, 255, 255, 255)
    draw.text((info_x + 10, badge_y), rarity_label,
              fill=badge_text_color, font=font_badge)

    # Type info
    if type_names:
        type_y = badge_y + 40
        draw.text((info_x, type_y), f"타입  {type_names}",
                  fill=(190, 210, 230, 255), font=font_info)

    # Catch rate
    if catch_rate > 0:
        rate_y = badge_y + 40 + (30 if type_names else 0)
        rate_pct = int(catch_rate * 100)
        draw.text((info_x, rate_y), f"포획률  {rate_pct}%",
                  fill=(190, 210, 230, 255), font=font_info)

    # Owned status (colored dot + text, avoids Unicode glyph issues)
    status_y = badge_y + 80 + (30 if type_names else 0)
    dot_r = 7
    dot_cy = status_y + 11
    if owned:
        draw.ellipse([info_x, dot_cy - dot_r, info_x + dot_r * 2, dot_cy + dot_r],
                     fill=(100, 220, 140, 255))
        draw.text((info_x + dot_r * 2 + 8, status_y), "보유 중",
                  fill=(100, 220, 140, 255), font=font_info)
    else:
        draw.ellipse([info_x, dot_cy - dot_r, info_x + dot_r * 2, dot_cy + dot_r],
                     fill=(200, 100, 100, 255))
        draw.text((info_x + dot_r * 2 + 8, status_y), "미보유",
                  fill=(200, 100, 100, 255), font=font_info)

    # ── 6. Device decorations ──
    # Small LED indicator (top-left of device, like a camera/sensor)
    draw.ellipse([30, 8, 40, 18], fill=(50, 50, 60, 255),
                 outline=(80, 80, 90, 255))
    draw.ellipse([32, 10, 38, 16], fill=(80, 200, 255, 180))

    # Two small dots next to LED
    draw.ellipse([46, 10, 52, 16], fill=(200, 60, 60, 180))
    draw.ellipse([58, 10, 64, 16], fill=(120, 200, 80, 180))

    # Bottom bar - thin accent line inside screen
    draw.rectangle(
        [scr_x + 10, scr_y + scr_h - 6, scr_x + scr_w - 10, scr_y + scr_h - 4],
        fill=(*accent, 80),
    )

    # "POKEDEX" watermark bottom-right of screen
    font_wm = _get_font(12, "bold")
    draw.text((scr_x + scr_w - 85, scr_y + scr_h - 22), "POKEDEX",
              fill=(60, 80, 100, 120), font=font_wm)

    # Output
    buf = io.BytesIO()
    card_rgb = card.convert("RGB")
    card_rgb.save(buf, format="JPEG", quality=88)
    buf.seek(0)
    buf.name = "pokedex.jpg"
    return buf


