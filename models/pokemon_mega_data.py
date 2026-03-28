"""
메가진화 포켓몬 데이터 정의.

본가 공식 스탯 기반 (6세대~).
키: "mega_{원본ID}" 또는 "mega_{원본ID}_x"/"mega_{원본ID}_y" (폼 구분)

base_stats: (hp, atk, def, spa, spdef, spd, [type1, type2_or_None])
  — pokemon_base_stats.py와 동일 포맷

battle_data: (primary_type, stat_type)
  — pokemon_battle_data.py와 동일 포맷

이미지: assets/pokemon/mega_{id}.png
"""

# ── 메가진화 기본 스탯 ───────────────────────────────────────
# 포맷: (hp, atk, def, spa, spdef, spd, [types])

MEGA_BASE_STATS = {
    # === Common (BST 480~590) ===
    "mega_15":    (65, 150, 40, 15, 80, 145, ["bug", "poison"]),          # 메가독침붕
    "mega_18":    (83, 80, 80, 135, 80, 121, ["normal", "flying"]),       # 메가피죤투
    "mega_302":   (50, 85, 125, 85, 115, 20, ["dark", "ghost"]),          # 메가깜까미

    # === Rare (BST 555~610) ===
    "mega_65":    (55, 50, 65, 175, 105, 150, ["psychic"]),               # 메가후딘
    "mega_80":    (95, 75, 180, 130, 80, 30, ["water", "psychic"]),       # 메가야도란
    "mega_94":    (60, 65, 80, 170, 95, 130, ["ghost", "poison"]),        # 메가팬텀
    "mega_115":   (105, 125, 100, 60, 100, 100, ["normal"]),              # 메가캥카
    "mega_127":   (65, 155, 120, 65, 90, 105, ["bug", "flying"]),         # 메가쁘사이저
    "mega_208":   (75, 125, 230, 55, 95, 30, ["steel", "ground"]),        # 메가강철톤
    "mega_308":   (60, 100, 85, 80, 85, 100, ["fighting", "psychic"]),    # 메가요가램
    "mega_310":   (70, 75, 80, 135, 80, 135, ["electric"]),               # 메가라이볼트
    "mega_319":   (70, 140, 70, 110, 65, 105, ["water", "dark"]),         # 메가샤크니아
    "mega_323":   (70, 120, 100, 145, 105, 20, ["fire", "ground"]),       # 메가폭타
    "mega_334":   (75, 110, 110, 110, 105, 80, ["dragon", "fairy"]),      # 메가파비코리
    "mega_354":   (64, 165, 75, 93, 83, 75, ["ghost"]),                   # 메가다크펫
    "mega_362":   (80, 120, 80, 120, 80, 100, ["ice"]),                   # 메가얼음귀신
    "mega_428":   (65, 136, 94, 54, 96, 135, ["normal", "fighting"]),     # 메가이어롭
    "mega_460":   (90, 132, 105, 132, 105, 30, ["grass", "ice"]),         # 메가눈설왕

    # === Epic (BST 600~700) ===
    "mega_3":     (80, 100, 123, 122, 120, 80, ["grass", "poison"]),      # 메가이상해꽃
    "mega_6_x":   (78, 130, 111, 130, 85, 100, ["fire", "dragon"]),       # 메가리자몽X
    "mega_6_y":   (78, 104, 78, 159, 115, 100, ["fire", "flying"]),       # 메가리자몽Y
    "mega_9":     (79, 103, 120, 135, 115, 78, ["water"]),                # 메가거북왕
    "mega_130":   (95, 155, 109, 70, 130, 81, ["water", "dark"]),         # 메가갸라도스
    "mega_142":   (80, 135, 85, 70, 95, 150, ["rock", "flying"]),         # 메가프테라
    "mega_181":   (90, 95, 105, 165, 110, 45, ["electric", "dragon"]),    # 메가전룡
    "mega_212":   (70, 150, 140, 65, 100, 75, ["bug", "steel"]),          # 메가핫삼
    "mega_214":   (80, 185, 115, 40, 105, 75, ["bug", "fighting"]),       # 메가헤라크로스
    "mega_229":   (75, 90, 90, 140, 90, 115, ["dark", "fire"]),           # 메가헬가
    "mega_248":   (100, 164, 150, 95, 120, 71, ["rock", "dark"]),         # 메가마기라스
    "mega_254":   (70, 110, 75, 145, 85, 145, ["grass", "dragon"]),       # 메가나무킹
    "mega_257":   (80, 160, 80, 130, 80, 100, ["fire", "fighting"]),      # 메가번치코
    "mega_260":   (100, 150, 110, 95, 110, 70, ["water", "ground"]),      # 메가라그라지
    "mega_282":   (68, 85, 65, 165, 135, 100, ["psychic", "fairy"]),      # 메가가디안
    "mega_303":   (50, 105, 125, 55, 95, 50, ["steel", "fairy"]),         # 메가입치트
    "mega_306":   (70, 140, 230, 60, 80, 50, ["steel"]),                  # 메가대짱이
    "mega_359":   (65, 150, 60, 115, 60, 115, ["dark"]),                  # 메가앱솔
    "mega_373":   (95, 145, 130, 120, 90, 120, ["dragon", "flying"]),     # 메가보만다
    "mega_376":   (80, 145, 150, 105, 110, 110, ["steel", "psychic"]),    # 메가메타그로스
    "mega_445":   (108, 170, 115, 120, 95, 92, ["dragon", "ground"]),     # 메가한카리아스
    "mega_448":   (70, 145, 88, 140, 70, 112, ["fighting", "steel"]),     # 메가루카리오
    "mega_475":   (68, 165, 95, 65, 115, 110, ["psychic", "fighting"]),   # 메가엘레이드

    # === Legendary ===
    "mega_380":   (80, 100, 120, 140, 150, 110, ["dragon", "psychic"]),   # 메가라티아스
    "mega_381":   (80, 130, 100, 160, 120, 110, ["dragon", "psychic"]),   # 메가라티오스

    # === Ultra Legendary ===
    "mega_150_x": (106, 190, 100, 154, 100, 130, ["psychic", "fighting"]),  # 메가뮤츠X
    "mega_150_y": (106, 150, 70, 194, 120, 140, ["psychic"]),               # 메가뮤츠Y
    "mega_384":   (105, 180, 100, 180, 100, 115, ["dragon", "flying"]),     # 메가레쿠쟈
}


