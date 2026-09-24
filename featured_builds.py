"""
Configurations mises en avant sur la page d'accueil.

Pour chaque profil (budget + usage), cherche dans le catalogue EN STOCK la
meilleure paire CPU/GPU que le budget permet, complétée par des pièces
compatibles et raisonnables (carte mère, RAM, SSD, alimentation, boîtier,
ventirad). Tout est recalculé à partir des prix du moment : les configs
suivent le catalogue au lieu d'être figées à la main.

Fonction pure (reçoit la liste des composants de get_all_components_light) :
aucun accès base ni réseau ici.
"""
import math
import re

import fps_data
from compatibility import verifier_compatibilite

PROFILES = [
    {
        "id": "1080p", "onglet": "1080p", "titre": "Premier PC gaming", "usage": "Jouer en 1080p",
        "budget": 850, "resolution": "1080p", "qualite": "ultra",
        "ram_go": 16, "ssd_go": 500,
        "min_prix": {"Carte mère": 70, "Boîtier": 45, "Alimentation": 45, "Refroidissement": 15},
    },
    {
        "id": "1440p", "onglet": "1440p", "titre": "Le bon compromis", "usage": "Jouer en 1440p",
        "budget": 1300, "resolution": "1440p", "qualite": "ultra",
        "ram_go": 32, "ssd_go": 1000,
        "min_prix": {"Carte mère": 100, "Boîtier": 60, "Alimentation": 60, "Refroidissement": 25},
    },
    {
        "id": "1440p-plus", "onglet": "1440p+", "titre": "Haut de gamme", "usage": "1440p en ultra, haute fréquence",
        "budget": 2000, "resolution": "1440p", "notes_sur": ["1440p", "1080p"], "qualite": "ultra",
        "ram_go": 32, "ssd_go": 2000, "ram_type": "DDR5",
        "min_prix": {"Carte mère": 140, "Boîtier": 80, "Alimentation": 80, "Refroidissement": 35},
    },
    {
        "id": "4k", "onglet": "4K", "titre": "Sans compromis", "usage": "Jouer en 4K",
        "budget": 3200, "resolution": "4k", "notes_sur": ["4k", "1440p"], "qualite": "ultra",
        "ram_go": 32, "ssd_go": 2000, "ram_type": "DDR5",
        "min_prix": {"Carte mère": 180, "Boîtier": 100, "Alimentation": 110, "Refroidissement": 60},
    },
]

# Jeux affichés pour chaque config (noms tels que connus de fps_data).
SHOWCASE_GAMES = ["Cyberpunk 2077", "Fortnite", "Counter-Strike 2"]

# Panel servant à noter chaque paire CPU/GPU : jeux lourds pour la carte
# graphique ET jeux où le processeur limite vite, pour que le choix reflète
# un usage réel plutôt qu'un seul type de jeu.
SCORING_GAMES = ["cyberpunk 2077", "black myth wukong", "alan wake 2",
                 "counter-strike 2", "fortnite", "baldur's gate 3"]

# Marge d'alimentation au-delà de CPU + GPU (carte mère, disques, ventilateurs,
# pics de consommation) : plus large que le minimum du contrôle de compatibilité.
PSU_HEADROOM_W = 200

# Alimentations d'entrée de gamme à la fiabilité discutable : jamais proposées
# dans une config mise en avant (elles restent disponibles au configurateur).
PSU_BRANDS_EXCLUDED = ("mars gaming", "tacens")

_RAM_KIT = re.compile(r"(\d)\s*x\s*(\d+)\s*go\b", re.IGNORECASE)
_RAM_TOTAL = re.compile(r"(\d+)\s*go\b", re.IGNORECASE)
_RAM_SPEED = re.compile(r"(\d{4})\s*mhz\b", re.IGNORECASE)
_SSD_TO = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:to|tb)\b", re.IGNORECASE)
_SSD_GO = re.compile(r"(\d{3,4})\s*(?:go|gb)\b", re.IGNORECASE)


def _price(c):
    p = c.get("prix_indicatif")
    return float(p) if p else 0.0


def _ram_go(nom):
    m = _RAM_KIT.search(nom)
    if m:
        return int(m.group(1)) * int(m.group(2))
    m = _RAM_TOTAL.search(nom)
    return int(m.group(1)) if m else None


