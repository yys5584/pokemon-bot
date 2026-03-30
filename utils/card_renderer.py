"""HTML 템플릿 기반 카드 렌더링 — Playwright로 완전한 카드 생성.

CSS 원본 그대로 사용하므로 폰트/색상/레이아웃이 100% 일치.

최적화:
  - 페이지 풀 재사용 (new_page 비용 제거)
  - set_content로 파일 I/O 제거
  - 스타트업 워밍업
  - 동시성 세마포어
"""
import io
import asyncio
import random
import logging
from pathlib import Path
from functools import lru_cache

logger = logging.getLogger(__name__)

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
    """card_spawn_styles.html에서 <style> 블록 추출 + asset 경로를 절대 경로로 변환."""
    text = CSS_SOURCE.read_text(encoding="utf-8")
    start = text.index("<style>") + len("<style>")
    end = text.index("</style>")
    css = text[start:end]
    root_url = ROOT.as_posix()
    css = css.replace('url("assets/', f'url("file:///{root_url}/assets/')
    css = css.replace("url('assets/", f"url('file:///{root_url}/assets/")
    return css


@lru_cache(maxsize=1)
def _load_template() -> str:
    """HTML 템플릿 로드 + CSS 인라인 (캐시)."""
    css = _load_css()
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    return template.replace("{{CSS}}", css)


def _build_html(pokemon_id: int, name_ko: str, rarity: str,
                is_shiny: bool, iv_total: int | None,
                types: list[str] | None,
                mega_key: str | None = None,
                personality_str: str | None = None) -> str:
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

    # 성격 뱃지
    pers_badge = ""
    if personality_str:
        from utils.battle_calc import personality_from_str
        _p = personality_from_str(personality_str)
        if _p:
            pers_badge = f'<span class="pers-badge pers-{_p["tier"]}">{_p["name"]}</span>'

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

    # HTML 조립 (캐시된 템플릿+CSS 사용)
    html = _load_template()
    html = html.replace("{{WRAP_CLASS}}", wrap_cls)
    html = html.replace("{{CARD_BG}}", card_bg)
    html = html.replace("{{PLATE_CLASS}}", plate_cls)
    html = html.replace("{{POKEMON_ID}}", f"{pokemon_id:03d}")
    html = html.replace("{{POKEMON_NAME}}", name_ko)
    html = html.replace("{{SHINY_BADGE}}", shiny_badge)
    html = html.replace("{{PERSONALITY_BADGE}}", pers_badge)
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


# ── LRU 카드 캐시 ──────────────────────────────────────────────────────

from collections import OrderedDict

_card_cache: OrderedDict[tuple, bytes] = OrderedDict()
CACHE_MAX = 300  # 최대 300장 (~15MB)
_cache_hits = 0
_cache_misses = 0


def _cache_key(pokemon_id, is_shiny, personality_str, iv_total):
    """캐시 키 생성. IV 등급 + 홀로 레벨로 버킷팅."""
    iv_grade = "D"
    if iv_total is not None:
        for threshold, letter, _ in _IV_GRADES:
            if iv_total >= threshold:
                iv_grade = letter
                break
    # 홀로 이펙트 레벨 (등급과 분기점이 다름)
    holo = "h" if iv_total and iv_total > 120 else ("l" if iv_total and iv_total > 60 else "n")
    return (pokemon_id, bool(is_shiny), personality_str or "", iv_grade, holo)


def _cache_get(key: tuple) -> bytes | None:
    global _cache_hits
    if key in _card_cache:
        _card_cache.move_to_end(key)
        _cache_hits += 1
        return _card_cache[key]
    return None


def _cache_put(key: tuple, jpeg_bytes: bytes):
    global _cache_misses
    _cache_misses += 1
    _card_cache[key] = jpeg_bytes
    while len(_card_cache) > CACHE_MAX:
        _card_cache.popitem(last=False)


def get_cache_stats() -> dict:
    """캐시 통계 (디버깅/모니터링용)."""
    return {"size": len(_card_cache), "max": CACHE_MAX,
            "hits": _cache_hits, "misses": _cache_misses,
            "hit_rate": f"{_cache_hits/max(1,_cache_hits+_cache_misses)*100:.1f}%"}


# ── Playwright 페이지 풀 ──────────────────────────────────────────────

_playwright = None
_browser = None
_page_pool: asyncio.Queue | None = None  # 재사용 가능한 페이지 큐
_render_sem: asyncio.Semaphore | None = None  # 동시 렌더링 제한

POOL_SIZE = 3  # 동시 렌더링 가능 페이지 수


