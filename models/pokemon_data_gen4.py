"""
Gen 4 (387-493) Pokemon data for 4th generation update.
Each tuple: (id, name_ko, name_en, emoji, rarity, catch_rate, evolves_from, evolves_to, evolution_method)
"""

ALL_POKEMON_GEN4 = [
    # --- Turtwig line ---
    (387, "모부기", "Turtwig", "🌿", "common", 0.80, None, 388, "friendship"),
    (388, "수풀부기", "Grotle", "🌿", "rare", 0.50, 387, 389, "friendship"),
    (389, "토대부기", "Torterra", "🌿", "epic", 0.15, 388, None, "none"),

    # --- Chimchar line ---
    (390, "불꽃숭이", "Chimchar", "🔥", "common", 0.80, None, 391, "friendship"),
    (391, "파이숭이", "Monferno", "🔥", "rare", 0.50, 390, 392, "friendship"),
    (392, "초염몽", "Infernape", "🔥", "epic", 0.15, 391, None, "none"),

    # --- Piplup line ---
    (393, "팽도리", "Piplup", "💧", "common", 0.80, None, 394, "friendship"),
    (394, "팽태자", "Prinplup", "💧", "rare", 0.50, 393, 395, "friendship"),
    (395, "엠페르트", "Empoleon", "💧", "epic", 0.15, 394, None, "none"),

    # --- Starly line ---
    (396, "찌르꼬", "Starly", "⭐", "common", 0.80, None, 397, "friendship"),
    (397, "찌르버드", "Staravia", "⭐", "common", 0.80, 396, 398, "friendship"),
    (398, "찌르호크", "Staraptor", "⭐", "rare", 0.50, 397, None, "none"),

    # --- Bidoof line ---
    (399, "비버니", "Bidoof", "⭐", "common", 0.80, None, 400, "friendship"),
    (400, "비버통", "Bibarel", "⭐", "common", 0.80, 399, None, "none"),

    # --- Kricketot line ---
    (401, "귀뚤뚜기", "Kricketot", "🐛", "common", 0.80, None, 402, "friendship"),
    (402, "귀뚤톡크", "Kricketune", "🐛", "common", 0.80, 401, None, "none"),

    # --- Shinx line ---
    (403, "꼬링크", "Shinx", "⚡", "common", 0.80, None, 404, "friendship"),
    (404, "럭시오", "Luxio", "⚡", "rare", 0.50, 403, 405, "friendship"),
    (405, "렌트라", "Luxray", "⚡", "epic", 0.15, 404, None, "none"),

    # --- Budew / Roserade (cross-gen evolutions) ---
    (406, "꼬몽울", "Budew", "🌿", "common", 0.80, None, 315, "friendship"),
    (407, "로즈레이드", "Roserade", "🌿", "epic", 0.15, 315, None, "none"),

    # --- Cranidos line ---
    (408, "두개도스", "Cranidos", "🪨", "rare", 0.50, None, 409, "friendship"),
    (409, "램펄드", "Rampardos", "🪨", "epic", 0.15, 408, None, "none"),

    # --- Shieldon line ---
    (410, "방패톱스", "Shieldon", "🪨", "rare", 0.50, None, 411, "friendship"),
    (411, "바리톱스", "Bastiodon", "🪨", "epic", 0.15, 410, None, "none"),

    # --- Burmy line ---
    (412, "도롱충이", "Burmy", "🐛", "common", 0.80, None, 413, "friendship"),
    (413, "도롱마담", "Wormadam", "🐛", "rare", 0.50, 412, None, "none"),
    (414, "나메일", "Mothim", "🐛", "rare", 0.50, 412, None, "none"),

    # --- Combee / Vespiquen ---
    (415, "세꿀버리", "Combee", "🐛", "common", 0.80, None, 416, "friendship"),
    (416, "비퀸", "Vespiquen", "🐛", "rare", 0.50, 415, None, "none"),

    # --- Pachirisu ---
    (417, "파치리스", "Pachirisu", "⚡", "common", 0.80, None, None, "none"),

    # --- Buizel line ---
    (418, "브이젤", "Buizel", "💧", "common", 0.80, None, 419, "friendship"),
    (419, "플로젤", "Floatzel", "💧", "rare", 0.50, 418, None, "none"),

    # --- Cherubi line ---
    (420, "체리버", "Cherubi", "🌿", "common", 0.80, None, 421, "friendship"),
    (421, "체리꼬", "Cherrim", "🌿", "common", 0.80, 420, None, "none"),

    # --- Shellos line ---
    (422, "깝질무", "Shellos", "💧", "common", 0.80, None, 423, "friendship"),
    (423, "트리토돈", "Gastrodon", "💧", "rare", 0.50, 422, None, "none"),

    # --- Ambipom (cross-gen) ---
    (424, "겟핸보숭", "Ambipom", "⭐", "rare", 0.50, 190, None, "none"),

    # --- Drifloon line ---
    (425, "흔들풍손", "Drifloon", "👻", "common", 0.80, None, 426, "friendship"),
    (426, "둥실라이드", "Drifblim", "👻", "rare", 0.50, 425, None, "none"),

    # --- Buneary line ---
    (427, "이어롤", "Buneary", "⭐", "common", 0.80, None, 428, "friendship"),
    (428, "이어롭", "Lopunny", "⭐", "rare", 0.50, 427, None, "none"),

    # --- Mismagius (cross-gen) ---
    (429, "무우마직", "Mismagius", "👻", "epic", 0.15, 200, None, "none"),

    # --- Honchkrow (cross-gen) ---
    (430, "돈크로우", "Honchkrow", "🌑", "epic", 0.15, 198, None, "none"),

    # --- Glameow line ---
    (431, "나옹마", "Glameow", "⭐", "common", 0.80, None, 432, "friendship"),
    (432, "몬냥이", "Purugly", "⭐", "rare", 0.50, 431, None, "none"),

    # --- Chingling (cross-gen baby) ---
    (433, "랑딸랑", "Chingling", "🔮", "common", 0.80, None, 358, "friendship"),

    # --- Stunky line ---
    (434, "스컹뿡", "Stunky", "🌑", "common", 0.80, None, 435, "friendship"),
    (435, "스컹탱크", "Skuntank", "🌑", "rare", 0.50, 434, None, "none"),

    # --- Bronzor line ---
    (436, "동미러", "Bronzor", "⚙️", "common", 0.80, None, 437, "friendship"),
    (437, "동탁군", "Bronzong", "⚙️", "rare", 0.50, 436, None, "none"),

    # --- Bonsly (cross-gen baby) ---
    (438, "꼬지지", "Bonsly", "🪨", "common", 0.80, None, 185, "friendship"),

    # --- Mime Jr. (cross-gen baby) ---
    (439, "흉내내", "Mime Jr.", "🔮", "common", 0.80, None, 122, "friendship"),

    # --- Happiny (cross-gen baby) ---
    (440, "핑복", "Happiny", "⭐", "common", 0.80, None, 113, "friendship"),

    # --- Chatot ---
    (441, "페라페", "Chatot", "⭐", "common", 0.80, None, None, "none"),

    # --- Spiritomb ---
    (442, "화강돌", "Spiritomb", "👻", "epic", 0.15, None, None, "none"),

    # --- Gible line ---
    (443, "딥상어동", "Gible", "🐉", "rare", 0.50, None, 444, "friendship"),
    (444, "한바이트", "Gabite", "🐉", "rare", 0.50, 443, 445, "friendship"),
    (445, "한카리아스", "Garchomp", "🐉", "epic", 0.15, 444, None, "none"),

    # --- Munchlax (cross-gen baby) ---
    (446, "먹고자", "Munchlax", "⭐", "rare", 0.50, None, 143, "friendship"),

    # --- Riolu line ---
    (447, "리오르", "Riolu", "⭐", "rare", 0.50, None, 448, "friendship"),
    (448, "루카리오", "Lucario", "⭐", "epic", 0.15, 447, None, "none"),

    # --- Hippopotas line ---
    (449, "히포포타스", "Hippopotas", "🌍", "common", 0.80, None, 450, "friendship"),
    (450, "하마돈", "Hippowdon", "🌍", "rare", 0.50, 449, None, "none"),

    # --- Skorupi line ---
    (451, "스콜피", "Skorupi", "🌑", "common", 0.80, None, 452, "friendship"),
    (452, "드래피온", "Drapion", "🌑", "rare", 0.50, 451, None, "none"),

    # --- Croagunk line ---
    (453, "삐딱구리", "Croagunk", "🌑", "common", 0.80, None, 454, "friendship"),
    (454, "독개굴", "Toxicroak", "🌑", "rare", 0.50, 453, None, "none"),

    # --- Carnivine ---
    (455, "무스틈니", "Carnivine", "🌿", "rare", 0.50, None, None, "none"),

    # --- Finneon line ---
    (456, "형광어", "Finneon", "💧", "common", 0.80, None, 457, "friendship"),
    (457, "네오라이트", "Lumineon", "💧", "rare", 0.50, 456, None, "none"),

    # --- Mantyke (cross-gen baby) ---
    (458, "타만타", "Mantyke", "💧", "common", 0.80, None, 226, "friendship"),

    # --- Snover line ---
    (459, "눈쓰개", "Snover", "❄️", "common", 0.80, None, 460, "friendship"),
    (460, "눈설왕", "Abomasnow", "❄️", "rare", 0.50, 459, None, "none"),

    # --- Weavile (cross-gen) ---
    (461, "포푸니라", "Weavile", "🌑", "epic", 0.15, 215, None, "none"),

    # --- Magnezone (cross-gen) ---
    (462, "자포코일", "Magnezone", "⚡", "epic", 0.15, 82, None, "none"),

    # --- Lickilicky (cross-gen) ---
    (463, "내룸벨트", "Lickilicky", "⭐", "rare", 0.50, 108, None, "none"),

    # --- Rhyperior (cross-gen) ---
    (464, "거대코뿌리", "Rhyperior", "🌍", "epic", 0.15, 112, None, "none"),

    # --- Tangrowth (cross-gen) ---
    (465, "덩쿠림보", "Tangrowth", "🌿", "rare", 0.50, 114, None, "none"),

    # --- Electivire (cross-gen) ---
    (466, "에레키블", "Electivire", "⚡", "epic", 0.15, 125, None, "none"),

    # --- Magmortar (cross-gen) ---
    (467, "마그마번", "Magmortar", "🔥", "epic", 0.15, 126, None, "none"),

    # --- Togekiss (cross-gen) ---
    (468, "토게키스", "Togekiss", "⭐", "epic", 0.15, 176, None, "none"),

    # --- Yanmega (cross-gen) ---
    (469, "메가자리", "Yanmega", "🐛", "rare", 0.50, 193, None, "none"),

    # --- Leafeon (cross-gen Eevee) ---
    (470, "리피아", "Leafeon", "🌿", "epic", 0.15, 133, None, "none"),

    # --- Glaceon (cross-gen Eevee) ---
    (471, "글레이시아", "Glaceon", "❄️", "epic", 0.15, 133, None, "none"),

    # --- Gliscor (cross-gen) ---
    (472, "글라이온", "Gliscor", "🌍", "rare", 0.50, 207, None, "none"),

    # --- Mamoswine (cross-gen) ---
    (473, "맘모꾸리", "Mamoswine", "❄️", "epic", 0.15, 221, None, "none"),

    # --- Porygon-Z (cross-gen) ---
    (474, "폴리곤Z", "Porygon-Z", "⭐", "epic", 0.15, 233, None, "none"),

    # --- Gallade (cross-gen) ---
    (475, "엘레이드", "Gallade", "🔮", "epic", 0.15, 281, None, "none"),

    # --- Probopass (cross-gen) ---
    (476, "대코파스", "Probopass", "🪨", "rare", 0.50, 299, None, "none"),

    # --- Dusknoir (cross-gen) ---
    (477, "야느와르몽", "Dusknoir", "👻", "epic", 0.15, 356, None, "none"),

    # --- Froslass (cross-gen) ---
    (478, "눈여아", "Froslass", "❄️", "epic", 0.15, 361, None, "none"),

    # --- Rotom ---
    (479, "로토무", "Rotom", "⚡", "epic", 0.15, None, None, "none"),

    # --- Uxie ---
    (480, "유크시", "Uxie", "🔮", "legendary", 0.05, None, None, "none"),

    # --- Mesprit ---
    (481, "엠라이트", "Mesprit", "🔮", "legendary", 0.05, None, None, "none"),

    # --- Azelf ---
    (482, "아그놈", "Azelf", "🔮", "legendary", 0.05, None, None, "none"),

    # --- Dialga ---
    (483, "디아루가", "Dialga", "🐉", "ultra_legendary", 0.03, None, None, "none"),

    # --- Palkia ---
    (484, "펄기아", "Palkia", "🐉", "ultra_legendary", 0.03, None, None, "none"),

    # --- Heatran ---
    (485, "히드런", "Heatran", "🔥", "legendary", 0.05, None, None, "none"),

    # --- Regigigas ---
    (486, "레지기가스", "Regigigas", "⭐", "legendary", 0.08, None, None, "none"),

    # --- Giratina ---
    (487, "기라티나", "Giratina", "👻", "ultra_legendary", 0.03, None, None, "none"),

    # --- Cresselia ---
    (488, "크레세리아", "Cresselia", "🔮", "legendary", 0.05, None, None, "none"),

    # --- Phione ---
    (489, "피오네", "Phione", "💧", "legendary", 0.05, None, None, "none"),

    # --- Manaphy ---
    (490, "마나피", "Manaphy", "💧", "ultra_legendary", 0.03, None, None, "none"),

    # --- Darkrai ---
    (491, "다크라이", "Darkrai", "🌑", "ultra_legendary", 0.03, None, None, "none"),

    # --- Shaymin ---
    (492, "쉐이미", "Shaymin", "🌿", "ultra_legendary", 0.03, None, None, "none"),

    # --- Arceus ---
    (493, "아르세우스", "Arceus", "⭐", "ultra_legendary", 0.03, None, None, "none"),
]
