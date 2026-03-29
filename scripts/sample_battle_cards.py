"""Generate sample battle card mockups v3 - premium effects."""
import io, math, random, os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ASSETS_DIR = Path(__file__).parent.parent / "assets" / "pokemon"


def get_font(size, bold=False):
    paths = (
        ["C:/Windows/Fonts/malgunbd.ttf", "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"]
        if bold
        else ["C:/Windows/Fonts/malgun.ttf", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"]
    )
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def load_sprite(pid, max_size=280):
    sp = ASSETS_DIR / f"{pid}.png"
    if not sp.exists():
        return None
    img = Image.open(sp).convert("RGBA")
    ratio = min(max_size / img.width, max_size / img.height)
    return img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)


def make_gradient(w, h, top, bot):
    img = Image.new("RGB", (w, h))
    pixels = []
    for y in range(h):
        r = y / h
        c = tuple(int(top[i] + (bot[i] - top[i]) * r) for i in range(3))
        pixels.extend([c] * w)
    img.putdata(pixels)
    return img


TYPE_COLORS = {
    "fire": ((255, 70, 20), (255, 140, 30), (255, 200, 60)),       # deep, mid, bright
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


# ── Shiny: White sparkles ──────────────────────────────────────

def _draw_shiny_sparkles(card, cx, cy, radius=190):
    """Shiny effect: radiant light rays + tons of white sparkles."""
    layer = Image.new("RGBA", card.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    random.seed(77)

    # 1) Light rays shooting outward from center
    for _ in range(16):
        angle = random.uniform(0, 2 * math.pi)
        length = random.randint(int(radius * 0.7), int(radius * 1.3))
        x1 = cx + int(20 * math.cos(angle))
        y1 = cy + int(20 * math.sin(angle))
        x2 = cx + int(length * math.cos(angle))
        y2 = cy + int(length * math.sin(angle))
        alpha = random.randint(30, 70)
        w = random.randint(3, 8)
        ld.line([(x1, y1), (x2, y2)], fill=(255, 255, 255, alpha), width=w)
        # Thinner bright core
        ld.line([(x1, y1), (x2, y2)], fill=(255, 255, 255, alpha + 30), width=max(1, w - 2))

    # 2) Central soft white glow
    for i in range(25, 0, -1):
        r = int(60 * (i / 25))
        alpha = int(15 * (i / 25))
        ld.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, alpha))

    # 3) Tons of sparkle stars (small)
    for _ in range(40):
        angle = random.uniform(0, 2 * math.pi)
        dist = random.randint(int(radius * 0.15), radius)
        px = cx + int(dist * math.cos(angle))
        py = cy + int(dist * math.sin(angle))
        size = random.randint(3, 8)
        alpha = random.randint(150, 255)
        _draw_star4(ld, px, py, size, (255, 255, 255, alpha))

    # 4) Medium sparkles
    for _ in range(15):
        angle = random.uniform(0, 2 * math.pi)
        dist = random.randint(int(radius * 0.1), int(radius * 0.85))
        px = cx + int(dist * math.cos(angle))
        py = cy + int(dist * math.sin(angle))
        size = random.randint(10, 18)
        alpha = random.randint(180, 255)
        _draw_star4(ld, px, py, size, (255, 255, 255, alpha))
        # Glow behind
        ld.ellipse([px - size, py - size, px + size, py + size],
                   fill=(255, 255, 255, alpha // 6))

    # 5) A few big dramatic sparkles
    for _ in range(4):
        angle = random.uniform(0, 2 * math.pi)
        dist = random.randint(int(radius * 0.2), int(radius * 0.5))
        px = cx + int(dist * math.cos(angle))
        py = cy + int(dist * math.sin(angle))
        size = random.randint(20, 28)
        _draw_star4(ld, px, py, size, (255, 255, 255, 220))
        ld.ellipse([px - size - 4, py - size - 4, px + size + 4, py + size + 4],
                   fill=(255, 255, 255, 25))

    # Blur the layer slightly for soft glow, then composite sharp on top
    glow_layer = layer.filter(ImageFilter.GaussianBlur(radius=3))
    result = Image.alpha_composite(card, glow_layer)
    result = Image.alpha_composite(result, layer)
    return result


def _draw_star4(draw, cx, cy, size, color):
    """Draw a 4-pointed star (sparkle)."""
    pts = [
        (cx, cy - size),       # top
        (cx + size // 4, cy - size // 4),
        (cx + size, cy),       # right
        (cx + size // 4, cy + size // 4),
        (cx, cy + size),       # bottom
        (cx - size // 4, cy + size // 4),
        (cx - size, cy),       # left
        (cx - size // 4, cy - size // 4),
    ]
    draw.polygon(pts, fill=color)


# ── Fire FX: Big fireball + flame trail ────────────────────────

def _draw_fire_fx(layer, sx, sy, ex, ey, colors):
    """Blazing fireball traveling from attacker to defender."""
    fd = ImageDraw.Draw(layer)
    random.seed(101)
    deep, mid, bright = colors

    # 1) Flame trail (wider, curvy)
    steps = 50
    for s in range(steps):
        t = s / steps
        x = sx + (ex - sx) * t
        y = sy + (ey - sy) * t + math.sin(t * math.pi * 3) * 18

        # Trail gets thinner as it goes
        base_r = int(22 * (1 - t * 0.5))

        # Outer glow (deep red)
        r_out = base_r + random.randint(5, 14)
        alpha_out = int(80 * (1 - t * 0.6))
        fd.ellipse([x - r_out, y - r_out, x + r_out, y + r_out],
                   fill=(*deep, alpha_out))

        # Mid flame
        r_mid = base_r + random.randint(0, 5)
        alpha_mid = int(130 * (1 - t * 0.4))
        fd.ellipse([x - r_mid, y - r_mid, x + r_mid, y + r_mid],
                   fill=(*mid, alpha_mid))

        # Core (bright yellow)
        r_core = max(2, base_r - 6)
        alpha_core = int(180 * (1 - t * 0.3))
        fd.ellipse([x - r_core, y - r_core, x + r_core, y + r_core],
                   fill=(*bright, alpha_core))

    # 2) BIG fireball near the midpoint/impact
    fb_x = sx + (ex - sx) * 0.65
    fb_y = sy + (ey - sy) * 0.65
    for i in range(40, 0, -1):
        ratio = i / 40
        r = int(50 * ratio)
        if ratio > 0.7:
            c = (*bright, int(220 * ratio))
        elif ratio > 0.4:
            c = (*mid, int(200 * ratio))
        else:
            c = (*deep, int(120 * ratio))
        fd.ellipse([fb_x - r, fb_y - r, fb_x + r, fb_y + r], fill=c)

    # 3) Ember particles
    for _ in range(50):
        t = random.uniform(0.05, 1.05)
        x = sx + (ex - sx) * t + random.randint(-40, 40)
        y = sy + (ey - sy) * t + random.randint(-50, 30) - random.randint(0, 20)
        r = random.randint(1, 5)
        c = random.choice([deep, mid, bright])
        alpha = random.randint(80, 220)
        fd.ellipse([x - r, y - r, x + r, y + r], fill=(*c, alpha))

    # 4) Rising heat wisps
    for _ in range(12):
        bx = random.randint(int(sx), int(ex))
        by = random.randint(int(min(sy, ey)) - 60, int(max(sy, ey)))
        for j in range(6):
            wy = by - j * 12
            wr = max(1, 4 - j)
            alpha = max(0, 100 - j * 20)
            fd.ellipse([bx - wr, wy - wr, bx + wr, wy + wr],
                       fill=(*mid, alpha))


def _draw_electric_fx(layer, sx, sy, ex, ey, colors):
    """Thick lightning bolts with electric glow."""
    fd = ImageDraw.Draw(layer)
    random.seed(202)
    deep, mid, bright = colors

    # Multiple lightning bolts (3 main + branches)
    for bolt in range(4):
        points = [(sx + random.randint(-10, 10), sy + random.randint(-15, 15))]
        segments = random.randint(10, 16)
        for s in range(1, segments + 1):
            t = s / segments
            x = sx + (ex - sx) * t
            y = sy + (ey - sy) * t + random.randint(-45, 45)
            points.append((x, y))

        # Thick outer glow
        w_outer = random.randint(8, 14)
        for i in range(len(points) - 1):
            fd.line([points[i], points[i + 1]],
                    fill=(*deep, 60), width=w_outer + 8)

        # Mid bolt
        w_mid = random.randint(4, 8)
        for i in range(len(points) - 1):
            fd.line([points[i], points[i + 1]],
                    fill=(*mid, 160), width=w_mid + 2)

        # Bright core
        w_core = random.randint(2, 4)
        for i in range(len(points) - 1):
            fd.line([points[i], points[i + 1]],
                    fill=(*bright, 220), width=w_core)

        # Branch bolts
        if bolt < 2:
            for _ in range(3):
                branch_idx = random.randint(2, len(points) - 2)
                bp = points[branch_idx]
                blen = random.randint(30, 70)
                b_angle = random.uniform(-math.pi / 3, math.pi / 3) + (math.pi / 6 if random.random() > 0.5 else -math.pi / 6)
                bex = bp[0] + blen * math.cos(b_angle)
                bey = bp[1] + blen * math.sin(b_angle)
                mid_x = (bp[0] + bex) / 2 + random.randint(-15, 15)
                mid_y = (bp[1] + bey) / 2 + random.randint(-15, 15)
                fd.line([bp, (mid_x, mid_y), (bex, bey)],
                        fill=(*mid, 120), width=2)

    # Electric sparks
    for _ in range(30):
        px = random.randint(int(sx - 20), int(ex + 40))
        py = random.randint(int(min(sy, ey) - 70), int(max(sy, ey) + 70))
        pr = random.randint(1, 4)
        fd.ellipse([px - pr, py - pr, px + pr, py + pr],
                   fill=(*bright, random.randint(120, 255)))

    # Glow orbs at start and end
    for gx, gy, gr in [(sx, sy, 35), (ex, ey, 30)]:
        for i in range(20, 0, -1):
            ratio = i / 20
            r = int(gr * ratio)
            fd.ellipse([gx - r, gy - r, gx + r, gy + r],
                       fill=(*mid, int(40 * ratio)))


def _draw_water_fx(layer, sx, sy, ex, ey, colors):
    """Powerful water cannon / hydro pump beam."""
    fd = ImageDraw.Draw(layer)
    random.seed(303)
    deep, mid, bright = colors

    # Main water beam (thick, wavy)
    steps = 60
    prev_pts = None
    for s in range(steps):
        t = s / steps
        x = sx + (ex - sx) * t
        y = sy + (ey - sy) * t + math.sin(t * math.pi * 5) * 22

        beam_w = int(16 + 8 * math.sin(t * math.pi * 3))

        # Outer spray
        r_out = beam_w + random.randint(4, 10)
        fd.ellipse([x - r_out, y - r_out, x + r_out, y + r_out],
                   fill=(*deep, 40))

        # Mid water
        fd.ellipse([x - beam_w, y - beam_w, x + beam_w, y + beam_w],
                   fill=(*mid, 100))

        # Core
        r_core = max(3, beam_w - 6)
        fd.ellipse([x - r_core, y - r_core, x + r_core, y + r_core],
                   fill=(*bright, 160))

    # Water droplets / splash
    for _ in range(45):
        t = random.uniform(0.1, 1.15)
        x = sx + (ex - sx) * t + random.randint(-50, 50)
        y = sy + (ey - sy) * t + random.randint(-60, 40)
        r = random.randint(2, 7)
        c = random.choice([mid, bright])
        alpha = random.randint(80, 200)
        fd.ellipse([x - r, y - r, x + r, y + r], fill=(*c, alpha))

    # Splash ring at impact
    for i in range(25, 0, -1):
        ratio = i / 25
        r = int(60 * ratio)
        fd.ellipse([ex - r, ey - r, ex + r, ey + r],
                   fill=(*mid, int(30 * ratio)))


def _draw_psychic_fx(layer, sx, sy, ex, ey, colors):
    """Psychic energy rings + mind wave."""
    fd = ImageDraw.Draw(layer)
    random.seed(404)
    deep, mid, bright = colors

    # Traveling energy rings
    num_rings = 8
    for i in range(num_rings):
        t = i / num_rings
        x = sx + (ex - sx) * t
        y = sy + (ey - sy) * t
        ring_r = int(20 + 15 * math.sin(t * math.pi))
        alpha = int(160 - 80 * t)

        # Ring (circle outline via multiple ellipses)
        for w in range(4, 0, -1):
            fd.ellipse([x - ring_r - w, y - ring_r - w, x + ring_r + w, y + ring_r + w],
                       outline=(*mid, alpha // (5 - w)), width=2)
        fd.ellipse([x - ring_r, y - ring_r, x + ring_r, y + ring_r],
                   outline=(*bright, alpha), width=2)

    # Wavy energy stream
    for s in range(40):
        t = s / 40
        x = sx + (ex - sx) * t
        y1 = sy + (ey - sy) * t + math.sin(t * math.pi * 4) * 25
        y2 = sy + (ey - sy) * t - math.sin(t * math.pi * 4) * 25
        r = int(5 + 3 * (1 - t))
        alpha = int(120 - 50 * t)
        fd.ellipse([x - r, y1 - r, x + r, y1 + r], fill=(*mid, alpha))
        fd.ellipse([x - r, y2 - r, x + r, y2 + r], fill=(*deep, alpha))

    # Particles
    for _ in range(25):
        t = random.uniform(0, 1)
        x = sx + (ex - sx) * t + random.randint(-40, 40)
        y = sy + (ey - sy) * t + random.randint(-40, 40)
        r = random.randint(2, 5)
        c = random.choice([deep, mid, bright])
        fd.ellipse([x - r, y - r, x + r, y + r], fill=(*c, random.randint(60, 180)))


def _draw_generic_fx(layer, sx, sy, ex, ey, colors):
    """Generic energy blast for other types."""
    fd = ImageDraw.Draw(layer)
    random.seed(505)
    deep, mid, bright = colors

    # Energy orb trail
    steps = 35
    for s in range(steps):
        t = s / steps
        x = sx + (ex - sx) * t
        y = sy + (ey - sy) * t + math.sin(t * math.pi * 2.5) * 15
        r = int(14 * (1 - t * 0.4))
        fd.ellipse([x - r - 4, y - r - 4, x + r + 4, y + r + 4],
                   fill=(*deep, int(60 * (1 - t * 0.5))))
        fd.ellipse([x - r, y - r, x + r, y + r],
                   fill=(*mid, int(140 * (1 - t * 0.3))))
        r_core = max(2, r - 5)
        fd.ellipse([x - r_core, y - r_core, x + r_core, y + r_core],
                   fill=(*bright, int(180 * (1 - t * 0.3))))

    # Particles
    for _ in range(35):
        t = random.uniform(0, 1.1)
        x = sx + (ex - sx) * t + random.randint(-35, 35)
        y = sy + (ey - sy) * t + random.randint(-35, 35)
        r = random.randint(2, 5)
        c = random.choice([deep, mid, bright])
        fd.ellipse([x - r, y - r, x + r, y + r], fill=(*c, random.randint(60, 180)))


FX_FUNCS = {
    "fire": _draw_fire_fx,
    "electric": _draw_electric_fx,
    "water": _draw_water_fx,
    "ice": _draw_water_fx,
    "psychic": _draw_psychic_fx,
    "dragon": _draw_generic_fx,
    "ghost": _draw_psychic_fx,
    "fairy": _draw_psychic_fx,
}


def _draw_impact(layer, cx, cy, colors):
    """Impact explosion at defender."""
    fd = ImageDraw.Draw(layer)
    random.seed(666)
    deep, mid, bright = colors

    # Shockwave rings
    for i in range(3):
        r = 40 + i * 25
        alpha = 80 - i * 25
        fd.ellipse([cx - r, cy - r, cx + r, cy + r],
                   outline=(*mid, max(10, alpha)), width=2)

    # Radial burst
    for _ in range(18):
        angle = random.uniform(0, 2 * math.pi)
        length = random.randint(30, 90)
        x1 = cx + int(12 * math.cos(angle))
        y1 = cy + int(12 * math.sin(angle))
        x2 = cx + int(length * math.cos(angle))
        y2 = cy + int(length * math.sin(angle))
        c = random.choice([mid, bright])
        fd.line([(x1, y1), (x2, y2)], fill=(*c, random.randint(80, 180)),
                width=random.randint(1, 3))

    # Impact particles
    for _ in range(12):
        angle = random.uniform(0, 2 * math.pi)
        dist = random.randint(15, 65)
        px = cx + int(dist * math.cos(angle))
        py = cy + int(dist * math.sin(angle))
        pr = random.randint(2, 5)
        fd.ellipse([px - pr, py - pr, px + pr, py + pr],
                   fill=(*bright, random.randint(100, 220)))


def generate_battle_card(
    atk_id, atk_name, def_id, def_name,
    skill_name, skill_type, damage,
    atk_shiny=False, def_shiny=False
):
    W, H = 960, 540
    colors = TYPE_COLORS.get(skill_type, TYPE_COLORS["normal"])

    card = make_gradient(W, H, (10, 12, 22), (4, 4, 10))
    card = card.convert("RGBA")

    ATK_CX, ATK_CY = 220, 255
    DEF_CX, DEF_CY = 720, 265

    # Attacker type glow
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for i in range(30, 0, -1):
        alpha = int(25 * (i / 30))
        r = int(180 * (i / 30))
        gd.ellipse([ATK_CX - r, ATK_CY - r, ATK_CX + r, ATK_CY + r],
                   fill=(*colors[0], alpha))

    # Defender subtle dark glow
    for i in range(22, 0, -1):
        alpha = int(10 * (i / 22))
        r = int(140 * (i / 22))
        gd.ellipse([DEF_CX - r, DEF_CY - r, DEF_CX + r, DEF_CY + r],
                   fill=(120, 30, 30, alpha))
    card = Image.alpha_composite(card, glow)

    # Skill effect layer (drawn on separate layer, then blurred slightly for glow)
    fx = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fx_func = FX_FUNCS.get(skill_type, _draw_generic_fx)
    fx_func(fx, ATK_CX + 80, ATK_CY, DEF_CX - 40, DEF_CY, colors)
    _draw_impact(fx, DEF_CX, DEF_CY, colors)

    # Soft glow version
    fx_glow = fx.filter(ImageFilter.GaussianBlur(radius=4))
    card = Image.alpha_composite(card, fx_glow)
    card = Image.alpha_composite(card, fx)

    # Shiny sparkles (behind sprites but above fx)
    if atk_shiny:
        card = _draw_shiny_sparkles(card, ATK_CX, ATK_CY, radius=180)
    if def_shiny:
        card = _draw_shiny_sparkles(card, DEF_CX, DEF_CY, radius=150)

    # Attacker sprite
    atk_sprite = load_sprite(atk_id, 270)
    if atk_sprite:
        ax = ATK_CX - atk_sprite.width // 2 + 15
        ay = ATK_CY - atk_sprite.height // 2 - 15
        card.paste(atk_sprite, (ax, ay), atk_sprite)

    # Defender sprite (faded + slight red, NO box)
    def_sprite = load_sprite(def_id, 230)
    if def_sprite:
        r, g, b, a = def_sprite.split()
        a = a.point(lambda x: int(x * 0.65))
        def_faded = Image.merge("RGBA", (r, g, b, a))
        tint = Image.new("RGBA", def_faded.size, (255, 30, 30, 25))
        def_tinted = Image.alpha_composite(def_faded, tint)
        dx = DEF_CX - def_tinted.width // 2
        dy = DEF_CY - def_tinted.height // 2 - 5
        card.paste(def_tinted, (dx, dy), def_tinted)

    # ── Text ──
    draw = ImageDraw.Draw(card)
    font_big = get_font(36, bold=True)
    font_name = get_font(22, bold=True)
    font_dmg = get_font(54, bold=True)

    # Skill banner
    banner = Image.new("RGBA", (W, 56), (*colors[0], 140))
    card.paste(banner, (0, 0), banner)
    draw = ImageDraw.Draw(card)

    skill_text = f"{atk_name}의 {skill_name}!"
    bbox = draw.textbbox((0, 0), skill_text, font=font_big)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2 + 2, 10), skill_text, fill=(0, 0, 0, 100), font=font_big)
    draw.text(((W - tw) // 2, 8), skill_text, fill=(255, 255, 255), font=font_big)

    # Attacker name (no shiny text mark — sparkles speak for themselves)
    atk_label = atk_name
    bbox = draw.textbbox((0, 0), atk_label, font=font_name)
    nw = bbox[2] - bbox[0]
    draw.text((ATK_CX - nw // 2 + 16, 415 + 1), atk_label, fill=(0, 0, 0, 120), font=font_name)
    draw.text((ATK_CX - nw // 2 + 15, 415), atk_label, fill=(255, 255, 255), font=font_name)

    # Defender name
    def_label = def_name
    bbox = draw.textbbox((0, 0), def_label, font=font_name)
    nw = bbox[2] - bbox[0]
    draw.text((DEF_CX - nw // 2 + 1, 425 + 1), def_label, fill=(0, 0, 0, 120), font=font_name)
    draw.text((DEF_CX - nw // 2, 425), def_label, fill=(255, 150, 150), font=font_name)

    # Damage
    dmg_text = f"-{damage}"
    bbox = draw.textbbox((0, 0), dmg_text, font=font_dmg)
    dw = bbox[2] - bbox[0]
    draw.text((DEF_CX - dw // 2 + 3, 458 + 3), dmg_text, fill=(0, 0, 0, 150), font=font_dmg)
    draw.text((DEF_CX - dw // 2, 458), dmg_text, fill=(255, 65, 65), font=font_dmg)

    buf = io.BytesIO()
    card.convert("RGB").save(buf, format="JPEG", quality=92)
    buf.seek(0)
    return buf


if __name__ == "__main__":
    out = Path(__file__).parent.parent

    samples = [
        (6, "리자몽", 9, "거북왕", "화염방사", "fire", 342, False, False, "fire"),
        (25, "피카츄", 6, "리자몽", "번개", "electric", 256, False, False, "electric"),
        (9, "거북왕", 6, "리자몽", "하이드로펌프", "water", 410, False, False, "water"),
        (150, "뮤츠", 249, "루기아", "사이코키네시스", "psychic", 380, False, False, "psychic"),
        (149, "망나뇽", 248, "마기라스", "역린", "dragon", 320, False, False, "dragon"),
        # Shiny tests
        (6, "리자몽", 150, "뮤츠", "화염방사", "fire", 342, True, False, "fire_shiny_atk"),
        (150, "뮤츠", 249, "루기아", "사이코키네시스", "psychic", 380, True, True, "psychic_both_shiny"),
    ]

    for atk_id, atk_n, def_id, def_n, skill, stype, dmg, a_sh, d_sh, label in samples:
        buf = generate_battle_card(atk_id, atk_n, def_id, def_n, skill, stype, dmg, a_sh, d_sh)
        fname = f"sample_{label}.jpg"
        with open(out / fname, "wb") as f:
            f.write(buf.read())
        print(fname)
