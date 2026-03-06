"""
Real Pokemon base stats for all 251 Gen 1+2 Pokemon (6-stat system).

Source: Official Pokemon game data (PokeAPI / Gen 2 base stats).

All 6 original base stats are preserved:
  HP     = original HP
  ATK    = original Attack (physical)
  DEF    = original Defense (physical)
  SPA    = original Special Attack
  SPDEF  = original Special Defense
  SPD    = original Speed

These are RAW stats (not normalized). Use normalize() to scale to 20~180 range:
  normalize(stat) = round(20 + (stat - 5) / (255 - 5) * (180 - 20))

Format: {pokemon_id: (base_hp, base_atk, base_def, base_spa, base_spdef, base_spd, [type1, type2_or_None])}
"""

POKEMON_BASE_STATS = {
    # pokemon_id: (base_hp, base_atk, base_def, base_spa, base_spdef, base_spd, [types])
    # === Gen 1 (1-151) ===
    1: (45, 49, 49, 65, 65, 45, ["grass", "poison"]),                       # Bulbasaur
    2: (60, 62, 63, 80, 80, 60, ["grass", "poison"]),                       # Ivysaur
    3: (80, 82, 83, 100, 100, 80, ["grass", "poison"]),                     # Venusaur
    4: (39, 52, 43, 60, 50, 65, ["fire"]),                                  # Charmander
    5: (58, 64, 58, 80, 65, 80, ["fire"]),                                  # Charmeleon
    6: (78, 84, 78, 109, 85, 100, ["fire", "flying"]),                      # Charizard
    7: (44, 48, 65, 50, 64, 43, ["water"]),                                 # Squirtle
    8: (59, 63, 80, 65, 80, 58, ["water"]),                                 # Wartortle
    9: (79, 83, 100, 85, 105, 78, ["water"]),                               # Blastoise
    10: (45, 30, 35, 20, 20, 45, ["bug"]),                                  # Caterpie
    11: (50, 20, 55, 25, 25, 30, ["bug"]),                                  # Metapod
    12: (60, 45, 50, 90, 80, 70, ["bug", "flying"]),                        # Butterfree
    13: (40, 35, 30, 20, 20, 50, ["bug", "poison"]),                        # Weedle
    14: (45, 25, 50, 25, 25, 35, ["bug", "poison"]),                        # Kakuna
    15: (65, 90, 40, 45, 80, 75, ["bug", "poison"]),                        # Beedrill
    16: (40, 45, 40, 35, 35, 56, ["normal", "flying"]),                     # Pidgey
    17: (63, 60, 55, 50, 50, 71, ["normal", "flying"]),                     # Pidgeotto
    18: (83, 80, 75, 70, 70, 101, ["normal", "flying"]),                    # Pidgeot
    19: (30, 56, 35, 25, 35, 72, ["normal"]),                               # Rattata
    20: (55, 81, 60, 50, 70, 97, ["normal"]),                               # Raticate
    21: (40, 60, 30, 31, 31, 70, ["normal", "flying"]),                     # Spearow
    22: (65, 90, 65, 61, 61, 100, ["normal", "flying"]),                    # Fearow
    23: (35, 60, 44, 40, 54, 55, ["poison"]),                               # Ekans
    24: (60, 95, 69, 65, 79, 80, ["poison"]),                               # Arbok
    25: (35, 55, 40, 50, 50, 90, ["electric"]),                             # Pikachu
    26: (60, 90, 55, 90, 80, 110, ["electric"]),                            # Raichu
    27: (50, 75, 85, 20, 30, 40, ["ground"]),                               # Sandshrew
    28: (75, 100, 110, 45, 55, 65, ["ground"]),                             # Sandslash
    29: (55, 47, 52, 40, 40, 41, ["poison"]),                               # Nidoran F
    30: (70, 62, 67, 55, 55, 56, ["poison"]),                               # Nidorina
    31: (90, 92, 87, 75, 85, 76, ["poison", "ground"]),                     # Nidoqueen
    32: (46, 57, 40, 40, 40, 50, ["poison"]),                               # Nidoran M
    33: (61, 72, 57, 55, 55, 65, ["poison"]),                               # Nidorino
    34: (81, 102, 77, 85, 75, 85, ["poison", "ground"]),                    # Nidoking
    35: (70, 45, 48, 60, 65, 35, ["fairy"]),                                # Clefairy
    36: (95, 70, 73, 95, 90, 60, ["fairy"]),                                # Clefable
    37: (38, 41, 40, 50, 65, 65, ["fire"]),                                 # Vulpix
    38: (73, 76, 75, 81, 100, 100, ["fire"]),                               # Ninetales
    39: (115, 45, 20, 45, 25, 20, ["normal", "fairy"]),                     # Jigglypuff
    40: (140, 70, 45, 85, 50, 45, ["normal", "fairy"]),                     # Wigglytuff
    41: (40, 45, 35, 30, 40, 55, ["poison", "flying"]),                     # Zubat
    42: (75, 80, 70, 65, 75, 90, ["poison", "flying"]),                     # Golbat
    43: (45, 50, 55, 75, 65, 30, ["grass", "poison"]),                      # Oddish
    44: (60, 65, 70, 85, 75, 40, ["grass", "poison"]),                      # Gloom
    45: (75, 80, 85, 110, 90, 50, ["grass", "poison"]),                     # Vileplume
    46: (35, 70, 55, 45, 55, 25, ["bug", "grass"]),                         # Paras
    47: (60, 95, 80, 60, 80, 30, ["bug", "grass"]),                         # Parasect
    48: (60, 55, 50, 40, 55, 45, ["bug", "poison"]),                        # Venonat
    49: (70, 65, 60, 90, 75, 90, ["bug", "poison"]),                        # Venomoth
    50: (10, 55, 25, 35, 45, 95, ["ground"]),                               # Diglett
    51: (35, 100, 50, 50, 70, 120, ["ground"]),                             # Dugtrio
    52: (40, 45, 35, 40, 40, 90, ["normal"]),                               # Meowth
    53: (65, 70, 60, 65, 65, 115, ["normal"]),                              # Persian
    54: (50, 52, 48, 65, 50, 55, ["water"]),                                # Psyduck
    55: (80, 82, 78, 95, 80, 85, ["water"]),                                # Golduck
    56: (40, 80, 35, 35, 45, 70, ["fighting"]),                             # Mankey
    57: (65, 105, 60, 60, 70, 95, ["fighting"]),                            # Primeape
    58: (55, 70, 45, 70, 50, 60, ["fire"]),                                 # Growlithe
    59: (90, 110, 80, 100, 80, 95, ["fire"]),                               # Arcanine
    60: (40, 50, 40, 40, 40, 90, ["water"]),                                # Poliwag
    61: (65, 65, 65, 50, 50, 90, ["water"]),                                # Poliwhirl
    62: (90, 95, 95, 70, 90, 70, ["water", "fighting"]),                    # Poliwrath
    63: (25, 20, 15, 105, 55, 90, ["psychic"]),                             # Abra
    64: (40, 35, 30, 120, 70, 105, ["psychic"]),                            # Kadabra
    65: (55, 50, 45, 135, 95, 120, ["psychic"]),                            # Alakazam
    66: (70, 80, 50, 35, 35, 35, ["fighting"]),                             # Machop
    67: (80, 100, 70, 50, 60, 45, ["fighting"]),                            # Machoke
    68: (90, 130, 80, 65, 85, 55, ["fighting"]),                            # Machamp
    69: (50, 75, 35, 70, 30, 40, ["grass", "poison"]),                      # Bellsprout
    70: (65, 90, 50, 85, 45, 55, ["grass", "poison"]),                      # Weepinbell
    71: (80, 105, 65, 100, 70, 70, ["grass", "poison"]),                    # Victreebel
    72: (40, 40, 35, 50, 100, 70, ["water", "poison"]),                     # Tentacool
    73: (80, 70, 65, 80, 120, 100, ["water", "poison"]),                    # Tentacruel
    74: (40, 80, 100, 30, 30, 20, ["rock", "ground"]),                      # Geodude
    75: (55, 95, 115, 45, 45, 35, ["rock", "ground"]),                      # Graveler
    76: (80, 120, 130, 55, 65, 45, ["rock", "ground"]),                     # Golem
    77: (50, 85, 55, 65, 65, 90, ["fire"]),                                 # Ponyta
    78: (65, 100, 70, 80, 80, 105, ["fire"]),                               # Rapidash
    79: (90, 65, 65, 40, 40, 15, ["water", "psychic"]),                     # Slowpoke
    80: (95, 75, 110, 100, 80, 30, ["water", "psychic"]),                   # Slowbro
    81: (25, 35, 70, 95, 55, 45, ["electric", "steel"]),                    # Magnemite
    82: (50, 60, 95, 120, 70, 70, ["electric", "steel"]),                   # Magneton
    83: (52, 90, 55, 58, 62, 60, ["normal", "flying"]),                     # Farfetch'd
    84: (35, 85, 45, 35, 35, 75, ["normal", "flying"]),                     # Doduo
    85: (60, 110, 70, 60, 60, 110, ["normal", "flying"]),                   # Dodrio
    86: (65, 45, 55, 45, 70, 45, ["water"]),                                # Seel
    87: (90, 70, 80, 70, 95, 70, ["water", "ice"]),                         # Dewgong
    88: (80, 80, 50, 40, 50, 25, ["poison"]),                               # Grimer
    89: (105, 105, 75, 65, 100, 50, ["poison"]),                            # Muk
    90: (30, 65, 100, 45, 25, 40, ["water"]),                               # Shellder
    91: (50, 95, 180, 85, 45, 70, ["water", "ice"]),                        # Cloyster
    92: (30, 35, 30, 100, 35, 80, ["ghost", "poison"]),                     # Gastly
    93: (45, 50, 45, 115, 55, 95, ["ghost", "poison"]),                     # Haunter
    94: (60, 65, 60, 130, 75, 110, ["ghost", "poison"]),                    # Gengar
    95: (35, 45, 160, 30, 45, 70, ["rock", "ground"]),                      # Onix
    96: (60, 48, 45, 43, 90, 42, ["psychic"]),                              # Drowzee
    97: (85, 73, 70, 73, 115, 67, ["psychic"]),                             # Hypno
    98: (30, 105, 90, 25, 25, 50, ["water"]),                               # Krabby
    99: (55, 130, 115, 50, 50, 75, ["water"]),                              # Kingler
    100: (40, 30, 50, 55, 55, 100, ["electric"]),                           # Voltorb
    101: (60, 50, 70, 80, 80, 150, ["electric"]),                           # Electrode
    102: (60, 40, 80, 60, 45, 40, ["grass", "psychic"]),                    # Exeggcute
    103: (95, 95, 85, 125, 75, 55, ["grass", "psychic"]),                   # Exeggutor
    104: (50, 50, 95, 40, 50, 35, ["ground"]),                              # Cubone
    105: (60, 80, 110, 50, 80, 45, ["ground"]),                             # Marowak
    106: (50, 120, 53, 35, 110, 87, ["fighting"]),                          # Hitmonlee
    107: (50, 105, 79, 35, 110, 76, ["fighting"]),                          # Hitmonchan
    108: (90, 55, 75, 60, 75, 30, ["normal"]),                              # Lickitung
    109: (40, 65, 95, 60, 45, 35, ["poison"]),                              # Koffing
    110: (65, 90, 120, 85, 70, 60, ["poison"]),                             # Weezing
    111: (80, 85, 95, 30, 30, 25, ["ground", "rock"]),                      # Rhyhorn
    112: (105, 130, 120, 45, 45, 40, ["ground", "rock"]),                   # Rhydon
    113: (250, 5, 5, 35, 105, 50, ["normal"]),                              # Chansey
    114: (65, 55, 115, 100, 40, 60, ["grass"]),                             # Tangela
    115: (105, 95, 80, 40, 80, 90, ["normal"]),                             # Kangaskhan
    116: (30, 40, 70, 70, 25, 60, ["water"]),                               # Horsea
    117: (55, 65, 95, 95, 45, 85, ["water"]),                               # Seadra
    118: (45, 67, 60, 35, 50, 63, ["water"]),                               # Goldeen
    119: (80, 92, 65, 65, 80, 68, ["water"]),                               # Seaking
    120: (30, 45, 55, 70, 55, 85, ["water"]),                               # Staryu
    121: (60, 75, 85, 100, 85, 115, ["water", "psychic"]),                  # Starmie
    122: (40, 45, 65, 100, 120, 90, ["psychic", "fairy"]),                  # Mr. Mime
    123: (70, 110, 80, 55, 80, 105, ["bug", "flying"]),                     # Scyther
    124: (65, 50, 35, 115, 95, 95, ["ice", "psychic"]),                     # Jynx
    125: (65, 83, 57, 95, 85, 105, ["electric"]),                           # Electabuzz
    126: (65, 95, 57, 100, 85, 93, ["fire"]),                               # Magmar
    127: (65, 125, 100, 55, 70, 85, ["bug"]),                               # Pinsir
    128: (75, 100, 95, 40, 70, 110, ["normal"]),                            # Tauros
    129: (20, 10, 55, 15, 20, 80, ["water"]),                               # Magikarp
    130: (95, 125, 79, 60, 100, 81, ["water", "flying"]),                   # Gyarados
    131: (130, 85, 80, 85, 95, 60, ["water", "ice"]),                       # Lapras
    132: (48, 48, 48, 48, 48, 48, ["normal"]),                              # Ditto
    133: (55, 55, 50, 45, 65, 55, ["normal"]),                              # Eevee
    134: (130, 65, 60, 110, 95, 65, ["water"]),                             # Vaporeon
    135: (65, 65, 60, 110, 95, 130, ["electric"]),                          # Jolteon
    136: (65, 130, 60, 95, 110, 65, ["fire"]),                              # Flareon
    137: (65, 60, 70, 85, 75, 40, ["normal"]),                              # Porygon
    138: (35, 40, 100, 90, 55, 35, ["rock", "water"]),                      # Omanyte
    139: (70, 60, 125, 115, 70, 55, ["rock", "water"]),                     # Omastar
    140: (30, 80, 90, 55, 45, 55, ["rock", "water"]),                       # Kabuto
    141: (60, 115, 105, 65, 70, 80, ["rock", "water"]),                     # Kabutops
    142: (80, 105, 65, 60, 75, 130, ["rock", "flying"]),                    # Aerodactyl
    143: (160, 110, 65, 65, 110, 30, ["normal"]),                           # Snorlax
    144: (90, 85, 100, 95, 125, 85, ["ice", "flying"]),                     # Articuno
    145: (90, 90, 85, 125, 90, 100, ["electric", "flying"]),                # Zapdos
    146: (90, 100, 90, 125, 85, 90, ["fire", "flying"]),                    # Moltres
    147: (41, 64, 45, 50, 50, 50, ["dragon"]),                              # Dratini
    148: (61, 84, 65, 70, 70, 70, ["dragon"]),                              # Dragonair
    149: (91, 134, 95, 100, 100, 80, ["dragon", "flying"]),                 # Dragonite
    150: (106, 110, 90, 154, 90, 130, ["psychic"]),                         # Mewtwo
    151: (100, 100, 100, 100, 100, 100, ["psychic"]),                       # Mew

    # === Gen 2 (152-251) ===
    152: (45, 49, 65, 49, 65, 45, ["grass"]),                               # Chikorita
    153: (60, 62, 80, 63, 80, 60, ["grass"]),                               # Bayleef
    154: (80, 82, 100, 83, 100, 80, ["grass"]),                             # Meganium
    155: (39, 52, 43, 60, 50, 65, ["fire"]),                                # Cyndaquil
    156: (58, 64, 58, 80, 65, 80, ["fire"]),                                # Quilava
    157: (78, 84, 78, 109, 85, 100, ["fire"]),                              # Typhlosion
    158: (50, 65, 64, 44, 48, 43, ["water"]),                               # Totodile
    159: (65, 80, 80, 59, 63, 58, ["water"]),                               # Croconaw
    160: (85, 105, 100, 79, 83, 78, ["water"]),                             # Feraligatr
    161: (35, 46, 34, 35, 45, 20, ["normal"]),                              # Sentret
    162: (85, 76, 64, 45, 55, 90, ["normal"]),                              # Furret
    163: (60, 30, 30, 36, 56, 50, ["normal", "flying"]),                    # Hoothoot
    164: (100, 50, 50, 86, 96, 70, ["normal", "flying"]),                   # Noctowl
    165: (40, 20, 30, 40, 80, 55, ["bug", "flying"]),                       # Ledyba
    166: (55, 35, 50, 55, 110, 85, ["bug", "flying"]),                      # Ledian
    167: (40, 60, 40, 40, 40, 30, ["bug", "poison"]),                       # Spinarak
    168: (70, 90, 70, 60, 70, 40, ["bug", "poison"]),                       # Ariados
    169: (85, 90, 80, 70, 80, 130, ["poison", "flying"]),                   # Crobat
    170: (75, 38, 38, 56, 56, 67, ["water", "electric"]),                   # Chinchou
    171: (125, 58, 58, 76, 76, 67, ["water", "electric"]),                  # Lanturn
    172: (20, 40, 15, 35, 35, 60, ["electric"]),                            # Pichu
    173: (50, 25, 28, 45, 55, 15, ["fairy"]),                               # Cleffa
    174: (90, 30, 15, 40, 20, 15, ["normal", "fairy"]),                     # Igglybuff
    175: (35, 20, 65, 40, 65, 20, ["fairy"]),                               # Togepi
    176: (55, 40, 85, 80, 105, 40, ["fairy", "flying"]),                    # Togetic
    177: (40, 50, 45, 70, 45, 70, ["psychic", "flying"]),                   # Natu
    178: (65, 75, 70, 95, 70, 95, ["psychic", "flying"]),                   # Xatu
    179: (55, 40, 40, 65, 45, 35, ["electric"]),                            # Mareep
    180: (70, 55, 55, 80, 60, 45, ["electric"]),                            # Flaaffy
    181: (90, 75, 85, 115, 90, 55, ["electric"]),                           # Ampharos
    182: (75, 80, 95, 90, 100, 50, ["grass"]),                              # Bellossom
    183: (70, 20, 50, 20, 50, 40, ["water", "fairy"]),                      # Marill
    184: (100, 50, 80, 60, 80, 50, ["water", "fairy"]),                     # Azumarill
    185: (70, 100, 115, 30, 65, 30, ["rock"]),                              # Sudowoodo
    186: (90, 75, 75, 90, 100, 70, ["water"]),                              # Politoed
    187: (35, 35, 40, 35, 55, 50, ["grass", "flying"]),                     # Hoppip
    188: (55, 45, 50, 45, 65, 80, ["grass", "flying"]),                     # Skiploom
    189: (75, 55, 70, 55, 95, 110, ["grass", "flying"]),                    # Jumpluff
    190: (55, 70, 55, 40, 55, 85, ["normal"]),                              # Aipom
    191: (30, 30, 30, 30, 30, 30, ["grass"]),                               # Sunkern
    192: (75, 75, 55, 105, 85, 30, ["grass"]),                              # Sunflora
    193: (65, 65, 45, 75, 45, 95, ["bug", "flying"]),                       # Yanma
    194: (55, 45, 45, 25, 25, 15, ["water", "ground"]),                     # Wooper
    195: (95, 85, 85, 65, 65, 35, ["water", "ground"]),                     # Quagsire
    196: (65, 65, 60, 130, 95, 110, ["psychic"]),                           # Espeon
    197: (95, 65, 110, 60, 130, 65, ["dark"]),                              # Umbreon
    198: (60, 85, 42, 85, 42, 91, ["dark", "flying"]),                      # Murkrow
    199: (95, 75, 80, 100, 110, 30, ["water", "psychic"]),                  # Slowking
    200: (60, 60, 60, 85, 85, 85, ["ghost"]),                               # Misdreavus
    201: (48, 72, 48, 72, 48, 48, ["psychic"]),                             # Unown
    202: (190, 33, 58, 33, 58, 33, ["psychic"]),                            # Wobbuffet
    203: (70, 80, 65, 90, 65, 85, ["normal", "psychic"]),                   # Girafarig
    204: (50, 65, 90, 35, 35, 15, ["bug"]),                                 # Pineco
    205: (75, 90, 140, 60, 60, 40, ["bug", "steel"]),                       # Forretress
    206: (100, 70, 70, 65, 65, 45, ["normal"]),                             # Dunsparce
    207: (65, 75, 105, 35, 65, 85, ["ground", "flying"]),                   # Gligar
    208: (75, 85, 200, 55, 65, 30, ["steel", "ground"]),                    # Steelix
    209: (60, 80, 50, 40, 40, 30, ["fairy"]),                               # Snubbull
    210: (90, 120, 75, 60, 60, 45, ["fairy"]),                              # Granbull
    211: (65, 95, 85, 55, 55, 85, ["water", "poison"]),                     # Qwilfish
    212: (70, 130, 100, 55, 80, 65, ["bug", "steel"]),                      # Scizor
    213: (20, 10, 230, 10, 230, 5, ["bug", "rock"]),                        # Shuckle
    214: (80, 125, 75, 40, 95, 85, ["bug", "fighting"]),                    # Heracross
    215: (55, 95, 55, 35, 75, 115, ["dark", "ice"]),                        # Sneasel
    216: (60, 80, 50, 50, 50, 40, ["normal"]),                              # Teddiursa
    217: (90, 130, 75, 75, 75, 55, ["normal"]),                             # Ursaring
    218: (40, 40, 40, 70, 40, 20, ["fire"]),                                # Slugma
    219: (60, 50, 120, 90, 80, 30, ["fire", "rock"]),                       # Magcargo
    220: (50, 50, 40, 30, 30, 50, ["ice", "ground"]),                       # Swinub
    221: (100, 100, 80, 60, 60, 50, ["ice", "ground"]),                     # Piloswine
    222: (65, 55, 95, 65, 95, 35, ["water", "rock"]),                       # Corsola
    223: (35, 65, 35, 65, 35, 65, ["water"]),                               # Remoraid
    224: (75, 105, 75, 105, 75, 45, ["water"]),                             # Octillery
    225: (45, 55, 45, 65, 45, 75, ["ice", "flying"]),                       # Delibird
    226: (85, 40, 70, 80, 140, 70, ["water", "flying"]),                    # Mantine
    227: (65, 80, 140, 40, 70, 70, ["steel", "flying"]),                    # Skarmory
    228: (45, 60, 30, 80, 50, 65, ["dark", "fire"]),                        # Houndour
    229: (75, 90, 50, 110, 80, 95, ["dark", "fire"]),                       # Houndoom
    230: (75, 95, 95, 95, 95, 85, ["water", "dragon"]),                     # Kingdra
    231: (90, 60, 60, 40, 40, 40, ["ground"]),                              # Phanpy
    232: (90, 120, 120, 60, 60, 50, ["ground"]),                            # Donphan
    233: (85, 80, 90, 105, 95, 60, ["normal"]),                             # Porygon2
    234: (73, 95, 62, 85, 65, 85, ["normal"]),                              # Stantler
    235: (55, 20, 35, 20, 45, 75, ["normal"]),                              # Smeargle
    236: (35, 35, 35, 35, 35, 35, ["fighting"]),                            # Tyrogue
    237: (50, 95, 95, 35, 110, 70, ["fighting"]),                           # Hitmontop
    238: (45, 30, 15, 85, 65, 65, ["ice", "psychic"]),                      # Smoochum
    239: (45, 63, 37, 65, 55, 95, ["electric"]),                            # Elekid
    240: (45, 75, 37, 70, 55, 83, ["fire"]),                                # Magby
    241: (95, 80, 105, 40, 70, 100, ["normal"]),                            # Miltank
    242: (255, 10, 10, 75, 135, 55, ["normal"]),                            # Blissey
    243: (90, 85, 75, 115, 100, 115, ["electric"]),                         # Raikou
    244: (115, 115, 85, 90, 75, 100, ["fire"]),                             # Entei
    245: (100, 75, 115, 90, 115, 85, ["water"]),                            # Suicune
    246: (50, 64, 50, 45, 50, 41, ["rock", "ground"]),                      # Larvitar
    247: (70, 84, 70, 65, 70, 51, ["rock", "ground"]),                      # Pupitar
    248: (100, 134, 110, 95, 100, 61, ["rock", "dark"]),                    # Tyranitar
    249: (106, 90, 130, 90, 154, 110, ["psychic", "flying"]),               # Lugia
    250: (106, 130, 90, 110, 154, 90, ["fire", "flying"]),                  # Ho-Oh
    251: (100, 100, 100, 100, 100, 100, ["psychic", "grass"]),              # Celebi
}

