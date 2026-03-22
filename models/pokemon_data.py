"""
Complete Gen 1+2 (251) Pokemon data.
Each tuple: (id, name_ko, name_en, emoji, rarity, catch_rate, evolves_from, evolves_to, evolution_method)
evolution_method: 'friendship', 'trade', 'none'
"""

ALL_POKEMON = [
    # --- Bulbasaur line ---
    (1, "이상해씨", "Bulbasaur", "🌱", "common", 0.80, None, 2, "friendship"),
    (2, "이상해풀", "Ivysaur", "🌿", "rare", 0.50, 1, 3, "friendship"),
    (3, "이상해꽃", "Venusaur", "🌺", "epic", 0.15, 2, None, "none"),

    # --- Charmander line ---
    (4, "파이리", "Charmander", "🔥", "common", 0.80, None, 5, "friendship"),
    (5, "리자드", "Charmeleon", "🔥", "rare", 0.50, 4, 6, "friendship"),
    (6, "리자몽", "Charizard", "🔥", "epic", 0.15, 5, None, "none"),

    # --- Squirtle line ---
    (7, "꼬부기", "Squirtle", "💧", "common", 0.80, None, 8, "friendship"),
    (8, "어니부기", "Wartortle", "💧", "rare", 0.50, 7, 9, "friendship"),
    (9, "거북왕", "Blastoise", "💧", "epic", 0.15, 8, None, "none"),

    # --- Caterpie line ---
    (10, "캐터피", "Caterpie", "🐛", "common", 0.80, None, 11, "friendship"),
    (11, "단데기", "Metapod", "🐛", "common", 0.80, 10, 12, "friendship"),
    (12, "버터플", "Butterfree", "🦋", "common", 0.80, 11, None, "none"),

    # --- Weedle line ---
    (13, "뿔충이", "Weedle", "🐛", "common", 0.80, None, 14, "friendship"),
    (14, "딱충이", "Kakuna", "🐛", "common", 0.80, 13, 15, "friendship"),
    (15, "독침붕", "Beedrill", "🐝", "common", 0.80, 14, None, "none"),

    # --- Pidgey line ---
    (16, "구구", "Pidgey", "🐦", "common", 0.80, None, 17, "friendship"),
    (17, "피죤", "Pidgeotto", "🐦", "common", 0.80, 16, 18, "friendship"),
    (18, "피죤투", "Pidgeot", "🦅", "rare", 0.50, 17, None, "none"),

    # --- Rattata line ---
    (19, "꼬렛", "Rattata", "🐀", "common", 0.80, None, 20, "friendship"),
    (20, "레트라", "Raticate", "🐀", "rare", 0.50, 19, None, "none"),

    # --- Spearow line ---
    (21, "깨비참", "Spearow", "🐦", "common", 0.80, None, 22, "friendship"),
    (22, "깨비드릴조", "Fearow", "🦅", "rare", 0.50, 21, None, "none"),

    # --- Ekans line ---
    (23, "아보", "Ekans", "🐍", "common", 0.80, None, 24, "friendship"),
    (24, "아보크", "Arbok", "🐍", "rare", 0.50, 23, None, "none"),

    # --- Pikachu line ---
    (25, "피카츄", "Pikachu", "⚡", "common", 0.80, None, 26, "friendship"),
    (26, "라이츄", "Raichu", "⚡", "rare", 0.50, 25, None, "none"),

    # --- Sandshrew line ---
    (27, "모래두지", "Sandshrew", "🏜️", "common", 0.80, None, 28, "friendship"),
    (28, "고지", "Sandslash", "🏜️", "rare", 0.50, 27, None, "none"),

    # --- Nidoran♀ line ---
    (29, "니드런♀", "Nidoran♀", "💜", "common", 0.80, None, 30, "friendship"),
    (30, "니드리나", "Nidorina", "💜", "common", 0.80, 29, 31, "friendship"),
    (31, "니드퀸", "Nidoqueen", "💜", "epic", 0.15, 30, None, "none"),

    # --- Nidoran♂ line ---
    (32, "니드런♂", "Nidoran♂", "💙", "common", 0.80, None, 33, "friendship"),
    (33, "니드리노", "Nidorino", "💙", "common", 0.80, 32, 34, "friendship"),
    (34, "니드킹", "Nidoking", "💙", "epic", 0.15, 33, None, "none"),

    # --- Clefairy line ---
    (35, "삐삐", "Clefairy", "🌙", "common", 0.80, None, 36, "friendship"),
    (36, "픽시", "Clefable", "🌙", "rare", 0.50, 35, None, "none"),

    # --- Vulpix line ---
    (37, "식스테일", "Vulpix", "🦊", "common", 0.80, None, 38, "friendship"),
    (38, "나인테일", "Ninetales", "🦊", "rare", 0.50, 37, None, "none"),

    # --- Jigglypuff line ---
    (39, "푸린", "Jigglypuff", "🎤", "common", 0.80, None, 40, "friendship"),
    (40, "푸크린", "Wigglytuff", "🎤", "rare", 0.50, 39, None, "none"),

    # --- Zubat line ---
    (41, "주뱃", "Zubat", "🦇", "common", 0.80, None, 42, "friendship"),
    (42, "골뱃", "Golbat", "🦇", "rare", 0.50, 41, None, "none"),

    # --- Oddish line ---
    (43, "뚜벅쵸", "Oddish", "🌱", "common", 0.80, None, 44, "friendship"),
    (44, "냄새꼬", "Gloom", "🌱", "common", 0.80, 43, 45, "friendship"),
    (45, "라플레시아", "Vileplume", "🌸", "rare", 0.50, 44, None, "none"),

    # --- Paras line ---
    (46, "파라스", "Paras", "🍄", "common", 0.80, None, 47, "friendship"),
    (47, "파라섹트", "Parasect", "🍄", "rare", 0.50, 46, None, "none"),

    # --- Venonat line ---
    (48, "콘팡", "Venonat", "🐛", "common", 0.80, None, 49, "friendship"),
    (49, "도나리", "Venomoth", "🦋", "rare", 0.50, 48, None, "none"),

    # --- Diglett line ---
    (50, "디그다", "Diglett", "🕳️", "common", 0.80, None, 51, "friendship"),
    (51, "닥트리오", "Dugtrio", "🕳️", "rare", 0.50, 50, None, "none"),

    # --- Meowth line ---
    (52, "나옹", "Meowth", "🐱", "common", 0.80, None, 53, "friendship"),
    (53, "페르시온", "Persian", "🐱", "rare", 0.50, 52, None, "none"),

    # --- Psyduck line ---
    (54, "고라파덕", "Psyduck", "🦆", "common", 0.80, None, 55, "friendship"),
    (55, "골덕", "Golduck", "🦆", "rare", 0.50, 54, None, "none"),

    # --- Mankey line ---
    (56, "망키", "Mankey", "🐵", "common", 0.80, None, 57, "friendship"),
    (57, "성원숭", "Primeape", "🐵", "rare", 0.50, 56, None, "none"),

    # --- Growlithe line ---
    (58, "가디", "Growlithe", "🐕", "common", 0.80, None, 59, "friendship"),
    (59, "윈디", "Arcanine", "🐕", "epic", 0.15, 58, None, "none"),

    # --- Poliwag line ---
    (60, "발챙이", "Poliwag", "💧", "common", 0.80, None, 61, "friendship"),
    (61, "슈륙챙이", "Poliwhirl", "💧", "common", 0.80, 60, 62, "friendship"),
    (62, "강챙이", "Poliwrath", "💧", "epic", 0.15, 61, None, "none"),

    # --- Abra line (Kadabra evolves by trade) ---
    (63, "캐이시", "Abra", "🔮", "common", 0.80, None, 64, "friendship"),
    (64, "윤겔라", "Kadabra", "🔮", "rare", 0.50, 63, 65, "trade"),
    (65, "후딘", "Alakazam", "🔮", "epic", 0.15, 64, None, "none"),

    # --- Machop line (Machoke evolves by trade) ---
    (66, "알통몬", "Machop", "💪", "common", 0.80, None, 67, "friendship"),
    (67, "근육몬", "Machoke", "💪", "rare", 0.50, 66, 68, "trade"),
    (68, "괴력몬", "Machamp", "💪", "epic", 0.15, 67, None, "none"),

    # --- Bellsprout line ---
    (69, "모다피", "Bellsprout", "🌱", "common", 0.80, None, 70, "friendship"),
    (70, "우츠동", "Weepinbell", "🌱", "common", 0.80, 69, 71, "friendship"),
    (71, "우츠보트", "Victreebel", "🌱", "rare", 0.50, 70, None, "none"),

    # --- Tentacool line ---
    (72, "왕눈해", "Tentacool", "🪼", "common", 0.80, None, 73, "friendship"),
    (73, "독파리", "Tentacruel", "🪼", "epic", 0.15, 72, None, "none"),

    # --- Geodude line (Graveler evolves by trade) ---
    (74, "꼬마돌", "Geodude", "🪨", "common", 0.80, None, 75, "friendship"),
    (75, "데구리", "Graveler", "🪨", "common", 0.80, 74, 76, "trade"),
    (76, "딱구리", "Golem", "🪨", "rare", 0.50, 75, None, "none"),

    # --- Ponyta line ---
    (77, "포니타", "Ponyta", "🐴", "rare", 0.50, None, 78, "friendship"),
    (78, "날쌩마", "Rapidash", "🐴", "rare", 0.50, 77, None, "none"),

    # --- Slowpoke line ---
    (79, "야돈", "Slowpoke", "🦛", "common", 0.80, None, 80, "friendship"),
    (80, "야도란", "Slowbro", "🦛", "rare", 0.50, 79, None, "none"),

    # --- Magnemite line ---
    (81, "코일", "Magnemite", "🧲", "common", 0.80, None, 82, "friendship"),
    (82, "레어코일", "Magneton", "🧲", "rare", 0.50, 81, 462, "friendship"),

    # --- Farfetch'd (no evolution) ---
    (83, "파오리", "Farfetch'd", "🦆", "common", 0.80, None, None, "none"),

    # --- Doduo line ---
    (84, "두두", "Doduo", "🐦", "common", 0.80, None, 85, "friendship"),
    (85, "두트리오", "Dodrio", "🐦", "rare", 0.50, 84, None, "none"),

    # --- Seel line ---
    (86, "쥬쥬", "Seel", "🦭", "common", 0.80, None, 87, "friendship"),
    (87, "쥬레곤", "Dewgong", "🦭", "rare", 0.50, 86, None, "none"),

    # --- Grimer line ---
    (88, "질퍽이", "Grimer", "🟢", "common", 0.80, None, 89, "friendship"),
    (89, "질뻐기", "Muk", "🟢", "epic", 0.15, 88, None, "none"),

    # --- Shellder line ---
    (90, "셀러", "Shellder", "🐚", "common", 0.80, None, 91, "friendship"),
    (91, "파르셀", "Cloyster", "🐚", "epic", 0.15, 90, None, "none"),

    # --- Gastly line (Haunter evolves by trade) ---
    (92, "고오스", "Gastly", "👻", "common", 0.80, None, 93, "friendship"),
    (93, "고우스트", "Haunter", "👻", "rare", 0.50, 92, 94, "trade"),
    (94, "팬텀", "Gengar", "👻", "epic", 0.15, 93, None, "none"),

    # --- Onix → Steelix (trade evolution) ---
    (95, "롱스톤", "Onix", "🪨", "common", 0.80, None, 208, "trade"),

    # --- Drowzee line ---
    (96, "슬리프", "Drowzee", "😴", "common", 0.80, None, 97, "friendship"),
    (97, "슬리퍼", "Hypno", "😴", "rare", 0.50, 96, None, "none"),

    # --- Krabby line ---
    (98, "크랩", "Krabby", "🦀", "common", 0.80, None, 99, "friendship"),
    (99, "킹크랩", "Kingler", "🦀", "rare", 0.50, 98, None, "none"),

    # --- Voltorb line ---
    (100, "찌리리공", "Voltorb", "⚡", "common", 0.80, None, 101, "friendship"),
    (101, "붐볼", "Electrode", "⚡", "rare", 0.50, 100, None, "none"),

    # --- Exeggcute line ---
    (102, "아라리", "Exeggcute", "🥚", "common", 0.80, None, 103, "friendship"),
    (103, "나시", "Exeggutor", "🌴", "epic", 0.15, 102, None, "none"),

    # --- Cubone line ---
    (104, "탕구리", "Cubone", "🦴", "common", 0.80, None, 105, "friendship"),
    (105, "텅구리", "Marowak", "🦴", "rare", 0.50, 104, None, "none"),

    # --- Hitmonlee (no evolution) ---
    (106, "시라소몬", "Hitmonlee", "🦵", "rare", 0.50, None, None, "none"),

    # --- Hitmonchan (no evolution) ---
    (107, "홍수몬", "Hitmonchan", "🥊", "rare", 0.50, None, None, "none"),

    # --- Lickitung (no evolution in Gen1) ---
    (108, "내루미", "Lickitung", "👅", "common", 0.80, None, 463, "friendship"),

    # --- Koffing line ---
    (109, "또가스", "Koffing", "💨", "common", 0.80, None, 110, "friendship"),
    (110, "또도가스", "Weezing", "💨", "rare", 0.50, 109, None, "none"),

    # --- Rhyhorn line ---
    (111, "뿔카노", "Rhyhorn", "🦏", "common", 0.80, None, 112, "friendship"),
    (112, "코뿌리", "Rhydon", "🦏", "rare", 0.50, 111, 464, "friendship"),

    # --- Chansey (no evolution in Gen1) ---
    (113, "럭키", "Chansey", "🥚", "rare", 0.50, None, None, "none"),

    # --- Tangela (no evolution in Gen1) ---
    (114, "덩쿠리", "Tangela", "🌿", "rare", 0.50, None, 465, "friendship"),

    # --- Kangaskhan (no evolution) ---
    (115, "캥카", "Kangaskhan", "🦘", "rare", 0.50, None, None, "none"),

    # --- Horsea line ---
    (116, "쏘드라", "Horsea", "🐉", "common", 0.80, None, 117, "friendship"),
    (117, "시드라", "Seadra", "🐉", "rare", 0.50, 116, 230, "trade"),

    # --- Goldeen line ---
    (118, "콘치", "Goldeen", "🐟", "common", 0.80, None, 119, "friendship"),
    (119, "왕콘치", "Seaking", "🐟", "rare", 0.50, 118, None, "none"),

    # --- Staryu line ---
    (120, "별가사리", "Staryu", "⭐", "common", 0.80, None, 121, "friendship"),
    (121, "아쿠스타", "Starmie", "⭐", "epic", 0.15, 120, None, "none"),

    # --- Mr. Mime (no evolution in Gen1) ---
    (122, "마임맨", "Mr. Mime", "🤡", "rare", 0.50, None, None, "none"),

    # --- Scyther → Scizor (trade evolution) ---
    (123, "스라크", "Scyther", "🗡️", "epic", 0.15, None, 212, "trade"),

    # --- Jynx (no evolution in Gen1) ---
    (124, "루주라", "Jynx", "💋", "rare", 0.50, None, None, "none"),

    # --- Electabuzz (no evolution in Gen1) ---
    (125, "에레브", "Electabuzz", "⚡", "rare", 0.50, None, 466, "friendship"),

    # --- Magmar (no evolution in Gen1) ---
    (126, "마그마", "Magmar", "🔥", "rare", 0.50, None, 467, "friendship"),

    # --- Pinsir (no evolution) ---
    (127, "쁘사이저", "Pinsir", "🪲", "epic", 0.15, None, None, "none"),

    # --- Tauros (no evolution) ---
    (128, "켄타로스", "Tauros", "🐂", "rare", 0.50, None, None, "none"),

    # --- Magikarp line ---
    (129, "잉어킹", "Magikarp", "🐟", "common", 0.80, None, 130, "friendship"),
    (130, "갸라도스", "Gyarados", "🐲", "epic", 0.15, 129, None, "none"),

    # --- Lapras (no evolution) ---
    (131, "라프라스", "Lapras", "🐢", "epic", 0.15, None, None, "none"),

    # --- Ditto (no evolution) ---
    (132, "메타몽", "Ditto", "🟣", "common", 0.80, None, None, "none"),

    # --- Eevee line (special: random evolution) ---
    (133, "이브이", "Eevee", "🦊", "common", 0.80, None, None, "friendship"),
    (134, "샤미드", "Vaporeon", "💧", "epic", 0.15, 133, None, "none"),
    (135, "쥬피썬더", "Jolteon", "⚡", "epic", 0.15, 133, None, "none"),
    (136, "부스터", "Flareon", "🔥", "epic", 0.15, 133, None, "none"),

    # --- Porygon → Porygon2 (trade evolution) ---
    (137, "폴리곤", "Porygon", "🤖", "common", 0.80, None, 233, "trade"),

    # --- Omanyte line ---
    (138, "암나이트", "Omanyte", "🐚", "common", 0.80, None, 139, "friendship"),
    (139, "암스타", "Omastar", "🐚", "rare", 0.50, 138, None, "none"),

    # --- Kabuto line ---
    (140, "투구", "Kabuto", "🦀", "common", 0.80, None, 141, "friendship"),
    (141, "투구푸스", "Kabutops", "🦀", "rare", 0.50, 140, None, "none"),

    # --- Aerodactyl (no evolution) ---
    (142, "프테라", "Aerodactyl", "🦖", "epic", 0.15, None, None, "none"),

    # --- Snorlax (no evolution in Gen1) ---
    (143, "잠만보", "Snorlax", "😴", "epic", 0.15, None, None, "none"),

    # --- Articuno ---
    (144, "프리저", "Articuno", "❄️", "legendary", 0.05, None, None, "none"),

    # --- Zapdos ---
    (145, "썬더", "Zapdos", "⚡", "legendary", 0.05, None, None, "none"),

    # --- Moltres ---
    (146, "파이어", "Moltres", "🔥", "legendary", 0.05, None, None, "none"),

    # --- Dratini line ---
    (147, "미뇽", "Dratini", "🐉", "common", 0.80, None, 148, "friendship"),
    (148, "신뇽", "Dragonair", "🐉", "rare", 0.50, 147, 149, "friendship"),
    (149, "망나뇽", "Dragonite", "🐉", "epic", 0.15, 148, None, "none"),

    # --- Mewtwo ---
    (150, "뮤츠", "Mewtwo", "🧬", "ultra_legendary", 0.03, None, None, "none"),

    # --- Mew ---
    (151, "뮤", "Mew", "🩷", "legendary", 0.05, None, None, "none"),

    # ============================================================
    # Gen 2 — Johto (152-251)
    # ============================================================

    # --- Chikorita line (Grass starter) ---
    (152, "치코리타", "Chikorita", "🌿", "common", 0.80, None, 153, "friendship"),
    (153, "베이리프", "Bayleef", "🌿", "rare", 0.50, 152, 154, "friendship"),
    (154, "메가니움", "Meganium", "🌺", "epic", 0.15, 153, None, "none"),

    # --- Cyndaquil line (Fire starter) ---
    (155, "브케인", "Cyndaquil", "🔥", "common", 0.80, None, 156, "friendship"),
    (156, "마그케인", "Quilava", "🔥", "rare", 0.50, 155, 157, "friendship"),
    (157, "블레이범", "Typhlosion", "🔥", "epic", 0.15, 156, None, "none"),

    # --- Totodile line (Water starter) ---
    (158, "리아코", "Totodile", "💧", "common", 0.80, None, 159, "friendship"),
    (159, "엘리게이", "Croconaw", "💧", "rare", 0.50, 158, 160, "friendship"),
    (160, "장크로다일", "Feraligatr", "💧", "epic", 0.15, 159, None, "none"),

    # --- Sentret line ---
    (161, "꼬리선", "Sentret", "🐿️", "common", 0.80, None, 162, "friendship"),
    (162, "다꼬리", "Furret", "🐿️", "rare", 0.50, 161, None, "none"),

    # --- Hoothoot line ---
    (163, "부우부", "Hoothoot", "🦉", "common", 0.80, None, 164, "friendship"),
    (164, "야부엉", "Noctowl", "🦉", "rare", 0.50, 163, None, "none"),

    # --- Ledyba line ---
    (165, "레디바", "Ledyba", "🐛", "common", 0.80, None, 166, "friendship"),
    (166, "레디안", "Ledian", "🐛", "common", 0.80, 165, None, "none"),

    # --- Spinarak line ---
    (167, "페이검", "Spinarak", "🕷️", "common", 0.80, None, 168, "friendship"),
    (168, "아리아도스", "Ariados", "🕷️", "rare", 0.50, 167, None, "none"),

    # --- Crobat (evo from Golbat 42) ---
    (169, "크로뱃", "Crobat", "🦇", "epic", 0.15, 42, None, "none"),

    # --- Chinchou line ---
    (170, "초라기", "Chinchou", "💧", "common", 0.80, None, 171, "friendship"),
    (171, "랜턴", "Lanturn", "💧", "rare", 0.50, 170, None, "none"),

    # --- Baby Pokemon ---
    (172, "피츄", "Pichu", "⚡", "common", 0.80, None, 25, "friendship"),
    (173, "삐", "Cleffa", "⭐", "common", 0.80, None, 35, "friendship"),
    (174, "푸푸린", "Igglybuff", "🎵", "common", 0.80, None, 39, "friendship"),

    # --- Togepi line ---
    (175, "토게피", "Togepi", "⭐", "common", 0.80, None, 176, "friendship"),
    (176, "토게틱", "Togetic", "⭐", "common", 0.80, 175, 468, "friendship"),

    # --- Natu line ---
    (177, "네이티", "Natu", "🔮", "common", 0.80, None, 178, "friendship"),
    (178, "네이티오", "Xatu", "🔮", "rare", 0.50, 177, None, "none"),

    # --- Mareep line ---
    (179, "메리프", "Mareep", "⚡", "common", 0.80, None, 180, "friendship"),
    (180, "보송송", "Flaaffy", "⚡", "common", 0.80, 179, 181, "friendship"),
    (181, "전룡", "Ampharos", "⚡", "epic", 0.15, 180, None, "none"),

    # --- Bellossom (alt evo from Gloom 44) ---
    (182, "아르코", "Bellossom", "🌺", "rare", 0.50, 44, None, "none"),

    # --- Marill line ---
    (183, "마릴", "Marill", "💧", "common", 0.80, None, 184, "friendship"),
    (184, "마릴리", "Azumarill", "💧", "rare", 0.50, 183, None, "none"),

    # --- Sudowoodo ---
    (185, "꼬지모", "Sudowoodo", "🪨", "rare", 0.50, None, None, "none"),

    # --- Politoed (trade evo from Poliwhirl 61) ---
    (186, "왕구리", "Politoed", "💧", "epic", 0.15, 61, None, "none"),

    # --- Hoppip line ---
    (187, "통통코", "Hoppip", "🌿", "common", 0.80, None, 188, "friendship"),
    (188, "두코", "Skiploom", "🌿", "common", 0.80, 187, 189, "friendship"),
    (189, "솜솜코", "Jumpluff", "🌿", "rare", 0.50, 188, None, "none"),

    # --- Aipom ---
    (190, "에이팜", "Aipom", "🐒", "common", 0.80, None, 424, "friendship"),

    # --- Sunkern line ---
    (191, "해너츠", "Sunkern", "🌻", "common", 0.80, None, 192, "friendship"),
    (192, "해루미", "Sunflora", "🌻", "rare", 0.50, 191, None, "none"),

    # --- Yanma ---
    (193, "왕자리", "Yanma", "🪰", "common", 0.80, None, 469, "friendship"),

    # --- Wooper line ---
    (194, "우파", "Wooper", "💧", "common", 0.80, None, 195, "friendship"),
    (195, "누오", "Quagsire", "💧", "rare", 0.50, 194, None, "none"),

    # --- Espeon (evo from Eevee 133) ---
    (196, "에브이", "Espeon", "🔮", "epic", 0.15, 133, None, "none"),

    # --- Umbreon (evo from Eevee 133) ---
    (197, "블래키", "Umbreon", "🌙", "epic", 0.15, 133, None, "none"),

    # --- Murkrow ---
    (198, "니로우", "Murkrow", "🌙", "rare", 0.50, None, 430, "friendship"),

    # --- Slowking (trade evo from Slowpoke 79) ---
    (199, "야도킹", "Slowking", "🔮", "rare", 0.50, 79, None, "none"),

    # --- Misdreavus ---
    (200, "무우마", "Misdreavus", "👻", "rare", 0.50, None, 429, "friendship"),

    # --- Unown ---
    (201, "안농", "Unown", "🔮", "common", 0.80, None, None, "none"),

    # --- Wobbuffet ---
    (202, "마자용", "Wobbuffet", "🔮", "rare", 0.50, None, None, "none"),

    # --- Girafarig ---
    (203, "키링키", "Girafarig", "🔮", "rare", 0.50, None, None, "none"),

    # --- Pineco line ---
    (204, "피콘", "Pineco", "🐛", "common", 0.80, None, 205, "friendship"),
    (205, "쏘콘", "Forretress", "🐛", "rare", 0.50, 204, None, "none"),

    # --- Dunsparce ---
    (206, "노고치", "Dunsparce", "🐍", "rare", 0.50, None, None, "none"),

    # --- Gligar ---
    (207, "글라이거", "Gligar", "🦂", "rare", 0.50, None, 472, "friendship"),

    # --- Steelix (trade evo from Onix 95) ---
    (208, "강철톤", "Steelix", "⚙️", "epic", 0.15, 95, None, "none"),

    # --- Snubbull line ---
    (209, "블루", "Snubbull", "🧚", "common", 0.80, None, 210, "friendship"),
    (210, "그랑블루", "Granbull", "🧚", "rare", 0.50, 209, None, "none"),

    # --- Qwilfish ---
    (211, "침바루", "Qwilfish", "💧", "rare", 0.50, None, None, "none"),

    # --- Scizor (trade evo from Scyther 123) ---
    (212, "핫삼", "Scizor", "🐛", "epic", 0.15, 123, None, "none"),

    # --- Shuckle ---
    (213, "단단지", "Shuckle", "🐛", "epic", 0.15, None, None, "none"),

    # --- Heracross ---
    (214, "헤라크로스", "Heracross", "🐛", "epic", 0.15, None, None, "none"),

    # --- Sneasel ---
    (215, "포푸니", "Sneasel", "🌙", "rare", 0.50, None, 461, "friendship"),

    # --- Teddiursa line ---
    (216, "깜지곰", "Teddiursa", "🐻", "common", 0.80, None, 217, "friendship"),
    (217, "링곰", "Ursaring", "🐻", "epic", 0.15, 216, None, "none"),

    # --- Slugma line ---
    (218, "마그마그", "Slugma", "🔥", "common", 0.80, None, 219, "friendship"),
    (219, "마그카르고", "Magcargo", "🔥", "rare", 0.50, 218, None, "none"),

    # --- Swinub line ---
    (220, "꾸꾸리", "Swinub", "❄️", "common", 0.80, None, 221, "friendship"),
    (221, "메꾸리", "Piloswine", "❄️", "rare", 0.50, 220, 473, "friendship"),

    # --- Corsola ---
    (222, "코산호", "Corsola", "💧", "common", 0.80, None, None, "none"),

    # --- Remoraid line ---
    (223, "총어", "Remoraid", "💧", "common", 0.80, None, 224, "friendship"),
    (224, "대포무노", "Octillery", "💧", "rare", 0.50, 223, None, "none"),

    # --- Delibird ---
    (225, "딜리버드", "Delibird", "❄️", "common", 0.80, None, None, "none"),

    # --- Mantine ---
    (226, "만타인", "Mantine", "💧", "rare", 0.50, None, None, "none"),

    # --- Skarmory ---
    (227, "무장조", "Skarmory", "⚙️", "rare", 0.50, None, None, "none"),

    # --- Houndour line ---
    (228, "델빌", "Houndour", "🔥", "common", 0.80, None, 229, "friendship"),
    (229, "헬가", "Houndoom", "🔥", "epic", 0.15, 228, None, "none"),

    # --- Kingdra (trade evo from Seadra 117) ---
    (230, "킹드라", "Kingdra", "💧", "epic", 0.15, 117, None, "none"),

    # --- Phanpy line ---
    (231, "코코리", "Phanpy", "🐘", "common", 0.80, None, 232, "friendship"),
    (232, "코리갑", "Donphan", "🐘", "epic", 0.15, 231, None, "none"),

    # --- Porygon2 (trade evo from Porygon 137) ---
    (233, "폴리곤2", "Porygon2", "💻", "epic", 0.15, 137, 474, "trade"),

    # --- Stantler ---
    (234, "노라키", "Stantler", "🦌", "rare", 0.50, None, None, "none"),

    # --- Smeargle ---
    (235, "루브도", "Smeargle", "🎨", "common", 0.80, None, None, "none"),

    # --- Tyrogue line ---
    (236, "배루키", "Tyrogue", "💪", "common", 0.80, None, 237, "friendship"),
    (237, "카포에라", "Hitmontop", "💪", "rare", 0.50, 236, None, "none"),

    # --- Baby Pokemon (evolve to Gen 1) ---
    (238, "뽀뽀라", "Smoochum", "❄️", "common", 0.80, None, 124, "friendship"),
    (239, "에레키드", "Elekid", "⚡", "common", 0.80, None, 125, "friendship"),
    (240, "마그비", "Magby", "🔥", "common", 0.80, None, 126, "friendship"),

    # --- Miltank ---
    (241, "밀탱크", "Miltank", "🐮", "rare", 0.50, None, None, "none"),

    # --- Blissey (evo from Chansey 113) ---
    (242, "해피너스", "Blissey", "🩷", "epic", 0.15, 113, None, "none"),

    # --- Legendary Beasts ---
    (243, "라이코", "Raikou", "⚡", "legendary", 0.05, None, None, "none"),
    (244, "앤테이", "Entei", "🔥", "legendary", 0.05, None, None, "none"),
    (245, "스이쿤", "Suicune", "💧", "legendary", 0.05, None, None, "none"),

    # --- Larvitar line (pseudo-legendary) ---
    (246, "애버라스", "Larvitar", "🪨", "common", 0.80, None, 247, "friendship"),
    (247, "데기라스", "Pupitar", "🪨", "rare", 0.50, 246, 248, "friendship"),
    (248, "마기라스", "Tyranitar", "🪨", "epic", 0.15, 247, None, "none"),

    # --- Tower Legends ---
    (249, "루기아", "Lugia", "🔮", "ultra_legendary", 0.03, None, None, "none"),
    (250, "칠색조", "Ho-Oh", "🔥", "ultra_legendary", 0.03, None, None, "none"),

    # --- Mythical ---
    (251, "세레비", "Celebi", "🌿", "legendary", 0.05, None, None, "none"),
]

# Merge Gen 3 data
from models.pokemon_data_gen3 import ALL_POKEMON_GEN3
ALL_POKEMON = ALL_POKEMON + ALL_POKEMON_GEN3

# Merge Gen 4 data
from models.pokemon_data_gen4 import ALL_POKEMON_GEN4
ALL_POKEMON = ALL_POKEMON + ALL_POKEMON_GEN4
