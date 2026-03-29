"""HTML 템플릿 기반 카드 렌더링 — Playwright로 완전한 카드 생성.

CSS 원본 그대로 사용하므로 폰트/색상/레이아웃이 100% 일치.
"""
import io
import random
from pathlib import Path
from functools import lru_cache

ROOT = Path(__file__).parent.parent
TEMPLATE_PATH = ROOT / "assets" / "card_template.html"
CSS_SOURCE = ROOT / "assets" / "card_spawn_styles.html"

# 등급별 클래스 매핑 (HTML CSS 원본 그대로)
_RARITY_MAP = {
    "common": {
        "wrap": "common", "card_bg": "common-bg",
        "plate": "common-plate", "frame": "common-frame",
        "art_bg": "common-art", "glow": "common-glow",
        "info": "common-info", "accent": "common-accent",
        "badge_cls": "common", "badge_text": "일반",
    },
    "rare": {
        "wrap": "rare", "card_bg": "rare-bg",
        "plate": "rare-plate", "frame": "rare-frame",
        "art_bg": "rare-art", "glow": "rare-glow",
        "info": "rare-info", "accent": "rare-accent",
        "badge_cls": "rare", "badge_text": "레어",
    },
    "epic": {
        "wrap": "epic", "card_bg": "epic-bg",
        "plate": "", "frame": "",
        "art_bg": "epic-art", "glow": "",
        "info": "", "accent": "",
        "badge_cls": "epic", "badge_text": "에픽",
    },
    "legendary": {
        "wrap": "legendary", "card_bg": "legendary-bg",
        "plate": "legendary-plate", "frame": "legendary-frame",
        "art_bg": "legendary-art", "glow": "legendary-glow",
        "info": "legendary-info", "accent": "legendary-accent",
        "badge_cls": "legendary", "badge_text": "전설",
    },
    "ultra_legendary": {
        "wrap": "ultra-legendary", "card_bg": "ultra-legendary-bg",
        "plate": "ultra-plate", "frame": "ultra-frame",
        "art_bg": "ultra-art", "glow": "ultra-glow",
        "info": "ultra-info", "accent": "ultra-accent",
        "badge_cls": "ultra-legendary", "badge_text": "초전설",
    },
}

_SHINY_VARIANTS = ["gold", "cool", "rose", "toxic"]

_TYPE_KO = {
    "normal": "노말", "fire": "불꽃", "water": "물", "grass": "풀",
    "electric": "전기", "ice": "얼음", "fighting": "격투", "poison": "독",
    "ground": "땅", "flying": "비행", "psychic": "에스퍼", "bug": "벌레",
    "rock": "바위", "ghost": "고스트", "dragon": "드래곤", "dark": "악",
    "steel": "강철", "fairy": "페어리",
}

_IV_GRADES = [
    (160, "S", "iv-s"), (120, "A", "iv-a"),
    (93, "B", "iv-b"), (62, "C", "iv-c"),
    (0, "D", "iv-d"),
]


@lru_cache(maxsize=1)
def _load_css() -> str:
    """test_card_spawn.html에서 <style> 블록 추출 + asset 경로를 절대 경로로 변환."""
    text = CSS_SOURCE.read_text(encoding="utf-8")
    start = text.index("<style>") + len("<style>")
    end = text.index("</style>")
    css = text[start:end]
    root_url = ROOT.as_posix()
    css = css.replace('url("assets/', f'url("file:///{root_url}/assets/')
    css = css.replace("url('assets/", f"url('file:///{root_url}/assets/")
    return css