# ── 메가진화 배틀 데이터 ─────────────────────────────────────
# 포맷: (primary_type, stat_type)

MEGA_BATTLE_DATA = {
    # Common
    "mega_15":    ("bug", "offensive"),         # 메가독침붕 — ATK+SPD 극단적
    "mega_18":    ("normal", "offensive"),       # 메가피죤투 — SPA 특수 어태커
    "mega_302":   ("dark", "defensive"),         # 메가깜까미 — DEF+SPDEF 탱커

    # Rare
    "mega_65":    ("psychic", "speedy"),         # 메가후딘 — SPA+SPD
    "mega_80":    ("water", "defensive"),        # 메가야도란 — DEF 극단적
    "mega_94":    ("ghost", "offensive"),        # 메가팬텀 — SPA 극단적
    "mega_115":   ("normal", "balanced"),        # 메가캥카 — 균형
    "mega_127":   ("bug", "offensive"),          # 메가쁘사이저 — ATK+DEF
    "mega_208":   ("steel", "defensive"),        # 메가강철톤 — DEF 극단적
    "mega_308":   ("fighting", "balanced"),      # 메가요가램 — ATK+SPD 균형
    "mega_310":   ("electric", "speedy"),        # 메가라이볼트 — SPA+SPD
    "mega_319":   ("water", "offensive"),        # 메가샤크니아 — ATK 물리 어태커
    "mega_323":   ("fire", "offensive"),         # 메가폭타 — SPA 특수 어태커
    "mega_334":   ("dragon", "balanced"),        # 메가파비코리 — 균형
    "mega_354":   ("ghost", "offensive"),        # 메가다크펫 — ATK 극단적
    "mega_362":   ("ice", "balanced"),           # 메가얼음귀신 — ATK+SPA 균형
    "mega_428":   ("normal", "speedy"),          # 메가이어롭 — ATK+SPD
    "mega_460":   ("grass", "offensive"),        # 메가눈설왕 — ATK+SPA

    # Epic
    "mega_3":     ("grass", "balanced"),         # 메가이상해꽃 — 균형
    "mega_6_x":   ("fire", "offensive"),         # 메가리자몽X — ATK+SPA
    "mega_6_y":   ("fire", "offensive"),         # 메가리자몽Y — SPA 특수 어태커
    "mega_9":     ("water", "defensive"),        # 메가거북왕 — SPA+DEF
    "mega_130":   ("water", "offensive"),        # 메가갸라도스 — ATK 물리 어태커
    "mega_142":   ("rock", "speedy"),            # 메가프테라 — ATK+SPD
    "mega_181":   ("electric", "offensive"),     # 메가전룡 — SPA 특수 어태커
    "mega_212":   ("bug", "offensive"),          # 메가핫삼 — ATK+DEF
    "mega_214":   ("bug", "offensive"),          # 메가헤라크로스 — ATK 극단적
    "mega_229":   ("dark", "offensive"),         # 메가헬가 — SPA+SPD
    "mega_248":   ("rock", "offensive"),         # 메가마기라스 — ATK+DEF 탱커딜러
    "mega_254":   ("grass", "speedy"),           # 메가나무킹 — SPA+SPD
    "mega_257":   ("fire", "offensive"),         # 메가번치코 — ATK 극단적
    "mega_260":   ("water", "offensive"),        # 메가라그라지 — ATK 물리 어태커
    "mega_282":   ("psychic", "offensive"),      # 메가가디안 — SPA 특수 어태커
    "mega_303":   ("steel", "defensive"),        # 메가입치트 — 밸런스
    "mega_306":   ("steel", "defensive"),        # 메가대짱이 — DEF 극단적
    "mega_359":   ("dark", "offensive"),         # 메가앱솔 — ATK+SPA
    "mega_373":   ("dragon", "offensive"),       # 메가보만다 — ATK+DEF
    "mega_376":   ("steel", "defensive"),        # 메가메타그로스 — 균형 탱커
    "mega_445":   ("dragon", "offensive"),       # 메가한카리아스 — ATK 극단적
    "mega_448":   ("fighting", "offensive"),     # 메가루카리오 — ATK+SPA
    "mega_475":   ("psychic", "offensive"),      # 메가엘레이드 — ATK 극단적

    # Legendary
    "mega_380":   ("dragon", "defensive"),       # 메가라티아스 — SPDEF 특수 탱커
    "mega_381":   ("dragon", "offensive"),       # 메가라티오스 — SPA 특수 어태커

    # Ultra Legendary
    "mega_150_x": ("psychic", "offensive"),      # 메가뮤츠X — ATK 극단적
    "mega_150_y": ("psychic", "offensive"),      # 메가뮤츠Y — SPA 극단적
    "mega_384":   ("dragon", "offensive"),       # 메가레쿠쟈 — ATK+SPA
}


