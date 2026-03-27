"""Crawl Gen 3 Pokemon data (252-386) from PokeAPI.
Outputs two files ready for bot integration:
  - gen3_pokemon_data.py  (ALL_POKEMON_GEN3 tuples)
  - gen3_base_stats.py    (POKEMON_BASE_STATS_GEN3 dict)

Excludes: Mega evolutions, Deoxys alternate forms (Attack/Defense/Speed).
"""

import json
import time
import urllib.request

API = "https://pokeapi.co/api/v2"

# Korean names: official Korean names for Gen 3 (#252-386)
# Source: pokemonkorea.co.kr / official Korean localization
KOREAN_NAMES = {
    252: "나무지기", 253: "나무돌이", 254: "나무킹",
    255: "아차모", 256: "영치코", 257: "번치코",
    258: "물짱이", 259: "늪짱이", 260: "대짱이",
    261: "포챠나", 262: "그라에나",
    263: "지그제구리", 264: "직구리",
    265: "개무소", 266: "실쿤", 267: "뷰티플라이",
    268: "카스쿤", 269: "독케일",
    270: "연꽃몬", 271: "로토스", 272: "루딕로",
    273: "도토링", 274: "잎새코", 275: "다탱구",
    276: "테일로", 277: "스왈로",
    278: "갈모매", 279: "패리퍼",
    280: "랄토스", 281: "킬리아", 282: "가디안",
    283: "비구술", 284: "비나방",
    285: "버섯꼬", 286: "버섯모",
    287: "게을로", 288: "발바로", 289: "게을킹",
    290: "토중몬", 291: "아이스크", 292: "껍질몬",
    293: "소곤룡", 294: "노공룡", 295: "폭음룡",
    296: "마크탕", 297: "하리뭉",
    298: "루리리",
    299: "코코파스",
    300: "에나비", 301: "델케티",
    302: "깜까미",
    303: "입치트",
    304: "가보리", 305: "갱도라", 306: "보스로라",
    307: "요가램", 308: "요가램",  # will fix below
    309: "썬더라이", 310: "썬더볼트",
    311: "플러시", 312: "마이농",
    313: "볼비트", 314: "네오비트",
    315: "로젤리아",
    316: "꼴깍몬", 317: "꿀꺽몬",
    318: "샤프니아", 319: "샤크니아",
    320: "고래왕자", 321: "고래왕",
    322: "둔타", 323: "폭타",
    324: "코터스",
    325: "스푸링", 326: "피그킹",
    327: "얼루기",
    328: "톱치", 329: "비브라바", 330: "플라이곤",
    331: "선인왕", 332: "밤선인",
    333: "파비코", 334: "파비코리",
    335: "쟝고",
    336: "세비퍼",
    337: "루나톤", 338: "솔록",
    339: "미꾸리", 340: "메꾸리",
    341: "가재군", 342: "가재장군",
    343: "오뚝군", 344: "점토도리",
    345: "릴링", 346: "릴리요",
    347: "아노딥스", 348: "아말도",
    349: "빈티나", 350: "밀로틱",
    351: "캐스퐁",
    352: "켈리몬",
    353: "어둠대신", 354: "다크펫",
    355: "해골몽", 356: "미라몽",
    357: "트로피우스",
    358: "치렁",
    359: "앱솔",
    360: "마자용",
    361: "눈꼬마", 362: "얼음귀신",
    363: "대굴레오", 364: "씨레오", 365: "투스카이",
    366: "진주몽", 367: "헌테일", 368: "분홍장이",
    369: "시라칸",
    370: "사랑동이",
    371: "아공이", 372: "쉘곤", 373: "보만다",
    374: "메탕", 375: "메탕구", 376: "메타그로스",
    377: "레지록", 378: "레지아이스", 379: "레지스틸",
    380: "라티아스", 381: "라티오스",
    382: "가이오가", 383: "그란돈", 384: "레쿠쟈",
    385: "지라치", 386: "테오키스",
}

