"""Étape 10 : dimensions physiques relevées sur les fiches des fabricants
(jamais les « Dimensions de l'article » d'Amazon, qui mesurent souvent le carton).
Usage : python fix_dimensions_2026_09.py <base> [--appliquer]   (sans --appliquer : simulation)

Chaque ligne donne l'id, un bout du nom attendu (garde-fou contre un mauvais id)
et les valeurs à écrire. Une valeur déjà en base et différente est signalée et
remplacée : les fiches fabricant font foi."""
import json, sqlite3, sys

db = sqlite3.connect(sys.argv[1], timeout=10)
APPLY = "--appliquer" in sys.argv

# Boîtiers : longueur GPU max / hauteur ventirad max (mm), fiches fabricant.
BOITIERS = {
    2598: ("Prime AP202", 420, 175),            # asus.com techspec
    2824: ("GT502 Horizon", 400, 163),          # asus.com techspec
    2832: ("GT502 Plus", 400, 163),             # asus.com techspec
    2828: ("GT502 Plus", 400, 163),
    2592: ("3200D RS", 400, 165),               # corsair.com
    2587: ("3500X LX-R", 425, 170),             # corsair.com
    2591: ("3500X RS-R", 425, 170),             # corsair.com
    2593: ("AIR 5400", 360, 180),               # corsair.com
    2586: ("4000D RS", 430, 170),               # corsair.com
    2589: ("4500X", 460, 185),                  # corsair.com
    2588: ("4000D", 430, 170),                  # corsair.com
    2594: ("4000D Wood", 430, 170),             # corsair.com
    2590: ("4500X", 460, 185),
    2871: ("North XL", 413, 185),               # fractal-design.com
    2870: ("O11 Dynamic Mini V2", 400, 160),    # lian-li.com
    2579: ("Forge 100M", 330, 160),             # msi.com (toutes les fiches MSI)
    2578: ("Forge 100R", 330, 160),
    2599: ("Forge 110R", 330, 160),
    2576: ("Forge 112R", 330, 160),
    2577: ("Forge 120A", 330, 160),
    2869: ("Forge 320R", 390, 160),
    2584: ("Forge 320R", 390, 160),
    2581: ("Forge 321R", 390, 160),
    2585: ("Forge M100R", 300, 160),
    2580: ("PANO 100R", 400, 166),
    2574: ("PANO 110R", 400, 160),
    2575: ("PANO M100L", 390, 175),
    2583: ("GUNGNIR 300R", 360, 175),
    2582: ("Gungnir 110R", 340, 165),
    2873: ("MC-CURV", 334, 165),                # marsgaming.eu
    2867: ("MC-VIEW3", 330, 155),               # marsgaming.eu
    2597: ("H3 Flow", 352, 170),                # nzxt.com (avec ventilateurs en façade)
    2596: ("H5 Flow", 410, 170),                # nzxt.com
    2875: ("H6 Flow", 365, 163),                # nzxt.com
    2872: ("H6 Flow", 365, 163),
    2868: ("A70", 420, 168),                    # thermalright.com (168,4)
    2595: ("A70", 420, 168),
}

UPDATES = {cid: (nom, {"gpu_max_length_mm": g, "cpu_cooler_max_height_mm": h})
           for cid, (nom, g, h) in BOITIERS.items()}

# Valeurs fausses déjà en base (souvent la taille du carton Amazon), corrigées
# d'après la fiche fabricant. Longueur GPU = carte avec équerre quand le
# fabricant donne les deux (c'est ce qui compte dans le boîtier).
UPDATES.update({
    2487: ("RX 9070 Challenger", {"longueur_mm": 290}),      # asrock.com (400 = carton)
    2517: ("Swift RX 9060 XT 8", {"longueur_mm": 290}),      # xfxforce.com, RX-96TS38GB7 triple ventilateur (406 = carton)
    2299: ("Phoenix GeForce RTX 3050 V2", {"longueur_mm": 178}),  # asus.com (123 = largeur)
    2432: ("3090 Gaming X Trio", {"longueur_mm": 323}),      # msi.com
    2503: ("Quicksilver", {"longueur_mm": 350}),             # xfxforce.com
    2135: ("B850 Steel Legend", {"m2_slots": 4, "sata_ports": 4}),   # asrock.com (24 SATA : erreur)
    2164: ("Z890-E", {"m2_slots": 7, "sata_ports": 4}),      # rog.asus.com (1 SATA : erreur)
    2107: ("A520M-A PRO", {"m2_slots": 1, "sata_ports": 4}),        # msi.com
    2085: ("B550-A Pro", {"m2_slots": 2, "sata_ports": 6}),         # msi.com
    2078: ("B850M Gaming Plus", {"m2_slots": 2, "sata_ports": 4}),  # msi.com
    2090: ("B850M Mortar", {"m2_slots": 3, "sata_ports": 4}),       # msi.com
    2186: ("TUF Gaming B650-Plus", {"m2_slots": 3, "sata_ports": 4}),  # asus.com
})

changes, problems = [], []
for cid, (expected, values) in UPDATES.items():
    r = db.execute("select nom, specs_json from components where id=?", (cid,)).fetchone()
    if not r or expected.lower() not in r[0].lower():
        problems.append(f"{cid} : attendu « {expected} », trouvé {r[0] if r else 'rien'} -> ignoré")
        continue
    specs = json.loads(r[1] or "{}")
    diff = {k: v for k, v in values.items() if specs.get(k) != v}
    if not diff:
        continue
    note = ", ".join(f"{k} {specs[k]} -> {v}" if k in specs else f"{k} = {v}" for k, v in diff.items())
    changes.append(f"{cid} | {r[0][:50]} | {note}")
    if APPLY:
        db.execute("update components set specs_json=? where id=?",
                   (json.dumps({**specs, **diff}, ensure_ascii=False), cid))

for c in changes: print(c)
for p in problems: print("!!", p)
print(f"\n{len(changes)} fiche(s) {'MODIFIÉE(S)' if APPLY else 'à modifier (simulation, rien écrit)'}, {len(problems)} ignorée(s)")
if APPLY: db.commit()
