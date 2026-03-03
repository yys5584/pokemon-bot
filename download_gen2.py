"""Download Gen 2 Pokemon images (#152-251) and convert to 390x390 RGBA PNG."""

import os
import urllib.request
import time
from PIL import Image
from io import BytesIO

ASSET_DIR = r"C:\Users\Administrator\Desktop\pokemon-bot\assets\pokemon"
BASE_URL = "https://data1.pokemonkorea.co.kr/newdata/pokedex/mid/{:04d}01.png"

success = 0
fail = 0

for num in range(152, 252):
    out_path = os.path.join(ASSET_DIR, f"{num}.png")
    if os.path.exists(out_path):
        print(f"  SKIP #{num} (already exists)")
        success += 1
        continue

    url = BASE_URL.format(num)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = resp.read()

        # Open and convert to 390x390 RGBA
        img = Image.open(BytesIO(data))
        img = img.convert("RGBA")

        # Resize to fit 390x390 while keeping aspect ratio, then paste on transparent canvas
        # First, calculate the scale to fit within 390x390
        w, h = img.size
        scale = min(390 / w, 390 / h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        img_resized = img.resize((new_w, new_h), Image.LANCZOS)

        # Create 390x390 transparent canvas and center the image
        canvas = Image.new("RGBA", (390, 390), (255, 255, 255, 0))
        offset_x = (390 - new_w) // 2
        offset_y = (390 - new_h) // 2
        canvas.paste(img_resized, (offset_x, offset_y), img_resized)

        canvas.save(out_path, "PNG")
        success += 1
        print(f"  OK  #{num} ({len(data)} bytes -> 390x390)")

    except Exception as e:
        fail += 1
        print(f"  FAIL #{num}: {e}")

    time.sleep(0.3)  # Be polite to server

print(f"\nDone! Success: {success}, Failed: {fail}")
