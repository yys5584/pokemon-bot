"""Generate camp map image — SNG 스타일 월드맵.

풀맵 베이스 이미지 1장 위에:
- 열린 존: 포켓몬 스프라이트 배치
- 잠긴 존: 안개/구름 오버레이 + 자물쇠
- UI: 캠프명, 레벨, 자원 표시
"""

import io
import math
from pathlib import Path
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

import config
from utils.card_generator import _get_font, ASSETS_DIR

# ── 상수 ──
MAP_WIDTH = 1024
MAP_HEIGHT = 576

# 베이스 맵 이미지 경로
CAMP_MAP_DIR = Path(__file__).parent.parent / "assets" / "camp"
BASE_MAP_PATH = CAMP_MAP_DIR / "map_base.png"

# ── 존 정의 (풀맵 기준 비율 좌표) ──
# 각 존: (x_center%, y_center%, width%, height%)
# 비율이므로 이미지 크기가 바뀌어도 대응 가능
# 포켓몬 배치 가능 영역 + 안개 덮을 영역
ZONE_REGIONS = {
    # 숲: 좌상단 꽃밭/나무 영역
    "forest": {
        "center": (0.20, 0.22),
        "area": (0.02, 0.02, 0.42, 0.45),  # (x1%, y1%, x2%, y2%) 안개 영역
        "slots": [  # 포켓몬 배치 좌표 (center% 기준)
            (0.14, 0.18), (0.22, 0.14), (0.30, 0.20),
            (0.12, 0.28), (0.20, 0.32), (0.28, 0.28),
            (0.16, 0.38), (0.24, 0.40), (0.32, 0.36),
            (0.10, 0.16), (0.26, 0.24), (0.18, 0.24),
        ],
    },
    # 호수: 우상단 물/부두 영역
    "lake": {
        "center": (0.72, 0.22),
        "area": (0.52, 0.02, 0.98, 0.48),
        "slots": [
            (0.62, 0.12), (0.70, 0.08), (0.80, 0.14),
            (0.58, 0.22), (0.68, 0.28), (0.78, 0.24),
            (0.64, 0.36), (0.74, 0.38), (0.84, 0.32),
            (0.60, 0.32), (0.72, 0.18), (0.86, 0.22),
        ],
    },
    # 화산/동굴: 중하단 바위 영역 (이 맵에서는 cave 느낌)
    "volcano": {
        "center": (0.55, 0.62),
        "area": (0.38, 0.48, 0.72, 0.82),
        "slots": [
            (0.46, 0.54), (0.54, 0.52), (0.62, 0.56),
            (0.44, 0.64), (0.52, 0.66), (0.60, 0.62),
            (0.48, 0.74), (0.56, 0.72), (0.64, 0.70),
            (0.50, 0.58), (0.58, 0.58), (0.42, 0.70),
        ],
    },
    # 도시: 좌하단 절벽/송전탑 영역
    "city": {
        "center": (0.18, 0.68),
        "area": (0.0, 0.48, 0.38, 0.98),
        "slots": [
            (0.10, 0.56), (0.20, 0.54), (0.30, 0.58),
            (0.08, 0.66), (0.18, 0.68), (0.28, 0.64),
            (0.12, 0.76), (0.22, 0.78), (0.32, 0.74),
            (0.16, 0.62), (0.26, 0.70), (0.06, 0.72),
        ],
    },
    # 동굴: 중하단 왼쪽 (바위 많은 곳)
    "cave": {
        "center": (0.55, 0.78),
        "area": (0.38, 0.68, 0.72, 0.98),
        "slots": [
            (0.44, 0.74), (0.52, 0.72), (0.60, 0.76),
            (0.42, 0.82), (0.50, 0.84), (0.58, 0.80),
            (0.46, 0.90), (0.54, 0.88), (0.62, 0.86),
            (0.48, 0.78), (0.56, 0.92), (0.40, 0.88),
        ],
    },
    # 신전: 우하단 보라빛 유적 영역
    "temple": {
        "center": (0.82, 0.65),
        "area": (0.72, 0.48, 0.98, 0.98),
        "slots": [
            (0.76, 0.54), (0.84, 0.52), (0.92, 0.56),
            (0.74, 0.64), (0.82, 0.66), (0.90, 0.62),
            (0.78, 0.74), (0.86, 0.76), (0.94, 0.72),
            (0.80, 0.58), (0.88, 0.68), (0.76, 0.70),
        ],
    },
}

