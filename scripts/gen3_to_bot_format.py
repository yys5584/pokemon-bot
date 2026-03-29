"""Convert gen3_raw.json to bot-compatible format files.

Outputs:
  models/pokemon_data_gen3.py   - ALL_POKEMON_GEN3 list
  models/pokemon_base_stats_gen3.py - POKEMON_BASE_STATS_GEN3 dict
"""

import json

# Type mapping: English -> bot type string
TYPE_MAP = {
    "normal": "normal", "fire": "fire", "water": "water", "grass": "grass",
    "electric": "electric", "ice": "ice", "fighting": "fighting",
    "poison": "poison", "ground": "ground", "flying": "flying",
    "psychic": "psychic", "bug": "bug", "rock": "rock",
    "ghost": "ghost", "dragon": "dragon", "dark": "dark",
    "steel": "steel", "fairy": "fairy",
}

# Emoji mapping by primary type
TYPE_EMOJI = {
    "grass": "\U0001f33f", "fire": "\U0001f525", "water": "\U0001f4a7",
    "bug": "\U0001f41b", "normal": "\u2b50", "dark": "\U0001f311",
    "poison": "\u2620\ufe0f", "flying": "\U0001f985", "psychic": "\U0001f52e",
    "fighting": "\U0001f94a", "ground": "\U0001f30d", "rock": "\U0001f5ff",
    "ghost": "\U0001f47b", "dragon": "\U0001f409", "steel": "\u2699\ufe0f",
    "ice": "\u2744\ufe0f", "electric": "\u26a1", "fairy": "\U0001f9da",
}

# Rarity assignment based on BST + legendary/mythical status
def assign_rarity(p):
    bst = p["bst"]
    if p["is_mythical"]:
        return "ultra_legendary"
    if p["is_legendary"]:
        if bst >= 670:  # Cover legendaries (Kyogre, Groudon, Rayquaza)
            return "ultra_legendary"
        return "legendary"
    if bst >= 580:
        return "legendary"  # pseudo-legendaries (Salamence, Metagross)
    if bst >= 500:
        return "epic"
    if bst >= 400:
        return "rare"
    if bst >= 300:
        return "common"
    return "common"

# Catch rate based on rarity
CATCH_RATES = {
    "common": 0.80,
    "rare": 0.50,
    "epic": 0.15,
    "legendary": 0.05,
    "ultra_legendary": 0.03,
}