async def _ensure_browser():
    """브라우저 + 페이지 풀 초기화 (한 번만)."""
    global _playwright, _browser, _page_pool, _render_sem

    if _browser is not None and _browser.is_connected():
        return

    from playwright.async_api import async_playwright
    if _playwright:
        try:
            await _playwright.stop()
        except Exception:
            pass
    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch(
        args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
    )

    # 페이지 풀 생성
    _page_pool = asyncio.Queue()
    _render_sem = asyncio.Semaphore(POOL_SIZE)
    for _ in range(POOL_SIZE):
        ctx = await _browser.new_context(viewport={"width": 940, "height": 520})
        page = await ctx.new_page()
        _page_pool.put_nowait(page)

    logger.info(f"Playwright browser ready (pool={POOL_SIZE})")


async def _get_page():
    """풀에서 페이지 가져오기. 브라우저 미초기화 시 자동 초기화."""
    await _ensure_browser()
    return await _page_pool.get()


def _return_page(page):
    """페이지 풀에 반환."""
    try:
        _page_pool.put_nowait(page)
    except Exception:
        pass


async def _reset_browser():
    """브라우저 강제 리셋 (장애 시)."""
    global _browser, _playwright, _page_pool
    logger.warning("Playwright browser reset triggered")
    try:
        if _browser:
            await _browser.close()
    except Exception:
        pass
    _browser = None
    if _page_pool:
        # 풀 비우기
        while not _page_pool.empty():
            try:
                _page_pool.get_nowait()
            except Exception:
                break
        _page_pool = None


async def warmup_browser():
    """봇 스타트업 시 호출 — 브라우저 + 페이지 풀 미리 생성."""
    try:
        await _ensure_browser()
        # 더미 렌더링으로 폰트/CSS 캐시 워밍업
        page = await _get_page()
        try:
            dummy_html = _build_html(1, "워밍업", "common", False, 100, ["grass"])
            await page.set_content(dummy_html)
            await page.screenshot(clip={"x": 0, "y": 0, "width": 940, "height": 520})
        finally:
            _return_page(page)
        logger.info("Playwright warmup complete")
    except Exception as e:
        logger.warning(f"Playwright warmup failed: {e}")


# ── 메인 렌더링 함수 ──────────────────────────────────────────────────

async def render_card_html_async(pokemon_id: int, name_ko: str, rarity: str,
                                 is_shiny: bool = False, mega_key: str | None = None,
                                 iv_total: int | None = None,
                                 types: list[str] | None = None,
                                 personality_str: str | None = None) -> io.BytesIO:
    """HTML 템플릿으로 카드 렌더링 (async) → JPEG BytesIO 반환.

    최적화: LRU 캐시 → 페이지 풀 재사용 → set_content → 세마포어 동시성 제한.
    """
    # 1. LRU 캐시 체크
    ck = _cache_key(pokemon_id, is_shiny, personality_str, iv_total)
    cached = _cache_get(ck)
    if cached:
        buf = io.BytesIO(cached)
        buf.name = "card.jpg"
        return buf

    html = _build_html(pokemon_id, name_ko, rarity, is_shiny, iv_total, types, mega_key, personality_str)

    await _render_sem.acquire()
    page = None
    try:
        page = await asyncio.wait_for(_get_page(), timeout=5)
        import uuid
        tmp_path = ROOT / f"_tmp_card_{uuid.uuid4().hex[:8]}.html"
        tmp_path.write_text(html, encoding="utf-8")
        try:
            await asyncio.wait_for(
                page.goto(f"file:///{tmp_path.as_posix()}", wait_until="load"),
                timeout=8,
            )
        finally:
            tmp_path.unlink(missing_ok=True)
        # CSS 애니메이션 렌더링 대기 (최소한)
        await page.wait_for_timeout(100)
        png_bytes = await asyncio.wait_for(
            page.screenshot(clip={"x": 0, "y": 0, "width": 940, "height": 520}),
            timeout=5,
        )
    except Exception:
        # 장애 시 페이지 폐기 + 브라우저 리셋
        if page:
            try:
                await page.close()
            except Exception:
                pass
            page = None  # 풀에 반환하지 않음
        await _reset_browser()
        raise
    finally:
        if page:
            _return_page(page)
        _render_sem.release()

    # PNG → JPEG 변환
    from PIL import Image
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    img = img.resize((960, 540), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    buf.seek(0)
    buf.name = "card.jpg"

    # 2. 캐시에 저장
    _cache_put(ck, buf.getvalue())

    return buf
