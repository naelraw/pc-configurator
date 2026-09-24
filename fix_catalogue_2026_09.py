"""Correction du catalogue : catégories, caractéristiques manquantes, écritures normalisées.
Usage : python fix_catalog.py <base> [--appliquer]   (sans --appliquer : simulation)"""
import json, re, sqlite3, sys

db = sqlite3.connect(sys.argv[1], timeout=10)
APPLY = "--appliquer" in sys.argv
changes = []

def row(cid):
    r = db.execute("select categorie, nom, specs_json from components where id=?", (cid,)).fetchone()
    return (r[0], r[1], json.loads(r[2] or "{}")) if r else None

def update(cid, cat=None, nom=None, specs=None, why=""):
    old_cat, old_nom, old_specs = row(cid)
    cat, nom = cat or old_cat, nom or old_nom
    new_specs = {**old_specs, **(specs or {})} if specs is not None else old_specs
    if cat != old_cat or nom != old_nom:
        while db.execute("select 1 from components where categorie=? and nom=? and id!=?", (cat, nom, cid)).fetchone():
            couleur = new_specs.get("couleur")
            nom = f"{nom} {couleur}" if couleur and not nom.endswith(couleur) else f"{nom} ({cid})"
    if (cat, nom, new_specs) == (old_cat, old_nom, old_specs):
        return
    changes.append(f"{cid} | {old_cat}{' -> ' + cat if cat != old_cat else ''} | {nom[:55]} | {why} | {old_specs} -> {new_specs}")
    if APPLY:
        db.execute("update components set categorie=?, nom=?, specs_json=? where id=?",
                   (cat, nom, json.dumps(new_specs, ensure_ascii=False), cid))

# 1. Fiches mal classées
for cid in (2794, 2798, 2806, 2804, 2844, 2811, 2799, 2810):
    update(cid, cat="RAM", specs={"type": "DDR4"}, why="RAM rangée dans CPU")
update(2827, cat="Refroidissement", specs={"sockets_supportes": ["LGA1851", "LGA1700", "LGA1200", "LGA1151", "AM5", "AM4"]}, why="watercooling rangé dans CPU")
update(2868, cat="Boîtier", nom="Thermalright A70 ARGB", specs={"formats_supportes": ["ATX", "Micro-ATX", "Mini-ITX"], "gpu_max_length_mm": 420}, why="boîtier rangé dans GPU")
update(2828, cat="Boîtier", nom="ASUS TUF Gaming GT502 Plus", specs={"formats_supportes": ["ATX", "Micro-ATX", "Mini-ITX"]}, why="boîtier rangé dans Carte mère")

# 2. Caractéristiques essentielles manquantes (déduites du modèle exact)
for cid, specs in {
    2823: {"socket": "LGA1700", "format": "ATX", "ram_type": "DDR5"},
    2834: {"socket": "LGA1700", "format": "ATX", "ram_type": "DDR4"},
    2821: {"socket": "AM5", "format": "Micro-ATX", "ram_type": "DDR5"},
    2836: {"socket": "LGA1851", "format": "ATX", "ram_type": "DDR5"},
    2087: {"ram_type": "DDR5"},
    2598: {"formats_supportes": ["Micro-ATX", "Mini-ITX"]},
    2593: {"formats_supportes": ["ATX", "Micro-ATX", "Mini-ITX"]},
    2594: {"formats_supportes": ["ATX", "Micro-ATX", "Mini-ITX"]},
    2870: {"formats_supportes": ["ATX", "Micro-ATX", "Mini-ITX"]},
    2599: {"formats_supportes": ["ATX", "Micro-ATX", "Mini-ITX"]},
    2786: {"tdp": 65},
    2847: {"type": "DDR5"}, 2849: {"type": "DDR5"}, 2813: {"type": "DDR5"},
    2865: {"type": "NVMe"}, 2860: {"type": "NVMe"},
    2829: {"wattage": 1200}, 2830: {"wattage": 650},
}.items():
    update(cid, specs=specs, why="caractéristique manquante")

# 3. Écritures normalisées (le contrôle de compatibilité compare le texte exact)
FORMATS = {"atx": "ATX", "e-atx": "E-ATX", "eatx": "E-ATX", "micro-atx": "Micro-ATX", "micro atx": "Micro-ATX",
           "matx": "Micro-ATX", "m-atx": "Micro-ATX", "mini-itx": "Mini-ITX", "mini itx": "Mini-ITX", "mitx": "Mini-ITX"}
for cid, specs_json in db.execute("select id, specs_json from components where categorie='Boîtier'").fetchall():
    s = json.loads(specs_json or "{}")
    fmts = s.get("formats_supportes")
    if isinstance(fmts, list):
        norm = list(dict.fromkeys(FORMATS.get(f.strip().lower(), f.strip()) for f in fmts))
        if norm != fmts:
            update(cid, specs={"formats_supportes": norm}, why="formats normalisés")

def norm_socket(v):
    v = re.sub(r"^(intel|amd)\s+", "", v.strip(), flags=re.I).upper().replace(" ", "")
    if v in ("115X", "LGA115X"): return ["LGA1150", "LGA1151", "LGA1155", "LGA1156"]
    if v in ("17XX", "LGA17XX"): return ["LGA1700"]
    if v == "1556": return ["LGA1156"]  # coquille évidente dans la fiche
    if re.fullmatch(r"\d{4}", v): return ["LGA" + v]
    if re.fullmatch(r"LGA\d{4}", v) or re.fullmatch(r"AM\d", v) or v in ("STR5", "TR4", "STRX4"): return [v.replace("STR", "sTR")]
    return [v]

for cid, specs_json in db.execute("select id, specs_json from components where categorie='Refroidissement'").fetchall():
    s = json.loads(specs_json or "{}")
    sk = s.get("sockets_supportes")
    if isinstance(sk, list) and sk:
        norm = list(dict.fromkeys(x for v in sk for x in norm_socket(str(v))))
        # LGA1851 (Core Ultra) garde les fixations de LGA1700 : un ventirad
        # compatible LGA1700 l'est aussi, même si sa fiche ne le cite pas.
        if "LGA1700" in norm and "LGA1851" not in norm:
            norm.insert(norm.index("LGA1700"), "LGA1851")
        if norm != sk:
            update(cid, specs={"sockets_supportes": norm}, why="sockets normalisés")

for c in changes: print(c)
print(f"\n{len(changes)} fiche(s) {'MODIFIÉE(S)' if APPLY else 'à modifier (simulation, rien écrit)'}")
if APPLY: db.commit()
