"""카드 배경 템플릿 렌더링 — Playwright로 HTML → PNG.

등급별 × 홀로레벨/이로치변형 조합으로 35장 생성:
- normal: 5 rarity × 3 holo (none, low, high) = 15
- shiny: 5 rarity × 4 variant (gold, cool, rose, toxic) = 20
"""
import os, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent
OUT_DIR = ROOT / "assets" / "card_templates"
OUT_DIR.mkdir(parents=True, exist_ok=True)

RARITIES = [
    ("common", "common", "common-bg", "common-plate", "common-frame", "common-art", "common-glow", "common-info", "common-accent"),
    ("rare", "rare", "rare-bg", "rare-plate", "rare-frame", "rare-art", "rare-glow", "rare-info", "rare-accent"),
    ("epic", "epic", "epic-bg", "", "", "epic-art", "", "", ""),
    ("legendary", "legendary", "legendary-bg", "legendary-plate", "legendary-frame", "legendary-art", "legendary-glow", "legendary-info", "legendary-accent"),
    ("ultra_legendary", "ultra-legendary", "ultra-legendary-bg", "ultra-plate", "ultra-frame", "ultra-art", "ultra-glow", "ultra-info", "ultra-accent"),
]

HOLO_LEVELS = ["none", "low", "high"]
SHINY_VARIANTS = ["gold", "cool", "rose", "toxic"]

# 카드 크기: 940×510 (card-wrap padding 5px → inner 930×500)
CARD_W = 940
CARD_H = 520

# CSS 절대경로 (HTML에서 참조)
css_abs = (ROOT / "scripts" / "card_template.css").as_posix()


RARITY_LABELS = {
    "common": "일반", "rare": "레어", "epic": "에픽",
    "legendary": "전설", "ultra_legendary": "초전설",
}
BADGE_CLS = {
    "common": "common", "rare": "rare", "epic": "epic",
    "legendary": "legendary", "ultra_legendary": "ultra-legendary",
}


def build_normal_html(rarity_key, wrap_cls, card_bg, plate_cls, frame_cls, art_cls, glow_cls, info_cls, accent_cls, holo_level):
    """일반 카드 템플릿 HTML — 뱃지 포함, 스프라이트/이름 없음."""
    holo_cls = {"none": "", "low": "iv-low", "high": "iv-high"}[holo_level]
    holo_div = f'<div class="holo-shine {holo_cls}"></div>' if holo_cls else ''
    badge_label = RARITY_LABELS[rarity_key]
    badge_cls = BADGE_CLS[rarity_key]

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<link rel="stylesheet" href="file:///{css_abs}">
</head><body style="margin:0;padding:0;width:{CARD_W}px;height:{CARD_H}px;">
<div class="card-wrap {wrap_cls}" style="width:{CARD_W}px;height:{CARD_H}px;">
  <div class="card {card_bg}">
    <div class="nameplate {plate_cls}">
      <div class="name-section"></div>
      <div class="hp-section">
        <span class="badge {badge_cls}">{badge_label}</span>
      </div>
    </div>
    <div class="art-frame {frame_cls}">
      <div class="art-bg {art_cls}"></div>
      <div class="normal-grain"></div>
      <div class="art-glow {glow_cls}"></div>
      {holo_div}
    </div>
    <div class="info-panel {info_cls}"></div>
    <div class="accent-line {accent_cls}"></div>
  </div>
</div>
</body></html>"""


def build_shiny_html(rarity_key, wrap_cls, card_bg, art_cls, glow_cls, variant):
    """이로치 카드 템플릿 HTML — 뱃지+SHINY 뱃지 포함."""
    badge_label = RARITY_LABELS[rarity_key]
    badge_cls = BADGE_CLS[rarity_key]

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<link rel="stylesheet" href="file:///{css_abs}">
</head><body style="margin:0;padding:0;width:{CARD_W}px;height:{CARD_H}px;">
<div class="card-wrap shiny variant-{variant}" style="width:{CARD_W}px;height:{CARD_H}px;">
  <div class="card {card_bg}">
    <div class="nameplate shiny-plate">
      <div class="name-section"></div>
      <div class="hp-section">
        <span class="badge {badge_cls}">{badge_label}</span>
      </div>
    </div>
    <div class="art-frame shiny-frame">
      <div class="art-bg {art_cls}"></div>
      <div class="art-glow {glow_cls}"></div>
      <div class="shiny-cosmos"></div>
      <div class="shiny-inner-glow"></div>
      <div class="art-foil"></div>
      <div class="art-prism-ref"></div>
      <div class="art-glare-ref"></div>
    </div>
    <div class="info-panel shiny-info"></div>
    <div class="accent-line shiny-accent"></div>
  </div>
</div>
</body></html>"""


def main():
    # CSS 파일 생성 (test_card_spawn.html에서 <style> 추출)
    css_path = ROOT / "scripts" / "card_template.css"
    extract_css(css_path)

    with sync_playwright() as p:
        browser = p.chromium.launch()

        count = 0
        # 일반 카드
        for rarity_key, wrap_cls, card_bg, plate_cls, frame_cls, art_cls, glow_cls, info_cls, accent_cls in RARITIES:
            for holo in HOLO_LEVELS:
                html = build_normal_html(rarity_key, wrap_cls, card_bg, plate_cls, frame_cls, art_cls, glow_cls, info_cls, accent_cls, holo)
                fname = f"normal_{rarity_key}_{holo}.png"
                render(browser, html, OUT_DIR / fname)
                count += 1
                print(f"  [{count}/35] {fname}")

        # 이로치 카드
        for rarity_key, wrap_cls, card_bg, plate_cls, frame_cls, art_cls, glow_cls, info_cls, accent_cls in RARITIES:
            for variant in SHINY_VARIANTS:
                html = build_shiny_html(rarity_key, wrap_cls, card_bg, art_cls, glow_cls, variant)
                fname = f"shiny_{rarity_key}_{variant}.png"
                render(browser, html, OUT_DIR / fname)
                count += 1
                print(f"  [{count}/35] {fname}")

        browser.close()
    print(f"\nDone! {count} templates saved to {OUT_DIR}")


def render(browser, html_content: str, out_path: Path):
    """HTML을 렌더링하여 PNG로 저장."""
    tmp_html = ROOT / "_tmp_template.html"  # 프로젝트 루트에 생성 (asset 경로 해결)
    tmp_html.write_text(html_content, encoding="utf-8")

    page = browser.new_page(viewport={"width": CARD_W, "height": CARD_H})
    page.goto(f"file:///{tmp_html.as_posix()}")
    page.wait_for_timeout(300)
    page.screenshot(path=str(out_path), clip={"x": 0, "y": 0, "width": CARD_W, "height": CARD_H})
    page.close()
    tmp_html.unlink(missing_ok=True)


def extract_css(css_path: Path):
    """test_card_spawn.html에서 <style> 블록 추출, 에셋 경로를 절대경로로 변환."""
    html_file = ROOT / "test_card_spawn.html"
    text = html_file.read_text(encoding="utf-8")
    start = text.index("<style>") + len("<style>")
    end = text.index("</style>")
    css = text[start:end]
    # asset URL을 절대 경로로 변환
    root_url = ROOT.as_posix()
    css = css.replace('url("assets/', f'url("file:///{root_url}/assets/')
    css = css.replace("url('assets/", f"url('file:///{root_url}/assets/")
    # body 스타일 오버라이드 (배경 투명)
    css += "\nbody { background: transparent !important; }\n"
    css_path.write_text(css, encoding="utf-8")
    print(f"CSS extracted to {css_path}")


if __name__ == "__main__":
    main()
