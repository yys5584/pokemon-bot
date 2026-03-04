"""Generate 18 Pokemon type icons matching the official type color scheme.

Creates 48x48 PNG icons with:
- Rounded rectangle background in the official type color
- White geometric symbol representing each type
- Transparent background outside the rounded rect
"""

import math
from pathlib import Path
from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).parent.parent / "dashboard" / "static" / "types"
SIZE = 48
RADIUS = 10  # corner radius
PAD = 8  # padding for the symbol inside

# Official Pokemon type colors (from Bulbapedia / official games)
TYPE_COLORS = {
    "normal":   "#A8A878",
    "fire":     "#F08030",
    "water":    "#6890F0",
    "grass":    "#78C850",
    "electric": "#F8D030",
    "ice":      "#98D8D8",
    "fighting": "#C03028",
    "poison":   "#A040A0",
    "ground":   "#E0C068",
    "flying":   "#A890F0",
    "psychic":  "#F85888",
    "bug":      "#A8B820",
    "rock":     "#B8A038",
    "ghost":    "#705898",
    "dragon":   "#7038F8",
    "dark":     "#705848",
    "steel":    "#B8B8D0",
    "fairy":    "#EE99AC",
}


def rounded_rect(draw, xy, radius, fill):
    """Draw a rounded rectangle."""
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.pieslice([x0, y0, x0 + 2*radius, y0 + 2*radius], 180, 270, fill=fill)
    draw.pieslice([x1 - 2*radius, y0, x1, y0 + 2*radius], 270, 360, fill=fill)
    draw.pieslice([x0, y1 - 2*radius, x0 + 2*radius, y1], 90, 180, fill=fill)
    draw.pieslice([x1 - 2*radius, y1 - 2*radius, x1, y1], 0, 90, fill=fill)


