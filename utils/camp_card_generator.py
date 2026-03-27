"""Generate 16:9 camp zone card images for news/event display."""

import io
import math
import random
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

from utils.card_generator import _get_font, _load_sprite, CARD_WIDTH, CARD_HEIGHT

# Zone → gradient colors (top, bottom)
ZONE_BG_COLORS = {
    "grass":    ((22, 60, 22),   (10, 30, 10)),
    "water":    ((14, 36, 70),   (8, 18, 40)),
    "fire":     ((70, 28, 12),   (40, 12, 5)),
    "rock":     ((55, 42, 24),   (28, 20, 12)),
    "sky":      ((30, 55, 80),   (15, 30, 50)),
    "shadow":   ((38, 18, 52),   (18, 8, 28)),
    "electric": ((65, 58, 12),   (35, 30, 5)),
}

# Zone → accent glow color
ZONE_ACCENT = {
    "grass":    (100, 200, 80),
    "water":    (80, 160, 240),
    "fire":     (240, 140, 60),
    "rock":     (180, 140, 90),
    "sky":      (140, 200, 255),
    "shadow":   (160, 100, 220),
    "electric": (255, 220, 50),
}

# Zone → ambient particle color
ZONE_PARTICLE = {
    "grass":    [(120, 220, 80), (180, 240, 100), (80, 200, 60)],
    "water":    [(80, 180, 255), (120, 200, 255), (60, 140, 220)],
    "fire":     [(255, 160, 40), (255, 100, 30), (255, 200, 80)],
    "rock":     [(200, 180, 140), (160, 140, 100), (220, 200, 160)],
    "sky":      [(200, 230, 255), (255, 255, 255), (160, 210, 255)],
    "shadow":   [(180, 100, 255), (140, 80, 200), (220, 140, 255)],
    "electric": [(255, 240, 80), (255, 255, 150), (255, 200, 40)],
}


@lru_cache(maxsize=8)
def _make_zone_gradient(width: int, height: int, top: tuple, bot: tuple) -> Image.Image:
    """Create vertical gradient for zone background."""
    img = Image.new("RGB", (width, height))
    pixels = []
    for y in range(height):
        ratio = y / height
        c = (
            int(top[0] + (bot[0] - top[0]) * ratio),
            int(top[1] + (bot[1] - top[1]) * ratio),
            int(top[2] + (bot[2] - top[2]) * ratio),
        )
        pixels.extend([c] * width)
    img.putdata(pixels)
    return img


def _draw_zone_glow(draw: ImageDraw.Draw, cx: int, cy: int, radius: int, color: tuple, steps: int = 25):
    """Draw soft zone glow (slightly larger than spawn card glow)."""
    for i in range(steps, 0, -1):
        alpha = int(35 * (i / steps))
        r = int(radius * (i / steps))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*color, alpha))