def _ssd_go(nom):
    m = _SSD_TO.search(nom)
    if m:
        return float(m.group(1).replace(",", ".")) * 1000
    m = _SSD_GO.search(nom)
    return float(m.group(1)) if m else None


def _cooler_fits(cooler, socket):
    specs = cooler.get("specs") or {}
    sockets = specs.get("sockets_supportes")
    if isinstance(sockets, list) and sockets:
        return socket in sockets
    if specs.get("socket"):
        return specs["socket"] == socket
    return False


def _cheapest(items, key=None, min_price=0):
    """Le moins cher au-dessus d'un prix plancher (évite le bas de gamme douteux) ; sinon le moins cher tout court."""
    pool = [c for c in items if key is None or key(c)]
    if not pool:
        return None
    above = [c for c in pool if _price(c) >= min_price]
    return min(above or pool, key=_price)


def _usable(components):
    by_cat = {}
    for c in components:
        if not c.get("en_stock") or _price(c) <= 0 or not c.get("image_url"):
            continue
        by_cat.setdefault(c["categorie"], []).append(c)
    return by_cat


def _platform(cpu, cat, profile):
    """Carte mère + RAM + ventirad les moins chers et corrects pour ce CPU."""
    socket = cpu["specs"].get("socket")
    mins = profile["min_prix"]
    options = []
    for mb in cat.get("Carte mère", []):
        ms = mb.get("specs") or {}
        if ms.get("socket") != socket or not ms.get("ram_type") or not ms.get("format"):
            continue
        # Configs haut de gamme : plateforme actuelle (DDR5) uniquement.
        if profile.get("ram_type") and ms["ram_type"] != profile["ram_type"]:
            continue
        ram = _cheapest(
            cat.get("RAM", []),
            key=lambda r: (r.get("specs") or {}).get("type") == ms["ram_type"]
            and (_ram_go(r["nom"]) or 0) == profile["ram_go"]
            and int((_RAM_SPEED.search(r["nom"]) or [0, 0])[1]) >= (5600 if ms["ram_type"] == "DDR5" else 3200),
        ) or _cheapest(
            cat.get("RAM", []),
            key=lambda r: (r.get("specs") or {}).get("type") == ms["ram_type"] and (_ram_go(r["nom"]) or 0) >= profile["ram_go"],
        )
        if ram:
            options.append((mb, ram, _price(mb) + _price(ram)))
    if not options:
        return None
    # La moins chère au-dessus du prix plancher ; à défaut, la plus proche de ce plancher.
    above = [o for o in options if _price(o[0]) >= mins["Carte mère"]]
    best = min(above, key=lambda o: o[2]) if above else max(options, key=lambda o: _price(o[0]))
    cooler = _cheapest(cat.get("Refroidissement", []), key=lambda k: _cooler_fits(k, socket),
                       min_price=mins["Refroidissement"])
    if not cooler:
        return None
    return {"Carte mère": best[0], "RAM": best[1], "Refroidissement": cooler,
            "cout": best[2] + _price(cooler)}


