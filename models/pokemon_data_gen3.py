"""
Gen 3 (252-386) Pokemon data for 3rd generation update.
Each tuple: (id, name_ko, name_en, emoji, rarity, catch_rate, evolves_from, evolves_to, evolution_method)
"""

ALL_POKEMON_GEN3 = [
    (252, "나무지기", "Treecko", "🌿", "common", 0.80, None, 253, "friendship"),  # Treecko
    (253, "나무돌이", "Grovyle", "🌿", "rare", 0.50, 252, 254, "friendship"),  # Grovyle
    (254, "나무킹", "Sceptile", "🌿", "epic", 0.15, 253, None, "none"),  # Sceptile

    (255, "아차모", "Torchic", "🔥", "common", 0.80, None, 256, "friendship"),  # Torchic
    (256, "영치코", "Combusken", "🔥", "rare", 0.50, 255, 257, "friendship"),  # Combusken
    (257, "번치코", "Blaziken", "🔥", "epic", 0.15, 256, None, "none"),  # Blaziken

    (258, "물짱이", "Mudkip", "💧", "common", 0.80, None, 259, "friendship"),  # Mudkip
    (259, "늪짱이", "Marshtomp", "💧", "rare", 0.50, 258, 260, "friendship"),  # Marshtomp
    (260, "대짱이", "Swampert", "💧", "epic", 0.15, 259, None, "none"),  # Swampert

    (261, "포챠나", "Poochyena", "🌑", "common", 0.80, None, 262, "friendship"),  # Poochyena
    (262, "그라에나", "Mightyena", "🌑", "rare", 0.50, 261, None, "none"),  # Mightyena

    (263, "지그제구리", "Zigzagoon", "⭐", "common", 0.80, None, 264, "friendship"),  # Zigzagoon
    (264, "직구리", "Linoone", "⭐", "rare", 0.50, 263, None, "none"),  # Linoone

    (265, "개무소", "Wurmple", "🐛", "common", 0.80, None, 268, "friendship"),  # Wurmple
    (266, "실쿤", "Silcoon", "🐛", "common", 0.80, 265, 267, "friendship"),  # Silcoon
    (267, "뷰티플라이", "Beautifly", "🐛", "common", 0.80, 266, None, "none"),  # Beautifly
    (268, "카스쿤", "Cascoon", "🐛", "common", 0.80, 265, 269, "friendship"),  # Cascoon
    (269, "독케일", "Dustox", "🐛", "common", 0.80, 268, None, "none"),  # Dustox

    (270, "연꽃몬", "Lotad", "💧", "common", 0.80, None, 271, "friendship"),  # Lotad
    (271, "로토스", "Lombre", "💧", "common", 0.80, 270, 272, "friendship"),  # Lombre
    (272, "로파파", "Ludicolo", "💧", "rare", 0.50, 271, None, "none"),  # Ludicolo

    (273, "도토링", "Seedot", "🌿", "common", 0.80, None, 274, "friendship"),  # Seedot
    (274, "잎새코", "Nuzleaf", "🌿", "common", 0.80, 273, 275, "friendship"),  # Nuzleaf
    (275, "다탱구", "Shiftry", "🌿", "rare", 0.50, 274, None, "none"),  # Shiftry

    (276, "테일로", "Taillow", "⭐", "common", 0.80, None, 277, "friendship"),  # Taillow
    (277, "스왈로", "Swellow", "⭐", "rare", 0.50, 276, None, "none"),  # Swellow

    (278, "갈모매", "Wingull", "💧", "common", 0.80, None, 279, "friendship"),  # Wingull
    (279, "패리퍼", "Pelipper", "💧", "rare", 0.50, 278, None, "none"),  # Pelipper

    (280, "랄토스", "Ralts", "🔮", "common", 0.80, None, 281, "friendship"),  # Ralts
    (281, "킬리아", "Kirlia", "🔮", "common", 0.80, 280, 282, "friendship"),  # Kirlia
    (282, "가디안", "Gardevoir", "🔮", "epic", 0.15, 281, None, "none"),  # Gardevoir

    (283, "비구술", "Surskit", "🐛", "common", 0.80, None, 284, "friendship"),  # Surskit
    (284, "비나방", "Masquerain", "🐛", "rare", 0.50, 283, None, "none"),  # Masquerain

    (285, "버섯꼬", "Shroomish", "🌿", "common", 0.80, None, 286, "friendship"),  # Shroomish
    (286, "버섯모", "Breloom", "🌿", "rare", 0.50, 285, None, "none"),  # Breloom

    (287, "게을로", "Slakoth", "⭐", "common", 0.80, None, 288, "friendship"),  # Slakoth
    (288, "발바로", "Vigoroth", "⭐", "rare", 0.50, 287, 289, "friendship"),  # Vigoroth
    (289, "게을킹", "Slaking", "⭐", "epic", 0.15, 288, None, "none"),  # Slaking (에픽 하향)

    (290, "토중몬", "Nincada", "🐛", "common", 0.80, None, 291, "friendship"),  # Nincada
    (291, "아이스크", "Ninjask", "🐛", "rare", 0.50, 290, None, "none"),  # Ninjask

    (292, "껍질몬", "Shedinja", "🐛", "common", 0.80, None, None, "none"),  # Shedinja

    (293, "소곤룡", "Whismur", "⭐", "common", 0.80, None, 294, "friendship"),  # Whismur
    (294, "노공룡", "Loudred", "⭐", "common", 0.80, 293, 295, "friendship"),  # Loudred
    (295, "폭음룡", "Exploud", "⭐", "rare", 0.50, 294, None, "none"),  # Exploud

    (296, "마크탕", "Makuhita", "🥊", "common", 0.80, None, 297, "friendship"),  # Makuhita
    (297, "하리뭉", "Hariyama", "🥊", "rare", 0.50, 296, None, "none"),  # Hariyama

    (298, "루리리", "Azurill", "⭐", "common", 0.80, None, None, "none"),  # Azurill

    (299, "코코파스", "Nosepass", "🗿", "common", 0.80, None, 476, "none"),  # Nosepass

    (300, "에나비", "Skitty", "⭐", "common", 0.80, None, 301, "friendship"),  # Skitty
    (301, "델케티", "Delcatty", "⭐", "rare", 0.50, 300, None, "none"),  # Delcatty

    (302, "깜까미", "Sableye", "🌑", "common", 0.80, None, None, "none"),  # Sableye

    (303, "입치트", "Mawile", "⚙️", "common", 0.80, None, None, "none"),  # Mawile

    (304, "가보리", "Aron", "⚙️", "common", 0.80, None, 305, "friendship"),  # Aron
    (305, "갱도라", "Lairon", "⚙️", "rare", 0.50, 304, 306, "friendship"),  # Lairon
    (306, "보스로라", "Aggron", "⚙️", "epic", 0.15, 305, None, "none"),  # Aggron

    (307, "요가랑", "Meditite", "🥊", "common", 0.80, None, 308, "friendship"),  # Meditite
    (308, "요가램", "Medicham", "🥊", "rare", 0.50, 307, None, "none"),  # Medicham

    (309, "썬더라이", "Electrike", "⚡", "common", 0.80, None, 310, "friendship"),  # Electrike
    (310, "썬더볼트", "Manectric", "⚡", "rare", 0.50, 309, None, "none"),  # Manectric

    (311, "플러시", "Plusle", "⚡", "rare", 0.50, None, None, "none"),  # Plusle

    (312, "마이농", "Minun", "⚡", "common", 0.80, None, None, "none"),  # Minun

    (313, "볼비트", "Volbeat", "🐛", "rare", 0.50, None, None, "none"),  # Volbeat

    (314, "네오비트", "Illumise", "🐛", "rare", 0.50, None, None, "none"),  # Illumise

    (315, "로젤리아", "Roselia", "🌿", "rare", 0.50, None, 407, "none"),  # Roselia

    (316, "꼴깍몬", "Gulpin", "☠️", "common", 0.80, None, 317, "friendship"),  # Gulpin
    (317, "꿀꺽몬", "Swalot", "☠️", "rare", 0.50, 316, None, "none"),  # Swalot

    (318, "샤프니아", "Carvanha", "💧", "common", 0.80, None, 319, "friendship"),  # Carvanha
    (319, "샤크니아", "Sharpedo", "💧", "rare", 0.50, 318, None, "none"),  # Sharpedo

    (320, "고래왕자", "Wailmer", "💧", "rare", 0.50, None, 321, "friendship"),  # Wailmer
    (321, "고래왕", "Wailord", "💧", "epic", 0.15, 320, None, "none"),  # Wailord

    (322, "둔타", "Numel", "🔥", "common", 0.80, None, 323, "friendship"),  # Numel
    (323, "폭타", "Camerupt", "🔥", "rare", 0.50, 322, None, "none"),  # Camerupt

    (324, "코터스", "Torkoal", "🔥", "rare", 0.50, None, None, "none"),  # Torkoal

    (325, "피그점프", "Spoink", "🔮", "common", 0.80, None, 326, "friendship"),  # Spoink
    (326, "피그킹", "Grumpig", "🔮", "rare", 0.50, 325, None, "none"),  # Grumpig

    (327, "얼루기", "Spinda", "⭐", "common", 0.80, None, None, "none"),  # Spinda

    (328, "톱치", "Trapinch", "🌍", "common", 0.80, None, 329, "friendship"),  # Trapinch
    (329, "비브라바", "Vibrava", "🌍", "common", 0.80, 328, 330, "friendship"),  # Vibrava
    (330, "플라이곤", "Flygon", "🌍", "epic", 0.15, 329, None, "none"),  # Flygon

    (331, "선인왕", "Cacnea", "🌿", "common", 0.80, None, 332, "friendship"),  # Cacnea
    (332, "밤선인", "Cacturne", "🌿", "rare", 0.50, 331, None, "none"),  # Cacturne

    (333, "파비코", "Swablu", "⭐", "common", 0.80, None, 334, "friendship"),  # Swablu
    (334, "파비코리", "Altaria", "🐉", "rare", 0.50, 333, None, "none"),  # Altaria

    (335, "쟝고", "Zangoose", "⭐", "rare", 0.50, None, None, "none"),  # Zangoose

    (336, "세비퍼", "Seviper", "☠️", "rare", 0.50, None, None, "none"),  # Seviper

    (337, "루나톤", "Lunatone", "🗿", "rare", 0.50, None, None, "none"),  # Lunatone

    (338, "솔록", "Solrock", "🗿", "rare", 0.50, None, None, "none"),  # Solrock

    (339, "미꾸리", "Barboach", "💧", "common", 0.80, None, 340, "friendship"),  # Barboach
    (340, "메깅", "Whiscash", "💧", "rare", 0.50, 339, None, "none"),  # Whiscash

    (341, "가재군", "Corphish", "💧", "common", 0.80, None, 342, "friendship"),  # Corphish
    (342, "가재장군", "Crawdaunt", "💧", "rare", 0.50, 341, None, "none"),  # Crawdaunt

    (343, "오뚝군", "Baltoy", "🌍", "common", 0.80, None, 344, "friendship"),  # Baltoy
    (344, "점토도리", "Claydol", "🌍", "rare", 0.50, 343, None, "none"),  # Claydol

    (345, "릴링", "Lileep", "🗿", "common", 0.80, None, 346, "friendship"),  # Lileep
    (346, "릴리요", "Cradily", "🗿", "rare", 0.50, 345, None, "none"),  # Cradily

    (347, "아노딥스", "Anorith", "🗿", "common", 0.80, None, 348, "friendship"),  # Anorith
    (348, "아말도", "Armaldo", "🗿", "rare", 0.50, 347, None, "none"),  # Armaldo

    (349, "빈티나", "Feebas", "💧", "common", 0.80, None, 350, "trade"),  # Feebas
    (350, "밀로틱", "Milotic", "💧", "epic", 0.15, 349, None, "none"),  # Milotic

    (351, "캐스퐁", "Castform", "⭐", "rare", 0.50, None, None, "none"),  # Castform

    (352, "켈리몬", "Kecleon", "⭐", "rare", 0.50, None, None, "none"),  # Kecleon

    (353, "어둠대신", "Shuppet", "👻", "common", 0.80, None, 354, "friendship"),  # Shuppet
    (354, "다크펫", "Banette", "👻", "rare", 0.50, 353, None, "none"),  # Banette

    (355, "해골몽", "Duskull", "👻", "common", 0.80, None, 356, "friendship"),  # Duskull
    (356, "미라몽", "Dusclops", "👻", "rare", 0.50, 355, 477, "none"),  # Dusclops

    (357, "트로피우스", "Tropius", "🌿", "rare", 0.50, None, None, "none"),  # Tropius

    (358, "치렁", "Chimecho", "🔮", "rare", 0.50, None, None, "none"),  # Chimecho

    (359, "앱솔", "Absol", "🌑", "rare", 0.50, None, None, "none"),  # Absol

    (360, "마자", "Wynaut", "🔮", "common", 0.80, None, None, "none"),  # Wynaut

    (361, "눈꼬마", "Snorunt", "❄️", "common", 0.80, None, 362, "friendship"),  # Snorunt
    (362, "얼음귀신", "Glalie", "❄️", "rare", 0.50, 361, None, "none"),  # Glalie

    (363, "대굴레오", "Spheal", "❄️", "common", 0.80, None, 364, "friendship"),  # Spheal
    (364, "씨레오", "Sealeo", "❄️", "rare", 0.50, 363, 365, "friendship"),  # Sealeo
    (365, "씨카이저", "Walrein", "❄️", "epic", 0.15, 364, None, "none"),  # Walrein

    (366, "진주몽", "Clamperl", "💧", "common", 0.80, None, 368, "trade"),  # Clamperl
    (367, "헌테일", "Huntail", "💧", "rare", 0.50, 366, None, "none"),  # Huntail
    (368, "분홍장이", "Gorebyss", "💧", "rare", 0.50, 366, None, "none"),  # Gorebyss

    (369, "시라칸", "Relicanth", "💧", "rare", 0.50, None, None, "none"),  # Relicanth

    (370, "사랑동이", "Luvdisc", "💧", "common", 0.80, None, None, "none"),  # Luvdisc

    (371, "아공이", "Bagon", "🐉", "common", 0.80, None, 372, "friendship"),  # Bagon
    (372, "쉘곤", "Shelgon", "🐉", "rare", 0.50, 371, 373, "friendship"),  # Shelgon
    (373, "보만다", "Salamence", "🐉", "epic", 0.15, 372, None, "none"),  # Salamence (3진화 → 에픽)

    (374, "메탕", "Beldum", "⚙️", "common", 0.80, None, 375, "friendship"),  # Beldum
    (375, "메탕구", "Metang", "⚙️", "rare", 0.50, 374, 376, "friendship"),  # Metang
    (376, "메타그로스", "Metagross", "⚙️", "epic", 0.15, 375, None, "none"),  # Metagross (3진화 → 에픽)

    (377, "레지락", "Regirock", "🗿", "legendary", 0.05, None, None, "none"),  # Regirock

    (378, "레지아이스", "Regice", "❄️", "legendary", 0.05, None, None, "none"),  # Regice

    (379, "레지스틸", "Registeel", "⚙️", "legendary", 0.05, None, None, "none"),  # Registeel

    (380, "라티아스", "Latias", "🐉", "legendary", 0.05, None, None, "none"),  # Latias

    (381, "라티오스", "Latios", "🐉", "legendary", 0.05, None, None, "none"),  # Latios

    (382, "가이오가", "Kyogre", "💧", "ultra_legendary", 0.03, None, None, "none"),  # Kyogre

    (383, "그란돈", "Groudon", "🌍", "ultra_legendary", 0.03, None, None, "none"),  # Groudon

    (384, "레쿠쟈", "Rayquaza", "🐉", "ultra_legendary", 0.03, None, None, "none"),  # Rayquaza

    (385, "지라치", "Jirachi", "⚙️", "ultra_legendary", 0.03, None, None, "none"),  # Jirachi

    (386, "테오키스", "Deoxys Normal", "🔮", "ultra_legendary", 0.03, None, None, "none"),  # Deoxys Normal
]