# Fix 308
KOREAN_NAMES[308] = "차렘"

def fetch_json(url):
    """Fetch JSON from URL with retry."""
    for attempt in range(3):
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "PokemonBot-Crawler/1.0")
            resp = urllib.request.urlopen(req, timeout=15)
            return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"  Retry {attempt+1} for {url}: {e}")
            time.sleep(2)
    raise RuntimeError(f"Failed to fetch {url}")


def get_pokemon_species(pid):
    """Get species data (for Korean name verification & egg groups)."""
    data = fetch_json(f"{API}/pokemon-species/{pid}")
    ko_name = None
    for name_entry in data.get("names", []):
        if name_entry["language"]["name"] == "ko":
            ko_name = name_entry["name"]
            break
    return {
        "ko_name": ko_name,
        "is_legendary": data.get("is_legendary", False),
        "is_mythical": data.get("is_mythical", False),
    }


def get_pokemon_data(pid):
    """Get base stats and types from Pokemon endpoint."""
    data = fetch_json(f"{API}/pokemon/{pid}")
    stats = {}
    for s in data["stats"]:
        name = s["stat"]["name"]
        stats[name] = s["base_stat"]

    types = []
    for t in sorted(data["types"], key=lambda x: x["slot"]):
        types.append(t["type"]["name"])

    return {
        "name_en": data["name"].replace("-", " ").title(),
        "stats": stats,
        "types": types,
    }


def main():
    results = []
    base_stats = {}

    for pid in range(252, 387):
        name_ko = KOREAN_NAMES.get(pid, f"???_{pid}")
        print(f"Fetching #{pid} {name_ko}...", end=" ", flush=True)

        try:
            poke = get_pokemon_data(pid)
            species = get_pokemon_species(pid)
        except Exception as e:
            print(f"ERROR: {e}")
            continue

        # Use official Korean name from API if available, fallback to our dict
        if species["ko_name"]:
            name_ko = species["ko_name"]

        s = poke["stats"]
        hp = s.get("hp", 50)
        atk = s.get("attack", 50)
        def_ = s.get("defense", 50)
        spa = s.get("special-attack", 50)
        spdef = s.get("special-defense", 50)
        spd = s.get("speed", 50)

        types = poke["types"]
        name_en = poke["name_en"]

        # Fix capitalization for English names
        name_en = name_en.replace("Mr ", "Mr. ").replace("Ho Oh", "Ho-Oh")

        is_legend = species["is_legendary"]
        is_myth = species["is_mythical"]

        results.append({
            "id": pid,
            "name_ko": name_ko,
            "name_en": name_en,
            "types": types,
            "hp": hp, "atk": atk, "def": def_,
            "spa": spa, "spdef": spdef, "spd": spd,
            "bst": hp + atk + def_ + spa + spdef + spd,
            "is_legendary": is_legend,
            "is_mythical": is_myth,
        })

        base_stats[pid] = {
            "stats": (hp, atk, def_, spa, spdef, spd),
            "types": types,
            "name_en": name_en,
        }

        print(f"OK  {name_en} | {'/'.join(types)} | BST={hp+atk+def_+spa+spdef+spd}" +
              (" ★LEGEND" if is_legend else "") + (" ★MYTHICAL" if is_myth else ""))
        time.sleep(0.3)  # Rate limit

    # Save JSON
    with open("scripts/gen3_raw.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Fetched {len(results)} Pokemon")
    print(f"   Saved to scripts/gen3_raw.json")

    # Print summary
    legendaries = [r for r in results if r["is_legendary"]]
    mythicals = [r for r in results if r["is_mythical"]]
    print(f"   Legendaries: {len(legendaries)} — {', '.join(r['name_ko'] for r in legendaries)}")
    print(f"   Mythicals: {len(mythicals)} — {', '.join(r['name_ko'] for r in mythicals)}")


if __name__ == "__main__":
    main()
