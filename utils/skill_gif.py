"""미리 생성된 스킬 프레임 + 상대 스프라이트 런타임 합성."""
import io
from pathlib import Path
from PIL import Image

_FRAMES_DIR = Path(__file__).parent.parent / "assets" / "skill_frames"
_ASSETS_DIR = Path(__file__).parent.parent / "assets" / "pokemon"

# 상대 스프라이트 위치 (400x225 기준, 우측 중앙)
_DEF_CX, _DEF_CY = 310, 100
_DEF_SIZE = 90

_FRAME_DURATIONS = (
    [160] * 3 +   # 스킬명
    [120] * 3 +   # 차징
    [100] * 5 +   # 발사
    [60] * 2 +    # 임팩트
    [80] * 3 +    # 흔들림
    [100] * 4 +   # 데미지
    [150] * 4     # 정리
)

# 프레임 캐시 (메모리에 유지)
_frame_cache: dict[int, list[Image.Image]] = {}

# 셰이크 (임팩트~흔들림 구간)
_SHAKES = [(8, -5), (-6, 4), (3, -2)]


def _load_frames(pokemon_id: int) -> list[Image.Image] | None:
    if pokemon_id in _frame_cache:
        return _frame_cache[pokemon_id]
    frame_dir = _FRAMES_DIR / str(pokemon_id)
    if not frame_dir.exists():
        return None
    frames = []
    for i in range(24):
        path = frame_dir / f"{i:02d}.png"
        if not path.exists():
            return None
        frames.append(Image.open(path).convert("RGBA"))
    _frame_cache[pokemon_id] = frames
    return frames


def _load_sprite(pokemon_id: int) -> Image.Image | None:
    path = _ASSETS_DIR / f"{pokemon_id}.png"
    if not path.exists():
        return None
    img = Image.open(path).convert("RGBA")
    img = img.resize((_DEF_SIZE, _DEF_SIZE), Image.LANCZOS)
    return img


def compose_skill_gif(atk_id: int, def_id: int) -> io.BytesIO | None:
    """미리 생성된 프레임에 상대 스프라이트를 합성하여 GIF 반환."""
    frames = _load_frames(atk_id)
    if not frames:
        return None

    def_sprite = _load_sprite(def_id)

    composed = []
    for i, frame in enumerate(frames):
        # 먼저 RGB로 변환 (배경이 확정된 상태)
        f = frame.convert("RGB")
        if def_sprite:
            # 임팩트~흔들림 구간(프레임 11~15)에서 상대 흔들림
            dx, dy = 0, 0
            if 11 <= i <= 13:
                si = i - 11
                if si < len(_SHAKES):
                    dx, dy = _SHAKES[si]
            # RGB 프레임 위에 RGBA 스프라이트 합성 (알파 마스크)
            pos = (_DEF_CX - _DEF_SIZE // 2 + dx, _DEF_CY - _DEF_SIZE // 2 + dy)
            f.paste(def_sprite.convert("RGB"), pos, def_sprite.split()[3])
        # 팔레트 양자화
        f = f.quantize(colors=192, method=Image.Quantize.FASTOCTREE).convert("RGB")
        composed.append(f)

    buf = io.BytesIO()
    composed[0].save(
        buf, format="GIF", save_all=True,
        append_images=composed[1:],
        duration=_FRAME_DURATIONS,
        loop=0,
        optimize=True,
    )
    buf.seek(0)
    buf.name = "skill.gif"
    return buf


# 지원 포켓몬 목록
SUPPORTED_IDS = {150, 249, 250, 382, 383, 384, 385, 386, 483, 484, 487, 490, 491, 492, 493}


def has_skill_gif(pokemon_id: int) -> bool:
    return pokemon_id in SUPPORTED_IDS