def draw_symbol(draw, type_name, cx, cy, r, color="white"):
    """Draw a geometric symbol for each type."""

    if type_name == "normal":
        # Circle with inner circle (donut)
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=color, width=3)
        draw.ellipse([cx-r//3, cy-r//3, cx+r//3, cy+r//3], fill=color)

    elif type_name == "fire":
        # Flame shape (teardrop pointing up)
        pts = []
        for i in range(24):
            angle = i * (2 * math.pi / 24) - math.pi/2
            if -math.pi/2 <= angle <= math.pi/2:
                rx, ry = r*0.8, r
            else:
                rx, ry = r*0.6, r*0.5
            pts.append((cx + rx * math.cos(angle), cy + ry * math.sin(angle) * 0.8))
        # Simplified flame: inverted teardrop
        flame = [
            (cx, cy - r),  # top
            (cx + r*0.7, cy + r*0.3),
            (cx + r*0.4, cy + r),
            (cx, cy + r*0.6),
            (cx - r*0.4, cy + r),
            (cx - r*0.7, cy + r*0.3),
        ]
        draw.polygon(flame, fill=color)

    elif type_name == "water":
        # Water drop
        drop = [
            (cx, cy - r),  # top point
            (cx + r*0.65, cy + r*0.1),
            (cx + r*0.5, cy + r*0.7),
            (cx, cy + r),
            (cx - r*0.5, cy + r*0.7),
            (cx - r*0.65, cy + r*0.1),
        ]
        draw.polygon(drop, fill=color)

    elif type_name == "grass":
        # Leaf shape
        leaf = [
            (cx - r, cy + r*0.3),
            (cx - r*0.3, cy - r),
            (cx + r*0.1, cy - r*0.8),
            (cx + r, cy - r*0.3),
            (cx + r*0.3, cy + r),
        ]
        draw.polygon(leaf, fill=color)
        # Leaf vein
        draw.line([(cx - r*0.5, cy + r*0.6), (cx + r*0.5, cy - r*0.5)], fill=TYPE_COLORS["grass"], width=2)

    elif type_name == "electric":
        # Lightning bolt
        bolt = [
            (cx - r*0.1, cy - r),
            (cx + r*0.6, cy - r),
            (cx + r*0.1, cy - r*0.1),
            (cx + r*0.7, cy - r*0.1),
            (cx - r*0.1, cy + r),
            (cx + r*0.1, cy + r*0.1),
            (cx - r*0.5, cy + r*0.1),
        ]
        draw.polygon(bolt, fill=color)

    elif type_name == "ice":
        # Snowflake (6-pointed star with lines)
        for i in range(6):
            angle = i * math.pi / 3 - math.pi/2
            x1 = cx + r * math.cos(angle)
            y1 = cy + r * math.sin(angle)
            draw.line([(cx, cy), (x1, y1)], fill=color, width=2)
            # Small branches
            bx = cx + r*0.6 * math.cos(angle)
            by = cy + r*0.6 * math.sin(angle)
            for d in [-0.4, 0.4]:
                ex = bx + r*0.3 * math.cos(angle + d)
                ey = by + r*0.3 * math.sin(angle + d)
                draw.line([(bx, by), (ex, ey)], fill=color, width=2)

    elif type_name == "fighting":
        # Fist / glove shape (simplified as a star-burst)
        draw.ellipse([cx-r*0.5, cy-r*0.5, cx+r*0.5, cy+r*0.5], fill=color)
        for i in range(8):
            angle = i * math.pi / 4
            x1 = cx + r*0.4 * math.cos(angle)
            y1 = cy + r*0.4 * math.sin(angle)
            x2 = cx + r * math.cos(angle)
            y2 = cy + r * math.sin(angle)
            draw.line([(x1, y1), (x2, y2)], fill=color, width=3)

    elif type_name == "poison":
        # Skull / poison symbol (two circles)
        draw.ellipse([cx-r*0.8, cy-r*0.5, cx+r*0.05, cy+r*0.5], fill=color)
        draw.ellipse([cx-r*0.05, cy-r*0.5, cx+r*0.8, cy+r*0.5], fill=color)
        # Drip
        drip = [(cx, cy+r*0.4), (cx-r*0.2, cy+r), (cx+r*0.2, cy+r)]
        draw.polygon(drip, fill=color)

    elif type_name == "ground":
        # Mountain / ground layers
        # Two triangle peaks
        peak1 = [(cx-r, cy+r*0.6), (cx-r*0.2, cy-r), (cx+r*0.3, cy+r*0.6)]
        peak2 = [(cx-r*0.1, cy+r*0.6), (cx+r*0.5, cy-r*0.5), (cx+r, cy+r*0.6)]
        draw.polygon(peak1, fill=color)
        draw.polygon(peak2, fill=color)
        # Base line
        draw.rectangle([cx-r, cy+r*0.5, cx+r, cy+r*0.8], fill=color)

    elif type_name == "flying":
        # Wing shape
        wing = [
            (cx - r, cy + r*0.3),
            (cx - r*0.5, cy - r*0.5),
            (cx, cy - r),
            (cx + r*0.5, cy - r*0.5),
            (cx + r, cy + r*0.3),
            (cx + r*0.5, cy),
            (cx, cy + r*0.2),
            (cx - r*0.5, cy),
        ]
        draw.polygon(wing, fill=color)

    elif type_name == "psychic":
        # Eye / psi symbol
        draw.ellipse([cx-r, cy-r*0.5, cx+r, cy+r*0.5], fill=color)
        draw.ellipse([cx-r*0.35, cy-r*0.35, cx+r*0.35, cy+r*0.35], fill=TYPE_COLORS["psychic"])
        draw.ellipse([cx-r*0.15, cy-r*0.15, cx+r*0.15, cy+r*0.15], fill=color)

    elif type_name == "bug":
        # Bug / hexagon
        hex_pts = []
        for i in range(6):
            angle = i * math.pi / 3 - math.pi/6
            hex_pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
        draw.polygon(hex_pts, fill=color)
        # Inner circle
        draw.ellipse([cx-r*0.4, cy-r*0.4, cx+r*0.4, cy+r*0.4], fill=TYPE_COLORS["bug"])

    elif type_name == "rock":
        # Rock / diamond shape
        diamond = [
            (cx, cy - r),
            (cx + r, cy),
            (cx + r*0.5, cy + r),
            (cx - r*0.5, cy + r),
            (cx - r, cy),
        ]
        draw.polygon(diamond, fill=color)
        # Crack line
        draw.line([(cx-r*0.3, cy-r*0.2), (cx+r*0.1, cy+r*0.3)], fill=TYPE_COLORS["rock"], width=2)

    elif type_name == "ghost":
        # Ghost shape
        ghost_pts = [
            (cx - r*0.7, cy + r),
            (cx - r*0.7, cy - r*0.3),
            (cx - r*0.5, cy - r*0.8),
            (cx, cy - r),
            (cx + r*0.5, cy - r*0.8),
            (cx + r*0.7, cy - r*0.3),
            (cx + r*0.7, cy + r),
            (cx + r*0.4, cy + r*0.5),
            (cx, cy + r),
            (cx - r*0.4, cy + r*0.5),
        ]
        draw.polygon(ghost_pts, fill=color)
        # Eyes
        draw.ellipse([cx-r*0.4, cy-r*0.3, cx-r*0.1, cy+r*0.1], fill=TYPE_COLORS["ghost"])
        draw.ellipse([cx+r*0.1, cy-r*0.3, cx+r*0.4, cy+r*0.1], fill=TYPE_COLORS["ghost"])

    elif type_name == "dragon":
        # Dragon fang / chevron
        fang = [
            (cx - r, cy - r*0.8),
            (cx, cy + r),
            (cx + r, cy - r*0.8),
            (cx + r*0.5, cy - r*0.8),
            (cx, cy + r*0.2),
            (cx - r*0.5, cy - r*0.8),
        ]
        draw.polygon(fang, fill=color)

    elif type_name == "dark":
        # Crescent moon
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=color)
        draw.ellipse([cx-r*0.3, cy-r*1.1, cx+r*1.1, cy+r*0.7], fill=TYPE_COLORS["dark"])

    elif type_name == "steel":
        # Gear shape
        outer_r = r
        inner_r = r * 0.55
        teeth = 8
        pts = []
        for i in range(teeth * 2):
            angle = i * math.pi / teeth - math.pi/2
            radius = outer_r if i % 2 == 0 else inner_r
            pts.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        draw.polygon(pts, fill=color)
        draw.ellipse([cx-r*0.3, cy-r*0.3, cx+r*0.3, cy+r*0.3], fill=TYPE_COLORS["steel"])

    elif type_name == "fairy":
        # Star shape (6-pointed)
        pts = []
        for i in range(12):
            angle = i * math.pi / 6 - math.pi/2
            radius = r if i % 2 == 0 else r * 0.45
            pts.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        draw.polygon(pts, fill=color)


def generate_icon(type_name, color_hex):
    """Generate a single type icon."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw rounded rectangle background
    rounded_rect(draw, (0, 0, SIZE-1, SIZE-1), RADIUS, color_hex)

    # Draw symbol
    cx, cy = SIZE // 2, SIZE // 2
    r = (SIZE - 2*PAD) // 2
    draw_symbol(draw, type_name, cx, cy, r)

    return img


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for type_name, color_hex in TYPE_COLORS.items():
        img = generate_icon(type_name, color_hex)
        out_path = OUT_DIR / f"{type_name}.png"
        img.save(out_path, "PNG")
        print(f"  Created: {out_path.name}")

    print(f"\nDone! {len(TYPE_COLORS)} icons saved to {OUT_DIR}")


if __name__ == "__main__":
    main()
