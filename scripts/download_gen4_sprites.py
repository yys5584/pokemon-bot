"""4세대(신오) 포켓몬 스프라이트 다운로드 — pokemonkorea.co.kr"""

import os
import time
import requests

BASE_URL = "https://data1.pokemonkorea.co.kr/newdata/pokedex/mid/"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "pokemon")

# Gen 4: 387 ~ 493
GEN4_START = 387
GEN4_END = 493


def download_sprites():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    success = 0
    fail = 0

    for pid in range(GEN4_START, GEN4_END + 1):
        filename = f"{pid:04d}01.png"
        url = f"{BASE_URL}{filename}"
        out_path = os.path.join(OUTPUT_DIR, f"{pid}.png")

        if os.path.exists(out_path):
            print(f"[SKIP] {pid}.png already exists")
            success += 1
            continue

        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200 and len(resp.content) > 100:
                with open(out_path, "wb") as f:
                    f.write(resp.content)
                print(f"[OK] {pid}.png ({len(resp.content)} bytes)")
                success += 1
            else:
                print(f"[FAIL] {pid}.png — status={resp.status_code}, size={len(resp.content)}")
                fail += 1
        except Exception as e:
            print(f"[ERROR] {pid}.png — {e}")
            fail += 1

        time.sleep(0.3)  # rate limit

    print(f"\nDone: {success} success, {fail} fail (total {GEN4_END - GEN4_START + 1})")


if __name__ == "__main__":
    download_sprites()
