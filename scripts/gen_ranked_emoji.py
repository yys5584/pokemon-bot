"""Generate pokeball-style ranked title emoji previews (128x128)."""
import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUT = "assets/ranked_emoji_preview"

# Color palettes for each rank tier
RANKS = {
    "ranked_first": {
        "name": "첫 랭크전",
        "top": "#EE4035",       # classic pokeball red
        "bottom": "#F5F5F5",
        "band": "#2C2C2C",
        "button_ring": "#2C2C2C",
        "button_fill": "#FFFFFF",
        "glow": None,
        "star": None,
    },
    "ranked_silver": {
        "name": "실버",
        "top": "#A8B8C8",       # silver
        "bottom": "#E8EDF2",
        "band": "#6B7B8B",
        "button_ring": "#6B7B8B",
        "button_fill": "#D0D8E0",
        "glow": "#C0CFE0",
        "star": None,
    },
    "ranked_gold": {
        "name": "골드",
        "top": "#FFD700",       # gold
        "bottom": "#FFF8DC",
        "band": "#B8860B",
        "button_ring": "#B8860B",
        "button_fill": "#FFE44D",
        "glow": "#FFE680",
        "star": None,
    },
    "ranked_platinum": {
        "name": "플래티넘",
        "top": "#7BD4E8",       # platinum cyan
        "bottom": "#E8F4F8",
        "band": "#3A8DA0",
        "button_ring": "#3A8DA0",
        "button_fill": "#B0E8F8",
        "glow": "#A0E0F0",
        "star": "⭐",
    },
    "ranked_diamond": {
        "name": "다이아",
        "top": "#5B8DEF",       # diamond blue
        "bottom": "#D8E8FF",
        "band": "#2855A8",
        "button_ring": "#2855A8",
        "button_fill": "#88B8FF",
        "glow": "#80B0FF",
        "star": "💎",
    },
    "ranked_master": {
        "name": "마스터",
        "top": "#8B45C8",       # master purple (like master ball)
        "bottom": "#E8D8F8",
        "band": "#5C2D91",
        "button_ring": "#5C2D91",
        "button_fill": "#C490FF",
        "glow": "#B070FF",
        "star": "👑",
        "m_mark": True,
    },
    "ranked_challenger": {
        "name": "챌린저",
        "top": "#1A1A2E",       # dark navy/black
        "bottom": "#2A2A4E",
        "band": "#FFD700",      # gold band!
        "button_ring": "#FFD700",
        "button_fill": "#FF4444",
        "glow": "#FF6644",
        "star": "🔥",
        "flames": True,
    },
    "ranked_champion": {
        "name": "시즌 챔피언",
        "top": "#FF2244",       # champion red
        "bottom": "#FFD700",    # gold bottom
        "band": "#FFD700",
        "button_ring": "#FFD700",
        "button_fill": "#FFFFFF",
        "glow": "#FFEE44",
        "star": "🏆",
        "crown": True,
    },
}


