"""타로 카드 데이터 빌드 — GitHub 원본 + 포켓몬 매핑 + 한국어 구조."""

import json

# ── 원본 데이터 로드 ──
with open("tarot_raw.json", encoding="utf-8") as f:
    raw = json.load(f)
raw_cards = raw.get("cards", raw) if isinstance(raw, dict) else raw

# ── 메이저 아르카나 포켓몬 매핑 (1세대) ──
MAJOR_POKEMON = {
    0:  {"name_ko": "바보", "pokemon": "고라파덕", "pokemon_id": 54},
    1:  {"name_ko": "마법사", "pokemon": "후딘", "pokemon_id": 65},
    2:  {"name_ko": "여사제", "pokemon": "뮤", "pokemon_id": 151},
    3:  {"name_ko": "여제", "pokemon": "푸린", "pokemon_id": 39},
    4:  {"name_ko": "황제", "pokemon": "리자몽", "pokemon_id": 6},
    5:  {"name_ko": "교황", "pokemon": "라프라스", "pokemon_id": 131},
    6:  {"name_ko": "연인", "pokemon": "니드킹&니드퀸", "pokemon_id": 34},
    7:  {"name_ko": "전차", "pokemon": "윈디", "pokemon_id": 59},
    8:  {"name_ko": "힘", "pokemon": "괴력몬", "pokemon_id": 68},
    9:  {"name_ko": "은둔자", "pokemon": "문박사", "pokemon_id": 0},
    10: {"name_ko": "운명의 수레바퀴", "pokemon": "럭키", "pokemon_id": 113},
    11: {"name_ko": "정의", "pokemon": "갸라도스", "pokemon_id": 130},
    12: {"name_ko": "매달린 남자", "pokemon": "야도란", "pokemon_id": 80},
    13: {"name_ko": "죽음", "pokemon": "팬텀", "pokemon_id": 94},
    14: {"name_ko": "절제", "pokemon": "쥬곤", "pokemon_id": 87},
    15: {"name_ko": "악마", "pokemon": "나인테일", "pokemon_id": 38},
    16: {"name_ko": "탑", "pokemon": "뮤츠", "pokemon_id": 150},
    17: {"name_ko": "별", "pokemon": "스타미", "pokemon_id": 121},
    18: {"name_ko": "달", "pokemon": "피죤투", "pokemon_id": 18},
    19: {"name_ko": "태양", "pokemon": "피카츄", "pokemon_id": 25},
    20: {"name_ko": "심판", "pokemon": "프리져", "pokemon_id": 144},
    21: {"name_ko": "세계", "pokemon": "뮤", "pokemon_id": 151},
}

# ── 마이너 아르카나 포켓몬 매핑 (수트별 1세대) ──
# Wands(지팡이/불) = 불/격투 타입
WANDS_POKEMON = [
    (4, "파이리"), (5, "리자드"), (6, "리자몽"), (37, "식스테일"),
    (38, "나인테일"), (58, "가디"), (59, "윈디"), (77, "포니타"),
    (78, "날쌩마"), (126, "마그마"), (136, "부스터"), (146, "파이어"),
    (56, "망키"), (57, "성원숭"),
]

# Cups(컵/물) = 물 타입
CUPS_POKEMON = [
    (7, "꼬부기"), (8, "어니부기"), (9, "거북왕"), (54, "고라파덕"),
    (55, "골덱"), (60, "발챙이"), (61, "슈륙챙이"), (62, "강챙이"),
    (116, "쏘드라"), (117, "시드라"), (118, "콘치"), (119, "왕콘치"),
    (120, "별가사리"), (121, "스타미"),
]

# Swords(검/바람) = 비행/에스퍼 타입
SWORDS_POKEMON = [
    (16, "피죤"), (17, "피죤투"), (18, "피죤투"), (63, "케이시"),
    (64, "윤겔라"), (65, "후딘"), (83, "파오리"), (84, "두두"),
    (85, "두트리오"), (123, "스라크"), (142, "프테라"), (144, "프리져"),
    (21, "깨비참"), (22, "깨비드릴조"),
]

