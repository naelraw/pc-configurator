"""
Estimation des FPS à partir de vrais tests publiés (septembre 2026).

Principe (celui des sites de tests) : dans un jeu donné, les FPS réels sont
le MINIMUM de deux limites :
  - ce que la carte graphique peut afficher à cette résolution (limite GPU) ;
  - ce que le processeur peut préparer, qui dépend énormément du jeu (limite
    CPU) : Counter-Strike 2 monte à ~780 FPS sur le meilleur CPU, Stalker 2
    plafonne à ~105.
  + un éventuel plafond du moteur (Elden Ring bloqué à 60, GTA V à ~187...).

Sources (TechPowerUp) :
  - FPS de chaque carte graphique dans chaque jeu (fps_measurements.json) :
    graphiques des tests RTX 5050/5060/5080/5090 (22 jeux, 40 cartes) et des
    tests dédiés à un jeu (Black Ops 6, Battlefield 6, AC Mirage...), lus
    automatiquement et recoupés avec la longueur de chaque barre. Une carte
    absente d'un jeu est extrapolée depuis les cartes testées dans CE jeu.
  - Écart moyen entre cartes par résolution (GPU_RELATIVE) : graphiques
    "Relative Performance" des tests RTX 5060, RTX 5050 et Arc B570.
  - Processeurs (CPU_RELATIVE) et plafond CPU par jeu : tests Ryzen 7 9850X3D
    et Ryzen 5 9600X en 720p (limités uniquement par le processeur).
Les jeux sans test publié sont marqués "estimé" : valeurs calées par
recoupement de benchmarks sur du matériel équivalent, moins fiables.
"""

import json
import math
import os
import re
import unicodedata

REFERENCE_CPU_INDEX_9850X3D = 142  # indice du 9850X3D dans main.CPU_PERFORMANCE_INDEX