def draw_pokeball(rank_id: str, cfg: dict):
    """Draw a single pokeball emoji."""
    size = 128
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = 64, 64
    r = 54  # ball radius

    # Outer glow
    if cfg.get("glow"):
        glow_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_img)
        glow_draw.ellipse([cx-r-6, cy-r-6, cx+r+6, cy+r+6], fill=cfg["glow"] + "60")
        glow_img = glow_img.filter(ImageFilter.GaussianBlur(4))
        img = Image.alpha_composite(img, glow_img)
        draw = ImageDraw.Draw(img)

    # --- Main ball circle ---
    # Bottom half (white/light)
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=cfg["bottom"], outline=cfg["band"], width=3)

    # Top half (colored) — draw as a chord
    draw.pieslice([cx-r, cy-r, cx+r, cy+r], start=180, end=360, fill=cfg["top"], outline=cfg["band"], width=3)

    # Re-draw outline to clean up
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=cfg["band"], width=3)

    # Center band (horizontal line)
    band_h = 5
    draw.rectangle([cx-r, cy-band_h, cx+r, cy+band_h], fill=cfg["band"])

    # Center button
    btn_r = 14
    draw.ellipse([cx-btn_r, cy-btn_r, cx+btn_r, cy+btn_r], fill=cfg["button_fill"], outline=cfg["button_ring"], width=3)
    # Inner button
    inner_r = 7
    draw.ellipse([cx-inner_r, cy-inner_r, cx+inner_r, cy+inner_r], fill=cfg["button_ring"])

    # M mark for master ball
    if cfg.get("m_mark"):
        try:
            font = ImageFont.truetype("arial.ttf", 16)
        except:
            font = ImageFont.load_default()
        draw.text((cx-5, cy-btn_r-22), "M", fill="#FFD700", font=font)

    # Crown on top for champion
    if cfg.get("crown"):
        # Simple crown shape
        crown_y = cy - r - 8
        pts = [
            (cx-16, crown_y+12), (cx-16, crown_y+4),
            (cx-10, crown_y+8), (cx-4, crown_y),
            (cx, crown_y+6), (cx+4, crown_y),
            (cx+10, crown_y+8), (cx+16, crown_y+4),
            (cx+16, crown_y+12),
        ]
        draw.polygon(pts, fill="#FFD700", outline="#B8860B")

    # Flames effect for challenger
    if cfg.get("flames"):
        for angle_offset in [-30, 0, 30]:
            fx = cx + int(22 * math.sin(math.radians(angle_offset)))
            fy = cy - r - 6
            flame_pts = [
                (fx, fy - 14), (fx - 6, fy), (fx - 2, fy - 4),
                (fx + 2, fy - 4), (fx + 6, fy),
            ]
            draw.polygon(flame_pts, fill="#FF4400")
            draw.polygon([(fx, fy-10), (fx-3, fy-2), (fx+3, fy-2)], fill="#FFAA00")

    # Shine highlight (top-left)
    shine_x, shine_y = cx - 20, cy - 24
    draw.ellipse([shine_x-8, shine_y-6, shine_x+8, shine_y+6], fill="#FFFFFF80")
    draw.ellipse([shine_x-4, shine_y-3, shine_x+4, shine_y+3], fill="#FFFFFFB0")

    # Save
    path = f"{OUT}/{rank_id}.png"
    img.save(path, "PNG")
    print(f"  ✅ {rank_id}: {cfg['name']} → {path}")
    return path


def make_preview_sheet():
    """Create a combined preview sheet showing all ranks side by side."""
    n = len(RANKS)
    cols = 4
    rows_count = math.ceil(n / cols)
    cell = 160
    pad = 16
    sheet_w = cols * cell + pad * 2
    sheet_h = rows_count * (cell + 30) + pad * 2

    sheet = Image.new("RGBA", (sheet_w, sheet_h), (30, 30, 46, 255))
    draw = ImageDraw.Draw(sheet)

    try:
        font = ImageFont.truetype("arial.ttf", 13)
        font_title = ImageFont.truetype("arial.ttf", 18)
    except:
        font = ImageFont.load_default()
        font_title = font

    draw.text((pad, pad-2), "🔴 포켓볼형 랭크 칭호 이모지 예시안", fill="#FFFFFF", font=font_title)

    for i, (rank_id, cfg) in enumerate(RANKS.items()):
        col = i % cols
        row = i // cols
        x = pad + col * cell + (cell - 128) // 2
        y = pad + 30 + row * (cell + 30)

        # Load individual emoji
        emoji_img = Image.open(f"{OUT}/{rank_id}.png").convert("RGBA")
        sheet.paste(emoji_img, (x, y), emoji_img)

        # Label
        label = cfg["name"]
        bbox = draw.textbbox((0, 0), label, font=font)
        tw = bbox[2] - bbox[0]
        lx = x + (128 - tw) // 2
        draw.text((lx, y + 132), label, fill="#CCCCCC", font=font)

    path = f"{OUT}/_preview_sheet.png"
    sheet.save(path, "PNG")
    print(f"\n📋 Preview sheet → {path}")
    return path


if __name__ == "__main__":
    print("Generating pokeball-style ranked emoji...\n")
    for rank_id, cfg in RANKS.items():
        draw_pokeball(rank_id, cfg)
    make_preview_sheet()
    print("\nDone!")
