"""Download Gen 3 Pokemon sprites (IDs 252-386) from PokeAPI GitHub."""

import os
import time
import urllib.request
import urllib.error

DEST_DIR = r"C:\Users\Administrator\Desktop\pokemon-bot\assets\pokemon"
START_ID = 252
END_ID = 386

# Primary: official artwork; fallback: default sprites
PRIMARY_URL = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/{id}.png"
FALLBACK_URL = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{id}.png"


def download_sprite(pokemon_id: int) -> bool:
    dest_path = os.path.join(DEST_DIR, f"{pokemon_id}.png")
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
        print(f"  [{pokemon_id}] Already exists, skipping.")
        return True

    for label, url_template in [("official-artwork", PRIMARY_URL), ("default", FALLBACK_URL)]:
        url = url_template.format(id=pokemon_id)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Pokemon-Bot-Sprite-Downloader"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                if len(data) < 100:
                    print(f"  [{pokemon_id}] {label}: suspiciously small ({len(data)} bytes), trying next...")
                    continue
                with open(dest_path, "wb") as f:
                    f.write(data)
                print(f"  [{pokemon_id}] OK from {label} ({len(data):,} bytes)")
                return True
        except urllib.error.HTTPError as e:
            print(f"  [{pokemon_id}] {label}: HTTP {e.code}")
        except Exception as e:
            print(f"  [{pokemon_id}] {label}: Error - {e}")

    print(f"  [{pokemon_id}] FAILED from all sources!")
    return False


def main():
    os.makedirs(DEST_DIR, exist_ok=True)
    total = END_ID - START_ID + 1
    success = 0
    failed = []

    print(f"Downloading Gen 3 sprites ({START_ID}-{END_ID}), {total} total.\n")

    for pid in range(START_ID, END_ID + 1):
        if download_sprite(pid):
            success += 1
        else:
            failed.append(pid)
        # Small delay to be polite to GitHub
        time.sleep(0.15)

    print(f"\n{'='*50}")
    print(f"Done! {success}/{total} downloaded successfully.")
    if failed:
        print(f"Failed IDs: {failed}")
    else:
        print("All sprites downloaded successfully!")


if __name__ == "__main__":
    main()