# --- Cartes graphiques ---------------------------------------------------
# (motif, {vram_go: (1080p, 1440p, 4K)}, vram par défaut) — RTX 5060 = 100.
# Ordre important : du plus spécifique au plus général (premier motif trouvé).
# "(est.)" : carte absente des trois graphiques, placée d'après ses voisines
# de génération les plus proches (écarts typiques publiés).
GPU_RELATIVE = [
    (r"rtx\s*5090", {32: (257, 315, 461)}, 32),
    (r"rtx\s*4090", {24: (230, 264, 351)}, 24),
    (r"rtx\s*5080", {16: (202, 228, 303)}, 16),
    (r"rtx\s*4080\s*super", {16: (194, 214, 272)}, 16),
    (r"rtx\s*4080", {16: (192, 212, 268)}, 16),
    (r"rx\s*7900\s*xtx", {24: (186, 206, 269)}, 24),
    (r"rtx\s*5070\s*ti", {16: (183, 205, 264)}, 16),
    (r"rx\s*9070\s*xt", {16: (180, 197, 253)}, 16),
    (r"rtx\s*4070\s*ti\s*super", {16: (170, 184, 229)}, 16),
    (r"rx\s*7900\s*xt(?!x)", {20: (166, 180, 229)}, 20),
    (r"rx\s*9070\s*gre", {12: (138, 148, 184)}, 12),          # (est.)
    (r"rx\s*9070", {16: (166, 179, 227)}, 16),
    (r"rtx\s*4070\s*ti", {12: (160, 170, 210)}, 12),
    (r"rtx\s*3090\s*ti", {24: (157, 175, 232)}, 24),
    (r"rtx\s*3090", {24: (144, 153, 213)}, 24),
    (r"rtx\s*3080\s*ti", {12: (140, 149, 207)}, 12),          # (est.)
    (r"rtx\s*5070", {12: (153, 166, 209)}, 12),
    (r"rtx\s*4070\s*super", {12: (149, 158, 193)}, 12),
    (r"rx\s*7900\s*gre", {16: (142, 153, 190)}, 16),
    (r"rx\s*6950\s*xt", {16: (142, 152, 189)}, 16),           # (est.)
    (r"rx\s*6900\s*xt", {16: (133, 142, 177)}, 16),
    (r"rtx\s*4070", {12: (132, 138, 167)}, 12),
    (r"rx\s*7800\s*xt", {16: (130, 139, 173)}, 16),
    (r"rtx\s*3080", {10: (130, 140, 181), 12: (130, 140, 181)}, 10),
    (r"rx\s*6800\s*xt", {16: (125, 133, 165)}, 16),
    (r"rx\s*6800", {16: (106, 111, 139)}, 16),
    (r"rtx\s*5060\s*ti", {8: (115, 116, 120), 16: (114, 120, 147)}, 16),
    (r"rx\s*7700\s*xt", {12: (112, 119, 143)}, 12),
    (r"rtx\s*3070\s*ti", {8: (109, 112, 134)}, 8),
    (r"rx\s*9060\s*xt", {8: (103, 105, 108), 16: (109, 111, 135)}, 16),
    (r"rtx\s*3070", {8: (103, 108, 127)}, 8),
    (r"rtx\s*4060\s*ti", {8: (101, 104, 112), 16: (102, 105, 122)}, 8),
    (r"rtx\s*2080\s*ti", {11: (101, 104, 125)}, 11),
    (r"rtx\s*5060", {8: (100, 100, 100)}, 8),
    (r"rx\s*6750\s*xt", {12: (93, 95, 119)}, 12),              # (est.)
    (r"rtx\s*3060\s*ti", {8: (90, 93, 108)}, 8),
    (r"rx\s*6700\s*xt", {12: (88, 90, 112)}, 12),
    (r"rx\s*7600\s*xt", {16: (81, 82, 98)}, 16),
    (r"arc\s*b580", {12: (81, 87, 114)}, 12),
    (r"rtx\s*4060", {8: (79, 79, 89)}, 8),
    (r"rtx\s*5050", {8: (78, 77, 87)}, 8),
    (r"rx\s*7600", {8: (75, 74, 74)}, 8),
    (r"arc\s*b570", {10: (74, 76, 90)}, 10),
    (r"arc\s*a770", {16: (71, 77, 99), 8: (69, 74, 84)}, 16),
    (r"rtx\s*3060", {12: (69, 72, 87), 8: (62, 64, 70)}, 12),
    (r"rx\s*6650\s*xt", {8: (70, 68, 69)}, 8),                 # (est.)
    (r"rx\s*6600\s*xt", {8: (68, 66, 67)}, 8),
    (r"arc\s*a750", {8: (66, 71, 68)}, 8),
    (r"rx\s*6600", {8: (58, 57, 58)}, 8),
    (r"rtx\s*2060", {6: (50, 49, 45), 12: (52, 51, 52)}, 6),
    (r"rtx\s*3050", {8: (50, 50, 55), 6: (40, 39, 38)}, 8),
    (r"gtx\s*1660", {6: (45, 43, 38)}, 6),                     # (est.)
    (r"rx\s*6500\s*xt", {4: (39, 36, 30), 8: (40, 38, 34)}, 4),  # (est.)
    (r"rx\s*6400", {4: (29, 27, 22)}, 4),                      # (est.)
]

# À 4K, la RTX 5060 de référence (8 Go) s'effondre dans 6 jeux sur 24 faute de
# mémoire vidéo, ce qui gonfle l'écart affiché par les cartes mieux dotées
# (ex. RTX 3080 : 1,45x la 5060 dans les jeux normaux, 1,81x "en moyenne").
# On retire ce biais pour les cartes > 8 Go ; les cartes <= 8 Go subissent à la
# place l'effondrement mesuré, jeu par jeu (voir "vram8" plus bas).
FOUR_K_VRAM_BIAS_CORRECTION = 0.80

VRAM_PATTERN = re.compile(r"\b(\d{1,2})\s*(?:go|gb|g)\b", re.IGNORECASE)

