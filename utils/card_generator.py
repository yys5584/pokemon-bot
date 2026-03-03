"""Generate 16:9 Pokemon card images for spawn/pokedex display."""

import io
import os
from pathlib import Path
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

ASSETS_DIR = Path(__file__).parent.parent / "assets" / "pokemon"
CARD_WIDTH = 960
CARD_HEIGHT = 540  # 16:9

# Rarity → gradient colors (top, bottom)
RARITY_COLORS = {
    "common":    ((34, 49, 34),   (20, 30, 20)),
    "rare":      ((20, 40, 80),   (10, 20, 50)),
    "epic":      ((55, 20, 80),   (30, 10, 50)),
    "legendary": ((80, 65, 10),   (50, 35, 5)),
}

# Rarity → accent color for border/glow
RARITY_ACCENT = {
    "common":    (82, 183, 136),
    "rare":      (72, 149, 239),
    "epic":      (177, 133, 219),
    "legendary": (255, 214, 10),
}


@lru_cache(maxsize=8)
def _make_gradient(width: int, height: int, top_color: tuple, bottom_color: tuple) -> Image.Image:
    """Create a vertical gradient image (cached per rarity)."""
    img = Image.new("RGB", (width, height))
    pixels = img.load()
    for y in range(height):
        ratio = y / height
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * ratio)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * ratio)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * ratio)
        for x in range(width):
            pixels[x, y] = (r, g, b)
    return img.copy()  # Return copy so original cache isn't mutated


@lru_cache(maxsize=256)
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


def generate_card(pokemon_id: int, name_ko: str, rarity: str, emoji: str = "") -> io.BytesIO:
    """Generate a 16:9 Pokemon card image and return as BytesIO (PNG)."""
    top_col, bot_col = RARITY_COLORS.get(rarity, RARITY_COLORS["common"])
    accent = RARITY_ACCENT.get(rarity, RARITY_ACCENT["common"])

    # 1. Gradient background
    card = _make_gradient(CARD_WIDTH, CARD_HEIGHT, top_col, bot_col)
    card = card.convert("RGBA")

    # 2. Glow behind Pokemon
    glow_layer = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)
    cx, cy = CARD_WIDTH // 2, CARD_HEIGHT // 2 - 10
    _draw_glow(glow_draw, cx, cy, 200, accent)
    card = Image.alpha_composite(card, glow_layer)

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
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 32)
        font_small = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 18)
    except (OSError, IOError):
        font = ImageFont.load_default()
        font_small = font

    # Name
    text = f"{emoji} {name_ko}" if emoji else name_ko
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    tx = (CARD_WIDTH - tw) // 2
    ty = CARD_HEIGHT - 65

    # Text shadow
    draw.text((tx + 2, ty + 2), text, fill=(0, 0, 0, 180), font=font)
    draw.text((tx, ty), text, fill=(255, 255, 255, 255), font=font)

    # Rarity label top-right
    rarity_labels = {"common": "일반", "rare": "희귀", "epic": "레어", "legendary": "전설"}
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

    # 6. Pokemon ID top-left
    id_text = f"#{pokemon_id:03d}"
    draw.text((22, 16), id_text, fill=(255, 255, 255, 100), font=font_small)

    # Convert to bytes (JPEG: much smaller & faster than PNG)
    buf = io.BytesIO()
    card_rgb = card.convert("RGB")
    card_rgb.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    buf.name = "card.jpg"  # Telegram needs extension hint
    return buf
