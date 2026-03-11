"""Generate 16:9 Pokemon card images for spawn/pokedex display."""

import io
import math
import os
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


def generate_card(pokemon_id: int, name_ko: str, rarity: str, emoji: str = "",
                  is_shiny: bool = False) -> io.BytesIO:
    """Generate a 16:9 Pokemon card image and return as BytesIO (PNG)."""
    top_col, bot_col = RARITY_COLORS.get(rarity, RARITY_COLORS["common"])
    accent = RARITY_ACCENT.get(rarity, RARITY_ACCENT["common"])

    # 1. Gradient background
    card = _make_gradient(CARD_WIDTH, CARD_HEIGHT, top_col, bot_col)
    card = card.convert("RGBA")

    # 2. Glow behind Pokemon (enhanced for shiny)
    glow_layer = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)
    cx, cy = CARD_WIDTH // 2, CARD_HEIGHT // 2 - 10
    _draw_glow(glow_draw, cx, cy, 200, accent)
    card = Image.alpha_composite(card, glow_layer)

    if is_shiny:
        card = _draw_shiny_glow(card, accent)

    # 3. Load and place Pokemon sprite (cached & pre-scaled)
    sprite = _load_sprite(pokemon_id)
    if sprite:
        sx = (CARD_WIDTH - sprite.width) // 2
        sy = (CARD_HEIGHT - sprite.height) // 2 - 30
        card.paste(sprite, (sx, sy), sprite)

    # 4. Draw rarity accent line at bottom
    draw = ImageDraw.Draw(card)
    draw.rectangle(
        [0, CARD_HEIGHT - 4, CARD_WIDTH, CARD_HEIGHT],
        fill=(*accent, 255),
    )

    # 5. Pokemon name text at bottom
    font = _get_font(32)
    font_small = _get_font(18)

    # Name (emoji omitted — font can't render Unicode emoji)
    text = name_ko
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    tx = (CARD_WIDTH - tw) // 2
    ty = CARD_HEIGHT - 65

    # Text shadow
    draw.text((tx + 2, ty + 2), text, fill=(0, 0, 0, 180), font=font)
    draw.text((tx, ty), text, fill=(255, 255, 255, 255), font=font)

    # Rarity label top-right
    rarity_labels = {"common": "일반", "rare": "레어", "epic": "에픽", "legendary": "전설", "ultra_legendary": "초전설"}
    rarity_text = rarity_labels.get(rarity, rarity)
    rbbox = draw.textbbox((0, 0), rarity_text, font=font_small)
    rw = rbbox[2] - rbbox[0]

    # Rarity badge background
    badge_x = CARD_WIDTH - rw - 28
    badge_y = 14
    draw.rounded_rectangle(
        [badge_x - 8, badge_y - 4, badge_x + rw + 8, badge_y + 24],
        radius=6,
        fill=(*accent, 200),
    )
    draw.text((badge_x, badge_y), rarity_text, fill=(255, 255, 255, 255), font=font_small)

    # Shiny badge (left of rarity badge)
    if is_shiny:
        shiny_text = "이로치"
        sbbox = draw.textbbox((0, 0), shiny_text, font=font_small)
        sw = sbbox[2] - sbbox[0]
        shiny_x = badge_x - sw - 28
        draw.rounded_rectangle(
            [shiny_x - 8, badge_y - 4, shiny_x + sw + 8, badge_y + 24],
            radius=6,
            fill=(205, 92, 92, 220),
        )
        draw.text((shiny_x, badge_y), shiny_text, fill=(255, 255, 255, 255), font=font_small)

    # 6. Pokemon ID top-left
    id_text = f"#{pokemon_id:03d}"
    draw.text((22, 16), id_text, fill=(255, 255, 255, 100), font=font_small)

    # 7. Shiny: thin rainbow accent line at bottom (replaces rarity line)
    if is_shiny:
        line_h = 6
        row_rgb = _rainbow_row_rgb(CARD_WIDTH)
        line_pixels = [(*c, 240) for c in row_rgb] * line_h
        line_img = Image.new("RGBA", (CARD_WIDTH, line_h))
        line_img.putdata(line_pixels)
        rainbow_layer = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 0))
        rainbow_layer.paste(line_img, (0, CARD_HEIGHT - line_h))
        card = Image.alpha_composite(card, rainbow_layer)

    # Convert to bytes (JPEG: much smaller & faster than PNG)
    buf = io.BytesIO()
    card_rgb = card.convert("RGB")
    card_rgb.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    buf.name = "card.jpg"  # Telegram needs extension hint
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
        date_str = datetime.now().strftime("%Y.%m.%d")

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