def build_profile(components, profile):
    cat = _usable(components)
    games = [(k, d) for k, d in (fps_data.find_game(g) for g in SCORING_GAMES) if k]
    quality = profile["qualite"]
    # Une config haut de gamme doit aussi tenir la haute fréquence dans la
    # définition inférieure : elle est notée sur plusieurs définitions.
    resolutions = profile.get("notes_sur") or [profile["resolution"]]

    # Limite FPS de chaque GPU seul (sans CPU) et de chaque CPU seul, par jeu :
    # le moteur FPS du site prend le minimum des deux, on peut donc noter
    # toutes les paires sans relancer l'estimation complète.
    gpu_fps = {}
    for g in cat.get("GPU", []):
        match = fps_data.match_gpu_full(g["nom"])
        if not match or match[1] is None or not isinstance((g.get("specs") or {}).get("tdp"), (int, float)):
            continue
        card, rel, vram = match
        card_key = f"{card}|{vram}" if card else None
        gpu_fps[g["id"]] = [
            est[res]["fps"]
            for k, d in games
            for est in [fps_data.estimate_game(k, d, card_key, rel, vram, None, quality)]
            for res in resolutions
        ]
    preset_cpu = fps_data.QUALITY_PRESETS[quality]["cpu"]
    cpu_fps = {}
    for c in cat.get("CPU", []):
        index, _origin = fps_data.match_cpu(c["nom"])
        specs = c.get("specs") or {}
        if not index or not specs.get("socket") or not isinstance(specs.get("tdp"), (int, float)):
            continue
        cpu_fps[c["id"]] = [
            (fps_data.MEASURED.get(k, {}).get("plafond_cpu") or d["cpu"])
            * (index / fps_data.REFERENCE_CPU_INDEX_9850X3D) * preset_cpu
            for k, d in games
            for _res in resolutions
        ]
    cpus = [c for c in cat.get("CPU", []) if c["id"] in cpu_fps]
    gpus = [g for g in cat.get("GPU", []) if g["id"] in gpu_fps]
    if not cpus or not gpus or not games:
        return None

    ssd = _cheapest(cat.get("Stockage", []),
                    key=lambda s: (s.get("specs") or {}).get("type") == "NVMe" and (_ssd_go(s["nom"]) or 0) >= profile["ssd_go"])
    if not ssd:
        return None
    psus = sorted(
        (p for p in cat.get("Alimentation", [])
         if isinstance((p.get("specs") or {}).get("wattage"), (int, float))
         and not p["nom"].lower().startswith(PSU_BRANDS_EXCLUDED)),
        key=_price,
    )
    cases = cat.get("Boîtier", [])

    platforms = {c["id"]: _platform(c, cat, profile) for c in cpus}

    psu_cache, case_cache = {}, {}

    def psu_for(need_w):
        if need_w not in psu_cache:
            psu_cache[need_w] = _cheapest(psus, key=lambda p: p["specs"]["wattage"] >= need_w,
                                          min_price=profile["min_prix"]["Alimentation"])
        return psu_cache[need_w]

    def case_for(mb_format, glen):
        k = (mb_format, glen)
        if k not in case_cache:
            case_cache[k] = _cheapest(
                cases,
                key=lambda b: mb_format in ((b.get("specs") or {}).get("formats_supportes") or [])
                and not (glen and (b.get("specs") or {}).get("gpu_max_length_mm")
                         and glen > b["specs"]["gpu_max_length_mm"]),
                min_price=profile["min_prix"]["Boîtier"],
            )
        return case_cache[k]

    best = None
    for cpu in cpus:
        plat = platforms[cpu["id"]]
        if not plat:
            continue
        mb_format = plat["Carte mère"]["specs"]["format"]
        base = _price(cpu) + plat["cout"] + _price(ssd)
        if base >= profile["budget"]:
            continue
        for gpu in gpus:
            if base + _price(gpu) >= profile["budget"]:
                continue
            psu = psu_for(cpu["specs"]["tdp"] + gpu["specs"]["tdp"] + PSU_HEADROOM_W)
            case = case_for(mb_format, (gpu.get("specs") or {}).get("longueur_mm"))
            if not psu or not case:
                continue
            total = base + _price(gpu) + _price(psu) + _price(case)
            if total > profile["budget"]:
                continue
            # FPS moyens estimés sur le panel (moyenne géométrique : un jeu à
            # 400 FPS ne masque pas un autre à 40). À 1 % près, la config la
            # moins chère l'emporte : un CPU plus cher qui ne change rien aux
            # FPS n'est jamais retenu.
            score = math.exp(sum(math.log(max(1.0, min(gf, cf)))
                                 for gf, cf in zip(gpu_fps[gpu["id"]], cpu_fps[cpu["id"]])) / len(gpu_fps[gpu["id"]]))
            key = (round(math.log(score), 2), -total)
            if best is None or key > best[0]:
                best = (key, {"CPU": cpu, "Carte mère": plat["Carte mère"], "RAM": plat["RAM"],
                              "GPU": gpu, "Refroidissement": plat["Refroidissement"],
                              "Stockage": ssd, "Alimentation": psu, "Boîtier": case}, total)
    if not best:
        return None

    parts = best[1]
    erreurs = verifier_compatibilite(
        parts["CPU"]["specs"], parts["Carte mère"]["specs"], parts["RAM"]["specs"],
        parts["Boîtier"]["specs"], parts["Alimentation"]["specs"], parts["GPU"]["specs"],
        [parts["Stockage"]["specs"]], parts["Refroidissement"]["specs"],
    )
    return {"parts": parts, "total": round(best[2], 2), "compatible": not erreurs, "erreurs": erreurs}