# Pentacles(동전/땅) = 바위/땅/노말 타입
PENTACLES_POKEMON = [
    (25, "피카츄"), (26, "라이츄"), (27, "모래두지"), (28, "고지"),
    (50, "디그다"), (51, "닥트리오"), (74, "꼬마돌"), (75, "데구리"),
    (76, "딱구리"), (95, "롱스톤"), (104, "탕구리"), (105, "텅구리"),
    (111, "뿔카노"), (112, "코뿌리"),
]

SUIT_MAP = {
    "wands": WANDS_POKEMON,
    "cups": CUPS_POKEMON,
    "swords": SWORDS_POKEMON,
    "pentacles": PENTACLES_POKEMON,
}

SUIT_KO = {
    "wands": "지팡이",
    "cups": "컵",
    "swords": "검",
    "pentacles": "동전",
}

SUIT_ELEMENT = {
    "wands": "불",
    "cups": "물",
    "swords": "바람",
    "pentacles": "땅",
}

VALUE_KO = {
    "1": "에이스", "2": "2", "3": "3", "4": "4", "5": "5",
    "6": "6", "7": "7", "8": "8", "9": "9", "10": "10",
    "page": "시종", "knight": "기사", "queen": "여왕", "king": "왕",
}

# ── 빌드 ──
tarot_cards = []

for card in raw_cards:
    entry = {
        "name": card["name"],
        "name_short": card["name_short"],
        "type": card["type"],
        "value": card.get("value", ""),
        "value_int": card.get("value_int", 0),
        "meaning_up_en": card.get("meaning_up", ""),
        "meaning_rev_en": card.get("meaning_rev", ""),
        "desc_en": card.get("desc", ""),
    }

    if card["type"] == "major":
        # The Fool은 value_int가 0이 아닐 수 있으므로 name으로 매칭
        idx = card.get("value_int", 0)
        if card["name"] == "The Fool":
            idx = 0
        pm = MAJOR_POKEMON.get(idx, {})
        entry["name_ko"] = pm.get("name_ko", card["name"])
        entry["pokemon"] = pm.get("pokemon", "")
        entry["pokemon_id"] = pm.get("pokemon_id", 0)
        entry["suit"] = None
        entry["suit_ko"] = None
        entry["element"] = None
    else:
        suit = card.get("suit", "")
        suit_pokemon = SUIT_MAP.get(suit, [])
        val = card.get("value", "1").lower()
        val_ko = VALUE_KO.get(val, val)

        # 수트 내 순서로 포켓몬 배정 (Ace=0, 2=1, ... King=13)
        order_map = {"1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6,
                     "8": 7, "9": 8, "10": 9, "page": 10, "knight": 11, "queen": 12, "king": 13}
        idx = order_map.get(val, 0)
        if idx < len(suit_pokemon):
            pid, pname = suit_pokemon[idx]
        else:
            pid, pname = 0, ""

        entry["name_ko"] = f"{SUIT_KO.get(suit, suit)}의 {val_ko}"
        entry["pokemon"] = pname
        entry["pokemon_id"] = pid
        entry["suit"] = suit
        entry["suit_ko"] = SUIT_KO.get(suit, suit)
        entry["element"] = SUIT_ELEMENT.get(suit, "")

    # 주제별 해석은 빈 구조로 (LLM으로 채울 예정)
    entry["meanings"] = {
        "연애": {"up": "", "rev": ""},
        "직장": {"up": "", "rev": ""},
        "재물": {"up": "", "rev": ""},
        "투자": {"up": "", "rev": ""},
        "인간관계": {"up": "", "rev": ""},
        "종합": {"up": "", "rev": ""},
    }

    tarot_cards.append(entry)

# 저장
output_path = "data/tarot_cards.json"
import os
os.makedirs("data", exist_ok=True)
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(tarot_cards, f, ensure_ascii=False, indent=2)

print(f"Built {len(tarot_cards)} cards → {output_path}")
print(f"  Major: {sum(1 for c in tarot_cards if c['type'] == 'major')}")
print(f"  Minor: {sum(1 for c in tarot_cards if c['type'] != 'major')}")
print(f"\nSample major:")
sample_major = next(c for c in tarot_cards if c["type"] == "major")
print(json.dumps(sample_major, ensure_ascii=False, indent=2)[:500])
print(f"\nSample minor:")
sample_minor = next(c for c in tarot_cards if c["type"] != "major")
print(json.dumps(sample_minor, ensure_ascii=False, indent=2)[:500])