# Merge Gen 3 base stats
from models.pokemon_base_stats_gen3 import POKEMON_BASE_STATS_GEN3
POKEMON_BASE_STATS.update(POKEMON_BASE_STATS_GEN3)


def normalize(stat: int, min_stat: int = 5, max_stat: int = 255,
              out_min: int = 20, out_max: int = 180) -> int:
    """Normalize a raw stat to the bot's stat range (default 20~180)."""
    return round(out_min + (stat - min_stat) / (max_stat - min_stat) * (out_max - out_min))


def get_normalized_stats(pokemon_id: int) -> dict | None:
    """Get normalized 6-stat dict for a Pokemon.

    Returns: {"hp": int, "atk": int, "def": int, "spa": int, "spdef": int, "spd": int, "types": list}
             or None if pokemon_id not found.
    """
    entry = POKEMON_BASE_STATS.get(pokemon_id)
    if entry is None:
        return None
    raw_hp, raw_atk, raw_def, raw_spa, raw_spdef, raw_spd, types = entry
    return {
        "hp": normalize(raw_hp),
        "atk": normalize(raw_atk),
        "def": normalize(raw_def),
        "spa": normalize(raw_spa),
        "spdef": normalize(raw_spdef),
        "spd": normalize(raw_spd),
        "types": types,
    }
