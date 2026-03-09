"""Unique skill data for all 386 Pokemon.

=== FORMAT ===
Single-type Pokemon:
    pokemon_id: ("skill_name_ko", power)

Dual-type Pokemon:
    pokemon_id: [("skill1_name_ko", power), ("skill2_name_ko", power)]
    - skill1 = type1 (primary type) 대표기술
    - skill2 = type2 (secondary type) 대표기술

=== POWER FORMULA (rarity + BST) ===
  - common BST<350: 1.2
  - common BST≥350: 1.3
  - rare BST<450: 1.3
  - rare BST≥450: 1.4
  - epic BST<500: 1.4
  - epic BST≥500: 1.5
  - legendary BST<680: 1.8
  - ultra_legendary BST≥680: 2.0

스킬은 배틀 중 일정 확률로 발동되며, 발동 시 데미지에 power 배율이 곱해진다.
듀얼타입 포켓몬은 두 스킬 중 랜덤으로 하나가 발동된다.
미등록 포켓몬은 fallback으로 ("몸통박치기", 1.2)를 사용한다.
"""

POKEMON_SKILLS = {
    # ============================================================
    # Gen 1 (1-151)
    # ============================================================

    # --- Bulbasaur line (grass/poison) ---
    1:  [("덩굴채찍", 1.2), ("독가루", 1.2)],           # 이상해씨 (common)
    2:  [("잎날가르기", 1.3), ("독찌르기", 1.3)],       # 이상해풀 (common)
    3:  [("솔라빔", 1.5), ("오물폭탄", 1.5)],           # 이상해꽃 (epic 최종)

    # --- Charmander line ---
    4:  ("불꽃세례", 1.2),       # 파이리 (common) fire
    5:  ("화염방사", 1.3),       # 리자드 (common) fire
    6:  [("블래스트번", 1.5), ("에어슬래시", 1.5)],     # 리자몽 (epic 최종) fire/flying

    # --- Squirtle line ---
    7:  ("물대포", 1.2),         # 꼬부기 (common) water
    8:  ("물의파동", 1.3),       # 어니부기 (common) water
    9:  ("하이드로펌프", 1.5),   # 거북왕 (epic 최종) water

    # --- Caterpie line ---
    10: ("실뿜기", 1.2),         # 캐터피 (common 1단) bug
    11: ("경화", 1.2),           # 단데기 (common 2단) bug
    12: [("은빛바람", 1.3), ("에어슬래시", 1.3)],       # 버터플 (common 최종) bug/flying

    # --- Weedle line (bug/poison) ---
    13: [("실뿜기", 1.2), ("독침", 1.2)],               # 뿔충이 (common 1단)
    14: [("경화", 1.2), ("독가루", 1.2)],               # 딱충이 (common 2단)
    15: [("시저크로스", 1.3), ("독찌르기", 1.3)],       # 독침붕 (common 최종)

    # --- Pidgey line (normal/flying) ---
    16: [("전광석화", 1.2), ("공중날기", 1.2)],         # 구구 (common 1단)
    17: [("전광석화", 1.2), ("에어슬래시", 1.2)],       # 피죤 (common 2단)
    18: [("하이퍼빔", 1.4), ("폭풍", 1.4)],             # 피죤투 (rare)

    # --- Rattata line ---
    19: ("전광석화", 1.2),       # 꼬렛 (common 1단) normal
    20: ("필살앞니", 1.3),       # 레트라 (common 최종) normal

    # --- Spearow line (normal/flying) ---
    21: [("전광석화", 1.2), ("공중날기", 1.2)],         # 깨비참 (common 1단)
    22: [("돌진", 1.3), ("드릴부리", 1.3)],             # 깨비드릴조 (common 최종)

    # --- Ekans line ---
    23: ("독침", 1.2),           # 아보 (common 1단) poison
    24: ("독엄니", 1.3),         # 아보크 (common 최종) poison

    # --- Pikachu line ---
    25: ("백만볼트", 1.2),       # 피카츄 (common) electric
    26: ("번개", 1.4),           # 라이츄 (rare 최종) electric

    # --- Sandshrew line ---
    27: ("모래뿌리기", 1.2),     # 모래두지 (common 1단) ground
    28: ("지진", 1.4),           # 고지 (rare) ground

    # --- Nidoran♀ line ---
    29: ("독침", 1.2),           # 니드런♀ (common 1단) poison
    30: ("독찌르기", 1.3),       # 니드리나 (common) poison
    31: [("오물폭탄", 1.5), ("대지의힘", 1.5)],         # 니드퀸 (epic) poison/ground

    # --- Nidoran♂ line ---
    32: ("뿔찌르기", 1.2),       # 니드런♂ (common 1단) poison
    33: ("독찌르기", 1.3),       # 니드리노 (common) poison
    34: [("오물폭탄", 1.5), ("대지의힘", 1.5)],         # 니드킹 (epic) poison/ground

    # --- Clefairy line ---
    35: ("손가락흔들기", 1.2),   # 삐삐 (common) fairy
    36: ("문포스", 1.4),         # 픽시 (rare 최종) fairy

    # --- Vulpix line ---
    37: ("불꽃세례", 1.2),       # 식스테일 (common) fire
    38: ("화염방사", 1.5),       # 나인테일 (epic) fire

    # --- Jigglypuff line (normal/fairy) ---
    39: [("하이퍼보이스", 1.2), ("달콤한키스", 1.2)],   # 푸린 (common)
    40: [("하이퍼보이스", 1.3), ("문포스", 1.3)],       # 푸크린 (common 최종)

    # --- Zubat line (poison/flying) ---
    41: [("독엄니", 1.2), ("공중날기", 1.2)],           # 주뱃 (common 1단)
    42: [("독엄니", 1.4), ("에어슬래시", 1.4)],         # 골뱃 (rare)

    # --- Oddish line (grass/poison) ---
    43: [("흡수", 1.2), ("독가루", 1.2)],               # 뚜벅쵸 (common 1단)
    44: [("메가드레인", 1.3), ("독가루", 1.3)],         # 냄새꼬 (common)
    45: [("꽃잎댄스", 1.4), ("오물폭탄", 1.4)],         # 라플레시아 (rare 최종)

    # --- Paras line (bug/grass) ---
    46: [("벌레의저항", 1.2), ("흡수", 1.2)],           # 파라스 (common 1단)
    47: [("시저크로스", 1.3), ("포자", 1.3)],           # 파라섹트 (common 최종)

    # --- Venonat line (bug/poison) ---
    48: [("벌레의저항", 1.2), ("독가루", 1.2)],         # 콘팡 (common 1단)
    49: [("시그널빔", 1.4), ("사이코키네시스", 1.4)],   # 도나리 (rare) bug/poison

    # --- Diglett line ---
    50: ("구멍파기", 1.2),       # 디그다 (common 1단) ground
    51: ("지진", 1.3),           # 닥트리오 (common 최종) ground

    # --- Meowth line ---
    52: ("고양이돈받기", 1.2),   # 나옹 (common 1단) normal
    53: ("베어가르기", 1.3),     # 페르시온 (common 최종) normal

    # --- Psyduck line ---
    54: ("물대포", 1.2),         # 고라파덕 (common 1단) water
    55: ("하이드로펌프", 1.5),   # 골덕 (epic) water

    # --- Mankey line ---
    56: ("태권당수", 1.2),       # 망키 (common 1단) fighting
    57: ("크로스촙", 1.4),       # 성원숭 (rare) fighting

    # --- Growlithe line ---
    58: ("불꽃세례", 1.3),       # 가디 (rare) fire
    59: ("신속", 1.5),           # 윈디 (epic) fire

    # --- Poliwag line ---
    60: ("물대포", 1.2),         # 발챙이 (common 1단) water
    61: ("거품광선", 1.3),       # 슈륙챙이 (common) water
    62: [("하이드로펌프", 1.5), ("인파이트", 1.5)],     # 강챙이 (epic) water/fighting

    # --- Abra line ---
    63: ("순간이동", 1.2),       # 캐이시 (common) psychic
    64: ("사이코키네시스", 1.3), # 윤겔라 (rare 2단) psychic
    65: ("사이코키네시스", 1.5), # 후딘 (epic 최종) psychic

    # --- Machop line ---
    66: ("태권당수", 1.2),       # 알통몬 (common 1단) fighting
    67: ("지옥굴리기", 1.3),     # 근육몬 (common) fighting
    68: ("크로스촙", 1.5),       # 괴력몬 (epic) fighting

    # --- Bellsprout line (grass/poison) ---
    69: [("덩굴채찍", 1.2), ("독가루", 1.2)],           # 모다피 (common 1단)
    70: [("잎날가르기", 1.3), ("독엄니", 1.3)],         # 우츠동 (common)
    71: [("리프블레이드", 1.4), ("오물폭탄", 1.4)],     # 우츠보트 (rare 최종)

    # --- Tentacool line (water/poison) ---
    72: [("거품광선", 1.2), ("독침", 1.2)],             # 왕눈해 (common 1단)
    73: [("하이드로펌프", 1.5), ("헤도로웨이브", 1.5)], # 독파리 (epic)

    # --- Geodude line (rock/ground) ---
    74: [("구르기", 1.2), ("진흙뿌리기", 1.2)],         # 꼬마돌 (common 1단)
    75: [("스톤에지", 1.3), ("지진", 1.3)],             # 데구리 (common)
    76: [("스톤에지", 1.4), ("지진", 1.4)],             # 딱구리 (rare 최종)

    # --- Ponyta line ---
    77: ("불꽃세례", 1.3),       # 포니타 (rare) fire
    78: ("화염방사", 1.5),       # 날쌩마 (epic) fire

    # --- Slowpoke line (water/psychic) ---
    79: [("물대포", 1.2), ("사념의머리", 1.2)],         # 야돈 (common)
    80: [("파도타기", 1.4), ("사이코키네시스", 1.4)],   # 야도란 (rare 최종)

    # --- Magnemite line (electric/steel) ---
    81: [("전기쇼크", 1.2), ("메탈클로", 1.2)],         # 코일 (common 1단)
    82: [("10만볼트", 1.4), ("라스터캐논", 1.4)],       # 레어코일 (rare)

    # --- Farfetch'd (normal/flying) ---
    83: [("베어가르기", 1.3), ("에어슬래시", 1.3)],     # 파오리 (rare)

    # --- Doduo line (normal/flying) ---
    84: [("전광석화", 1.2), ("공중날기", 1.2)],         # 두두 (common 1단)
    85: [("삼중공격", 1.4), ("드릴부리", 1.4)],         # 두트리오 (rare)

    # --- Seel line ---
    86: ("오로라빔", 1.2),       # 쥬쥬 (common 1단) water
    87: [("파도타기", 1.4), ("냉동빔", 1.4)],           # 쥬레곤 (rare) water/ice

    # --- Grimer line ---
    88: ("오물공격", 1.2),       # 질퍽이 (common 1단) poison
    89: ("오물폭탄", 1.5),       # 질뻐기 (epic) poison

    # --- Shellder line ---
    90: ("껍질가르기", 1.2),     # 셀러 (common 1단) water
    91: [("하이드로펌프", 1.5), ("냉동빔", 1.5)],       # 파르셀 (epic) water/ice

    # --- Gastly line (ghost/poison) ---
    92: [("핥기", 1.2), ("독가루", 1.2)],               # 고오스 (common)
    93: [("섀도볼", 1.3), ("오물폭탄", 1.3)],           # 고우스트 (rare 2단)
    94: [("섀도볼", 1.5), ("오물폭탄", 1.5)],           # 팬텀 (epic 최종)

    # --- Onix (rock/ground) ---
    95: [("바위떨구기", 1.3), ("지진", 1.3)],           # 롱스톤 (rare)

    # --- Drowzee line ---
    96: ("최면술", 1.2),         # 슬리프 (common 1단) psychic
    97: ("사이코키네시스", 1.4), # 슬리퍼 (rare) psychic

    # --- Krabby line ---
    98: ("거품광선", 1.2),       # 크랩 (common 1단) water
    99: ("크랩해머", 1.4),       # 킹크랩 (rare) water

    # --- Voltorb line ---
    100: ("전기쇼크", 1.2),      # 찌리리공 (common 1단) electric
    101: ("대폭발", 1.4),        # 붐볼 (rare) electric

    # --- Exeggcute line (grass/psychic) ---
    102: [("흡수", 1.2), ("염동력", 1.2)],              # 아라리 (common 1단)
    103: [("솔라빔", 1.5), ("사이코키네시스", 1.5)],    # 나시 (epic)

    # --- Cubone line ---
    104: ("뼈다귀치기", 1.2),    # 탕구리 (common 1단) ground
    105: ("뼈다귀부메랑", 1.3),  # 텅구리 (common 최종) ground

    # --- Hitmonlee ---
    106: ("메가킥", 1.4),        # 시라소몬 (rare) fighting

    # --- Hitmonchan ---
    107: ("메가펀치", 1.4),      # 홍수몬 (rare) fighting

    # --- Lickitung ---
    108: ("핥기", 1.3),          # 내루미 (rare) normal

    # --- Koffing line ---
    109: ("오물공격", 1.2),      # 또가스 (common 1단) poison
    110: ("대폭발", 1.4),        # 또도가스 (rare) poison

    # --- Rhyhorn line (ground/rock) ---
    111: [("진흙뿌리기", 1.2), ("바위떨구기", 1.2)],    # 뿔카노 (common 1단)
    112: [("지진", 1.4), ("스톤에지", 1.4)],            # 코뿌리 (rare 최종)

    # --- Chansey ---
    113: ("알폭탄", 1.4),        # 럭키 (rare) normal

    # --- Tangela ---
    114: ("솔라빔", 1.3),        # 덩쿠리 (rare) grass

    # --- Kangaskhan ---
    115: ("메가펀치", 1.4),      # 캥카 (rare) normal

    # --- Horsea line ---
    116: ("물대포", 1.2),        # 쏘드라 (common 1단) water
    117: ("용의파동", 1.3),      # 시드라 (common 최종) water

    # --- Goldeen line ---
    118: ("뿔찌르기", 1.2),      # 콘치 (common 1단) water
    119: ("폭포오르기", 1.4),    # 왕콘치 (rare) water

    # --- Staryu line ---
    120: ("물대포", 1.2),        # 별가사리 (common 1단) water
    121: [("하이드로펌프", 1.5), ("사이코키네시스", 1.5)],  # 아쿠스타 (epic) water/psychic

    # --- Mr. Mime (psychic/fairy) ---
    122: [("사이코키네시스", 1.4), ("매지컬샤인", 1.4)], # 마임맨 (rare)

    # --- Scyther (bug/flying) ---
    123: [("시저크로스", 1.5), ("에어슬래시", 1.5)],     # 스라크 (epic)

    # --- Jynx (ice/psychic) ---
    124: [("눈보라", 1.4), ("사이코키네시스", 1.4)],     # 루주라 (rare)

    # --- Electabuzz ---
    125: ("10만볼트", 1.4),      # 에레브 (rare) electric

    # --- Magmar ---
    126: ("화염방사", 1.4),      # 마그마 (rare) fire

    # --- Pinsir ---
    127: ("시저크로스", 1.5),    # 쁘사이저 (epic) bug

    # --- Tauros ---
    128: ("돌진", 1.4),          # 켄타로스 (rare) normal

    # --- Magikarp line ---
    129: ("튀어오르기", 1.2),    # 잉어킹 (common) water
    130: [("하이드로펌프", 1.5), ("폭풍", 1.5)],        # 갸라도스 (epic 최종) water/flying

    # --- Lapras (water/ice) ---
    131: [("하이드로펌프", 1.5), ("냉동빔", 1.5)],      # 라프라스 (epic)

    # --- Ditto ---
    132: ("변신", 1.2),          # 메타몽 (common) normal

    # --- Eevee ---
    133: ("돌진", 1.2),          # 이브이 (common) normal

    # --- Eeveelutions ---
    134: ("하이드로펌프", 1.5),  # 샤미드 (epic) water
    135: ("10만볼트", 1.5),      # 쥬피썬더 (epic) electric
    136: ("화염방사", 1.5),      # 부스터 (epic) fire

    # --- Porygon ---
    137: ("트라이어택", 1.3),    # 폴리곤 (rare) normal

    # --- Omanyte line (rock/water) ---
    138: [("고대의힘", 1.3), ("물대포", 1.3)],          # 암나이트 (rare 1단)
    139: [("스톤에지", 1.4), ("하이드로펌프", 1.4)],    # 암스타 (rare 최종)

    # --- Kabuto line (rock/water) ---
    140: [("고대의힘", 1.3), ("물대포", 1.3)],          # 투구 (rare 1단)
    141: [("스톤에지", 1.4), ("아쿠아테일", 1.4)],      # 투구푸스 (rare 최종)

    # --- Aerodactyl (rock/flying) ---
    142: [("스톤에지", 1.5), ("하늘가르기", 1.5)],      # 프테라 (epic)

    # --- Snorlax ---
    143: ("잠자기", 1.5),        # 잠만보 (epic) normal

    # --- Legendary Birds ---
    144: [("눈보라", 1.8), ("폭풍", 1.8)],              # 프리저 (legendary) ice/flying
    145: [("번개", 1.8), ("폭풍", 1.8)],                # 썬더 (legendary) electric/flying
    146: [("오버히트", 1.8), ("에어슬래시", 1.8)],      # 파이어 (legendary) fire/flying

    # --- Dratini line ---
    147: ("용의분노", 1.2),      # 미뇽 (common) dragon
    148: ("용의파동", 1.3),      # 신뇽 (rare 2단) dragon
    149: [("역린", 1.5), ("폭풍", 1.5)],                # 망나뇽 (epic 최종) dragon/flying

    # --- Mewtwo ---
    150: ("사이코브레이크", 2.0),# 뮤츠 (legendary 특수) psychic

    # --- Mew ---
    151: ("사이코키네시스", 1.8),# 뮤 (legendary) psychic

    # ============================================================
    # Gen 2 (152-251)
    # ============================================================

    # --- Chikorita line ---
    152: ("덩굴채찍", 1.2),      # 치코리타 (common) grass
    153: ("잎날가르기", 1.3),    # 베이리프 (common) grass
    154: ("꽃잎댄스", 1.5),      # 메가니움 (epic 최종) grass

    # --- Cyndaquil line ---
    155: ("불꽃세례", 1.2),      # 브케인 (common) fire
    156: ("화염방사", 1.3),      # 마그케인 (common) fire
    157: ("분화", 1.5),          # 블레이범 (epic 최종) fire

    # --- Totodile line ---
    158: ("물대포", 1.2),        # 리아코 (common) water
    159: ("물어뜯기", 1.3),      # 엘리게이 (common) water
    160: ("하이드로펌프", 1.5),  # 장크로다일 (epic 최종) water

    # --- Sentret line ---
    161: ("전광석화", 1.2),      # 꼬리선 (common 1단) normal
    162: ("돌진", 1.3),          # 다꼬리 (common 최종) normal

    # --- Hoothoot line (normal/flying) ---
    163: [("몸통박치기", 1.2), ("공중날기", 1.2)],      # 부우부 (common 1단)
    164: [("하이퍼빔", 1.4), ("에어슬래시", 1.4)],      # 야부엉 (rare)

    # --- Ledyba line (bug/flying) ---
    165: [("벌레의저항", 1.2), ("공중날기", 1.2)],      # 레디바 (common 1단)
    166: [("은빛바람", 1.3), ("에어슬래시", 1.3)],      # 레디안 (common 최종)

    # --- Spinarak line (bug/poison) ---
    167: [("벌레의저항", 1.2), ("독침", 1.2)],          # 페이검 (common 1단)
    168: [("시그널빔", 1.3), ("독찌르기", 1.3)],        # 아리아도스 (common 최종)

    # --- Crobat (poison/flying) ---
    169: [("크로스포이즌", 1.5), ("에어슬래시", 1.5)],  # 크로뱃 (epic)

    # --- Chinchou line (water/electric) ---
    170: [("거품광선", 1.2), ("전기쇼크", 1.2)],        # 초라기 (common 1단)
    171: [("파도타기", 1.4), ("10만볼트", 1.4)],        # 랜턴 (rare 최종)

    # --- Baby Pokemon ---
    172: ("전기쇼크", 1.2),      # 피츄 (common) electric
    173: ("매지컬샤인", 1.2),    # 삐 (common) fairy
    174: [("하이퍼보이스", 1.2), ("달콤한키스", 1.2)],  # 푸푸린 (common) normal/fairy

    # --- Togepi line ---
    175: ("손가락흔들기", 1.2),  # 토게피 (common) fairy
    176: [("매지컬샤인", 1.3), ("에어슬래시", 1.3)],    # 토게틱 (common) fairy/flying

    # --- Natu line (psychic/flying) ---
    177: [("염동력", 1.2), ("공중날기", 1.2)],          # 네이티 (common 1단)
    178: [("미래예지", 1.4), ("에어슬래시", 1.4)],      # 네이티오 (rare 최종)

    # --- Mareep line ---
    179: ("전기쇼크", 1.2),      # 메리프 (common 1단) electric
    180: ("10만볼트", 1.3),      # 보송송 (rare 2단) electric
    181: ("번개", 1.5),          # 전룡 (epic 최종) electric

    # --- Bellossom ---
    182: ("꽃잎댄스", 1.4),      # 아르코 (rare 최종) grass

    # --- Marill line (water/fairy) ---
    183: [("거품광선", 1.2), ("요정의바람", 1.2)],      # 마릴 (common 1단)
    184: [("아쿠아테일", 1.3), ("매지컬샤인", 1.3)],    # 마릴리 (common)

    # --- Sudowoodo ---
    185: ("스톤에지", 1.3),      # 꼬지모 (common) rock

    # --- Politoed ---
    186: ("하이드로펌프", 1.5),  # 왕구리 (epic) water

    # --- Hoppip line (grass/flying) ---
    187: [("흡수", 1.2), ("공중날기", 1.2)],            # 통통코 (common 1단)
    188: [("메가드레인", 1.2), ("에어슬래시", 1.2)],    # 두코 (common 2단)
    189: [("기가드레인", 1.4), ("에어슬래시", 1.4)],    # 솜솜코 (rare)

    # --- Aipom ---
    190: ("더블어택", 1.3),      # 에이팜 (common) normal

    # --- Sunkern line ---
    191: ("흡수", 1.2),          # 해너츠 (common 1단) grass
    192: ("솔라빔", 1.3),        # 해루미 (common) grass

    # --- Yanma (bug/flying) ---
    193: [("시그널빔", 1.3), ("에어슬래시", 1.3)],      # 왕자리 (common)

    # --- Wooper line (water/ground) ---
    194: [("물대포", 1.2), ("진흙뿌리기", 1.2)],        # 우파 (common 1단)
    195: [("파도타기", 1.3), ("지진", 1.3)],            # 누오 (common)

    # --- Espeon ---
    196: ("사이코키네시스", 1.5),# 에브이 (epic) psychic

    # --- Umbreon ---
    197: ("악의파동", 1.5),      # 블래키 (epic) dark

    # --- Murkrow (dark/flying) ---
    198: [("악의파동", 1.3), ("에어슬래시", 1.3)],      # 니로우 (common)

    # --- Slowking (water/psychic) ---
    199: [("파도타기", 1.4), ("사이코키네시스", 1.4)],  # 야도킹 (rare 최종)

    # --- Misdreavus ---
    200: ("섀도볼", 1.3),        # 무우마 (rare) ghost

    # --- Unown ---
    201: ("숨겨진힘", 1.2),      # 안농 (common) psychic

    # --- Wobbuffet ---
    202: ("반격", 1.3),          # 마자용 (common) psychic

    # --- Girafarig (normal/psychic) ---
    203: [("하이퍼빔", 1.4), ("사이코키네시스", 1.4)],  # 키링키 (rare)

    # --- Pineco line ---
    204: ("자폭", 1.2),          # 피콘 (common 1단) bug
    205: [("대폭발", 1.4), ("아이언헤드", 1.4)],        # 쏘콘 (rare 최종) bug/steel

    # --- Dunsparce ---
    206: ("비밀의힘", 1.3),      # 노고치 (common) normal

    # --- Gligar (ground/flying) ---
    207: [("대지의힘", 1.3), ("에어슬래시", 1.3)],      # 글라이거 (rare)

    # --- Steelix (steel/ground) ---
    208: [("아이언테일", 1.5), ("지진", 1.5)],          # 강철톤 (epic)

    # --- Snubbull line ---
    209: ("물어뜯기", 1.2),      # 블루 (common 1단) fairy
    210: ("매지컬샤인", 1.4),    # 그랑블루 (rare 최종) fairy

    # --- Qwilfish (water/poison) ---
    211: [("아쿠아테일", 1.3), ("독찌르기", 1.3)],      # 침바루 (common)

    # --- Scizor (bug/steel) ---
    212: [("시저크로스", 1.5), ("불릿펀치", 1.5)],      # 핫삼 (epic)

    # --- Shuckle (bug/rock) ---
    213: [("벌레의저항", 1.5), ("스톤에지", 1.5)],      # 단단지 (epic)

    # --- Heracross (bug/fighting) ---
    214: [("메가혼", 1.5), ("인파이트", 1.5)],          # 헤라크로스 (epic)

    # --- Sneasel (dark/ice) ---
    215: [("밤의슬래시", 1.3), ("냉동펀치", 1.3)],      # 포푸니 (rare)

    # --- Teddiursa line ---
    216: ("베어가르기", 1.2),    # 깜지곰 (common 1단) normal
    217: ("크로스촙", 1.5),      # 링곰 (epic) normal

    # --- Slugma line ---
    218: ("불꽃세례", 1.2),      # 마그마그 (common 1단) fire
    219: [("화염방사", 1.3), ("고대의힘", 1.3)],        # 마그카르고 (common) fire/rock

    # --- Swinub line (ice/ground) ---
    220: [("얼음뭉치", 1.2), ("진흙뿌리기", 1.2)],      # 꾸꾸리 (common 1단)
    221: [("냉동빔", 1.4), ("지진", 1.4)],              # 메꾸리 (rare 최종)

    # --- Corsola (water/rock) ---
    222: [("거품광선", 1.3), ("고대의힘", 1.3)],        # 코산호 (common)

    # --- Remoraid line ---
    223: ("물대포", 1.2),        # 총어 (common 1단) water
    224: ("옥토캐논", 1.4),      # 대포무노 (rare 최종) water

    # --- Delibird (ice/flying) ---
    225: [("선물", 1.2), ("공중날기", 1.2)],            # 딜리버드 (common)

    # --- Mantine (water/flying) ---
    226: [("거품광선", 1.4), ("에어슬래시", 1.4)],      # 만타인 (rare)

    # --- Skarmory (steel/flying) ---
    227: [("강철날개", 1.4), ("에어슬래시", 1.4)],      # 무장조 (rare)

    # --- Houndour line (dark/fire) ---
    228: [("물어뜯기", 1.2), ("불꽃세례", 1.2)],        # 델빌 (common 1단)
    229: [("악의파동", 1.5), ("화염방사", 1.5)],        # 헬가 (epic 최종)

    # --- Kingdra (water/dragon) ---
    230: [("하이드로펌프", 1.5), ("용의파동", 1.5)],    # 킹드라 (epic)

    # --- Phanpy line ---
    231: ("구르기", 1.2),        # 코코리 (common 1단) ground
    232: ("지진", 1.5),          # 코리갑 (epic) ground

    # --- Porygon2 ---
    233: ("트라이어택", 1.5),    # 폴리곤2 (epic) normal

    # --- Stantler ---
    234: ("박치기", 1.4),          # 노라키 (rare) normal

    # --- Smeargle ---
    235: ("스케치", 1.2),        # 루브도 (common) normal

    # --- Tyrogue line ---
    236: ("마하펀치", 1.2),      # 배루키 (common 1단) fighting
    237: ("트리플킥", 1.4),      # 카포에라 (rare 최종) fighting

    # --- Baby Pokemon (Gen 2 → Gen 1 evolutions) ---
    238: [("냉동펀치", 1.2), ("염동력", 1.2)],          # 뽀뽀라 (common) ice/psychic
    239: ("전기쇼크", 1.3),      # 에레키드 (common) electric
    240: ("불꽃세례", 1.3),      # 마그비 (common) fire

    # --- Miltank ---
    241: ("구르기", 1.4),        # 밀탱크 (rare) normal

    # --- Blissey ---
    242: ("알폭탄", 1.5),        # 해피너스 (epic) normal

    # --- Legendary Beasts ---
    243: ("번개", 1.8),          # 라이코 (legendary) electric
    244: ("성스러운불꽃", 1.8),  # 앤테이 (legendary) fire
    245: ("오로라빔", 1.8),      # 스이쿤 (legendary) water

    # --- Larvitar line (rock/ground) ---
    246: [("물어뜯기", 1.2), ("진흙뿌리기", 1.2)],      # 애버라스 (common)
    247: [("스톤에지", 1.3), ("지진", 1.3)],            # 데기라스 (rare 2단)
    248: [("스톤에지", 1.5), ("깨물어부수기", 1.5)],    # 마기라스 (epic 최종) rock/dark

    # --- Tower Legends ---
    249: [("에어로블래스트", 2.0), ("사이코키네시스", 2.0)],  # 루기아 (legendary 특수) psychic/flying
    250: [("성스러운불꽃", 2.0), ("폭풍", 2.0)],        # 칠색조 (legendary 특수) fire/flying

    # --- Mythical ---
    251: [("사이코키네시스", 1.8), ("리프스톰", 1.8)],  # 세레비 (legendary) psychic/grass

    # ============================================================
    # Gen 3 (252-386)
    # ============================================================

    # --- Treecko line ---
    252: ("흡수", 1.2),           # 나무지기 (common) grass
    253: ("잎날가르기", 1.3),     # 나무돌이 (rare) grass
    254: ("리프블레이드", 1.5),   # 나무킹 (epic) grass

    # --- Torchic line ---
    255: ("불꽃세례", 1.2),       # 아차모 (common) fire
    256: [("화염방사", 1.3), ("하이점프킥", 1.3)],      # 영치코 (rare) fire/fighting
    257: [("블레이즈킥", 1.5), ("인파이트", 1.5)],      # 번치코 (epic) fire/fighting

    # --- Mudkip line ---
    258: ("물대포", 1.2),         # 물짱이 (common) water
    259: [("탁류", 1.3), ("대지의힘", 1.3)],            # 늪짱이 (rare) water/ground
    260: [("하이드로캐논", 1.5), ("지진", 1.5)],        # 대짱이 (epic) water/ground

    # --- Poochyena line ---
    261: ("물어뜯기", 1.2),       # 포챠나 (common) dark
    262: ("깨물어부수기", 1.3),   # 그라에나 (rare) dark

    # --- Zigzagoon line ---
    263: ("박치기", 1.2),         # 지그제구리 (common) normal
    264: ("베어가르기", 1.3),     # 직구리 (rare) normal

    # --- Wurmple line ---
    265: ("실뿜기", 1.2),         # 개무소 (common) bug
    266: ("경화", 1.2),           # 실쿤 (common) bug
    267: [("은빛바람", 1.3), ("에어슬래시", 1.3)],      # 뷰티플라이 (common BST≥350) bug/flying
    268: ("경화", 1.2),           # 카스쿤 (common) bug
    269: [("시그널빔", 1.3), ("오물공격", 1.3)],        # 독케일 (common BST≥350) bug/poison

    # --- Lotad line (water/grass) ---
    270: [("거품광선", 1.2), ("흡수", 1.2)],            # 연꽃몬 (common)
    271: [("물의파동", 1.2), ("기가드레인", 1.2)],      # 로토스 (common)
    272: [("파도타기", 1.4), ("에너지볼", 1.4)],        # 로파파 (rare BST≥450)

    # --- Seedot line ---
    273: ("흡수", 1.2),           # 도토링 (common) grass
    274: [("잎날가르기", 1.2), ("물어뜯기", 1.2)],      # 잎새코 (common) grass/dark
    275: [("리프스톰", 1.4), ("악의파동", 1.4)],        # 다탱구 (rare BST≥450) grass/dark

    # --- Taillow line (normal/flying) ---
    276: [("전광석화", 1.2), ("공중날기", 1.2)],        # 테일로 (common)
    277: [("돌진", 1.4), ("브레이브버드", 1.4)],        # 스왈로 (rare BST≥450)

    # --- Wingull line (water/flying) ---
    278: [("물대포", 1.2), ("공중날기", 1.2)],          # 갈모매 (common)
    279: [("하이드로펌프", 1.3), ("에어슬래시", 1.3)],  # 패리퍼 (rare)

    # --- Ralts line (psychic/fairy) ---
    280: [("염동력", 1.2), ("요정의바람", 1.2)],        # 랄토스 (common)
    281: [("사이코키네시스", 1.2), ("매지컬샤인", 1.2)],# 킬리아 (common)
    282: [("사이코키네시스", 1.5), ("문포스", 1.5)],    # 가디안 (epic BST≥500)

    # --- Surskit line ---
    283: [("거품광선", 1.2), ("시그널빔", 1.2)],        # 비구술 (common) bug/water
    284: [("시그널빔", 1.4), ("에어슬래시", 1.4)],      # 비나방 (rare BST≥450) bug/flying

    # --- Shroomish line ---
    285: ("흡수", 1.2),           # 버섯꼬 (common) grass
    286: [("씨폭탄", 1.4), ("마하펀치", 1.4)],          # 버섯모 (rare BST≥450) grass/fighting

    # --- Slakoth line ---
    287: ("하품", 1.2),           # 게을로 (common) normal
    288: ("베어가르기", 1.3),     # 발바로 (rare) normal
    289: ("기가임팩트", 1.0),     # 게을킹 (나태 특성 반영) normal

    # --- Nincada line ---
    290: [("파헤치기", 1.2), ("시저크로스", 1.2)],      # 토중몬 (common) bug/ground
    291: [("시저크로스", 1.4), ("에어슬래시", 1.4)],    # 아이스크 (rare BST≥450) bug/flying
    292: [("섀도볼", 1.2), ("시저크로스", 1.2)],        # 껍질몬 (common) bug/ghost

    # --- Whismur line ---
    293: ("울음소리", 1.2),       # 소곤룡 (common) normal
    294: ("하이퍼보이스", 1.3),   # 노공룡 (common BST≥350) normal
    295: ("폭음파", 1.4),         # 폭음룡 (rare BST≥450) normal

    # --- Makuhita line ---
    296: ("장풍", 1.2),           # 마크탕 (common) fighting
    297: ("클로즈컴뱃", 1.4),     # 하리뭉 (rare BST≥450) fighting

    # --- Azurill (normal/fairy) ---
    298: [("몸통박치기", 1.2), ("요정의바람", 1.2)],    # 루리리 (common)

    # --- Nosepass ---
    299: ("스톤에지", 1.3),       # 코코파스 (common BST≥350) rock

    # --- Skitty line ---
    300: ("고양이돈받기", 1.2),   # 에나비 (common) normal
    301: ("하이퍼보이스", 1.3),   # 델케티 (rare) normal

    # --- Sableye (dark/ghost) ---
    302: [("악의파동", 1.3), ("섀도클로", 1.3)],        # 깜까미 (common BST≥350)

    # --- Mawile (steel/fairy) ---
    303: [("아이언헤드", 1.3), ("매지컬샤인", 1.3)],    # 입치트 (common BST≥350)

    # --- Aron line (steel/rock) ---
    304: [("아이언헤드", 1.2), ("바위떨구기", 1.2)],    # 가보리 (common)
    305: [("아이언테일", 1.3), ("스톤에지", 1.3)],      # 갱도라 (rare)
    306: [("헤비봄버", 1.5), ("스톤에지", 1.5)],        # 보스로라 (epic BST≥500)

    # --- Meditite line (fighting/psychic) ---
    307: [("잠깨움뺨치기", 1.2), ("염동력", 1.2)],      # 요가랑 (common)
    308: [("하이점프킥", 1.3), ("사이코키네시스", 1.3)],# 요가램 (rare)

    # --- Electrike line ---
    309: ("스파크", 1.2),         # 썬더라이 (common) electric
    310: ("번개", 1.4),           # 썬더볼트 (rare BST≥450) electric

    # --- Plusle ---
    311: ("스파크", 1.3),         # 플러시 (rare) electric

    # --- Minun ---
    312: ("방전", 1.3),           # 마이농 (rare) electric

    # --- Volbeat ---
    313: ("시그널빔", 1.3),       # 볼비트 (rare) bug

    # --- Illumise ---
    314: ("은빛바람", 1.3),       # 네오비트 (rare) bug

    # --- Roselia (grass/poison) ---
    315: [("기가드레인", 1.3), ("오물폭탄", 1.3)],      # 로젤리아 (rare)

    # --- Gulpin line ---
    316: ("독침", 1.2),           # 꼴깍몬 (common) poison
    317: ("오물폭탄", 1.4),       # 꿀꺽몬 (rare BST≥450) poison

    # --- Carvanha line (water/dark) ---
    318: [("물대포", 1.2), ("물어뜯기", 1.2)],          # 샤프니아 (common)
    319: [("아쿠아테일", 1.4), ("깨물어부수기", 1.4)],  # 샤크니아 (rare BST≥450)

    # --- Wailmer line ---
    320: ("물대포", 1.3),         # 고래왕자 (rare) water
    321: ("하이드로펌프", 1.5),   # 고래왕 (epic BST≥500) water

    # --- Numel line (fire/ground) ---
    322: [("불꽃세례", 1.2), ("진흙뿌리기", 1.2)],      # 둔타 (common)
    323: [("분화", 1.4), ("지진", 1.4)],                # 폭타 (rare BST≥450)

    # --- Torkoal ---
    324: ("오버히트", 1.4),       # 코터스 (rare BST≥450) fire

    # --- Spoink line ---
    325: ("사이코키네시스", 1.2), # 피그점프 (common) psychic
    326: ("사이코키네시스", 1.4), # 피그킹 (rare BST≥450) psychic

    # --- Spinda ---
    327: ("정신차리기", 1.3),     # 얼루기 (common BST≥350) normal

    # --- Trapinch line ---
    328: ("물어뜯기", 1.2),       # 톱치 (common) ground
    329: [("대지의힘", 1.2), ("용의숨결", 1.2)],        # 비브라바 (common) ground/dragon
    330: [("지진", 1.5), ("드래곤클로", 1.5)],          # 플라이곤 (epic BST≥500) ground/dragon

    # --- Cacnea line ---
    331: ("바늘팔", 1.2),         # 선인왕 (common) grass
    332: [("바늘미사일", 1.4), ("악의파동", 1.4)],      # 밤선인 (rare BST≥450) grass/dark

    # --- Swablu line ---
    333: [("전광석화", 1.2), ("공중날기", 1.2)],        # 파비코 (common) normal/flying
    334: [("용의파동", 1.4), ("하늘가르기", 1.4)],      # 파비코리 (rare BST≥450) dragon/flying

    # --- Zangoose ---
    335: ("베어가르기", 1.4),     # 쟝고 (rare BST≥450) normal

    # --- Seviper ---
    336: ("독엄니", 1.4),         # 세비퍼 (rare BST≥450) poison

    # --- Lunatone (rock/psychic) ---
    337: [("고대의힘", 1.4), ("사이코키네시스", 1.4)],  # 루나톤 (rare BST≥450)

    # --- Solrock (rock/psychic) ---
    338: [("스톤에지", 1.4), ("사이코키네시스", 1.4)],  # 솔록 (rare BST≥450)

    # --- Barboach line (water/ground) ---
    339: [("물대포", 1.2), ("진흙뿌리기", 1.2)],        # 미꾸리 (common)
    340: [("파도타기", 1.4), ("지진", 1.4)],            # 메깅 (rare BST≥450)

    # --- Corphish line ---
    341: ("거품광선", 1.2),       # 가재군 (common) water
    342: [("크랩해머", 1.4), ("밤의슬래시", 1.4)],      # 가재장군 (rare BST≥450) water/dark

    # --- Baltoy line (ground/psychic) ---
    343: [("진흙뿌리기", 1.2), ("염동력", 1.2)],        # 오뚝군 (common)
    344: [("대지의힘", 1.5), ("사이코키네시스", 1.5)],  # 점토도리 (epic BST≥500)

    # --- Lileep line (rock/grass) ---
    345: [("고대의힘", 1.3), ("기가드레인", 1.3)],      # 릴링 (common BST≥350)
    346: [("스톤에지", 1.4), ("에너지볼", 1.4)],        # 릴리요 (rare BST≥450)

    # --- Anorith line (rock/bug) ---
    347: [("고대의힘", 1.3), ("시저크로스", 1.3)],      # 아노딥스 (common BST≥350)
    348: [("스톤에지", 1.4), ("시저크로스", 1.4)],      # 아말도 (rare BST≥450)

    # --- Feebas line ---
    349: ("튀어오르기", 1.2),     # 빈티나 (common) water
    350: ("하이드로펌프", 1.5),   # 밀로틱 (epic BST≥500) water

    # --- Castform ---
    351: ("날씨공", 1.3),         # 캐스퐁 (rare) normal

    # --- Kecleon ---
    352: ("섀도클로", 1.3),       # 켈리몬 (rare) normal

    # --- Shuppet line ---
    353: ("섀도볼", 1.2),         # 어둠대신 (common) ghost
    354: ("섀도볼", 1.4),         # 다크펫 (rare BST≥450) ghost

    # --- Duskull line ---
    355: ("야습", 1.2),           # 해골몽 (common) ghost
    356: ("섀도펀치", 1.4),       # 미라몽 (rare BST≥450) ghost

    # --- Tropius (grass/flying) ---
    357: [("솔라빔", 1.4), ("에어슬래시", 1.4)],        # 트로피우스 (rare BST≥450)

    # --- Chimecho ---
    358: ("사이코키네시스", 1.4), # 치렁 (rare BST≥450) psychic

    # --- Absol ---
    359: ("악의파동", 1.4),       # 앱솔 (rare BST≥450) dark

    # --- Wynaut ---
    360: ("반격", 1.2),           # 마자 (common) psychic

    # --- Snorunt line ---
    361: ("냉동빔", 1.2),         # 눈꼬마 (common) ice
    362: ("냉동빔", 1.4),         # 얼음귀신 (rare BST≥450) ice

    # --- Spheal line (ice/water) ---
    363: [("얼음뭉치", 1.2), ("물대포", 1.2)],          # 대굴레오 (common)
    364: [("오로라빔", 1.3), ("파도타기", 1.3)],        # 씨레오 (rare)
    365: [("눈보라", 1.5), ("하이드로펌프", 1.5)],      # 씨카이저 (epic BST≥500)

    # --- Clamperl line ---
    366: ("조개의무기", 1.2),     # 진주몽 (common) water
    367: ("깨물어부수기", 1.4),   # 헌테일 (rare BST≥450) water
    368: ("사이코키네시스", 1.4), # 분홍장이 (rare BST≥450) water

    # --- Relicanth (water/rock) ---
    369: [("아쿠아테일", 1.4), ("머리깨기", 1.4)],      # 시라칸 (rare BST≥450)

    # --- Luvdisc ---
    370: ("달콤한키스", 1.2),     # 사랑동이 (common) water

    # --- Bagon line (pseudo-legendary) ---
    371: ("용의숨결", 1.2),       # 아공이 (common) dragon
    372: ("드래곤클로", 1.3),     # 쉘곤 (rare) dragon
    373: [("유성군", 1.8), ("폭풍", 1.8)],              # 보만다 (legendary) dragon/flying

    # --- Beldum line (pseudo-legendary) (steel/psychic) ---
    374: [("박치기", 1.2), ("염동력", 1.2)],            # 메탕 (common)
    375: [("메탈클로", 1.3), ("사이코키네시스", 1.3)],  # 메탕구 (rare)
    376: [("코메트펀치", 1.8), ("사이코키네시스", 1.8)],# 메타그로스 (legendary)

    # --- Regi trio ---
    377: ("스톤에지", 1.8),       # 레지락 (legendary) rock
    378: ("냉동빔", 1.8),         # 레지아이스 (legendary) ice
    379: ("아이언헤드", 1.8),     # 레지스틸 (legendary) steel

    # --- Eon duo (dragon/psychic) ---
    380: [("용의파동", 1.8), ("미스트볼", 1.8)],        # 라티아스 (legendary)
    381: [("용의파동", 1.8), ("러스터퍼지", 1.8)],      # 라티오스 (legendary)

    # --- Weather trio ---
    382: ("근원의파동", 2.0),     # 가이오가 (ultra_legendary) water
    383: ("단애의칼날", 2.0),     # 그란돈 (ultra_legendary) ground
    384: [("역린", 2.0), ("화룡점정", 2.0)],            # 레쿠쟈 (ultra_legendary) dragon/flying

    # --- Mythical ---
    385: [("멸망의소원", 2.0), ("사이코키네시스", 2.0)],# 지라치 (ultra_legendary) steel/psychic
    386: ("사이코부스트", 2.0),   # 테오키스 (ultra_legendary) psychic
}


def get_primary_skill(pokemon_id: int) -> tuple[str, float]:
    """Return (skill_name, power) — 단일속성이면 그대로, 이중속성이면 1차 스킬."""
    raw = POKEMON_SKILLS.get(pokemon_id, ("몸통박치기", 1.2))
    if isinstance(raw, list):
        return raw[0]
    return raw


def get_skill_display(pokemon_id: int) -> str:
    """Return skill name(s) for display: '화염방사/에어슬래시' or '솔라빔'."""
    raw = POKEMON_SKILLS.get(pokemon_id, ("몸통박치기", 1.2))
    if isinstance(raw, list):
        return "/".join(s[0] for s in raw)
    return raw[0]


def get_max_skill_power(pokemon_id: int) -> float:
    """Return highest skill power for tier calculations."""
    raw = POKEMON_SKILLS.get(pokemon_id, ("몸통박치기", 1.2))
    if isinstance(raw, list):
        return max(s[1] for s in raw)
    return raw[1]
