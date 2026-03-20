"""Battle card, skill GIF, dungeon/tournament GIF generators."""

import io
import math
import os
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from utils.card_generator import (
    _get_font, _load_sprite, _make_gradient, _draw_glow,
    ASSETS_DIR, CARD_WIDTH, CARD_HEIGHT,
)

# ── Battle Card (결승전 스킬 이펙트 이미지) ──────────────────────

_BATTLE_TYPE_COLORS = {
    "fire": ((255, 70, 20), (255, 140, 30), (255, 200, 60)),
    "water": ((20, 80, 220), (50, 140, 255), (130, 210, 255)),
    "electric": ((200, 170, 0), (255, 230, 30), (255, 255, 180)),
    "grass": ((30, 140, 50), (60, 200, 80), (140, 240, 120)),
    "psychic": ((180, 40, 120), (220, 80, 180), (255, 160, 220)),
    "ice": ((40, 140, 200), (80, 200, 240), (180, 240, 255)),
    "dragon": ((80, 40, 180), (120, 70, 220), (180, 130, 255)),
    "dark": ((60, 40, 60), (100, 70, 100), (150, 120, 150)),
    "normal": ((160, 160, 140), (200, 200, 180), (230, 230, 220)),
    "fighting": ((160, 50, 20), (200, 80, 40), (240, 130, 70)),
    "poison": ((120, 40, 160), (160, 70, 200), (200, 130, 240)),
    "ground": ((160, 130, 50), (200, 170, 80), (230, 210, 130)),
    "flying": ((100, 140, 210), (140, 180, 240), (190, 220, 255)),
    "bug": ((120, 160, 20), (160, 200, 60), (200, 240, 110)),
    "rock": ((140, 120, 80), (180, 160, 120), (210, 200, 170)),
    "ghost": ((60, 40, 120), (100, 70, 170), (150, 120, 220)),
    "steel": ((140, 150, 170), (180, 190, 200), (210, 220, 230)),
    "fairy": ((210, 110, 160), (240, 150, 190), (255, 200, 225)),
}