# --- Processeurs ---------------------------------------------------------
# Performance en jeu limitée par le processeur (720p, carte ultra rapide),
# échelle Ryzen 7 9850X3D = 142. Sources : test TechPowerUp du 9850X3D
# (RTX 5090, 13 processeurs) et du Ryzen 5 9600X (RTX 4090, 45 processeurs),
# raccordés via le 9600X présent dans les deux (écart de recoupement < 4 %).
# "d" = absent des deux tests, placé d'après le modèle mesuré le plus proche
# (même puce, fréquence ou cache différents).
CPU_RELATIVE = [
    (r"9850x3d", 142, "m"), (r"9800x3d", 140, "m"), (r"9950x3d", 132, "m"), (r"9900x3d", 129, "d"),
    (r"7800x3d", 126, "m"), (r"7600x3d", 122, "d"), (r"7950x3d", 120, "m"), (r"7500x3d", 118, "d"),
    (r"7900x3d", 117, "d"), (r"i9-14900ks", 120, "d"), (r"i9-14900k", 116, "m"), (r"i9-14900f", 110, "d"),
    (r"i9-14900", 111, "d"), (r"i9-13900k", 120, "m"), (r"i9-13900f", 114, "d"),
    (r"ultra\s*9\s*285", 116, "m"), (r"ultra\s*7\s*270k", 116, "d"), (r"ultra\s*7\s*265", 112, "m"),
    (r"ultra\s*5\s*250k", 112, "d"), (r"ultra\s*5\s*245k", 107, "d"), (r"ultra\s*5\s*225", 96, "d"),
    (r"9950x", 119, "m"), (r"9900x", 117, "d"), (r"9700x", 117, "m"), (r"9600x", 113, "m"),
    (r"i7-14700k", 114, "m"), (r"i7-14700f", 110, "d"), (r"i7-14700", 111, "d"),
    (r"i7-13700k", 116, "m"), (r"i7-13700f", 112, "d"),
    (r"i5-14600k", 112, "m"), (r"i5-13600k", 107, "m"), (r"i5-14500", 100, "d"),
    (r"i5-14400", 92, "d"), (r"i5-13400", 90, "m"), (r"i5-12600k", 95, "m"), (r"i5-12400", 88, "m"),
    (r"i5-11600k", 84, "m"), (r"i5-11400", 70, "m"), (r"i5-10400", 62, "d"),
    (r"i9-12900k", 107, "m"), (r"i9-12900", 103, "d"), (r"i7-12700k", 103, "m"), (r"i7-12700", 100, "d"),
    (r"i9-11900k", 90, "m"), (r"i9-11900", 87, "d"), (r"i7-11700k", 89, "m"), (r"i7-11700", 86, "d"),
    (r"i9-9900k", 80, "d"), (r"i7-8700k", 72, "d"),
    (r"i3-14100", 83, "m"), (r"i3-13100", 80, "d"), (r"i3-12100", 78, "m"), (r"i3-9100", 53, "d"),
    (r"7950x", 111, "m"), (r"7900x", 111, "m"), (r"7700x", 111, "m"), (r"7600x", 107, "m"),
    (r"7900(?!x)", 107, "m"), (r"7700(?!x)", 110, "m"), (r"7600(?!x)", 105, "m"), (r"7500f", 103, "d"),
    (r"8700[fg]", 90, "d"), (r"8600g", 86, "d"), (r"8500g", 83, "m"), (r"8400f", 82, "d"),
    (r"5800x3d", 107, "m"), (r"5700x3d", 102, "d"), (r"5950x", 95, "m"), (r"5900x", 94, "m"),
    (r"5800x", 89, "m"), (r"5700x", 87, "m"), (r"5700g", 78, "m"), (r"5700(?!x|g)", 78, "d"),
    (r"5600xt", 89, "d"), (r"5600x", 87, "m"), (r"5600gt", 77, "d"), (r"5600g", 76, "d"),
    (r"5600(?!x|g|t)", 85, "d"), (r"5500gt", 72, "d"), (r"5500", 72, "d"),
    (r"5300g", 63, "d"), (r"ryzen\s*5\s*4500", 61, "d"), (r"4350g", 60, "d"), (r"4100", 58, "d"),
    (r"3900x", 75, "m"), (r"3700x", 74, "m"), (r"3600", 69, "m"), (r"3400g", 55, "d"),
    (r"3300x", 67, "m"), (r"3200g", 50, "d"), (r"2700x", 55, "m"),
]


def match_cpu(nom: str):
    """Nom commercial -> (indice, "m" mesuré / "d" déduit) ou (None, None)."""
    n = normalize_cpu_name(nom)
    for pattern, value, origin in CPU_RELATIVE:
        if re.search(pattern, n):
            return value, origin
    return None, None