def _draw_ambient_particles(draw: ImageDraw.Draw, w: int, h: int, zone: str, seed: int = 0):
    """Draw zone-themed ambient particles (leaves, bubbles, sparks, etc.)."""
    colors = ZONE_PARTICLE.get(zone, [(200, 200, 200)])
    rng = random.Random(seed)

    particle_count = 35
    for _ in range(particle_count):
        x = rng.randint(0, w)
        y = rng.randint(0, h)
        color = rng.choice(colors)
        alpha = rng.randint(40, 120)
        size = rng.randint(2, 6)

        if zone == "grass":
            # Small leaf-like ellipses
            draw.ellipse([x - size, y - size // 2, x + size, y + size // 2],
                         fill=(*color, alpha))
        elif zone == "water":
            # Circular bubbles
            draw.ellipse([x - size, y - size, x + size, y + size],
                         outline=(*color, alpha), width=1)
        elif zone == "fire":
            # Upward spark lines
            length = rng.randint(4, 12)
            draw.line([(x, y), (x + rng.randint(-2, 2), y - length)],
                      fill=(*color, alpha), width=1)
        elif zone == "rock":
            # Small diamond shapes
            s = size
            draw.polygon([(x, y - s), (x + s, y), (x, y + s), (x - s, y)],
                         fill=(*color, alpha // 2))
        elif zone == "sky":
            # Soft cloud-like circles
            draw.ellipse([x - size * 2, y - size, x + size * 2, y + size],
                         fill=(*color, alpha // 2))
        elif zone == "shadow":
            # Ghostly wisps
            draw.ellipse([x - size, y - size, x + size, y + size],
                         fill=(*color, alpha))
            draw.ellipse([x - 1, y - 1, x + 1, y + 1],
                         fill=(255, 255, 255, alpha))
        elif zone == "electric":
            # Small lightning dots
            draw.ellipse([x - size, y - size, x + size, y + size],
                         fill=(*color, alpha))
            # Tiny ray
            angle = rng.uniform(0, 2 * math.pi)
            ex = int(x + size * 3 * math.cos(angle))
            ey = int(y + size * 3 * math.sin(angle))
            draw.line([(x, y), (ex, ey)], fill=(*color, alpha // 2), width=1)


def _draw_zone_label(draw: ImageDraw.Draw, zone_name: str, zone_emoji: str, w: int):
    """Draw zone label at top-left."""
    font = _get_font(18)
    label = f"{zone_emoji} {zone_name}"
    # Shadow
    draw.text((22, 16), label, fill=(0, 0, 0, 150), font=font)
    draw.text((20, 14), label, fill=(255, 255, 255, 220), font=font)


def _draw_news_text(draw: ImageDraw.Draw, text: str, w: int, h: int, accent: tuple):
    """Draw news/event text at bottom of card."""
    font = _get_font(22)
    # Truncate if too long
    if len(text) > 40:
        text = text[:38] + "…"

    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    tx = (w - tw) // 2
    ty = h - 60

    # Text shadow
    draw.text((tx + 1, ty + 1), text, fill=(0, 0, 0, 200), font=font)
    draw.text((tx, ty), text, fill=(255, 255, 255, 255), font=font)


def _draw_zone_accent_line(draw: ImageDraw.Draw, w: int, h: int, accent: tuple):
    """Draw accent line at bottom."""
    draw.rectangle([0, h - 4, w, h], fill=(*accent, 200))


def generate_camp_card(
    pokemon_id: int,
    name_ko: str,
    zone_key: str,
    zone_name: str,
    zone_emoji: str,
    news_text: str = "",
    is_shiny: bool = False,
    seed: int = 42,
) -> io.BytesIO:
    """Generate a camp zone card image and return as BytesIO (JPEG).

    Parameters:
        pokemon_id: Pokemon sprite ID
        name_ko: Pokemon Korean name
        zone_key: Zone key (grass, water, fire, etc.)
        zone_name: Zone display name (풀숲, 호수, etc.)
        zone_emoji: Zone emoji
        news_text: Optional text to display at bottom
        is_shiny: Whether pokemon is shiny (adds sparkle effect)
        seed: Random seed for consistent particle generation
    """
    top_col, bot_col = ZONE_BG_COLORS.get(zone_key, ZONE_BG_COLORS["grass"])
    accent = ZONE_ACCENT.get(zone_key, ZONE_ACCENT["grass"])

    # 1. Gradient background
    card = _make_zone_gradient(CARD_WIDTH, CARD_HEIGHT, top_col, bot_col).copy()
    card = card.convert("RGBA")

    # 2. Ambient particles (behind pokemon)
    particle_layer = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 0))
    particle_draw = ImageDraw.Draw(particle_layer)
    _draw_ambient_particles(particle_draw, CARD_WIDTH, CARD_HEIGHT, zone_key, seed)
    card = Image.alpha_composite(card, particle_layer)

    # 3. Zone glow
    glow_layer = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)
    cx, cy = CARD_WIDTH // 2, CARD_HEIGHT // 2 - 20
    _draw_zone_glow(glow_draw, cx, cy, 220, accent)
    card = Image.alpha_composite(card, glow_layer)

    # 4. Shiny extra glow
    if is_shiny:
        shiny_layer = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 0))
        shiny_draw = ImageDraw.Draw(shiny_layer)
        bright = tuple(min(255, c + 80) for c in accent)
        for i in range(20, 0, -1):
            alpha = int(40 * (i / 20))
            r = int(250 * (i / 20))
            shiny_draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*bright, alpha))

        # Sparkle particles
        rng = random.Random(seed + 7)
        for _ in range(30):
            angle = rng.uniform(0, 2 * math.pi)
            dist = rng.uniform(50, 200)
            sx = int(cx + dist * math.cos(angle))
            sy = int(cy + dist * math.sin(angle))
            if 0 <= sx < CARD_WIDTH and 0 <= sy < CARD_HEIGHT:
                s = rng.choice([2, 3, 4])
                sa = rng.randint(120, 230)
                arm = s * 2
                shiny_draw.line([(sx, sy - arm), (sx, sy + arm)],
                                fill=(255, 255, 255, sa), width=1)
                shiny_draw.line([(sx - arm, sy), (sx + arm, sy)],
                                fill=(255, 255, 255, sa), width=1)
                shiny_draw.ellipse([sx - s, sy - s, sx + s, sy + s],
                                   fill=(255, 255, 255, sa))
        card = Image.alpha_composite(card, shiny_layer)

    # 5. Pokemon sprite
    sprite = _load_sprite(pokemon_id)
    if sprite:
        sx = (CARD_WIDTH - sprite.width) // 2
        sy = (CARD_HEIGHT - sprite.height) // 2 - 30
        card.paste(sprite, (sx, sy), sprite)

    # 6. Overlays
    draw = ImageDraw.Draw(card)

    # Zone label (top-left)
    _draw_zone_label(draw, zone_name, zone_emoji, CARD_WIDTH)

    # Pokemon name (center-bottom area)
    font_name = _get_font(28)
    name_bbox = draw.textbbox((0, 0), name_ko, font=font_name)
    nw = name_bbox[2] - name_bbox[0]
    nx = (CARD_WIDTH - nw) // 2

    if news_text:
        ny = CARD_HEIGHT - 88
    else:
        ny = CARD_HEIGHT - 60

    draw.text((nx + 1, ny + 1), name_ko, fill=(0, 0, 0, 180), font=font_name)
    draw.text((nx, ny), name_ko, fill=(255, 255, 255, 255), font=font_name)

    # Shiny badge
    if is_shiny:
        font_small = _get_font(16)
        shiny_text = "✨ 이로치"
        sbbox = draw.textbbox((0, 0), shiny_text, font=font_small)
        sw = sbbox[2] - sbbox[0]
        draw.rounded_rectangle(
            [CARD_WIDTH - sw - 28, 12, CARD_WIDTH - 12, 34],
            radius=5,
            fill=(205, 92, 92, 200),
        )
        draw.text((CARD_WIDTH - sw - 22, 13), shiny_text,
                   fill=(255, 255, 255, 255), font=font_small)

    # News text (bottom)
    if news_text:
        _draw_news_text(draw, news_text, CARD_WIDTH, CARD_HEIGHT, accent)

    # Accent line
    _draw_zone_accent_line(draw, CARD_WIDTH, CARD_HEIGHT, accent)

    # Convert to bytes
    buf = io.BytesIO()
    card_rgb = card.convert("RGB")
    card_rgb.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    buf.name = "camp_card.jpg"
    return buf
