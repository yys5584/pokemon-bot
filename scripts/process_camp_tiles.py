"""캠프 필드 배경 이미지 가공 스크립트.

사용법:
    python scripts/process_camp_tiles.py <field_type> <image_path>

예시:
    python scripts/process_camp_tiles.py forest C:/Users/Administrator/Desktop/forest_raw.png
    python scripts/process_camp_tiles.py volcano C:/Users/Administrator/Desktop/volcano_raw.png

지원 필드: forest, volcano, lake, city, cave, temple

가공 내용:
    1. 400×180 비율로 center crop
    2. LANCZOS 리사이즈
    3. 약간 어둡게 (포켓몬 스프라이트 가독성)
    4. assets/camp_tiles/{field_type}.png 로 저장
"""

import sys
from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter

TILE_W = 400
TILE_H = 180
OUT_DIR = Path(__file__).parent.parent / "assets" / "camp_tiles"
VALID_FIELDS = {"forest", "volcano", "lake", "city", "cave", "temple"}


def process_tile(field_type: str, image_path: str):
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    img = Image.open(image_path).convert("RGBA")
    print(f"원본 크기: {img.size}")

    # 1. Center crop (400:180 = 20:9 비율)
    target_ratio = TILE_W / TILE_H
    cur_ratio = img.width / img.height

    if cur_ratio > target_ratio:
        # 너무 넓음 → 좌우 크롭
        new_w = int(img.height * target_ratio)
        left = (img.width - new_w) // 2
        img = img.crop((left, 0, left + new_w, img.height))
    else:
        # 너무 높음 → 상하 크롭
        new_h = int(img.width / target_ratio)
        top = (img.height - new_h) // 2
        img = img.crop((0, top, img.width, top + new_h))

    # 2. 리사이즈
    img = img.resize((TILE_W, TILE_H), Image.LANCZOS)

    # 3. 약간 어둡게 (brightness 0.7)
    enhancer = ImageEnhance.Brightness(img.convert("RGB"))
    darkened = enhancer.enhance(0.7).convert("RGBA")

    # 4. 저장
    out_path = OUT_DIR / f"{field_type}.png"
    darkened.save(out_path, "PNG")
    print(f"저장 완료: {out_path} ({TILE_W}×{TILE_H})")


def process_all_from_dir(dir_path: str):
    """폴더 내 이미지를 필드명으로 매칭해서 일괄 처리.

    파일명에 필드명이 포함되면 자동 매칭:
        forest_raw.png → forest
        my_volcano.jpg → volcano
    """
    d = Path(dir_path)
    for f in d.iterdir():
        if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            for ft in VALID_FIELDS:
                if ft in f.stem.lower():
                    print(f"\n--- {f.name} → {ft} ---")
                    process_tile(ft, str(f))
                    break


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if len(sys.argv) == 2:
        # 폴더 지정 → 일괄 처리
        process_all_from_dir(sys.argv[1])
    else:
        field_type = sys.argv[1]
        image_path = sys.argv[2]

        if field_type not in VALID_FIELDS:
            print(f"잘못된 필드: {field_type}")
            print(f"사용 가능: {', '.join(sorted(VALID_FIELDS))}")
            sys.exit(1)

        process_tile(field_type, image_path)