# --- Préréglages graphiques ---------------------------------------------
# Multiplicateurs appliqués à la limite GPU et à la limite CPU, par rapport à
# Ultra. Écarts typiques publiés entre préréglages (varient selon les jeux) :
# approximation, signalée comme telle dans l'interface.
QUALITY_PRESETS = {
    "ultra": {"label": "Ultra", "gpu": 1.00, "cpu": 1.00},
    "eleve": {"label": "Élevé", "gpu": 1.22, "cpu": 1.05},
    "moyen": {"label": "Moyen", "gpu": 1.55, "cpu": 1.10},
    "bas": {"label": "Bas / compétitif", "gpu": 1.95, "cpu": 1.15},
}

# --- Jeux ----------------------------------------------------------------
# gpu : FPS de la RTX 5060 en Ultra natif (1080p, 1440p, 4K), déjà corrigés
#       de l'effondrement mémoire à 4K (valeur "normale" de la carte).
# cpu : FPS limités par le processeur sur un Ryzen 7 9850X3D.
# cap : plafond imposé par le jeu lui-même (None = aucun).
# vram8 : facteur mesuré sur une carte 8 Go quand la mémoire vidéo sature.
# source : "mesure" (TechPowerUp) ou "estimation" (recoupement de benchmarks).
def _g(gpu, cpu, source="estimation", cap=None, vram8=None, aliases=()):
    return {"gpu": gpu, "cpu": cpu, "source": source, "cap": cap, "vram8": vram8 or {}, "aliases": aliases}

