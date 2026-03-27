"""Gen 3 card examples - generate sample spawn & pokedex cards."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.card_generator import generate_card

EXAMPLES = [
    # (pokemon_id, name_ko, rarity, emoji, is_shiny)
    (254, "나무킹", "rare", "", False),
    (282, "가디안", "epic", "", False),
    (289, "게을킹", "epic", "", False),
    (350, "밀로틱", "rare", "", False),
    (359, "앱솔", "rare", "", True),   # shiny example
    (376, "메타그로스", "epic", "", False),
    (384, "레쿠쟈", "ultra_legendary", "", False),
    (386, "테오키스", "legendary", "", False),
]

out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "examples")
os.makedirs(out_dir, exist_ok=True)

for pid, name, rarity, emoji, shiny in EXAMPLES:
    buf = generate_card(pid, name, rarity, emoji, shiny)
    tag = "shiny_" if shiny else ""
    fname = f"{tag}{pid}_{name}.jpg"
    path = os.path.join(out_dir, fname)
    with open(path, "wb") as f:
        f.write(buf.read())
    print(f"OK: {fname}")

print(f"\nDone! {len(EXAMPLES)} cards in {out_dir}")