def _build_html(pokemon_id: int, name_ko: str, rarity: str,
                is_shiny: bool, iv_total: int | None,
                types: list[str] | None,
                mega_key: str | None = None) -> str:
    """동적 파라미터로 카드 HTML 생성."""
    r = _RARITY_MAP.get(rarity, _RARITY_MAP["common"])
    root_url = ROOT.as_posix()

    # 이로치 여부에 따른 클래스
    if is_shiny:
        variant = random.choice(_SHINY_VARIANTS)
        wrap_cls = f"shiny variant-{variant}"
        plate_cls = "shiny-plate"
        frame_cls = "shiny-frame"
        info_cls = "shiny-info"
        accent_cls = "shiny-accent"
        card_bg = r["card_bg"]
        art_bg = r["art_bg"]
        glow_cls = r["glow"]
        sprite_cls = "shiny-sprite"
    else:
        wrap_cls = r["wrap"]
        plate_cls = r["plate"]
        frame_cls = r["frame"]
        info_cls = r["info"]
        accent_cls = r["accent"]
        card_bg = r["card_bg"]
        art_bg = r["art_bg"]
        glow_cls = r["glow"]
        sprite_cls = ""

    # 타입 아이콘 HTML
    type_icons = ""
    if types:
        for t in types:
            type_icons += f'<div class="type-icon"><img src="file:///{root_url}/assets/types/{t}.svg"></div>'

    # SHINY 뱃지
    shiny_badge = '<span class="shiny-badge">SHINY</span>' if is_shiny else ""

    # 스프라이트
    if mega_key:
        sprite_src = f"file:///{root_url}/assets/pokemon/{mega_key}.png"
    else:
        sprite_src = f"file:///{root_url}/assets/pokemon/{pokemon_id}.png"

    # 이펙트 레이어 (일반 vs 이로치)
    if is_shiny:
        effect_layers = (
            '<div class="shiny-cosmos"></div>'
            '<div class="shiny-inner-glow"></div>'
            '<div class="art-foil"></div>'
            '<div class="art-prism-ref"></div>'
            '<div class="art-glare-ref"></div>'
        )
        grain_div = ""
    else:
        # 홀로 레벨
        if iv_total is not None and iv_total > 120:
            holo = '<div class="holo-shine iv-high"></div>'
        elif iv_total is not None and iv_total > 60:
            holo = '<div class="holo-shine iv-low"></div>'
        else:
            holo = ""
        effect_layers = holo
        grain_div = '<div class="normal-grain"></div>'

    # IV 등급
    iv_class, iv_text = "iv-hidden", "IV: ???"
    if iv_total is not None:
        for threshold, letter, cls in _IV_GRADES:
            if iv_total >= threshold:
                iv_class = cls
                iv_text = f"IV: {letter}"
                break

    # info 라벨
    parts = [r["badge_text"]]
    if types:
        parts.append(" / ".join(_TYPE_KO.get(t, t) for t in types))
    info_label = " · ".join(parts)

    # HTML 조립
    css = _load_css()
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = template.replace("{{CSS}}", css)
    html = html.replace("{{WRAP_CLASS}}", wrap_cls)
    html = html.replace("{{CARD_BG}}", card_bg)
    html = html.replace("{{PLATE_CLASS}}", plate_cls)
    html = html.replace("{{POKEMON_ID}}", f"{pokemon_id:03d}")
    html = html.replace("{{POKEMON_NAME}}", name_ko)
    html = html.replace("{{SHINY_BADGE}}", shiny_badge)
    html = html.replace("{{TYPE_ICONS}}", type_icons)
    html = html.replace("{{BADGE_CLASS}}", r["badge_cls"])
    html = html.replace("{{BADGE_TEXT}}", r["badge_text"])
    html = html.replace("{{FRAME_CLASS}}", frame_cls)
    html = html.replace("{{ART_BG}}", art_bg)
    html = html.replace("{{GRAIN_DIV}}", grain_div)
    html = html.replace("{{GLOW_CLASS}}", glow_cls)
    html = html.replace("{{EFFECT_LAYERS}}", effect_layers)
    html = html.replace("{{SPRITE_CLASS}}", sprite_cls)
    html = html.replace("{{SPRITE_SRC}}", sprite_src)
    html = html.replace("{{INFO_CLASS}}", info_cls)
    html = html.replace("{{INFO_LABEL}}", info_label)
    html = html.replace("{{IV_CLASS}}", iv_class)
    html = html.replace("{{IV_TEXT}}", iv_text)
    html = html.replace("{{ACCENT_CLASS}}", accent_cls)
    return html


# Playwright async 브라우저 싱글톤
_browser = None
_playwright = None


async def _get_browser_async():
    """Playwright async 브라우저 싱글톤."""
    global _browser, _playwright
    if _browser is None or not _browser.is_connected():
        from playwright.async_api import async_playwright
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch()
    return _browser


async def render_card_html_async(pokemon_id: int, name_ko: str, rarity: str,
                                 is_shiny: bool = False, mega_key: str | None = None,
                                 iv_total: int | None = None,
                                 types: list[str] | None = None) -> io.BytesIO:
    """HTML 템플릿으로 카드 렌더링 (async) → JPEG BytesIO 반환."""
    html = _build_html(pokemon_id, name_ko, rarity, is_shiny, iv_total, types, mega_key)

    # 임시 HTML 파일 (동시 요청 충돌 방지: uuid)
    import uuid
    tmp_path = ROOT / f"_tmp_card_{uuid.uuid4().hex[:8]}.html"
    tmp_path.write_text(html, encoding="utf-8")

    try:
        browser = await _get_browser_async()
        page = await browser.new_page(viewport={"width": 940, "height": 520})
        await page.goto(f"file:///{tmp_path.as_posix()}")
        await page.wait_for_timeout(200)
        png_bytes = await page.screenshot(clip={"x": 0, "y": 0, "width": 940, "height": 520})
        await page.close()
    finally:
        tmp_path.unlink(missing_ok=True)

    # PNG → JPEG 변환
    from PIL import Image
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    img = img.resize((960, 540), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    buf.seek(0)
    buf.name = "card.jpg"
    return buf