# Evolution chains for Gen 3
# (base_id, mid_id, final_id) or (base_id, final_id) or (single_id,)
EVOLUTION_CHAINS = [
    (252, 253, 254),   # Treecko line
    (255, 256, 257),   # Torchic line
    (258, 259, 260),   # Mudkip line
    (261, 262),        # Poochyena line
    (263, 264),        # Zigzagoon line
    (265, 266, 267),   # Wurmple -> Silcoon -> Beautifly
    (265, 268, 269),   # Wurmple -> Cascoon -> Dustox  (NOTE: branching)
    (270, 271, 272),   # Lotad line
    (273, 274, 275),   # Seedot line
    (276, 277),        # Taillow line
    (278, 279),        # Wingull line
    (280, 281, 282),   # Ralts line (Gardevoir path)
    (283, 284),        # Surskit line
    (285, 286),        # Shroomish line
    (287, 288, 289),   # Slakoth line
    (290, 291),        # Nincada -> Ninjask
    (292,),            # Shedinja (special, no evo)
    (293, 294, 295),   # Whismur line
    (296, 297),        # Makuhita line
    (298,),            # Azurill (baby, evolves to Gen2 Marill=183)
    (299,),            # Nosepass (evolves in Gen4)
    (300, 301),        # Skitty line
    (302,),            # Sableye
    (303,),            # Mawile
    (304, 305, 306),   # Aron line
    (307, 308),        # Meditite line
    (309, 310),        # Electrike line
    (311,),            # Plusle
    (312,),            # Minun
    (313,),            # Volbeat
    (314,),            # Illumise
    (315,),            # Roselia (evolves in Gen4)
    (316, 317),        # Gulpin line
    (318, 319),        # Carvanha line
    (320, 321),        # Wailmer line
    (322, 323),        # Numel line
    (324,),            # Torkoal
    (325, 326),        # Spoink line
    (327,),            # Spinda
    (328, 329, 330),   # Trapinch line
    (331, 332),        # Cacnea line
    (333, 334),        # Swablu line
    (335,),            # Zangoose
    (336,),            # Seviper
    (337,),            # Lunatone
    (338,),            # Solrock
    (339, 340),        # Barboach line
    (341, 342),        # Corphish line
    (343, 344),        # Baltoy line
    (345, 346),        # Lileep line
    (347, 348),        # Anorith line
    (349, 350),        # Feebas line
    (351,),            # Castform
    (352,),            # Kecleon
    (353, 354),        # Shuppet line
    (355, 356),        # Duskull line (evolves further in Gen4)
    (357,),            # Tropius
    (358,),            # Chimecho
    (359,),            # Absol
    (360,),            # Wynaut (baby, evolves to Gen2 Wobbuffet=202)
    (361, 362),        # Snorunt -> Glalie (also Froslass in Gen4)
    (363, 364, 365),   # Spheal line
    (366, 367),        # Clamperl -> Huntail
    (366, 368),        # Clamperl -> Gorebyss (branching)
    (369,),            # Relicanth
    (370,),            # Luvdisc
    (371, 372, 373),   # Bagon line
    (374, 375, 376),   # Beldum line
    (377,),            # Regirock
    (378,),            # Regice
    (379,),            # Registeel
    (380,),            # Latias
    (381,),            # Latios
    (382,),            # Kyogre
    (383,),            # Groudon
    (384,),            # Rayquaza
    (385,),            # Jirachi
    (386,),            # Deoxys
]


def build_evo_map():
    """Build evolves_from/evolves_to maps."""
    evolves_from = {}
    evolves_to = {}
    evo_method = {}

    for chain in EVOLUTION_CHAINS:
        if len(chain) == 1:
            # Single Pokemon, no evolution
            evo_method[chain[0]] = "none"
        elif len(chain) == 2:
            base, final = chain
            evolves_to[base] = final
            evolves_from[final] = base
            evo_method[base] = "friendship"
            evo_method[final] = "none"
        elif len(chain) == 3:
            base, mid, final = chain
            evolves_to[base] = mid
            evolves_to[mid] = final
            evolves_from[mid] = base
            evolves_from[final] = mid
            evo_method[base] = "friendship"
            evo_method[mid] = "friendship"
            evo_method[final] = "none"

    # Special cases
    # Wurmple branches: already handled (265->266, 265->268)
    # Keep the first mapping for 265 (->266 Silcoon)
    # Clamperl branches: 366->367, 366->368 — keep first (->367 Huntail)

    # Azurill -> Marill (183, Gen2) - cross-gen, treat as no evo for now
    evo_method[298] = "none"
    # Wynaut -> Wobbuffet (202, Gen2) - cross-gen
    evo_method[360] = "none"
    # Nosepass evolves in Gen4 - no evo for now
    evo_method[299] = "none"
    # Roselia evolves in Gen4
    evo_method[315] = "none"
    # Duskull line: Dusclops evolves in Gen4
    evo_method[356] = "none"

    # Feebas -> Milotic: trade evolution
    evo_method[349] = "trade"
    # Clamperl -> Huntail/Gorebyss: trade
    evo_method[366] = "trade"

    return evolves_from, evolves_to, evo_method


