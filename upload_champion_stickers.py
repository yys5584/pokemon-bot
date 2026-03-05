"""Champion TGS 파일을 커스텀 이모지 스티커셋으로 업로드.
80% 스케일 (기존 static 이모지와 동일 비율) 적용.
"""
import requests
import json
import gzip
import os
import sys
import tempfile

BOT_TOKEN = "8578621482:AAETKN-hwDsiCLJ4Yk3SD45Rtrd3-dQtqYk"
OWNER_ID = 1832746512
SET_NAME = "champion_effects_by_TG_Poke_bot"
SET_TITLE = "Champion Effects"

API = f"https://api.telegram.org/bot{BOT_TOKEN}"

CHAMPION_DIR = os.path.join(os.path.dirname(__file__), "assets", "Champion")

TGS_FILES = [
    "first.tgs",
    "2914955.tgs",
    "2914957.tgs",
    "2914959.tgs",
    "2914961.tgs",
    "3742979.tgs",
]

EMOJI_LIST = ["🏆", "⭐", "🎖️", "👑", "🥇", "💎"]


def scale_tgs_80(input_path):
    """TGS 애니메이션을 80%로 축소하고 가운데 정렬.

    방법: null 레이어를 추가하고, 모든 기존 레이어의 parent를 이 null로 설정.
    null 레이어의 transform: anchor=(256,256), position=(256,256), scale=(80,80)
    """
    with gzip.open(input_path, "rt", encoding="utf-8") as f:
        data = json.load(f)

    w = data.get("w", 512)
    h = data.get("h", 512)
    cx, cy = w / 2, h / 2

    # Find max layer index
    max_ind = max((l.get("ind", i) for i, l in enumerate(data["layers"])), default=0)
    parent_ind = max_ind + 1

    # Create null parent layer for 80% scale centering
    null_layer = {
        "ty": 3,  # null layer
        "ind": parent_ind,
        "nm": "scale80",
        "ip": data.get("ip", 0),
        "op": data.get("op", 180),
        "st": 0,
        "sr": 1,
        "ks": {
            "p": {"a": 0, "k": [cx, cy, 0]},      # position: center
            "a": {"a": 0, "k": [cx, cy, 0]},      # anchor: center
            "s": {"a": 0, "k": [80, 80, 100]},     # scale: 80%
            "r": {"a": 0, "k": 0},
            "o": {"a": 0, "k": 100},
        },
    }

    # Set all existing layers to parent to the null layer (only if no parent already)
    for layer in data["layers"]:
        if "parent" not in layer:
            layer["parent"] = parent_ind

    # Add null layer at the beginning
    data["layers"].insert(0, null_layer)

    tmp = tempfile.NamedTemporaryFile(suffix=".tgs", delete=False)
    with gzip.open(tmp.name, "wt", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))

    size_kb = os.path.getsize(tmp.name) / 1024
    print(f"  Scaled to 80% ({size_kb:.1f}KB)")
    return tmp.name


def upload_stickers():
    # Delete existing set if it exists
    r = requests.get(f"{API}/getStickerSet", params={"name": SET_NAME})
    if r.json().get("ok"):
        print(f"기존 스티커셋 삭제 중...")
        r = requests.post(f"{API}/deleteStickerSet", data={"name": SET_NAME})
        if r.json().get("ok"):
            print("  삭제 완료")
        else:
            print(f"  삭제 실패: {r.json()}")
            sys.exit(1)

    # Upload each TGS (80% scaled)
    file_ids = []
    for tgs_file in TGS_FILES:
        path = os.path.join(CHAMPION_DIR, tgs_file)
        print(f"Processing: {tgs_file}")
        scaled_path = scale_tgs_80(path)

        with open(scaled_path, "rb") as fh:
            r = requests.post(
                f"{API}/uploadStickerFile",
                data={
                    "user_id": OWNER_ID,
                    "sticker_format": "animated",
                },
                files={"sticker": (tgs_file, fh, "application/x-tgsticker")},
            )

        os.unlink(scaled_path)

        result = r.json()
        if not result.get("ok"):
            print(f"  Upload FAIL: {result}")
            sys.exit(1)

        fid = result["result"]["file_id"]
        file_ids.append(fid)
        print(f"  Upload OK")

    # Create sticker set
    stickers = []
    for fid, emoji in zip(file_ids, EMOJI_LIST):
        stickers.append({
            "sticker": fid,
            "format": "animated",
            "emoji_list": [emoji],
        })

    print(f"\nCreating sticker set '{SET_NAME}'...")
    r = requests.post(
        f"{API}/createNewStickerSet",
        data={
            "user_id": OWNER_ID,
            "name": SET_NAME,
            "title": SET_TITLE,
            "sticker_type": "custom_emoji",
            "stickers": json.dumps(stickers),
        },
    )

    result = r.json()
    if not result.get("ok"):
        print(f"Error: {result}")
        sys.exit(1)

    print(f"스티커셋 생성 완료!")

    # Show results
    r = requests.get(f"{API}/getStickerSet", params={"name": SET_NAME})
    if r.json().get("ok"):
        sticker_set = r.json()["result"]
        print(f"\n=== 스티커셋 완료 ===")
        print(f"스티커 수: {len(sticker_set['stickers'])}")
        print(f"링크: https://t.me/addstickers/{SET_NAME}")
        print()
        for i, s in enumerate(sticker_set["stickers"]):
            fname = TGS_FILES[i] if i < len(TGS_FILES) else "?"
            eid = s.get("custom_emoji_id", "N/A")
            print(f"  [{fname}] custom_emoji_id: {eid}")


if __name__ == "__main__":
    upload_stickers()