GAMES = {
    # --- Mesurés (TechPowerUp, test RTX 5060 ; CPU : test 9850X3D quand dispo)
    "alan wake 2": _g((66.1, 47.1, 25.2), 229.5, "mesure"),
    "assassin's creed shadows": _g((37.4, 30.8, 19.9), 150, "mesure", aliases=("ac shadows",)),
    "avowed": _g((45.0, 30.9, 16.4), 160, "mesure", vram8={"4k": 0.57}),
    "baldur's gate 3": _g((121.1, 87.9, 46.3), 216.9, "mesure", aliases=("baldurs gate 3", "bg3")),
    "black myth wukong": _g((35.5, 27.1, 14.4), 250, "mesure", vram8={"4k": 0.65}, aliases=("wukong",)),
    "counter-strike 2": _g((279.0, 188.8, 97.5), 783.9, "mesure", aliases=("cs2", "counter strike 2", "csgo", "cs go")),
    "cyberpunk 2077": _g((102.2, 62.1, 28.1), 255.9, "mesure", aliases=("cyberpunk",)),
    "doom eternal": _g((157.6, 107.0, 67.0), 500, "mesure"),
    "dragon age veilguard": _g((65.0, 49.6, 24.5), 220, "mesure", aliases=("dragon age the veilguard",)),
    # Elden Ring est bloqué à 60 FPS par le jeu (TechPowerUp le teste débloqué).
    "elden ring": _g((140.1, 98.1, 56.2), 196, "mesure", cap=60),
    "f1 24": _g((133.3, 97.3, 44.6), 350, "mesure", aliases=("f1 2024",)),
    "ghost of tsushima": _g((80.8, 57.8, 32.3), 250, "mesure"),
    "god of war ragnarok": _g((85.2, 66.3, 38.8), 230, "mesure"),
    "hogwarts legacy": _g((73.7, 51.1, 29.6), 430, "mesure"),
    "horizon forbidden west": _g((83.5, 62.5, 37.1), 220, "mesure"),
    "kingdom come deliverance 2": _g((94.9, 63.2, 31.8), 272.2, "mesure", aliases=("kingdom come 2", "kcd2", "kingdom come deliverance ii")),
    "monster hunter wilds": _g((42.9, 30.0, 15.9), 130, "mesure", vram8={"4k": 0.81}),
    "marvel's spider-man 2": _g((81.5, 51.8, 27.5), 223.7, "mesure", vram8={"4k": 0.77}, aliases=("spider-man 2", "spiderman 2")),
    "stalker 2": _g((61.5, 43.8, 23.2), 104.8, "mesure", vram8={"4k": 0.17}, aliases=("s.t.a.l.k.e.r. 2",)),
    "starfield": _g((65.5, 50.6, 30.9), 204.4, "mesure"),
    "star wars outlaws": _g((52.7, 34.3, 17.6), 150, "mesure"),
    "the last of us": _g((57.7, 41.1, 21.8), 194.2, "mesure", vram8={"1440p": 0.81, "4k": 0.47}, aliases=("the last of us part i", "tlou")),
    "the witcher 3": _g((177.3, 131.5, 74.8), 300, "mesure", aliases=("witcher 3",)),
    # Tests dédiés TechPowerUp (plafond CPU mesuré pour Battlefield 6 seulement).
    "battlefield 6": _g((100, 75, 42), 271.4, "mesure", aliases=("bf6",)),
    "doom the dark ages": _g((80, 58, 32), 250, "mesure", aliases=("doom dark ages",)),
    "clair obscur expedition 33": _g((60, 44, 24), 200, "mesure", aliases=("clair obscur", "expedition 33")),

    # --- Estimés (recoupement de benchmarks publiés, Ultra natif) ---
    "fortnite": _g((105, 72, 41), 300),
    "valorant": _g((500, 380, 220), 950),
    "league of legends": _g((700, 600, 400), 650, aliases=("lol",)),
    "apex legends": _g((160, 115, 64), 300, cap=300, aliases=("apex",)),
    "call of duty warzone": _g((120, 88, 50), 250, aliases=("warzone", "cod warzone")),
    "call of duty modern warfare iii": _g((120, 88, 50), 270, aliases=("modern warfare 3", "modern warfare iii", "mw3")),
    "call of duty black ops 6": _g((118, 86, 48), 270, aliases=("black ops 6", "bo6")),
    "overwatch 2": _g((190, 140, 80), 600, cap=600, aliases=("overwatch",)),
    "rainbow six siege": _g((280, 200, 115), 600, aliases=("r6", "rainbow six", "r6 siege")),
    "pubg battlegrounds": _g((150, 110, 62), 250, aliases=("pubg",)),
    "minecraft": _g((500, 450, 320), 450),
    # Le moteur de GTA V (version historique) ne dépasse pas ~187 FPS.
    "grand theft auto v": _g((150, 115, 65), 180, cap=187, aliases=("gta v", "gta 5", "gta5")),
    "red dead redemption 2": _g((80, 62, 36), 200, aliases=("rdr2", "rdr 2")),
    "diablo iv": _g((140, 100, 55), 300, aliases=("diablo 4",)),
    "rocket league": _g((350, 280, 170), 500),
    "dota 2": _g((200, 160, 95), 300),
    "world of warcraft": _g((150, 115, 68), 180, aliases=("wow",)),
    "destiny 2": _g((160, 115, 65), 300),
    "escape from tarkov": _g((110, 85, 50), 150, aliases=("tarkov",)),
    "assassin's creed mirage": _g((90, 68, 40), 220),
    "assassin's creed valhalla": _g((85, 65, 38), 200),
    "forza horizon 5": _g((100, 78, 46), 250),
    "resident evil 4": _g((100, 72, 39), 250, vram8={"1440p": 0.9, "4k": 0.75}),
    "resident evil village": _g((150, 110, 60), 300),
    "street fighter 6": _g((200, 160, 100), 300, cap=60),
    "tekken 8": _g((140, 105, 60), 300, cap=60),
    "helldivers 2": _g((72, 53, 30), 140),
    "palworld": _g((70, 52, 30), 150),
    "sea of thieves": _g((110, 80, 45), 250),
    "fallout 4": _g((140, 110, 65), 160),
    "fallout 76": _g((150, 115, 65), 200, cap=63),
    "the elder scrolls v skyrim": _g((200, 160, 100), 200, cap=60, aliases=("skyrim",)),
    "terraria": _g((500, 500, 400), 500, cap=60),
    "stardew valley": _g((500, 500, 400), 500, cap=60),
    "among us": _g((500, 500, 400), 500, cap=60),
    "fall guys": _g((250, 190, 110), 350),
    # Genshin Impact plafonne à 60 FPS par défaut, 120 via l'option dédiée.
    "genshin impact": _g((160, 130, 75), 250, cap=120),
    "warframe": _g((220, 160, 90), 400),
    "path of exile 2": _g((110, 80, 45), 200, aliases=("poe2", "poe 2")),
    "final fantasy xiv": _g((140, 105, 60), 250, aliases=("ffxiv", "ff14")),
    "dead by daylight": _g((150, 120, 70), 300, cap=120, aliases=("dbd",)),
    "left 4 dead 2": _g((400, 330, 220), 350, aliases=("l4d2",)),
    "team fortress 2": _g((400, 330, 220), 350, aliases=("tf2",)),
    "battlefield 2042": _g((100, 75, 42), 180),
    "halo infinite": _g((95, 70, 40), 220),
    "far cry 6": _g((105, 80, 46), 170, vram8={"4k": 0.85}),
    "it takes two": _g((140, 105, 60), 300),
    "cities skylines ii": _g((45, 32, 18), 80, aliases=("cities skylines 2",)),
    "total war warhammer iii": _g((75, 55, 30), 150, aliases=("warhammer 3", "total war warhammer 3")),
    "marvel rivals": _g((90, 65, 35), 250),
    "silent hill 2": _g((50, 36, 19), 120),
    "dragon's dogma 2": _g((60, 47, 27), 95, aliases=("dragons dogma 2",)),
    "star wars jedi survivor": _g((65, 48, 27), 110, aliases=("jedi survivor",)),
    # Ajoutés avec les duels TechSpot (valeurs de repli ; la mesure prime).
    "hunt showdown 1896": _g((70, 52, 30), 200, aliases=("hunt showdown", "hunt: showdown")),
    "naraka bladepoint": _g((120, 90, 50), 300, aliases=("naraka",)),
    "war thunder": _g((150, 110, 65), 350),
    "rust": _g((70, 55, 33), 120),
    "ark survival ascended": _g((40, 30, 17), 90, aliases=("ark", "ark: survival ascended")),
    "delta force": _g((120, 90, 50), 250),
    "forza horizon 6": _g((80, 60, 34), 250),
    "the elder scrolls iv oblivion remastered": _g((45, 33, 18), 90, aliases=("oblivion remastered", "oblivion")),
}