def _draw_star4(draw: ImageDraw.Draw, cx: int, cy: int, size: int, color: tuple):
    """Draw a 4-pointed star (sparkle)."""
    pts = [
        (cx, cy - size),
        (cx + size // 4, cy - size // 4),
        (cx + size, cy),
        (cx + size // 4, cy + size // 4),
        (cx, cy + size),
        (cx - size // 4, cy + size // 4),
        (cx - size, cy),
        (cx - size // 4, cy - size // 4),
    ]
    draw.polygon(pts, fill=color)


def _draw_shiny_effect(card: Image.Image, cx: int, cy: int, radius: int = 190) -> Image.Image:
    """Shiny effect: radiant light rays + white sparkles."""
    from PIL import ImageFilter as IF
    layer = Image.new("RGBA", card.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    rng = random.Random(77)

    # Light rays
    for _ in range(16):
        angle = rng.uniform(0, 2 * math.pi)
        length = rng.randint(int(radius * 0.7), int(radius * 1.3))
        x1 = cx + int(20 * math.cos(angle))
        y1 = cy + int(20 * math.sin(angle))
        x2 = cx + int(length * math.cos(angle))
        y2 = cy + int(length * math.sin(angle))
        alpha = rng.randint(30, 70)
        w = rng.randint(3, 8)
        ld.line([(x1, y1), (x2, y2)], fill=(255, 255, 255, alpha), width=w)
        ld.line([(x1, y1), (x2, y2)], fill=(255, 255, 255, alpha + 30), width=max(1, w - 2))

    # Central glow
    for i in range(25, 0, -1):
        r = int(60 * (i / 25))
        a = int(15 * (i / 25))
        ld.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, a))

    # Small sparkles
    for _ in range(40):
        angle = rng.uniform(0, 2 * math.pi)
        dist = rng.randint(int(radius * 0.15), radius)
        px = cx + int(dist * math.cos(angle))
        py = cy + int(dist * math.sin(angle))
        size = rng.randint(3, 8)
        _draw_star4(ld, px, py, size, (255, 255, 255, rng.randint(150, 255)))

    # Medium sparkles
    for _ in range(15):
        angle = rng.uniform(0, 2 * math.pi)
        dist = rng.randint(int(radius * 0.1), int(radius * 0.85))
        px = cx + int(dist * math.cos(angle))
        py = cy + int(dist * math.sin(angle))
        size = rng.randint(10, 18)
        alpha = rng.randint(180, 255)
        _draw_star4(ld, px, py, size, (255, 255, 255, alpha))
        ld.ellipse([px - size, py - size, px + size, py + size],
                   fill=(255, 255, 255, alpha // 6))

    # Big sparkles
    for _ in range(4):
        angle = rng.uniform(0, 2 * math.pi)
        dist = rng.randint(int(radius * 0.2), int(radius * 0.5))
        px = cx + int(dist * math.cos(angle))
        py = cy + int(dist * math.sin(angle))
        size = rng.randint(20, 28)
        _draw_star4(ld, px, py, size, (255, 255, 255, 220))
        ld.ellipse([px - size - 4, py - size - 4, px + size + 4, py + size + 4],
                   fill=(255, 255, 255, 25))

    glow_layer = layer.filter(IF.GaussianBlur(radius=3))
    result = Image.alpha_composite(card, glow_layer)
    return Image.alpha_composite(result, layer)


# ── Type-specific FX ──

def _battle_fx_fire(fd, sx, sy, ex, ey, colors):
    deep, mid, bright = colors
    rng = random.Random(101)
    steps = 50
    for s in range(steps):
        t = s / steps
        x = sx + (ex - sx) * t
        y = sy + (ey - sy) * t + math.sin(t * math.pi * 3) * 18
        base_r = int(22 * (1 - t * 0.5))
        fd.ellipse([x - base_r - rng.randint(5, 14), y - base_r - 8, x + base_r + rng.randint(5, 14), y + base_r + 8],
                   fill=(*deep, int(80 * (1 - t * 0.6))))
        fd.ellipse([x - base_r - rng.randint(0, 5), y - base_r, x + base_r + rng.randint(0, 5), y + base_r],
                   fill=(*mid, int(130 * (1 - t * 0.4))))
        r_core = max(2, base_r - 6)
        fd.ellipse([x - r_core, y - r_core, x + r_core, y + r_core],
                   fill=(*bright, int(180 * (1 - t * 0.3))))
    # Fireball at 65%
    fb_x = sx + (ex - sx) * 0.65
    fb_y = sy + (ey - sy) * 0.65
    for i in range(40, 0, -1):
        ratio = i / 40
        r = int(50 * ratio)
        c = bright if ratio > 0.7 else (mid if ratio > 0.4 else deep)
        a = int((220 if ratio > 0.7 else (200 if ratio > 0.4 else 120)) * ratio)
        fd.ellipse([fb_x - r, fb_y - r, fb_x + r, fb_y + r], fill=(*c, a))
    # Embers
    for _ in range(50):
        t = rng.uniform(0.05, 1.05)
        x = sx + (ex - sx) * t + rng.randint(-40, 40)
        y = sy + (ey - sy) * t + rng.randint(-50, 30) - rng.randint(0, 20)
        r = rng.randint(1, 5)
        c = rng.choice([deep, mid, bright])
        fd.ellipse([x - r, y - r, x + r, y + r], fill=(*c, rng.randint(80, 220)))


def _battle_fx_electric(fd, sx, sy, ex, ey, colors):
    deep, mid, bright = colors
    rng = random.Random(202)
    for bolt in range(4):
        points = [(sx + rng.randint(-10, 10), sy + rng.randint(-15, 15))]
        for s in range(1, rng.randint(10, 16) + 1):
            t = s / 14
            points.append((sx + (ex - sx) * t, sy + (ey - sy) * t + rng.randint(-45, 45)))
        for w_layer, color, alpha in [(14, deep, 60), (6, mid, 160), (3, bright, 220)]:
            for i in range(len(points) - 1):
                fd.line([points[i], points[i + 1]], fill=(*color, alpha), width=w_layer)
        if bolt < 2:
            for _ in range(3):
                bp = points[rng.randint(2, len(points) - 2)]
                blen = rng.randint(30, 70)
                ba = rng.uniform(-math.pi / 3, math.pi / 3)
                bex, bey = bp[0] + blen * math.cos(ba), bp[1] + blen * math.sin(ba)
                fd.line([bp, (bex, bey)], fill=(*mid, 120), width=2)
    for _ in range(30):
        px = rng.randint(int(sx - 20), int(ex + 40))
        py = rng.randint(int(min(sy, ey) - 70), int(max(sy, ey) + 70))
        pr = rng.randint(1, 4)
        fd.ellipse([px - pr, py - pr, px + pr, py + pr], fill=(*bright, rng.randint(120, 255)))
    for gx, gy, gr in [(sx, sy, 35), (ex, ey, 30)]:
        for i in range(20, 0, -1):
            r = int(gr * (i / 20))
            fd.ellipse([gx - r, gy - r, gx + r, gy + r], fill=(*mid, int(40 * (i / 20))))


def _battle_fx_water(fd, sx, sy, ex, ey, colors):
    deep, mid, bright = colors
    rng = random.Random(303)
    for s in range(60):
        t = s / 60
        x = sx + (ex - sx) * t
        y = sy + (ey - sy) * t + math.sin(t * math.pi * 5) * 22
        bw = int(16 + 8 * math.sin(t * math.pi * 3))
        fd.ellipse([x - bw - rng.randint(4, 10), y - bw - 4, x + bw + rng.randint(4, 10), y + bw + 4],
                   fill=(*deep, 40))
        fd.ellipse([x - bw, y - bw, x + bw, y + bw], fill=(*mid, 100))
        rc = max(3, bw - 6)
        fd.ellipse([x - rc, y - rc, x + rc, y + rc], fill=(*bright, 160))
    for _ in range(45):
        t = rng.uniform(0.1, 1.15)
        x = sx + (ex - sx) * t + rng.randint(-50, 50)
        y = sy + (ey - sy) * t + rng.randint(-60, 40)
        r = rng.randint(2, 7)
        fd.ellipse([x - r, y - r, x + r, y + r], fill=(*rng.choice([mid, bright]), rng.randint(80, 200)))


def _battle_fx_psychic(fd, sx, sy, ex, ey, colors):
    deep, mid, bright = colors
    rng = random.Random(404)
    for i in range(8):
        t = i / 8
        x = sx + (ex - sx) * t
        y = sy + (ey - sy) * t
        rr = int(20 + 15 * math.sin(t * math.pi))
        alpha = int(160 - 80 * t)
        fd.ellipse([x - rr, y - rr, x + rr, y + rr], outline=(*bright, alpha), width=2)
        for w in range(4, 0, -1):
            fd.ellipse([x - rr - w, y - rr - w, x + rr + w, y + rr + w],
                       outline=(*mid, alpha // (5 - w)), width=2)
    for s in range(40):
        t = s / 40
        x = sx + (ex - sx) * t
        off = math.sin(t * math.pi * 4) * 25
        r = int(5 + 3 * (1 - t))
        alpha = int(120 - 50 * t)
        fd.ellipse([x - r, sy + (ey - sy) * t + off - r, x + r, sy + (ey - sy) * t + off + r],
                   fill=(*mid, alpha))
        fd.ellipse([x - r, sy + (ey - sy) * t - off - r, x + r, sy + (ey - sy) * t - off + r],
                   fill=(*deep, alpha))
    for _ in range(25):
        t = rng.uniform(0, 1)
        x = sx + (ex - sx) * t + rng.randint(-40, 40)
        y = sy + (ey - sy) * t + rng.randint(-40, 40)
        r = rng.randint(2, 5)
        fd.ellipse([x - r, y - r, x + r, y + r], fill=(*rng.choice([deep, mid, bright]), rng.randint(60, 180)))


def _battle_fx_generic(fd, sx, sy, ex, ey, colors):
    deep, mid, bright = colors
    rng = random.Random(505)
    for s in range(35):
        t = s / 35
        x = sx + (ex - sx) * t
        y = sy + (ey - sy) * t + math.sin(t * math.pi * 2.5) * 15
        r = int(14 * (1 - t * 0.4))
        fd.ellipse([x - r - 4, y - r - 4, x + r + 4, y + r + 4], fill=(*deep, int(60 * (1 - t * 0.5))))
        fd.ellipse([x - r, y - r, x + r, y + r], fill=(*mid, int(140 * (1 - t * 0.3))))
        rc = max(2, r - 5)
        fd.ellipse([x - rc, y - rc, x + rc, y + rc], fill=(*bright, int(180 * (1 - t * 0.3))))
    for _ in range(35):
        t = rng.uniform(0, 1.1)
        x = sx + (ex - sx) * t + rng.randint(-35, 35)
        y = sy + (ey - sy) * t + rng.randint(-35, 35)
        r = rng.randint(2, 5)
        fd.ellipse([x - r, y - r, x + r, y + r], fill=(*rng.choice([deep, mid, bright]), rng.randint(60, 180)))


_BATTLE_FX = {
    "fire": _battle_fx_fire,
    "electric": _battle_fx_electric,
    "water": _battle_fx_water,
    "ice": _battle_fx_water,
    "psychic": _battle_fx_psychic,
    "ghost": _battle_fx_psychic,
    "fairy": _battle_fx_psychic,
    "dragon": _battle_fx_generic,
}


def _battle_impact(fd, cx, cy, colors):
    deep, mid, bright = colors
    rng = random.Random(666)
    for i in range(3):
        r = 40 + i * 25
        fd.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*mid, max(10, 80 - i * 25)), width=2)
    for _ in range(18):
        angle = rng.uniform(0, 2 * math.pi)
        length = rng.randint(30, 90)
        x1 = cx + int(12 * math.cos(angle))
        y1 = cy + int(12 * math.sin(angle))
        x2 = cx + int(length * math.cos(angle))
        y2 = cy + int(length * math.sin(angle))
        fd.line([(x1, y1), (x2, y2)], fill=(*rng.choice([mid, bright]), rng.randint(80, 180)),
                width=rng.randint(1, 3))
    for _ in range(12):
        angle = rng.uniform(0, 2 * math.pi)
        dist = rng.randint(15, 65)
        px = cx + int(dist * math.cos(angle))
        py = cy + int(dist * math.sin(angle))
        pr = rng.randint(2, 5)
        fd.ellipse([px - pr, py - pr, px + pr, py + pr], fill=(*bright, rng.randint(100, 220)))


def generate_battle_card(
    atk_id: int, atk_name: str, def_id: int, def_name: str,
    skill_name: str, skill_type: str, damage: int,
    atk_shiny: bool = False, def_shiny: bool = False,
) -> io.BytesIO:
    """Generate a battle scene image with type-specific effects.

    Returns BytesIO (JPEG). Used in tournament finals.
    """
    from PIL import ImageFilter as IF

    W, H = CARD_WIDTH, CARD_HEIGHT  # 960x540
    colors = _BATTLE_TYPE_COLORS.get(skill_type, _BATTLE_TYPE_COLORS["normal"])

    card = _make_gradient(W, H, (10, 12, 22), (4, 4, 10)).convert("RGBA")

    ATK_CX, ATK_CY = 220, 255
    DEF_CX, DEF_CY = 720, 265

    # Attacker type glow
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for i in range(30, 0, -1):
        a = int(25 * (i / 30))
        r = int(180 * (i / 30))
        gd.ellipse([ATK_CX - r, ATK_CY - r, ATK_CX + r, ATK_CY + r], fill=(*colors[0], a))
    for i in range(22, 0, -1):
        a = int(10 * (i / 22))
        r = int(140 * (i / 22))
        gd.ellipse([DEF_CX - r, DEF_CY - r, DEF_CX + r, DEF_CY + r], fill=(120, 30, 30, a))
    card = Image.alpha_composite(card, glow)

    # Skill FX
    fx = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fx_draw = ImageDraw.Draw(fx)
    fx_func = _BATTLE_FX.get(skill_type, _battle_fx_generic)
    fx_func(fx_draw, ATK_CX + 80, ATK_CY, DEF_CX - 40, DEF_CY, colors)
    _battle_impact(fx_draw, DEF_CX, DEF_CY, colors)
    fx_glow = fx.filter(IF.GaussianBlur(radius=4))
    card = Image.alpha_composite(card, fx_glow)
    card = Image.alpha_composite(card, fx)

    # Shiny sparkles
    if atk_shiny:
        card = _draw_shiny_effect(card, ATK_CX, ATK_CY, 180)
    if def_shiny:
        card = _draw_shiny_effect(card, DEF_CX, DEF_CY, 150)

    # Attacker sprite
    atk_sprite = _load_sprite(atk_id)
    if atk_sprite:
        ax = ATK_CX - atk_sprite.width // 2 + 15
        ay = ATK_CY - atk_sprite.height // 2 - 15
        card.paste(atk_sprite, (ax, ay), atk_sprite)

    # Defender sprite (faded + red tint, no box)
    def_sprite = _load_sprite(def_id)
    if def_sprite:
        # Scale to 230px
        ratio = min(230 / def_sprite.width, 230 / def_sprite.height)
        ds = def_sprite.resize((int(def_sprite.width * ratio), int(def_sprite.height * ratio)), Image.LANCZOS)
        r, g, b, a = ds.split()
        a = a.point(lambda x: int(x * 0.65))
        ds = Image.merge("RGBA", (r, g, b, a))
        tint = Image.new("RGBA", ds.size, (255, 30, 30, 25))
        ds = Image.alpha_composite(ds, tint)
        dx = DEF_CX - ds.width // 2
        dy = DEF_CY - ds.height // 2 - 5
        card.paste(ds, (dx, dy), ds)

    # Text overlays
    draw = ImageDraw.Draw(card)
    font_big = _get_font(36, "bold")
    font_name = _get_font(22, "bold")
    font_dmg = _get_font(54, "bold")

    # Skill banner
    banner = Image.new("RGBA", (W, 56), (*colors[0], 140))
    card.paste(banner, (0, 0), banner)
    draw = ImageDraw.Draw(card)

    skill_text = f"{atk_name}의 {skill_name}!"
    bbox = draw.textbbox((0, 0), skill_text, font=font_big)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2 + 2, 10), skill_text, fill=(0, 0, 0, 100), font=font_big)
    draw.text(((W - tw) // 2, 8), skill_text, fill=(255, 255, 255), font=font_big)

    # Names
    bbox = draw.textbbox((0, 0), atk_name, font=font_name)
    nw = bbox[2] - bbox[0]
    draw.text((ATK_CX - nw // 2 + 16, 416), atk_name, fill=(0, 0, 0, 120), font=font_name)
    draw.text((ATK_CX - nw // 2 + 15, 415), atk_name, fill=(255, 255, 255), font=font_name)

    bbox = draw.textbbox((0, 0), def_name, font=font_name)
    nw = bbox[2] - bbox[0]
    draw.text((DEF_CX - nw // 2 + 1, 426), def_name, fill=(0, 0, 0, 120), font=font_name)
    draw.text((DEF_CX - nw // 2, 425), def_name, fill=(255, 150, 150), font=font_name)

    # Damage
    dmg_text = f"-{damage}"
    bbox = draw.textbbox((0, 0), dmg_text, font=font_dmg)
    dw = bbox[2] - bbox[0]
    draw.text((DEF_CX - dw // 2 + 3, 461), dmg_text, fill=(0, 0, 0, 150), font=font_dmg)
    draw.text((DEF_CX - dw // 2, 458), dmg_text, fill=(255, 65, 65), font=font_dmg)

    buf = io.BytesIO()
    card.convert("RGB").save(buf, format="JPEG", quality=90)
    buf.seek(0)
    buf.name = "battle.jpg"
    return buf


# ============================================================
# Skill GIF (960x540 고해상도 스킬 애니메이션)
# ============================================================

def _skill_base_frame(
    atk_id: int, atk_name: str, def_id: int, def_name: str,
    skill_type: str, atk_shiny: bool, def_shiny: bool,
    fx_progress: float = 0.0,
    impact: bool = False,
    shake: tuple[int, int] = (0, 0),
    def_alpha: float = 1.0,
    flash_color: tuple | None = None,
    flash_alpha: int = 0,
    screen_flash: float = 0.0,
) -> Image.Image:
    """스킬 GIF 단일 프레임 (960x540)."""
    from PIL import ImageFilter as IF

    W, H = CARD_WIDTH, CARD_HEIGHT
    colors = _BATTLE_TYPE_COLORS.get(skill_type, _BATTLE_TYPE_COLORS["normal"])
    deep, mid, bright = colors

    card = _make_gradient(W, H, (10, 12, 22), (4, 4, 10)).convert("RGBA")

    ATK_CX, ATK_CY = 220, 255
    DEF_CX, DEF_CY = 720, 265

    # 공격자 글로우 (빌드업에 따라 강도 변화)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    glow_intensity = min(1.0, fx_progress * 2)
    for i in range(30, 0, -1):
        a = int(25 * (i / 30) * glow_intensity)
        r = int(180 * (i / 30))
        gd.ellipse([ATK_CX - r, ATK_CY - r, ATK_CX + r, ATK_CY + r], fill=(*deep, a))

    # 피격자 임팩트 글로우
    if impact:
        for i in range(30, 0, -1):
            a = int(20 * (i / 30))
            r = int(160 * (i / 30))
            gd.ellipse([DEF_CX - r, DEF_CY - r, DEF_CX + r, DEF_CY + r], fill=(180, 40, 40, a))
    card = Image.alpha_composite(card, glow)

    # 스킬 FX (progress에 따라 부분 렌더)
    if fx_progress > 0:
        fx = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        fx_draw = ImageDraw.Draw(fx)
        # FX 경로를 progress만큼만 그리기
        sx, sy = ATK_CX + 80, ATK_CY
        ex, ey = DEF_CX - 40, DEF_CY
        # progress에 따라 도착점 이동
        px = sx + (ex - sx) * min(1.0, fx_progress)
        py = sy + (ey - sy) * min(1.0, fx_progress)
        fx_func = _BATTLE_FX.get(skill_type, _battle_fx_generic)
        fx_func(fx_draw, sx, sy, int(px), int(py), colors)
        if impact:
            _battle_impact(fx_draw, DEF_CX, DEF_CY, colors)
        fx_glow = fx.filter(IF.GaussianBlur(radius=4))
        card = Image.alpha_composite(card, fx_glow)
        card = Image.alpha_composite(card, fx)

    # 이로치 이펙트
    if atk_shiny:
        card = _draw_shiny_effect(card, ATK_CX, ATK_CY, 180)
    if def_shiny:
        card = _draw_shiny_effect(card, DEF_CX, DEF_CY, 150)

    # 공격자 스프라이트
    atk_sprite = _load_sprite(atk_id)
    if atk_sprite:
        ax = ATK_CX - atk_sprite.width // 2 + 15
        ay = ATK_CY - atk_sprite.height // 2 - 15
        card.paste(atk_sprite, (ax, ay), atk_sprite)

    # 피격자 스프라이트 (흔들림 + 알파)
    def_sprite = _load_sprite(def_id)
    if def_sprite:
        ratio = min(230 / def_sprite.width, 230 / def_sprite.height)
        ds = def_sprite.resize(
            (int(def_sprite.width * ratio), int(def_sprite.height * ratio)),
            Image.LANCZOS,
        )
        if def_alpha < 1.0:
            r2, g2, b2, a2 = ds.split()
            a2 = a2.point(lambda x: int(x * def_alpha))
            ds = Image.merge("RGBA", (r2, g2, b2, a2))
            if impact:
                tint = Image.new("RGBA", ds.size, (255, 30, 30, int(40 * (1 - def_alpha))))
                ds = Image.alpha_composite(ds, tint)
        dx = DEF_CX - ds.width // 2 + shake[0]
        dy = DEF_CY - ds.height // 2 - 5 + shake[1]
        card.paste(ds, (dx, dy), ds)

    # 전체 플래시 (스킬 발동 순간)
    if flash_color and flash_alpha > 0:
        overlay = Image.new("RGBA", (W, H), (*flash_color, flash_alpha))
        card = Image.alpha_composite(card, overlay)

    # 화면 플래시 (흰색, 임팩트 순간)
    if screen_flash > 0:
        overlay = Image.new("RGBA", (W, H), (255, 255, 255, int(180 * screen_flash)))
        card = Image.alpha_composite(card, overlay)

    return card


def make_skill_gif(
    atk_id: int, atk_name: str, def_id: int, def_name: str,
    skill_name: str, skill_type: str, damage: int,
    atk_shiny: bool = False, def_shiny: bool = False,
    is_crit: bool = False,
) -> tuple[io.BytesIO, int]:
    """스킬 발동 GIF (960x540). Returns (gif_buffer, total_duration_ms)."""
    colors = _BATTLE_TYPE_COLORS.get(skill_type, _BATTLE_TYPE_COLORS["normal"])
    deep, mid, bright = colors

    frames = []
    durs = []

    def add_frame(dur, **kw):
        f = _skill_base_frame(atk_id, atk_name, def_id, def_name,
                              skill_type, atk_shiny, def_shiny, **kw)
        # 텍스트 오버레이
        draw = ImageDraw.Draw(f)
        return f, dur

    # Phase 1: 스킬명 플래시 (타입 컬러 배너)
    f1 = _skill_base_frame(atk_id, atk_name, def_id, def_name,
                           skill_type, atk_shiny, def_shiny,
                           flash_color=deep, flash_alpha=60)
    draw = ImageDraw.Draw(f1)
    font_big = _get_font(36, "bold")
    font_name = _get_font(22, "bold")
    banner = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 0))
    bd = ImageDraw.Draw(banner)
    bd.rectangle([0, 0, CARD_WIDTH, 56], fill=(*deep, 160))
    draw = ImageDraw.Draw(f1)
    skill_text = f"{atk_name}의 {skill_name}!"
    bbox = draw.textbbox((0, 0), skill_text, font=font_big)
    tw = bbox[2] - bbox[0]
    draw.text(((CARD_WIDTH - tw) // 2 + 2, 10), skill_text, fill=(0, 0, 0, 100), font=font_big)
    draw.text(((CARD_WIDTH - tw) // 2, 8), skill_text, fill=(255, 255, 255), font=font_big)
    frames.append(f1.convert("RGB"))
    durs.append(600)

    # Phase 2: 글로우 빌드업 (2 프레임)
    for prog in [0.15, 0.3]:
        f, _ = add_frame(200, fx_progress=prog,
                         flash_color=deep, flash_alpha=int(30 * prog))
        frames.append(f.convert("RGB"))
        durs.append(200)

    # Phase 3: FX 발사 (3 프레임, progress 진행)
    for prog in [0.5, 0.75, 1.0]:
        f, _ = add_frame(180, fx_progress=prog)
        frames.append(f.convert("RGB"))
        durs.append(180)

    # Phase 4: 임팩트 — 화면 플래시
    f, _ = add_frame(120, fx_progress=1.0, impact=True, screen_flash=1.0)
    frames.append(f.convert("RGB"))
    durs.append(120)

    # Phase 5: 타격 흔들림 (4 프레임)
    shakes = [(18, -8), (-14, 10), (10, -6), (-6, 4)]
    for sx, sy in shakes:
        f, _ = add_frame(100, fx_progress=1.0, impact=True,
                         shake=(sx, sy), def_alpha=0.75,
                         screen_flash=0.3 if sx > 10 else 0)
        frames.append(f.convert("RGB"))
        durs.append(100)

    # Phase 6: 데미지 표시 (피격자 약간 투명 + 데미지 숫자)
    f = _skill_base_frame(atk_id, atk_name, def_id, def_name,
                          skill_type, atk_shiny, def_shiny,
                          fx_progress=0, def_alpha=0.65)
    draw = ImageDraw.Draw(f)
    font_dmg = _get_font(54, "bold")
    font_crit = _get_font(28, "bold")
    DEF_CX = 720
    dmg_text = f"-{damage}"
    bbox = draw.textbbox((0, 0), dmg_text, font=font_dmg)
    dw = bbox[2] - bbox[0]
    draw.text((DEF_CX - dw // 2 + 3, 401), dmg_text, fill=(0, 0, 0, 150), font=font_dmg)
    draw.text((DEF_CX - dw // 2, 398), dmg_text, fill=(255, 65, 65), font=font_dmg)
    if is_crit:
        crit_text = "크리티컬!"
        bbox2 = draw.textbbox((0, 0), crit_text, font=font_crit)
        cw = bbox2[2] - bbox2[0]
        draw.text((DEF_CX - cw // 2 + 2, 462), crit_text, fill=(0, 0, 0, 120), font=font_crit)
        draw.text((DEF_CX - cw // 2, 460), crit_text, fill=(255, 220, 50), font=font_crit)
    frames.append(f.convert("RGB"))
    durs.append(1000)

    # Phase 7: 정리 (원래 상태로 페이드백)
    f = _skill_base_frame(atk_id, atk_name, def_id, def_name,
                          skill_type, atk_shiny, def_shiny,
                          fx_progress=0, def_alpha=0.8)
    frames.append(f.convert("RGB"))
    durs.append(400)

    return _assemble_gif(frames, durs), sum(durs)


# ============================================================
# Dungeon Battle Card (게임보이 스타일)
# ============================================================

def _draw_hp_bar(
    draw: ImageDraw.Draw, x: int, y: int, w: int, h: int,
    current: int, maximum: int, show_numbers: bool = False,
    font: ImageFont.FreeTypeFont | None = None,
):
    """HP 바 그리기 (초록→노랑→빨강 그라데이션)."""
    ratio = max(0, min(1, current / maximum)) if maximum > 0 else 0

    # 배경 (어두운 회색)
    draw.rounded_rectangle([x, y, x + w, y + h], radius=3, fill=(40, 40, 40))

    # HP 바 색상
    if ratio > 0.5:
        color = (76, 209, 55)   # 초록
    elif ratio > 0.2:
        color = (251, 197, 49)  # 노랑
    else:
        color = (232, 65, 24)   # 빨강

    # HP 바 채움
    fill_w = max(0, int((w - 4) * ratio))
    if fill_w > 0:
        draw.rounded_rectangle([x + 2, y + 2, x + 2 + fill_w, y + h - 2], radius=2, fill=color)

    # HP 라벨
    hp_label = "HP"
    label_font = font or _get_font(max(10, h - 4), "bold")
    draw.text((x - 30, y - 1), hp_label, fill=(255, 203, 5), font=label_font)

    # 수치 표시
    if show_numbers and font:
        num_text = f"{max(0, current)} / {maximum}"
        bbox = draw.textbbox((0, 0), num_text, font=font)
        nw = bbox[2] - bbox[0]
        draw.text((x + w - nw, y + h + 4), num_text, fill=(255, 255, 255), font=font)


def generate_dungeon_battle_card(
    player_id: int, player_name: str, player_rarity: str,
    player_hp: int, player_max_hp: int,
    player_shiny: bool,
    enemy_id: int, enemy_name: str, enemy_rarity: str,
    enemy_hp_pct: float,
    floor: int, floor_type: str,
    type_display: str,
    damage_dealt: int, damage_taken: int,
    won: bool,
    skill_text: str = "",
) -> io.BytesIO:
    """게임보이 스타일 던전 배틀 카드 생성.

    Args:
        player_*: 플레이어 포켓몬 정보
        enemy_*: 적 포켓몬 정보
        enemy_hp_pct: 적 남은 HP 비율 (0~1, 패배 시 0)
        floor: 층수
        floor_type: "" / "★ 관장전" / "⚡ 엘리트"
        type_display: 상성 표시 텍스트
        won: 승패
        skill_text: 배틀 로그 텍스트
    """
    W, H = 960, 540
    # 배경: 어두운 배틀 필드
    card = _make_gradient(W, H, (18, 22, 35), (8, 10, 18)).convert("RGBA")
    draw = ImageDraw.Draw(card)

    # 폰트
    f_title = _get_font(20, "bold")
    f_name = _get_font(22, "bold")
    f_hp_num = _get_font(16, "regular")
    f_hp_label = _get_font(14, "bold")
    f_log = _get_font(18, "regular")
    f_floor = _get_font(28, "bold")
    f_result = _get_font(40, "bold")

    # ── 상단 바: 층수 + 타입 ──
    bar = Image.new("RGBA", (W, 48), (0, 0, 0, 120))
    card.paste(bar, (0, 0), bar)
    draw = ImageDraw.Draw(card)

    floor_label = f"📍 {floor}층"
    if floor_type:
        floor_label += f" {floor_type}"
    draw.text((20, 10), floor_label, fill=(255, 255, 255), font=f_floor)

    if type_display:
        bbox = draw.textbbox((0, 0), type_display, font=f_name)
        tw = bbox[2] - bbox[0]
        type_color = (76, 209, 55) if "유리" in type_display else ((232, 65, 24) if "불리" in type_display else (180, 180, 180))
        draw.text((W - tw - 20, 14), type_display, fill=type_color, font=f_name)

    # ── 게임보이 스타일 교차 배치 ──
    # 적 스프라이트: 오른쪽 상단 / 적 이름+HP: 왼쪽 상단
    # 내 스프라이트: 왼쪽 하단 / 내 이름+HP: 오른쪽 하단

    ENEMY_CX, ENEMY_CY = 700, 170      # 적 스프라이트 위치 (우상)
    PLAYER_CX, PLAYER_CY = 240, 310    # 내 스프라이트 위치 (좌하)

    # ── 적 정보 패널 (좌상) ──
    # 패널 배경
    panel_e = Image.new("RGBA", (420, 70), (0, 0, 0, 100))
    card.paste(panel_e, (20, 60), panel_e)
    draw = ImageDraw.Draw(card)

    rarity_label = _RARITY_LABEL_KO.get(enemy_rarity, "")
    enemy_label = f"{enemy_name}  [{rarity_label}]"
    draw.text((35, 65), enemy_label, fill=(255, 255, 255), font=f_name)
    _draw_hp_bar(draw, 65, 95, 340, 14, int(enemy_hp_pct * 100), 100, font=f_hp_label)

    # ── 적 스프라이트 (우상) ──
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    enemy_accent = RARITY_ACCENT.get(enemy_rarity, (150, 150, 150))
    for i in range(20, 0, -1):
        a = int(15 * (i / 20))
        r = int(130 * (i / 20))
        gd.ellipse([ENEMY_CX - r, ENEMY_CY - r, ENEMY_CX + r, ENEMY_CY + r], fill=(*enemy_accent, a))
    card = Image.alpha_composite(card, glow)
    draw = ImageDraw.Draw(card)

    enemy_sprite = _load_sprite(enemy_id)
    if enemy_sprite:
        ratio = min(220 / enemy_sprite.width, 220 / enemy_sprite.height)
        es = enemy_sprite.resize((int(enemy_sprite.width * ratio), int(enemy_sprite.height * ratio)), Image.LANCZOS)
        if won:
            r, g, b, a = es.split()
            a = a.point(lambda x: int(x * 0.4))
            es = Image.merge("RGBA", (r, g, b, a))
            tint = Image.new("RGBA", es.size, (255, 30, 30, 30))
            es = Image.alpha_composite(es, tint)
        ex = ENEMY_CX - es.width // 2
        ey = ENEMY_CY - es.height // 2
        card.paste(es, (ex, ey), es)

    # ── 내 스프라이트 (좌하) ──
    glow2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd2 = ImageDraw.Draw(glow2)
    player_accent = RARITY_ACCENT.get(player_rarity, (150, 150, 150))
    for i in range(25, 0, -1):
        a = int(20 * (i / 25))
        r = int(160 * (i / 25))
        gd2.ellipse([PLAYER_CX - r, PLAYER_CY - r, PLAYER_CX + r, PLAYER_CY + r], fill=(*player_accent, a))
    card = Image.alpha_composite(card, glow2)
    draw = ImageDraw.Draw(card)

    if player_shiny:
        card = _draw_shiny_effect(card, PLAYER_CX, PLAYER_CY, 150)
        draw = ImageDraw.Draw(card)

    player_sprite = _load_sprite(player_id)
    if player_sprite:
        ratio = min(280 / player_sprite.width, 280 / player_sprite.height)
        ps = player_sprite.resize((int(player_sprite.width * ratio), int(player_sprite.height * ratio)), Image.LANCZOS)
        px = PLAYER_CX - ps.width // 2
        py = PLAYER_CY - ps.height // 2
        card.paste(ps, (px, py), ps)

    # ── 내 정보 패널 (우하) ──
    panel_p = Image.new("RGBA", (420, 85), (0, 0, 0, 100))
    card.paste(panel_p, (520, 290), panel_p)
    draw = ImageDraw.Draw(card)

    shiny_mark = "✨" if player_shiny else ""
    player_label = f"{shiny_mark}{player_name}"
    draw.text((535, 295), player_label, fill=(255, 255, 255), font=f_name)
    _draw_hp_bar(draw, 565, 325, 340, 14, player_hp, player_max_hp, show_numbers=True, font=f_hp_num)

    # ── 배틀 로그 박스 (하단) ──
    log_box = Image.new("RGBA", (W, 110), (0, 0, 0, 160))
    card.paste(log_box, (0, H - 110), log_box)
    draw = ImageDraw.Draw(card)

    # 테두리
    draw.rounded_rectangle([10, H - 108, W - 10, H - 4], radius=8, outline=(100, 120, 150), width=2)

    # 배틀 로그 텍스트
    log_y = H - 100
    if skill_text:
        for i, line in enumerate(skill_text.split("\n")[:3]):
            draw.text((28, log_y + i * 28), line, fill=(255, 255, 255), font=f_log)
    else:
        result_text = "✅ 승리!" if won else "💀 패배..."
        draw.text((28, log_y), result_text, fill=(76, 209, 55) if won else (232, 65, 24), font=f_result)
        draw.text((28, log_y + 45), f"⚔️ {damage_dealt} 데미지  |  💥 {damage_taken} 피해", fill=(200, 200, 200), font=f_log)

    buf = io.BytesIO()
    card.convert("RGB").save(buf, format="JPEG", quality=90)
    buf.seek(0)
    buf.name = "dungeon_battle.jpg"
    return buf


# ============================================================
# Battle GIF Engine (던전 + 토너먼트 공용)
# ============================================================

_GIF_W, _GIF_H = 480, 270
_gif_sprite_cache: dict[tuple, Image.Image | None] = {}


def _gif_sprite(pokemon_id: int, max_size: int) -> Image.Image | None:
    key = (pokemon_id, max_size)
    if key not in _gif_sprite_cache:
        s = _load_sprite(pokemon_id)
        if s:
            r = min(max_size / s.width, max_size / s.height)
            s = s.resize((int(s.width * r), int(s.height * r)), Image.LANCZOS)
        _gif_sprite_cache[key] = s
    return _gif_sprite_cache[key]


def _gif_hp_bar(draw, x, y, w, h, ratio, font):
    draw.rounded_rectangle([x, y, x + w, y + h], radius=3, fill=(40, 40, 40))
    if ratio > 0.5:
        color = (76, 209, 55)
    elif ratio > 0.2:
        color = (251, 197, 49)
    else:
        color = (232, 65, 24)
    fw = max(0, int((w - 4) * ratio))
    if fw > 0:
        draw.rounded_rectangle([x + 2, y + 2, x + 2 + fw, y + h - 2], radius=2, fill=color)
    draw.text((x - 30, y - 1), "HP", fill=(255, 203, 5), font=font)


def _gif_battle_frame(
    p_id, p_name, p_rarity, p_hp_ratio, p_shiny,
    e_id, e_name, e_rarity, e_hp_ratio,
    floor_text, type_display, log_text,
    shake_x=0, shake_y=0,
    flash_color=None, flash_alpha=0,
    impact_side=None,
    dim_target=None,
):
    """배틀 GIF 단일 프레임 생성."""
    W, H = _GIF_W, _GIF_H
    f_nm = _get_font(13, "bold")
    f_hp = _get_font(9, "bold")
    f_fl = _get_font(16, "bold")
    f_log = _get_font(11, "regular")
    f_logb = _get_font(12, "bold")

    card = _make_gradient(W, H, (18, 22, 35), (8, 10, 18)).convert("RGBA")
    draw = ImageDraw.Draw(card)

    # 상단 바
    bar = Image.new("RGBA", (W, 28), (0, 0, 0, 120))
    card.paste(bar, (0, 0), bar)
    draw = ImageDraw.Draw(card)
    draw.text((10, 5), floor_text, fill=(255, 255, 255), font=f_fl)
    if type_display:
        tc = (76, 209, 55) if "유리" in type_display else ((232, 65, 24) if "불리" in type_display else (180, 180, 180))
        bbox = draw.textbbox((0, 0), type_display, font=f_nm)
        draw.text((W - (bbox[2] - bbox[0]) - 10, 8), type_display, fill=tc, font=f_nm)

    # 적 정보 (좌상)
    panel = Image.new("RGBA", (210, 38), (0, 0, 0, 100))
    card.paste(panel, (10, 32), panel)
    draw = ImageDraw.Draw(card)
    rl = _RARITY_LABEL_KO.get(e_rarity, "")
    draw.text((18, 34), f"{e_name} [{rl}]", fill=(255, 255, 255), font=f_nm)
    _gif_hp_bar(draw, 48, 52, 160, 8, e_hp_ratio, f_hp)

    # 적 스프라이트 (우상)
    ECX, ECY = 360, 100
    sx = shake_x if impact_side == "enemy" else 0
    sy = shake_y if impact_side == "enemy" else 0
    es = _gif_sprite(e_id, 110)
    if es:
        s = es.copy()
        if dim_target == "enemy":
            r2, g2, b2, a2 = s.split()
            a2 = a2.point(lambda x: int(x * 0.3))
            s = Image.merge("RGBA", (r2, g2, b2, a2))
        card.paste(s, (ECX - s.width // 2 + sx, ECY - s.height // 2 + sy), s)

    # 내 스프라이트 (좌하)
    PCX, PCY = 120, 160
    sx2 = shake_x if impact_side == "player" else 0
    sy2 = shake_y if impact_side == "player" else 0
    ps = _gif_sprite(p_id, 140)
    if ps:
        card.paste(ps, (PCX - ps.width // 2 + sx2, PCY - ps.height // 2 + sy2), ps)

    # 내 정보 (우하)
    panel2 = Image.new("RGBA", (210, 48), (0, 0, 0, 100))
    card.paste(panel2, (260, 150), panel2)
    draw = ImageDraw.Draw(card)
    sm = "✨" if p_shiny else ""
    draw.text((268, 152), f"{sm}{p_name}", fill=(255, 255, 255), font=f_nm)
    _gif_hp_bar(draw, 298, 170, 160, 8, p_hp_ratio, f_hp)

    # 임팩트 이펙트
    if impact_side:
        fx = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        fd = ImageDraw.Draw(fx)
        cx = ECX if impact_side == "enemy" else PCX
        cy = ECY if impact_side == "enemy" else PCY
        for i in range(15, 0, -1):
            a = int(40 * (i / 15))
            r = int(60 * (i / 15))
            fd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 200, a))
        card = Image.alpha_composite(card, fx)

    # 전체 플래시
    if flash_color and flash_alpha > 0:
        overlay = Image.new("RGBA", (W, H), (*flash_color, flash_alpha))
        card = Image.alpha_composite(card, overlay)

    # 로그 박스
    logbox = Image.new("RGBA", (W, 50), (0, 0, 0, 180))
    card.paste(logbox, (0, H - 50), logbox)
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle([5, H - 48, W - 5, H - 2], radius=4, outline=(100, 120, 150), width=1)
    for i, line in enumerate(log_text.split("\n")[:2]):
        c = (255, 100, 100) if ("데미지" in line or "피해" in line) else (255, 255, 255)
        draw.text((14, H - 44 + i * 18), line, fill=c, font=f_logb if i == 0 else f_log)

    return card.convert("RGB")


def _gif_text_frame(text: str, sub_text: str = "", bg_color=(10, 12, 25)):
    """텍스트만 표시하는 프레임 (토너먼트 멘트용)."""
    W, H = _GIF_W, _GIF_H
    card = Image.new("RGB", (W, H), bg_color)
    draw = ImageDraw.Draw(card)

    f_big = _get_font(28, "bold")
    f_sub = _get_font(16, "regular")

    bbox = draw.textbbox((0, 0), text, font=f_big)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (W - tw) // 2
    ty = (H - th) // 2 - 15
    # 그림자
    draw.text((tx + 2, ty + 2), text, fill=(0, 0, 0), font=f_big)
    draw.text((tx, ty), text, fill=(255, 255, 255), font=f_big)

    if sub_text:
        bbox2 = draw.textbbox((0, 0), sub_text, font=f_sub)
        sw = bbox2[2] - bbox2[0]
        draw.text(((W - sw) // 2, ty + th + 20), sub_text, fill=(200, 200, 200), font=f_sub)

    return card


def _assemble_gif(frames: list[Image.Image], durations: list[int]) -> io.BytesIO:
    """프레임 리스트 → GIF BytesIO."""
    buf = io.BytesIO()
    frames[0].save(
        buf, format="GIF", save_all=True, append_images=frames[1:],
        duration=durations, loop=0,
    )
    buf.seek(0)
    buf.name = "battle.gif"
    return buf


# ── 던전 배틀 GIF ──

def generate_dungeon_battle_gif(
    player_id: int, player_name: str, player_rarity: str,
    player_hp_before: int, player_max_hp: int, player_shiny: bool,
    enemy_id: int, enemy_name: str, enemy_rarity: str,
    floor: int, floor_type: str, type_display: str,
    damage_dealt: int, damage_taken: int, won: bool,
    player_hp_after: int,
    crit: bool = False,
) -> io.BytesIO:
    """던전 1v1 배틀 GIF 생성."""
    frames = []
    durs = []
    fl_text = f"{floor}층"
    if floor_type:
        fl_text += f" {floor_type}"

    p_before = player_hp_before / player_max_hp if player_max_hp else 1
    p_after = player_hp_after / player_max_hp if player_max_hp else 0

    def add(p_hp, e_hp, log, dur=1500, **kw):
        frames.append(_gif_battle_frame(
            player_id, player_name, player_rarity, p_hp, player_shiny,
            enemy_id, enemy_name, enemy_rarity, e_hp,
            fl_text, type_display, log, **kw,
        ))
        durs.append(dur)

    # 1. 등장
    add(p_before, 1.0, f"⚔️ {enemy_name} 등장!", dur=1800)

    # 2. 플레이어 공격 — 플래시
    flash_c = (50, 120, 255)
    skill_text = f"{player_name}의 공격!"
    if crit:
        skill_text += " 급소!"
        flash_c = (255, 255, 100)
    add(p_before, 1.0, skill_text, flash_color=flash_c, flash_alpha=45, dur=800)

    # 3. 임팩트 흔들림
    for sx, sy in [(10, -5), (-8, 6)]:
        add(p_before, 1.0, skill_text, impact_side="enemy", shake_x=sx, shake_y=sy, dur=250)
    if crit:
        add(p_before, 1.0, "급소에 명중했다!", impact_side="enemy", shake_x=6, shake_y=-4, dur=200)

    # 4. 적 HP 감소
    e_after = 0.0 if won else max(0.05, 1.0 - (damage_dealt / max(1, damage_dealt + 200)))
    add(p_before, e_after, f"→ {enemy_name}에게 {damage_dealt} 데미지!", dur=1500)

    if damage_taken > 0:
        # 5. 적 반격
        add(p_before, e_after, f"{enemy_name}의 반격!",
            flash_color=(255, 80, 20), flash_alpha=40, dur=800)
        for sx, sy in [(-7, 5), (5, -3)]:
            add(p_before, e_after, f"{enemy_name}의 반격!",
                impact_side="player", shake_x=sx, shake_y=sy, dur=250)

        # 6. 내 HP 감소
        add(p_after, e_after, f"→ {player_name}에게 {damage_taken} 피해", dur=1500)

    # 7. 결과
    if won:
        add(p_after, 0.0, f"✅ 승리! HP {int(p_after*100)}%", dim_target="enemy", dur=2500)
    else:
        add(0, e_after, f"💀 {player_name} 쓰러졌다...", dur=2500)

    return _assemble_gif(frames, durs)


# ── 토너먼트 단일 라운드 GIF ──

def make_round_gif(
    p1_name: str, p2_name: str,
    rd: dict, round_num: int,
    p1_score: int, p2_score: int,
) -> tuple[io.BytesIO, int]:
    """토너먼트 결승 단일 라운드(1v1) GIF.

    Returns (gif_buffer, total_duration_ms).

    rd: {
        "p1_id": int, "p1_poke": str, "p1_rarity": str, "p1_shiny": bool,
        "p2_id": int, "p2_poke": str, "p2_rarity": str, "p2_shiny": bool,
        "winner": "p1" | "p2",
        "damage_dealt": int, "damage_taken": int,
        "crit": bool,
    }
    """
    frames = []
    durs = []

    won = rd["winner"] == "p1"
    fl_text = f"R{round_num} [{p1_score}-{p2_score}]"

    p_id = rd["p1_id"]
    p_name_poke = rd["p1_poke"]
    p_rar = rd["p1_rarity"]
    p_shiny = rd.get("p1_shiny", False)
    e_id = rd["p2_id"]
    e_name_poke = rd["p2_poke"]
    e_rar = rd["p2_rarity"]

    dmg_dealt = rd.get("damage_dealt", 300)
    dmg_taken = rd.get("damage_taken", 200)
    crit = rd.get("crit", False)

    def add(p_hp, e_hp, log, dur=1500, **kw):
        frames.append(_gif_battle_frame(
            p_id, p_name_poke, p_rar, p_hp, p_shiny,
            e_id, e_name_poke, e_rar, e_hp,
            fl_text, "", log, **kw,
        ))
        durs.append(dur)

    # 라운드 타이틀
    frames.append(_gif_text_frame(
        f"Round {round_num}",
        f"{p_name_poke}  VS  {e_name_poke}",
    ))
    durs.append(1500)

    # 등장
    add(1.0, 1.0, f"{p_name_poke} vs {e_name_poke}!", dur=1500)

    # p1 공격
    skill = f"{p_name_poke}의 공격!"
    fc = (255, 255, 100) if crit else (50, 120, 255)
    if crit:
        skill += " 급소!"
    add(1.0, 1.0, skill, flash_color=fc, flash_alpha=45, dur=700)
    for sx, sy in [(10, -5), (-8, 6)]:
        add(1.0, 1.0, skill, impact_side="enemy", shake_x=sx, shake_y=sy, dur=200)

    e_after = 0.0 if won else 0.35
    add(1.0, e_after, f"→ {dmg_dealt} 데미지!", dur=1200)

    # p2 반격
    add(1.0, e_after, f"{e_name_poke}의 반격!",
        flash_color=(255, 80, 20), flash_alpha=40, dur=700)
    for sx, sy in [(-7, 5), (5, -3)]:
        add(1.0, e_after, f"{e_name_poke}의 반격!",
            impact_side="player", shake_x=sx, shake_y=sy, dur=200)

    p_after = 0.0 if not won else 0.55
    add(p_after, e_after, f"→ {dmg_taken} 피해!", dur=1200)

    # KO 결과
    if won:
        add(p_after, 0.0, f"{e_name_poke} 쓰러졌다!", dim_target="enemy", dur=1800)
    else:
        add(0.0, e_after, f"{p_name_poke} 쓰러졌다!", dur=1800)

    return _assemble_gif(frames, durs), sum(durs)


# ── 토너먼트 결승 GIF (전체 하이라이트) ──

def generate_tournament_battle_gif(
    p1_name: str, p2_name: str,
    rounds: list[dict],
) -> io.BytesIO:
    """토너먼트 6v6 결승 GIF.

    rounds: [{
        "p1_id": int, "p1_poke": str, "p1_rarity": str, "p1_shiny": bool,
        "p2_id": int, "p2_poke": str, "p2_rarity": str, "p2_shiny": bool,
        "winner": "p1" | "p2",
        "damage_dealt": int, "damage_taken": int,
        "crit": bool,
        "comment_before": str,  # 라운드 전 멘트 (선택)
        "comment_after": str,   # 라운드 후 멘트 (선택)
    }]
    """
    frames = []
    durs = []
    p1_score = 0
    p2_score = 0

    # 인트로
    frames.append(_gif_text_frame(f"🏆 결승전", f"{p1_name}  VS  {p2_name}"))
    durs.append(2500)

    for i, rd in enumerate(rounds):
        # 라운드 전 멘트
        comment = rd.get("comment_before", "")
        if comment:
            speaker = p1_name if rd["winner"] == "p1" else p2_name
            frames.append(_gif_text_frame(f'"{comment}"', f"— {speaker}"))
            durs.append(2000)

        # 라운드 타이틀
        frames.append(_gif_text_frame(
            f"Round {i+1}",
            f"{rd['p1_poke']}  VS  {rd['p2_poke']}",
        ))
        durs.append(1500)

        won = rd["winner"] == "p1"
        fl_text = f"R{i+1} [{p1_score}-{p2_score}]"

        # p1이 좌하(플레이어 위치), p2가 우상(적 위치)
        p_id = rd["p1_id"]
        p_name_poke = rd["p1_poke"]
        p_rar = rd["p1_rarity"]
        p_shiny = rd.get("p1_shiny", False)
        e_id = rd["p2_id"]
        e_name_poke = rd["p2_poke"]
        e_rar = rd["p2_rarity"]

        dmg_dealt = rd.get("damage_dealt", 300)
        dmg_taken = rd.get("damage_taken", 200)
        crit = rd.get("crit", False)

        def add(p_hp, e_hp, log, dur=1500, **kw):
            frames.append(_gif_battle_frame(
                p_id, p_name_poke, p_rar, p_hp, p_shiny,
                e_id, e_name_poke, e_rar, e_hp,
                fl_text, "", log, **kw,
            ))
            durs.append(dur)

        # 등장
        add(1.0, 1.0, f"{p_name_poke} vs {e_name_poke}!", dur=1500)

        # p1 공격
        skill = f"{p_name_poke}의 공격!"
        fc = (255, 255, 100) if crit else (50, 120, 255)
        if crit:
            skill += " 급소!"
        add(1.0, 1.0, skill, flash_color=fc, flash_alpha=45, dur=700)
        for sx, sy in [(10, -5), (-8, 6)]:
            add(1.0, 1.0, skill, impact_side="enemy", shake_x=sx, shake_y=sy, dur=200)

        e_after = 0.0 if won else 0.35
        add(1.0, e_after, f"→ {dmg_dealt} 데미지!", dur=1200)

        # p2 반격
        add(1.0, e_after, f"{e_name_poke}의 반격!",
            flash_color=(255, 80, 20), flash_alpha=40, dur=700)
        for sx, sy in [(-7, 5), (5, -3)]:
            add(1.0, e_after, f"{e_name_poke}의 반격!",
                impact_side="player", shake_x=sx, shake_y=sy, dur=200)

        p_after = 0.0 if not won else 0.55
        add(p_after, e_after, f"→ {dmg_taken} 피해!", dur=1200)

        # 결과
        if won:
            add(p_after, 0.0, f"{e_name_poke} 쓰러졌다!", dim_target="enemy", dur=1800)
            p1_score += 1
        else:
            add(0.0, e_after, f"{p_name_poke} 쓰러졌다!", dur=1800)
            p2_score += 1

        # 라운드 후 멘트
        comment_a = rd.get("comment_after", "")
        if comment_a:
            speaker = p1_name if rd["winner"] == "p1" else p2_name
            frames.append(_gif_text_frame(f'"{comment_a}"', f"— {speaker}"))
            durs.append(2000)

        # 스코어
        frames.append(_gif_text_frame(f"{p1_name} {p1_score} - {p2_score} {p2_name}"))
        durs.append(1500)

    # 최종 결과
    winner = p1_name if p1_score > p2_score else p2_name
    frames.append(_gif_text_frame(f"🏆 우승: {winner}!", f"{p1_score} - {p2_score}", bg_color=(30, 15, 5)))
    durs.append(4000)

    return _assemble_gif(frames, durs)