def main():
    with open("scripts/gen3_raw.json", "r", encoding="utf-8") as f:
        raw = json.load(f)

    evolves_from, evolves_to, evo_method = build_evo_map()

    # Build pokemon_data tuples
    pokemon_data_lines = []
    base_stats_lines = []

    for p in raw:
        pid = p["id"]
        name_ko = p["name_ko"]
        name_en = p["name_en"]
        types = p["types"]
        primary_type = types[0]
        emoji = TYPE_EMOJI.get(primary_type, "\u2b50")
        rarity = assign_rarity(p)
        catch_rate = CATCH_RATES[rarity]
        ef = evolves_from.get(pid)
        et = evolves_to.get(pid)
        em = evo_method.get(pid, "none")

        # Adjust catch rates for specific Pokemon
        if pid == 349:  # Feebas (rare find, low BST but evolves into epic)
            catch_rate = 0.80
        if pid == 292:  # Shedinja (special spawn)
            catch_rate = 0.15

        # Fix evolution method for no-evo Pokemon
        if ef is None and et is None:
            em = "none"

        # pokemon_data tuple
        ef_str = str(ef) if ef else "None"
        et_str = str(et) if et else "None"
        line = f'    ({pid}, "{name_ko}", "{name_en}", "{emoji}", "{rarity}", {catch_rate:.2f}, {ef_str}, {et_str}, "{em}"),'
        comment = f"  # {name_en}"
        pokemon_data_lines.append(line + comment)

        # base_stats entry
        type_list = "[" + ", ".join(f'"{t}"' for t in types) + "]"
        hp, atk, df, spa, spdef, spd = p["hp"], p["atk"], p["def"], p["spa"], p["spdef"], p["spd"]
        bst_comment = f"# {name_en} (BST {p['bst']})"
        stats_line = f'    {pid}: ({hp}, {atk}, {df}, {spa}, {spdef}, {spd}, {type_list}),'
        pad = " " * max(1, 72 - len(stats_line))
        base_stats_lines.append(stats_line + pad + bst_comment)

    # Write pokemon_data_gen3.py
    with open("models/pokemon_data_gen3.py", "w", encoding="utf-8") as f:
        f.write('"""\n')
        f.write("Gen 3 (252-386) Pokemon data for 3rd generation update.\n")
        f.write("Each tuple: (id, name_ko, name_en, emoji, rarity, catch_rate, evolves_from, evolves_to, evolution_method)\n")
        f.write('"""\n\n')
        f.write("ALL_POKEMON_GEN3 = [\n")

        # Group by evolution chains for readability
        prev_base = None
        for p in raw:
            pid = p["id"]
            # Add blank line between evolution families
            ef = evolves_from.get(pid)
            if ef is None and prev_base is not None:
                f.write("\n")
            prev_base = pid

            idx = next(i for i, r in enumerate(raw) if r["id"] == pid)
            f.write(pokemon_data_lines[idx] + "\n")

        f.write("]\n")

    # Write pokemon_base_stats_gen3.py
    with open("models/pokemon_base_stats_gen3.py", "w", encoding="utf-8") as f:
        f.write('"""\n')
        f.write("Gen 3 (252-386) base stats.\n")
        f.write("Format: {pokemon_id: (base_hp, base_atk, base_def, base_spa, base_spdef, base_spd, [type1, type2_or_None])}\n")
        f.write('"""\n\n')
        f.write("POKEMON_BASE_STATS_GEN3 = {\n")
        for line in base_stats_lines:
            f.write(line + "\n")
        f.write("}\n")

    print(f"Generated models/pokemon_data_gen3.py ({len(raw)} Pokemon)")
    print(f"Generated models/pokemon_base_stats_gen3.py ({len(raw)} entries)")

    # Summary
    by_rarity = {}
    for p in raw:
        r = assign_rarity(p)
        by_rarity.setdefault(r, []).append(p["name_ko"])
    for r in ["common", "rare", "epic", "legendary", "ultra_legendary"]:
        names = by_rarity.get(r, [])
        print(f"  {r}: {len(names)}")


if __name__ == "__main__":
    main()