# ── 메가진화 포켓몬 정보 ─────────────────────────────────────
# 키: mega_key, 값: (원본_pokemon_id, name_ko, name_en, rarity)
# rarity: 제련권 등급 (MEGA_STONE_RATES 확률로 뽑히는 등급)

MEGA_POKEMON_INFO = {
    # Common (3종)
    "mega_15":    (15,  "메가독침붕",     "Mega Beedrill",     "common"),
    "mega_18":    (18,  "메가피죤투",     "Mega Pidgeot",      "common"),
    "mega_302":   (302, "메가깜까미",     "Mega Sableye",      "common"),

    # Rare (16종)
    "mega_65":    (65,  "메가후딘",       "Mega Alakazam",     "rare"),
    "mega_80":    (80,  "메가야도란",     "Mega Slowbro",      "rare"),
    "mega_94":    (94,  "메가팬텀",       "Mega Gengar",       "rare"),
    "mega_115":   (115, "메가캥카",       "Mega Kangaskhan",   "rare"),
    "mega_127":   (127, "메가쁘사이저",   "Mega Pinsir",       "rare"),
    "mega_208":   (208, "메가강철톤",     "Mega Steelix",      "rare"),
    "mega_308":   (308, "메가요가램",     "Mega Medicham",     "rare"),
    "mega_310":   (310, "메가라이볼트",   "Mega Manectric",    "rare"),
    "mega_319":   (319, "메가샤크니아",   "Mega Sharpedo",     "rare"),
    "mega_323":   (323, "메가폭타",       "Mega Camerupt",     "rare"),
    "mega_334":   (334, "메가파비코리",   "Mega Altaria",      "rare"),
    "mega_354":   (354, "메가다크펫",     "Mega Banette",      "rare"),
    "mega_362":   (362, "메가얼음귀신",   "Mega Glalie",       "rare"),
    "mega_428":   (428, "메가이어롭",     "Mega Lopunny",      "rare"),
    "mega_460":   (460, "메가눈설왕",     "Mega Abomasnow",    "rare"),

    # Epic (22종)
    "mega_3":     (3,   "메가이상해꽃",   "Mega Venusaur",     "epic"),
    "mega_6_x":   (6,   "메가리자몽X",    "Mega Charizard X",  "epic"),
    "mega_6_y":   (6,   "메가리자몽Y",    "Mega Charizard Y",  "epic"),
    "mega_9":     (9,   "메가거북왕",     "Mega Blastoise",    "epic"),
    "mega_130":   (130, "메가갸라도스",   "Mega Gyarados",     "epic"),
    "mega_142":   (142, "메가프테라",     "Mega Aerodactyl",   "epic"),
    "mega_181":   (181, "메가전룡",       "Mega Ampharos",     "epic"),
    "mega_212":   (212, "메가핫삼",       "Mega Scizor",       "epic"),
    "mega_214":   (214, "메가헤라크로스", "Mega Heracross",    "epic"),
    "mega_229":   (229, "메가헬가",       "Mega Houndoom",     "epic"),
    "mega_248":   (248, "메가마기라스",   "Mega Tyranitar",    "epic"),
    "mega_254":   (254, "메가나무킹",     "Mega Sceptile",     "epic"),
    "mega_257":   (257, "메가번치코",     "Mega Blaziken",     "epic"),
    "mega_260":   (260, "메가라그라지",   "Mega Swampert",     "epic"),
    "mega_282":   (282, "메가가디안",     "Mega Gardevoir",    "epic"),
    "mega_303":   (303, "메가입치트",     "Mega Mawile",       "epic"),
    "mega_306":   (306, "메가대짱이",     "Mega Aggron",       "epic"),
    "mega_359":   (359, "메가앱솔",       "Mega Absol",        "epic"),
    "mega_373":   (373, "메가보만다",     "Mega Salamence",    "epic"),
    "mega_376":   (376, "메가메타그로스", "Mega Metagross",    "epic"),
    "mega_445":   (445, "메가한카리아스", "Mega Garchomp",     "epic"),
    "mega_448":   (448, "메가루카리오",   "Mega Lucario",      "epic"),
    "mega_475":   (475, "메가엘레이드",   "Mega Gallade",      "epic"),

    # Legendary (2종)
    "mega_380":   (380, "메가라티아스",   "Mega Latias",       "legendary"),
    "mega_381":   (381, "메가라티오스",   "Mega Latios",       "legendary"),

    # Ultra Legendary (3종)
    "mega_150_x": (150, "메가뮤츠X",      "Mega Mewtwo X",     "ultra_legendary"),
    "mega_150_y": (150, "메가뮤츠Y",      "Mega Mewtwo Y",     "ultra_legendary"),
    "mega_384":   (384, "메가레쿠쟈",     "Mega Rayquaza",     "ultra_legendary"),
}


# ── 메가폼 공통 규칙 ─────────────────────────────────────────
# - 친밀도: 7 고정 (이로치와 동일, config.MEGA_MAX_FRIENDSHIP)
# - 코스트: 원본 등급(rarity) 기준 RANKED_COST 그대로 적용
# - 이미지: assets/pokemon/{mega_key}.png (390x390 RGBA)


# ── 유틸 함수 ────────────────────────────────────────────────

def get_mega_image_path(mega_key: str) -> str:
    """메가폼 이미지 경로 반환."""
    return f"assets/pokemon/{mega_key}.png"


def get_mega_keys_by_rarity(rarity: str) -> list[str]:
    """특정 등급의 메가폼 키 목록 반환."""
    return [k for k, v in MEGA_POKEMON_INFO.items() if v[3] == rarity]


def get_mega_key_by_original_id(pokemon_id: int) -> list[str]:
    """원본 포켓몬 ID로 메가폼 키 목록 반환 (복수 가능: 리자몽X/Y 등)."""
    return [k for k, v in MEGA_POKEMON_INFO.items() if v[0] == pokemon_id]
