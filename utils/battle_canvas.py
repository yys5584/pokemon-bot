"""Canvas 기반 스킬 GIF 생성 — Playwright 캡처 파이프라인."""
import io
import base64
import json
import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

_ASSETS_DIR = Path(__file__).parent.parent / "assets" / "pokemon"
_TEMPLATE_PATH = Path(__file__).parent / "battle_animation.html"

_TYPE_COLORS = {
    "fire": [[255,70,20],[255,140,30],[255,200,60]],
    "water": [[20,80,220],[50,140,255],[130,210,255]],
    "electric": [[200,170,0],[255,230,30],[255,255,180]],
    "grass": [[30,140,50],[60,200,80],[140,240,120]],
    "psychic": [[180,40,120],[220,80,180],[255,160,220]],
    "ice": [[40,140,200],[80,200,240],[180,240,255]],
    "dragon": [[80,40,180],[120,70,220],[180,130,255]],
    "dark": [[60,40,60],[100,70,100],[150,120,150]],
    "normal": [[160,160,140],[200,200,180],[230,230,220]],
    "fighting": [[160,50,20],[200,80,40],[240,130,70]],
    "poison": [[120,40,160],[160,70,200],[200,130,240]],
    "ground": [[160,130,50],[200,170,80],[230,210,130]],
    "flying": [[100,140,210],[140,180,240],[190,220,255]],
    "bug": [[120,160,20],[160,200,60],[200,240,110]],
    "rock": [[140,120,80],[180,160,120],[210,200,170]],
    "ghost": [[60,40,120],[100,70,170],[150,120,220]],
    "steel": [[140,150,170],[180,190,200],[210,220,230]],
    "fairy": [[210,110,160],[240,150,190],[255,200,225]],
}

_pw = None
_browser = None

TOTAL_FRAMES = 60
_FRAME_DURATIONS = (
    [75] * 8 +    # 스킬명 (600ms)
    [50] * 8 +    # 차징 (400ms)
    [45] * 12 +   # 발사 (540ms)
    [30] * 5 +    # 임팩트 (150ms)
    [50] * 8 +    # 흔들림 (400ms)
    [90] * 11 +   # 데미지 (990ms)
    [80] * 8      # 정리 (640ms)
)


def _get_browser():
    global _pw, _browser
    if _browser is None:
        from playwright.sync_api import sync_playwright
        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch(headless=True)
    return _browser


def _sprite_to_base64(pokemon_id: int) -> str:
    path = _ASSETS_DIR / f"{pokemon_id}.png"
    if not path.exists():
        return ""
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode()
    return f"data:image/png;base64,{b64}"


def render_battle_gif(
    atk_id: int, atk_name: str, def_id: int, def_name: str,
    skill_name: str, skill_type: str, damage: int,
    atk_shiny: bool = False, def_shiny: bool = False,
    is_crit: bool = False,
    atk_rarity: str = "common", def_rarity: str = "common",
    hp_before: float = 1.0, hp_after: float = 0.35,
    atk_hp: float = 1.0,
    round_text: str = "",
) -> tuple[io.BytesIO, int]:
    """Canvas 기반 스킬 GIF 생성. Returns (gif_buffer, total_duration_ms)."""
    browser = _get_browser()

    data = {
        "atkSprite": _sprite_to_base64(atk_id),
        "defSprite": _sprite_to_base64(def_id),
        "skillType": skill_type,
        "skillName": skill_name,
        "atkName": atk_name,
        "defName": def_name,
        "atkRarity": atk_rarity,
        "defRarity": def_rarity,
        "atkShiny": atk_shiny,
        "defShiny": def_shiny,
        "damage": damage,
        "isCrit": is_crit,
        "hpBefore": hp_before,
        "hpAfter": hp_after,
        "atkHp": atk_hp,
        "typeColors": _TYPE_COLORS.get(skill_type, _TYPE_COLORS["normal"]),
        "roundText": round_text,
    }

    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    data_json = json.dumps(data, ensure_ascii=False)

    # 데이터 주입 — 기본값 블록을 실제 데이터로 교체
    marker_start = '/*__DATA__*/'
    marker_end = '/*__END__*/'
    idx_start = template.index(marker_start)
    idx_end = template.index(marker_end) + len(marker_end)
    html = template[:idx_start] + data_json + template[idx_end:]

    # 960x540에서 렌더 후 480x270으로 축소 (GIF 용량 절감)
    OUT_W, OUT_H = 480, 270
    page = browser.new_page(viewport={"width": 960, "height": 540})
    try:
        page.set_content(html)
        page.wait_for_function("window._ready === true", timeout=5000)

        frames = []
        for i in range(TOTAL_FRAMES):
            page.evaluate(f"renderFrame({i})")
            screenshot = page.screenshot(type="png")
            img = Image.open(io.BytesIO(screenshot)).convert("RGB")
            img = img.resize((OUT_W, OUT_H), Image.LANCZOS)
            frames.append(img)
    finally:
        page.close()

    total_dur = sum(_FRAME_DURATIONS)
    buf = io.BytesIO()
    frames[0].save(
        buf, format="GIF", save_all=True,
        append_images=frames[1:],
        duration=_FRAME_DURATIONS,
        loop=0,
        optimize=True,
    )
    buf.seek(0)
    buf.name = "skill.gif"
    return buf, total_dur
