"""Tournament presentation card generator for Telegram photo messages."""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = Path(__file__).resolve().parent.parent
EFFECTS_DIR = ROOT_DIR / "assets" / "card_effects"

WIDTH = 1440
HEIGHT = 810

_FONT_REGULAR = [
    "C:/Windows/Fonts/malgun.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]
_FONT_BOLD = [
    "C:/Windows/Fonts/malgunbd.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "C:/Windows/Fonts/malgun.ttf",
]
_FONT_IMPACT = [
    "C:/Windows/Fonts/impact.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/malgunbd.ttf",
]


@dataclass(frozen=True)
class MatchCard:
    seed: str
    player_a: str
    score_a: int
    player_b: str
    score_b: int
    live: bool = False


def _font(size: int, style: str = "bold") -> ImageFont.FreeTypeFont:
    paths = {
        "regular": _FONT_REGULAR,
        "bold": _FONT_BOLD,
        "impact": _FONT_IMPACT,
    }.get(style, _FONT_BOLD)
    for path in paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _vertical_gradient(width: int, height: int,
                       top: tuple[int, int, int],
                       bottom: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGBA", (width, height))
    pixels: list[tuple[int, int, int, int]] = []
    for y in range(height):
        t = y / max(1, height - 1)
        row = (
            int(top[0] + (bottom[0] - top[0]) * t),
            int(top[1] + (bottom[1] - top[1]) * t),
            int(top[2] + (bottom[2] - top[2]) * t),
            255,
        )
        pixels.extend([row] * width)
    img.putdata(pixels)
    return img


def _cover_texture(path: Path, width: int, height: int) -> Image.Image | None:
    if not path.exists():
        return None
    with Image.open(path) as src:
        img = src.convert("RGBA")
    scale = max(width / img.width, height / img.height)
    resized = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
    left = max(0, (resized.width - width) // 2)
    top = max(0, (resized.height - height) // 2)
    return resized.crop((left, top, left + width, top + height))


def _draw_glow(layer: Image.Image, center: tuple[int, int], radius: int,
               color: tuple[int, int, int], max_alpha: int) -> None:
    draw = ImageDraw.Draw(layer)
    cx, cy = center
    for i in range(radius, 0, -8):
        alpha = int(max_alpha * (i / radius) ** 2)
        draw.ellipse((cx - i, cy - i, cx + i, cy + i), fill=(*color, alpha))


def _draw_title_block(draw: ImageDraw.Draw, title: str, subtitle: str) -> None:
    font_meta = _font(13, "bold")
    font_title = _font(40, "bold")
    font_sub = _font(18, "regular")
    font_chip = _font(14, "bold")

    draw.text((58, 44), "DAILY ARCADE TOURNAMENT", fill=(220, 223, 236), font=font_meta)
    draw.rounded_rectangle((1164, 34, 1378, 74), radius=18, fill=(26, 30, 44, 224), outline=(255, 255, 255, 28))
    draw.text((1196, 45), "KST 22:00 메인 이벤트", fill=(244, 246, 252), font=font_chip)

    draw.rounded_rectangle((58, 100, 244, 138), radius=19, fill=(255, 127, 74, 22), outline=(255, 168, 122, 52))
    draw.text((82, 109), "오늘 밤 22시 브래킷 공개", fill=(255, 214, 190), font=font_chip)

    title_box = draw.textbbox((0, 0), title, font=font_title)
    title_x = (WIDTH - (title_box[2] - title_box[0])) // 2
    draw.text((title_x, 112), title, fill=(255, 200, 98), font=font_title)

    sub_box = draw.textbbox((0, 0), subtitle, font=font_sub)
    sub_x = (WIDTH - (sub_box[2] - sub_box[0])) // 2
    draw.text((sub_x, 170), subtitle, fill=(200, 208, 227), font=font_sub)

    pills = ("SINGLE ELIM", "8강 진행", "LIVE 하이라이트")
    total_w = len(pills) * 156 + (len(pills) - 1) * 12
    start_x = (WIDTH - total_w) // 2
    for index, text in enumerate(pills):
        x1 = start_x + index * 168
        x2 = x1 + 156
        draw.rounded_rectangle((x1, 214, x2, 252), radius=18, fill=(26, 30, 44, 220), outline=(255, 255, 255, 20))
        label_box = draw.textbbox((0, 0), text, font=font_chip)
        lx = x1 + (156 - (label_box[2] - label_box[0])) // 2
        draw.text((lx, 225), text, fill=(240, 243, 249), font=font_chip)


def _draw_match_box(draw: ImageDraw.Draw, box: tuple[int, int, int, int], match: MatchCard) -> None:
    x1, y1, x2, y2 = box
    fill = (28, 32, 46, 228)
    outline = (255, 255, 255, 24)
    if match.live:
        fill = (54, 36, 34, 238)
        outline = (255, 182, 118, 112)
    draw.rounded_rectangle(box, radius=22, fill=fill, outline=outline, width=2)

    if match.live:
        draw.rounded_rectangle((x2 - 84, y1 + 14, x2 - 18, y1 + 40), radius=12, fill=(255, 103, 76, 255))
        draw.text((x2 - 70, y1 + 19), "LIVE", fill=(255, 255, 255), font=_font(12, "bold"))

    draw.text((x1 + 16, y1 + 15), match.seed.upper(), fill=(134, 149, 191), font=_font(12, "bold"))

    name_font = _font(24, "bold")
    score_font = _font(28, "impact")
    divider = y1 + 72

    draw.text((x1 + 16, y1 + 42), match.player_a, fill=(247, 248, 251), font=name_font)
    draw.text((x2 - 38, y1 + 39), str(match.score_a), fill=(255, 208, 110), font=score_font)
    draw.line((x1 + 16, divider, x2 - 16, divider), fill=(255, 255, 255, 18), width=1)
    draw.text((x1 + 16, divider + 14), match.player_b, fill=(230, 234, 244), font=name_font)
    draw.text((x2 - 38, divider + 11), str(match.score_b), fill=(255, 208, 110), font=score_font)


def _draw_connector(draw: ImageDraw.Draw, start: tuple[int, int], end: tuple[int, int],
                    color: tuple[int, int, int, int]) -> None:
    sx, sy = start
    ex, ey = end
    mid = int((sx + ex) / 2)
    draw.line((sx, sy, mid, sy), fill=color, width=3)
    draw.line((mid, sy, mid, ey), fill=color, width=3)
    draw.line((mid, ey, ex, ey), fill=color, width=3)


def generate_tournament_bracket_card(
    title: str = "오늘의 토너먼트 브래킷",
    subtitle: str = "22:00 본선 시작 / 진행 중인 매치는 LIVE로 강조",
    left_quarter: list[MatchCard] | None = None,
    right_quarter: list[MatchCard] | None = None,
    left_semi: MatchCard | None = None,
    right_semi: MatchCard | None = None,
) -> io.BytesIO:
    if left_quarter is None:
        left_quarter = [
            MatchCard("Quarterfinal A", "루카", 2, "하린", 1),
            MatchCard("Quarterfinal B", "민성", 0, "이안", 2),
        ]
    if right_quarter is None:
        right_quarter = [
            MatchCard("Quarterfinal C", "도윤", 2, "지훈", 0),
            MatchCard("Quarterfinal D", "세아", 2, "태윤", 1),
        ]
    if left_semi is None:
        left_semi = MatchCard("Semifinal 1", "루카", 1, "이안", 1, live=True)
    if right_semi is None:
        right_semi = MatchCard("Semifinal 2", "도윤", 2, "세아", 0)

    base = _vertical_gradient(WIDTH, HEIGHT, (21, 24, 37), (15, 16, 23))
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    _draw_glow(overlay, (180, 130), 230, (255, 136, 82), 48)
    _draw_glow(overlay, (1270, 122), 200, (98, 141, 255), 42)
    _draw_glow(overlay, (720, 452), 165, (255, 185, 100), 34)
    base = Image.alpha_composite(base, overlay)

    grain = _cover_texture(EFFECTS_DIR / "grain.webp", WIDTH, HEIGHT)
    if grain is not None:
        grain.putalpha(24)
        base = Image.alpha_composite(base, grain)

    panel = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(panel)
    pdraw.rounded_rectangle((24, 24, WIDTH - 24, HEIGHT - 24), radius=30, fill=(255, 255, 255, 10), outline=(255, 255, 255, 18))
    base = Image.alpha_composite(base, panel)

    draw = ImageDraw.Draw(base)
    _draw_title_block(draw, title, subtitle)

    qx_left = 94
    sx_left = 344
    center_x = 720
    sx_right = 886
    qx_right = 1136
    top_y = 292
    gap_y = 170
    card_w = 214
    card_h = 122

    draw.text((qx_left, 260), "QUARTERFINAL", fill=(153, 164, 193), font=_font(13, "bold"))
    draw.text((sx_left, 260), "SEMIFINAL", fill=(153, 164, 193), font=_font(13, "bold"))
    draw.text((sx_right, 260), "SEMIFINAL", fill=(153, 164, 193), font=_font(13, "bold"))
    draw.text((qx_right, 260), "QUARTERFINAL", fill=(153, 164, 193), font=_font(13, "bold"))

    left_top_box = (qx_left, top_y, qx_left + card_w, top_y + card_h)
    left_bottom_box = (qx_left, top_y + gap_y, qx_left + card_w, top_y + gap_y + card_h)
    left_semi_box = (sx_left, top_y + 90, sx_left + card_w, top_y + 90 + card_h)
    right_semi_box = (sx_right, top_y + 90, sx_right + card_w, top_y + 90 + card_h)
    right_top_box = (qx_right, top_y, qx_right + card_w, top_y + card_h)
    right_bottom_box = (qx_right, top_y + gap_y, qx_right + card_w, top_y + gap_y + card_h)

    _draw_match_box(draw, left_top_box, left_quarter[0])
    _draw_match_box(draw, left_bottom_box, left_quarter[1])
    _draw_match_box(draw, left_semi_box, left_semi)
    _draw_match_box(draw, right_semi_box, right_semi)
    _draw_match_box(draw, right_top_box, right_quarter[0])
    _draw_match_box(draw, right_bottom_box, right_quarter[1])

    line_color = (255, 255, 255, 44)
    _draw_connector(draw, (left_top_box[2], (left_top_box[1] + left_top_box[3]) // 2), (left_semi_box[0], left_semi_box[1] + 38), line_color)
    _draw_connector(draw, (left_bottom_box[2], (left_bottom_box[1] + left_bottom_box[3]) // 2), (left_semi_box[0], left_semi_box[1] + 84), line_color)
    _draw_connector(draw, (right_semi_box[2], right_semi_box[1] + 38), (right_top_box[0], (right_top_box[1] + right_top_box[3]) // 2), line_color)
    _draw_connector(draw, (right_semi_box[2], right_semi_box[1] + 84), (right_bottom_box[0], (right_bottom_box[1] + right_bottom_box[3]) // 2), line_color)

    center_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    _draw_glow(center_layer, (center_x, 368), 104, (255, 178, 82), 76)
    base = Image.alpha_composite(base, center_layer)
    draw = ImageDraw.Draw(base)

    draw.ellipse((center_x - 92, 280, center_x + 92, 464), fill=(255, 255, 255, 10), outline=(255, 217, 126, 68), width=2)
    draw.text((center_x - 58, 338), "FINAL", fill=(255, 233, 180), font=_font(28, "impact"))
    draw.text((center_x - 117, 496), "Final Rush", fill=(245, 247, 251), font=_font(44, "impact"))
    draw.text(
        (center_x - 132, 552),
        "지금은 텍스트 대진표지만,\n브래킷 카드로 보내면 훨씬 읽기 쉽습니다.",
        fill=(190, 198, 218),
        font=_font(18, "regular"),
        spacing=7,
    )

    draw.rounded_rectangle((58, 716, WIDTH - 58, 764), radius=18, fill=(22, 26, 38, 228), outline=(255, 255, 255, 18))
    draw.text((78, 730), "추천 포인트", fill=(255, 204, 116), font=_font(14, "bold"))
    draw.text((190, 730), "유저가 자기 매치를 바로 찾고, LIVE 경기만 강조해서 관전 포인트를 만들 수 있습니다.", fill=(223, 228, 240), font=_font(15, "regular"))

    buf = io.BytesIO()
    base.convert("RGB").save(buf, format="PNG")
    buf.seek(0)
    buf.name = "tournament_bracket.png"
    return buf


if __name__ == "__main__":
    out = ROOT_DIR / "sample_tournament_bracket_card.png"
    out.write_bytes(generate_tournament_bracket_card().getvalue())