# 필드 해금 순서
FIELD_ORDER = ["forest", "lake", "volcano", "city", "cave", "temple"]

# 필드 아이콘 색
FIELD_ICON_COLOR = {
    "forest": (80, 180, 60), "volcano": (230, 100, 40),
    "lake": (60, 150, 230), "city": (220, 200, 80),
    "cave": (160, 130, 80), "temple": (170, 100, 240),
}
FIELD_ICON_LABEL = {
    "forest": "풀", "volcano": "불", "lake": "물",
    "city": "전", "cave": "암", "temple": "령",
}


# ── 이미지 로딩 ──
@lru_cache(maxsize=1)
def _load_base_map() -> Image.Image:
    """베이스 맵 이미지를 MAP_WIDTH×MAP_HEIGHT로 로드."""
    if not BASE_MAP_PATH.exists():
        # 폴백: 단색 배경
        return Image.new("RGBA", (MAP_WIDTH, MAP_HEIGHT), (40, 55, 40, 255))
    img = Image.open(BASE_MAP_PATH).convert("RGBA")
    if img.size != (MAP_WIDTH, MAP_HEIGHT):
        img = img.resize((MAP_WIDTH, MAP_HEIGHT), Image.LANCZOS)
    return img


@lru_cache(maxsize=64)
def _load_mini_sprite(pokemon_id: int, size: int = 48) -> Image.Image | None:
    """포켓몬 스프라이트를 작은 사이즈로 로드."""
    sprite_path = ASSETS_DIR / f"{pokemon_id}.png"
    if not sprite_path.exists():
        return None
    sprite = Image.open(sprite_path).convert("RGBA")
    ratio = min(size / sprite.width, size / sprite.height)
    new_w = int(sprite.width * ratio)
    new_h = int(sprite.height * ratio)
    return sprite.resize((new_w, new_h), Image.LANCZOS)


# ── 그리기 헬퍼 ──
def _draw_fog(canvas: Image.Image, area: tuple, strength: float = 0.85):
    """존 영역에 안개/구름 오버레이."""
    w, h = canvas.size
    x1 = int(area[0] * w)
    y1 = int(area[1] * h)
    x2 = int(area[2] * w)
    y2 = int(area[3] * h)

    # 안개 레이어
    fog = Image.new("RGBA", (x2 - x1, y2 - y1), (0, 0, 0, 0))
    fog_draw = ImageDraw.Draw(fog)
    fog_w, fog_h = fog.size

    # 부드러운 안개 (여러 겹의 타원)
    import random
    rng = random.Random(hash(area))

    # 베이스 반투명 채우기
    base_alpha = int(200 * strength)
    fog_draw.rectangle([0, 0, fog_w, fog_h], fill=(180, 190, 200, base_alpha))

    # 구름 덩어리들
    for _ in range(15):
        cx = rng.randint(0, fog_w)
        cy = rng.randint(0, fog_h)
        rx = rng.randint(fog_w // 4, fog_w // 2)
        ry = rng.randint(fog_h // 4, fog_h // 2)
        alpha = int(rng.randint(60, 140) * strength)
        fog_draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry],
                         fill=(220, 225, 235, alpha))

    # 블러로 부드럽게
    fog = fog.filter(ImageFilter.GaussianBlur(radius=15))

    canvas.paste(Image.alpha_composite(
        Image.new("RGBA", fog.size, (0, 0, 0, 0)), fog
    ), (x1, y1), fog)