# Jeux connus mais sans estimation possible (pas sortis sur PC, ou plafonds
# trop variables pour donner un chiffre honnête).
UNAVAILABLE_GAMES = {
    "grand theft auto vi": "pas encore sorti sur PC",
    "gta vi": "pas encore sorti sur PC",
    "gta 6": "pas encore sorti sur PC",
}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace("’", "'")
    text = re.sub(r"[^a-z0-9' ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_GAME_INDEX = {}
for _key, _data in GAMES.items():
    for _name in (_key, *_data["aliases"]):
        _GAME_INDEX[_normalize(_name)] = _key
        _GAME_INDEX[_normalize(_name).replace("'", "")] = _key


def find_game(name: str):
    """Retourne (clé, données) ou (None, raison) si le jeu n'est pas couvert."""
    n = _normalize(name)
    for variant in (n, n.replace("'", "")):
        if variant in UNAVAILABLE_GAMES:
            return None, UNAVAILABLE_GAMES[variant]
        if variant in _GAME_INDEX:
            key = _GAME_INDEX[variant]
            return key, GAMES[key]
    # Correspondance partielle ("Call of Duty: Warzone 2.0" -> "warzone") :
    # le nom connu le plus long contenu dans la saisie, 4 caractères minimum.
    flat = n.replace("'", "")
    best = None
    for known, key in _GAME_INDEX.items():
        if len(known) >= 4 and re.search(r"\b" + re.escape(known) + r"\b", flat):
            if best is None or len(known) > len(best[0]):
                best = (known, key)
    if best:
        return best[1], GAMES[best[1]]
    return None, None


def _canon(pattern: str) -> str:
    """Motif de GPU_RELATIVE -> nom lisible servant de clé ("rtx 4060 ti")."""
    name = re.sub(r"\(\?![^)]*\)", "", pattern)
    return re.sub(r"\\s\*", " ", name).strip()


# Indices relatifs par carte ("rtx 4060 ti|8" -> (1080p, 1440p, 4K)), pour
# extrapoler depuis les cartes mesurées dans un même jeu.
REL_BY_KEY = {
    f"{_canon(pattern)}|{vram}": values
    for pattern, variants, _ in GPU_RELATIVE
    for vram, values in variants.items()
}


def match_gpu_full(nom: str):
    """Nom commercial -> (clé canonique, indices par résolution, vram) ou (None, None, None)."""
    n = nom.lower()
    for pattern, variants, default_vram in GPU_RELATIVE:
        if re.search(pattern, n):
            m = VRAM_PATTERN.search(n)
            vram = int(m.group(1)) if m and int(m.group(1)) in variants else default_vram
            return _canon(pattern), variants[vram], vram
    return None, None, None


def match_gpu(nom: str):
    """Retourne (indices par résolution, vram en Go) ou (None, None)."""
    _, rel, vram = match_gpu_full(nom)
    return rel, vram


LABEL_VRAM = re.compile(r"(\d{1,2})\s*gb?\s*$", re.IGNORECASE)


def gpu_key(label: str):
    """
    Libellé de graphique ("RTX 4060 Ti 8 GB", parfois collé "RTX40608GB")
    -> (clé canonique, vram). Refuse les variantes absentes de la table
    (une "RTX 2060 Super" n'est pas une RTX 2060).
    """
    n = label.lower().strip()
    for pattern, variants, default_vram in GPU_RELATIVE:
        if re.search(pattern, n):
            canon = _canon(pattern)
            for suffix in ("super", "ti", "xt", "gre"):
                if re.search(suffix, n) and not re.search(suffix, canon):
                    return None, None
            m = LABEL_VRAM.search(n)
            vram = int(m.group(1)) if m else default_vram
            if vram not in variants:
                return None, None
            return canon, vram
    return None, None


def gpu_index_1440(nom: str):
    """Indice unique (1440p) pour le tri et le comparateur."""
    rel, _ = match_gpu(nom)
    return rel[1] if rel else None


def normalize_cpu_name(nom: str) -> str:
    # "Intel Core i7 14700K" -> "intel core i7-14700k" : les motifs de l'indice
    # CPU attendent le tiret, souvent absent des titres Amazon.
    return re.sub(r"\b(i[3579])\s+(\d{4,5})", r"\1-\2", nom.lower())


# --- Mesures carte par carte (fps_measurements.json) -----------------------
# Relevées dans les graphiques TechPowerUp de chaque jeu (lecture automatique
# recoupée avec la longueur des barres). {jeu: {"source", "reglages",
# "cartes": {"rtx 4060 ti|8": [1080p, 1440p, 4K]}}}
_MEASUREMENTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fps_measurements.json")
try:
    with open(_MEASUREMENTS_PATH, encoding="utf8") as _f:
        MEASURED = json.load(_f)
except (OSError, ValueError):
    MEASURED = {}


# Nombre minimal de cartes testées dans un jeu pour en déduire les autres.
MIN_MEASURED_CARDS = 2

# Écart typique entre résolutions pour une même carte (médiane des 24 jeux du
# test RTX 5060 de TechPowerUp) : 1440p ≈ 71 % du 1080p, 4K ≈ 53 % du 1440p.
# Sert quand un test ne couvre pas une résolution (ex. duels TechSpot sans 1080p).
RES_SCALING = (1.0, 0.712, 0.712 * 0.53)


def _measured_at(game, card_key, i, vram):
    exact = game["cartes"].get(card_key)
    if exact and exact[i]:
        return "mesuré", exact[i]
    target_rel = REL_BY_KEY.get(card_key)
    if not target_rel:
        return None
    points = []
    for key, values in game["cartes"].items():
        rel = REL_BY_KEY.get(key)
        if values[i] and rel:
            points.append((rel[i], values[i], int(key.rsplit("|", 1)[1])))
    if len(points) < MIN_MEASURED_CARDS:
        return None
    # À 1440p/4K, une carte 8 Go se compare d'abord à d'autres cartes 8 Go
    # (même risque de saturation de la mémoire vidéo), et inversement.
    if i >= 1:
        same_class = [p for p in points if (p[2] <= 8) == (vram <= 8)]
        if len(same_class) >= MIN_MEASURED_CARDS:
            points = same_class
    points.sort(key=lambda p: abs(math.log(p[0] / target_rel[i])))
    estimates = sorted(fps * target_rel[i] / rel for rel, fps, _ in points[:4])
    mid = len(estimates) // 2
    value = estimates[mid] if len(estimates) % 2 else (estimates[mid - 1] + estimates[mid]) / 2
    return "déduit", value


def _gpu_fps_measured(game_key, card_key, i, vram):
    """
    FPS limités par la carte graphique d'après les tests de ce jeu, au
    réglage du test : ("mesuré", fps) si la carte y a été testée, ("déduit",
    fps) si extrapolée depuis les cartes testées les plus proches (ou depuis une
    autre résolution du même test), None s'il n'existe aucun test du jeu.
    """
    game = MEASURED.get(game_key)
    if not game or not game.get("cartes"):
        return None
    found = _measured_at(game, card_key, i, vram)
    if found:
        return found
    target_rel = REL_BY_KEY.get(card_key)
    if not target_rel:
        return None
    for j in sorted((0, 1, 2), key=lambda j: abs(j - i)):
        if j == i:
            continue
        other = _measured_at(game, card_key, j, vram)
        if other:
            value = other[1] * (RES_SCALING[i] / RES_SCALING[j]) * (target_rel[i] / target_rel[j])
            return "déduit", value
    return None


RESOLUTIONS = (("1080p", 0), ("1440p", 1), ("4k", 2))


def estimate_game(game_key, game_data, gpu_card_key, gpu_rel, vram, cpu_index, quality="ultra"):
    """FPS par résolution, facteur limitant et origine de la valeur GPU."""
    preset = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["ultra"])
    results = {}
    for res, i in RESOLUTIONS:
        measured = _gpu_fps_measured(game_key, gpu_card_key, i, vram)
        if measured:
            origin, gpu_fps = measured
            # Mesure faite à un autre réglage que l'Ultra (ex. Medium pour
            # Marvel Rivals chez TechSpot) : ramenée à l'Ultra avant le préréglage.
            measured_quality = MEASURED[game_key].get("qualite", "ultra")
            gpu_fps /= QUALITY_PRESETS.get(measured_quality, QUALITY_PRESETS["ultra"])["gpu"]
        else:
            origin = "estimé"
            rel = gpu_rel[i] / 100
            if res == "4k" and vram > 8:
                rel *= FOUR_K_VRAM_BIAS_CORRECTION
            gpu_fps = game_data["gpu"][i] * rel
            if vram <= 8 and res in game_data["vram8"]:
                factor = game_data["vram8"][res]
                gpu_fps *= factor ** 1.5 if vram <= 6 else factor
        gpu_fps *= preset["gpu"]
        # Baisser les réglages soulage la mémoire vidéo : la saturation mesurée
        # en Ultra ne s'applique pleinement qu'en Ultra/Élevé.
        if vram <= 8 and res in game_data["vram8"] and quality in ("moyen", "bas"):
            gpu_fps /= game_data["vram8"][res] ** (0.5 if quality == "moyen" else 1)

        # Plafond processeur mesuré (duels TechSpot où même les cartes les plus
        # rapides plafonnent) : prime sur l'estimation.
        cpu_base = MEASURED.get(game_key, {}).get("plafond_cpu") or game_data["cpu"]
        cpu_fps = cpu_base * (cpu_index / REFERENCE_CPU_INDEX_9850X3D) * preset["cpu"] if cpu_index else None
        candidates = [("GPU", gpu_fps)]
        if cpu_fps:
            candidates.append(("CPU", cpu_fps))
        if game_data["cap"]:
            candidates.append(("jeu", float(game_data["cap"])))
        limit, fps = min(candidates, key=lambda c: c[1])
        # CPU et GPU à moins de 10 % l'un de l'autre : configuration équilibrée.
        if limit in ("GPU", "CPU") and cpu_fps and abs(gpu_fps - cpu_fps) / max(gpu_fps, cpu_fps) < 0.10:
            limit = "équilibré"
        results[res] = {"fps": round_fps(fps), "limite": limit, "origine": origin}
    return results


def game_source(game_key):
    """Lien et réglages du test publié utilisé pour ce jeu, s'il existe."""
    game = MEASURED.get(game_key)
    if not game:
        return None
    url = game.get("source")
    return {
        "url": url[0] if isinstance(url, list) else url,
        "reglages": game.get("reglages") or "maximum",
        "editeur": game.get("editeur", "TechPowerUp"),
    }


def round_fps(fps: float) -> int:
    # Précision honnête : à l'unité sous 60 FPS, à 5 près au-dessus.
    if fps < 60:
        return max(1, round(fps))
    return int(round(fps / 5) * 5)