def _draw_lock_badge(draw: ImageDraw.Draw, cx: int, cy: int,
                     unlock_level: int, field_name: str):
    """잠긴 존 위에 자물쇠 뱃지."""
    # 배경 원
    badge_r = 22
    draw.ellipse(
        [cx - badge_r, cy - badge_r, cx + badge_r, cy + badge_r],
        fill=(40, 45, 55, 200),
    )
    draw.ellipse(
        [cx - badge_r, cy - badge_r, cx + badge_r, cy + badge_r],
        outline=(80, 85, 100, 180), width=2,
    )

    # 자물쇠 고리
    arc_w = 10
    draw.arc(
        [cx - arc_w, cy - 14, cx + arc_w, cy - 2],
        start=180, end=360, fill=(160, 165, 180), width=2,
    )
    # 자물쇠 몸체
    draw.rounded_rectangle(
        [cx - 9, cy - 3, cx + 9, cy + 9],
        radius=2, fill=(120, 125, 140),
    )
    # 열쇠구멍
    draw.ellipse([cx - 2, cy + 1, cx + 2, cy + 5], fill=(60, 65, 78))

    # 레벨 텍스트
    font = _get_font(11, "bold")
    txt = f"Lv.{unlock_level}"
    bbox = draw.textbbox((0, 0), txt, font=font)
    tw = bbox[2] - bbox[0]
    draw.text((cx - tw // 2, cy + badge_r + 4), txt,
              font=font, fill=(180, 185, 200))


def _draw_zone_label(draw: ImageDraw.Draw, cx: int, cy: int,
                     field_type: str, field_name: str, count: int):
    """열린 존 라벨 — 리본 배너 스타일 (쿠키런 월드맵 참고)."""
    title_font = _get_font(13, "bold")
    sub_font = _get_font(10)
    title = field_name
    subtitle = f"{count}마리"

    # 타이틀 크기
    tbbox = draw.textbbox((0, 0), title, font=title_font)
    tw = tbbox[2] - tbbox[0]
    th = tbbox[3] - tbbox[1]

    # 서브타이틀 크기
    sbbox = draw.textbbox((0, 0), subtitle, font=sub_font)
    sw = sbbox[2] - sbbox[0]

    pad_x = 16
    pad_y = 5
    banner_w = max(tw, sw) + pad_x * 2
    banner_h = th + 18 + pad_y * 2  # 타이틀 + 서브타이틀 + 간격

    bx = cx - banner_w // 2
    by = cy - banner_h // 2

    color = FIELD_ICON_COLOR.get(field_type, (150, 150, 150))

    # 리본 꼬리 (좌우 삼각형)
    tail_w = 10
    tail_h = banner_h // 2
    # 왼쪽 꼬리
    draw.polygon([
        (bx - tail_w, by + banner_h // 2),
        (bx, by),
        (bx, by + banner_h),
    ], fill=(*color, 180))
    # 오른쪽 꼬리
    draw.polygon([
        (bx + banner_w + tail_w, by + banner_h // 2),
        (bx + banner_w, by),
        (bx + banner_w, by + banner_h),
    ], fill=(*color, 180))

    # 메인 배너 배경
    draw.rounded_rectangle(
        [bx, by, bx + banner_w, by + banner_h],
        radius=4, fill=(245, 240, 230, 220),
    )
    # 상단 컬러 스트라이프
    draw.rectangle(
        [bx, by, bx + banner_w, by + 3],
        fill=(*color, 200),
    )

    # 타이틀 텍스트 (진한 갈색)
    tx = cx - tw // 2
    ty = by + pad_y
    draw.text((tx, ty), title, font=title_font, fill=(60, 45, 30, 240))

    # 서브타이틀 (필드 컬러)
    sx = cx - sw // 2
    sy = ty + th + 4
    draw.text((sx, sy), subtitle, font=sub_font, fill=(*color, 220))


def _draw_sprite_with_shadow(canvas: Image.Image, sprite: Image.Image,
                              x: int, y: int, is_shiny: bool = False):
    """포켓몬 스프라이트를 그림자와 함께 배치."""
    # 그림자
    shadow = Image.new("RGBA", sprite.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    sw, sh = sprite.size
    shadow_draw.ellipse(
        [sw // 4, sh - 6, sw * 3 // 4, sh + 2],
        fill=(0, 0, 0, 60),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(3))

    # 이로치 글로우
    if is_shiny:
        glow = Image.new("RGBA", (sw + 20, sh + 20), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        for step in range(10, 0, -1):
            alpha = int(25 * step / 10)
            r = 10 + step * 2
            glow_draw.ellipse(
                [sw // 2 + 10 - r, sh // 2 + 10 - r,
                 sw // 2 + 10 + r, sh // 2 + 10 + r],
                fill=(255, 255, 180, alpha),
            )
        glow = glow.filter(ImageFilter.GaussianBlur(4))
        canvas.paste(Image.alpha_composite(
            Image.new("RGBA", glow.size, (0, 0, 0, 0)), glow
        ), (x - 10, y - 10), glow)

    # 그림자 → 스프라이트
    canvas.paste(shadow, (x, y), shadow)
    canvas.paste(sprite, (x, y), sprite)


def _draw_ui_header(draw: ImageDraw.Draw, canvas_w: int,
                    camp_name: str, camp_level: int, level_name: str):
    """상단 UI: 캠프명 + 레벨."""
    # 반투명 바
    draw.rounded_rectangle(
        [12, 8, 320, 52], radius=10, fill=(0, 0, 0, 150),
    )

    # 캠프명
    title_font = _get_font(18, "bold")
    draw.text((20, 10), camp_name, font=title_font, fill=(255, 255, 255, 240))

    # 레벨
    sub_font = _get_font(12)
    level_txt = f"Lv.{camp_level} {level_name}"
    draw.text((20, 32), level_txt, font=sub_font, fill=(180, 220, 180, 220))


def _draw_ui_resources(draw: ImageDraw.Draw, canvas_w: int,
                       fragments: dict | None, crystals: dict | None):
    """우상단 자원 표시."""
    if not fragments and not crystals:
        return

    res_font = _get_font(11)
    rx = canvas_w - 16
    ry = 12

    lines = []
    if crystals:
        cry = crystals.get("crystal", 0)
        rain = crystals.get("rainbow", 0)
        lines.append(f"결정 {cry}  무지개 {rain}")
    if fragments:
        total = sum(fragments.values())
        lines.append(f"조각 {total}개")

    # 배경 바
    max_tw = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=res_font)
        max_tw = max(max_tw, bbox[2] - bbox[0])

    bar_h = len(lines) * 18 + 10
    draw.rounded_rectangle(
        [rx - max_tw - 20, ry - 4, rx + 4, ry + bar_h],
        radius=8, fill=(0, 0, 0, 140),
    )

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=res_font)
        tw = bbox[2] - bbox[0]
        draw.text((rx - tw, ry + i * 18 + 2), line,
                  font=res_font, fill=(200, 210, 220))


# ── 메인 생성 ──
def generate_camp_map(
    camp_name: str,
    camp_level: int,
    active_fields: list[dict],
    field_placements: dict[int, list[dict]],
    field_bonuses: dict[int, dict],
    fragments: dict[str, int] | None = None,
    crystals: dict | None = None,
) -> io.BytesIO:
    """캠프 맵 이미지 생성.

    Args:
        camp_name: 캠프 이름
        camp_level: 캠프 레벨
        active_fields: 열린 필드 [{id, field_type, ...}]
        field_placements: {field_id: [{pokemon_id, is_shiny, score, ...}]}
        field_bonuses: {field_id: {pokemon_id, stat_type, stat_value}}
        fragments: {field_type: amount}
        crystals: {crystal: int, rainbow: int}
    """
    level_info = config.get_camp_level_info(camp_level)
    level_name = level_info[5]

    # 1. 베이스 맵 복사
    base = _load_base_map()
    canvas = base.copy()
    w, h = canvas.size

    # 2. 열린 필드 판별
    active_types = {f["field_type"] for f in active_fields}
    active_by_type = {f["field_type"]: f for f in active_fields}

    # 3. 열린 영역만 크롭 (먼저 크롭 → 그 위에 스프라이트/라벨)
    canvas, crop_offset = _crop_to_active_zones(canvas, active_types)
    w, h = canvas.size

    # 4. 열린 존에 포켓몬 스프라이트 배치
    sprite_size = 48
    for ftype in FIELD_ORDER:
        if ftype not in active_types:
            continue
        field = active_by_type[ftype]
        zone = ZONE_REGIONS.get(ftype)
        if not zone:
            continue

        placements = field_placements.get(field["id"], [])
        slots = zone["slots"]

        for i, p in enumerate(placements[:len(slots)]):
            sx, sy = _zone_pct_to_cropped_px(
                slots[i], crop_offset, w, h,
            )
            sx -= sprite_size // 2
            sy -= sprite_size // 2

            sprite = _load_mini_sprite(p["pokemon_id"], sprite_size)
            if sprite:
                _draw_sprite_with_shadow(
                    canvas, sprite, sx, sy,
                    is_shiny=p.get("is_shiny", False),
                )

    # 5. 열린 존 라벨 (리본 배너)
    draw = ImageDraw.Draw(canvas)
    for ftype in FIELD_ORDER:
        if ftype not in active_types:
            continue
        zone = ZONE_REGIONS.get(ftype)
        if not zone:
            continue
        field = active_by_type[ftype]
        field_info = config.CAMP_FIELDS.get(ftype, {})
        count = len(field_placements.get(field["id"], []))
        cx, cy = _zone_pct_to_cropped_px(
            zone["center"], crop_offset, w, h,
        )
        cy -= 35  # 라벨은 존 중심 위에
        _draw_zone_label(draw, cx, cy, ftype,
                         field_info.get("name", ftype), count)

    # 8. UI 오버레이 (크롭 후에 그려야 위치가 맞음)
    cw, ch = canvas.size
    draw2 = ImageDraw.Draw(canvas)
    _draw_ui_header(draw2, cw, camp_name, camp_level, level_name)
    _draw_ui_resources(draw2, cw, fragments, crystals)

    # 9. 출력
    buf = io.BytesIO()
    canvas_rgb = canvas.convert("RGB")
    canvas_rgb.save(buf, format="JPEG", quality=88)
    buf.seek(0)
    buf.name = "camp_map.jpg"
    return buf


def _crop_to_active_zones(
    canvas: Image.Image, active_types: set,
) -> tuple[Image.Image, tuple[float, float, float, float]]:
    """열린 존 영역만 크롭 & 확대.

    Returns:
        (cropped_image, (x1%, y1%, x2%, y2%))  크롭 영역 비율 좌표
    """
    w, h = canvas.size
    full = (0.0, 0.0, 1.0, 1.0)

    # 모든 필드가 열렸으면 크롭 불필요
    if len(active_types) >= len(FIELD_ORDER):
        return canvas, full

    # 열린 존들의 바운딩 박스 합산
    x1_min, y1_min = 1.0, 1.0
    x2_max, y2_max = 0.0, 0.0

    for ftype in active_types:
        zone = ZONE_REGIONS.get(ftype)
        if not zone:
            continue
        ax1, ay1, ax2, ay2 = zone["area"]
        x1_min = min(x1_min, ax1)
        y1_min = min(y1_min, ay1)
        x2_max = max(x2_max, ax2)
        y2_max = max(y2_max, ay2)

    if x2_max <= x1_min or y2_max <= y1_min:
        return canvas, full

    # 마진: 열린 영역 주변으로 10% 여유
    margin_x = (x2_max - x1_min) * 0.10
    margin_y = (y2_max - y1_min) * 0.10
    margin = max(margin_x, margin_y, 0.04)

    x1_min = max(0.0, x1_min - margin)
    y1_min = max(0.0, y1_min - margin)
    x2_max = min(1.0, x2_max + margin)
    y2_max = min(1.0, y2_max + margin)

    # 비율 유지 (MAP_WIDTH:MAP_HEIGHT)
    target_ratio = MAP_WIDTH / MAP_HEIGHT
    crop_w = x2_max - x1_min
    crop_h = y2_max - y1_min
    cur_ratio = crop_w / crop_h if crop_h > 0 else target_ratio

    if cur_ratio > target_ratio:
        new_h = crop_w / target_ratio
        expand = (new_h - crop_h) / 2
        y1_min = max(0.0, y1_min - expand)
        y2_max = min(1.0, y2_max + expand)
    else:
        new_w = crop_h * target_ratio
        expand = (new_w - crop_w) / 2
        x1_min = max(0.0, x1_min - expand)
        x2_max = min(1.0, x2_max + expand)

    # 크롭
    px1 = int(x1_min * w)
    py1 = int(y1_min * h)
    px2 = int(x2_max * w)
    py2 = int(y2_max * h)

    cropped = canvas.crop((px1, py1, px2, py2))
    resized = cropped.resize((MAP_WIDTH, MAP_HEIGHT), Image.LANCZOS)
    return resized, (x1_min, y1_min, x2_max, y2_max)


def _zone_pct_to_cropped_px(
    pct: tuple[float, float],
    crop_offset: tuple[float, float, float, float],
    out_w: int, out_h: int,
) -> tuple[int, int]:
    """원본 맵의 % 좌표 → 크롭된 이미지의 픽셀 좌표."""
    cx1, cy1, cx2, cy2 = crop_offset
    cw = cx2 - cx1
    ch = cy2 - cy1
    if cw <= 0 or ch <= 0:
        return int(pct[0] * out_w), int(pct[1] * out_h)
    x = int((pct[0] - cx1) / cw * out_w)
    y = int((pct[1] - cy1) / ch * out_h)
    return x, y


def _get_unlock_level(field_index: int) -> int:
    """필드 인덱스(1-based) → 해금 레벨."""
    for lv, fields, *_ in config.CAMP_LEVEL_TABLE:
        if fields >= field_index:
            return lv
    return config.CAMP_MAX_LEVEL
