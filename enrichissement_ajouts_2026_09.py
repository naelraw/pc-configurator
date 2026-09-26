"""Nom propre et caractéristiques complètes des 40 produits ajoutés le 2026-09-26
(recherche Amazon.fr en stock, import par la page admin). Les caractéristiques
remontées par Amazon étaient partielles ou fausses (hauteur de ventirad, formats
de carte mère, ports SATA...) : valeurs reprises des fiches fabricant (msi.com,
gigabyte.com, asus.com, bequiet.com), de TechPowerUp pour les cartes graphiques,
et des références Intel/AMD pour les processeurs.

Usage : python enrichissement_ajouts_2026_09.py <base> [--appliquer]   (sans --appliquer : simulation)
Repérage par ASIN (le nom change) ; une valeur None efface le champ."""
import json, sqlite3, sys

db = sqlite3.connect(sys.argv[1], timeout=10)
APPLY = "--appliquer" in sys.argv
INTEL_SOCKETS = ["LGA1851", "LGA1700", "LGA1200"]
AMD_SOCKETS = ["AM5", "AM4"]

FICHES = {
    # --- Processeurs ---
    "B0H5KBXR26": ("Intel Core Ultra 9 285K", {"socket": "LGA1851", "tdp": 125, "coeurs": 24, "threads": 24, "frequence_base_ghz": 3.7,
                   "frequence_boost_ghz": 5.7, "cache_l3_mo": 36, "memoire": "DDR5", "igpu": "Intel Graphics"}),
    "B0H2Z7VF4G": ("Intel Core Ultra 7 265KF", {"socket": "LGA1851", "tdp": 125, "coeurs": 20, "threads": 20, "frequence_base_ghz": 3.9,
                   "frequence_boost_ghz": 5.5, "cache_l3_mo": 30, "memoire": "DDR5", "igpu": "Aucune"}),
    "B0BCF5CZ16": ("Intel Core i5-13600KF", {"socket": "LGA1700", "tdp": 125, "coeurs": 14, "threads": 20, "frequence_base_ghz": 3.5,
                   "frequence_boost_ghz": 5.1, "cache_l3_mo": 24, "memoire": "DDR4/DDR5", "igpu": "Aucune"}),
    "B0BCF57FL5": ("Intel Core i7-13700K", {"socket": "LGA1700", "tdp": 125, "coeurs": 16, "threads": 24, "frequence_base_ghz": 3.4,
                   "frequence_boost_ghz": 5.4, "cache_l3_mo": 30, "memoire": "DDR4/DDR5", "igpu": "Intel UHD Graphics 770"}),
    "B0FHDXP318": ("AMD Ryzen 5 9600", {"socket": "AM5", "tdp": 65, "coeurs": 6, "threads": 12, "frequence_base_ghz": 3.8,
                   "frequence_boost_ghz": 5.2, "cache_l3_mo": 32, "memoire": "DDR5", "igpu": "AMD Radeon Graphics"}),
    # --- Cartes graphiques (TechPowerUp) ---
    "B0DNMH4KQM": ("Sparkle Intel Arc B580 Titan OC 12 Go", {"puce": "Arc B580", "vram_go": 12, "type_memoire": "GDDR6", "bus_memoire_bits": 192,
                   "tdp": 200, "longueur_mm": 315, "connecteur_alim": "1 x 8 broches"}),
    "B0DQYM2MHX": ("ASRock Intel Arc B570 Challenger OC 10 Go", {"puce": "Arc B570", "vram_go": 10, "type_memoire": "GDDR6", "bus_memoire_bits": 160,
                   "tdp": 150, "longueur_mm": 250, "connecteur_alim": "1 x 8 broches"}),
    "B0BT524DL4": ("Sapphire Nitro+ Radeon RX 7900 XTX Vapor-X 24 Go", {"puce": "RX 7900 XTX", "vram_go": 24, "type_memoire": "GDDR6",
                   "bus_memoire_bits": 384, "tdp": 420, "longueur_mm": 320, "connecteur_alim": "3 x 8 broches"}),
    # --- Cartes mères (fiches fabricant) ---
    "B0CD2KY2G7": ("GIGABYTE A620M DS3H", {"socket": "AM5", "ram_type": "DDR5", "format": "Micro-ATX", "chipset": "AMD A620",
                   "m2_slots": 1, "sata_ports": 4, "slots_ram": 4, "wifi": "Non"}),
    "B0BZW9RG3P": ("MSI PRO A620M-E", {"socket": "AM5", "ram_type": "DDR5", "format": "Micro-ATX", "chipset": "AMD A620",
                   "m2_slots": 1, "sata_ports": 4, "slots_ram": 2, "wifi": "Non"}),
    "B0CHM63K9W": ("GIGABYTE B650M D3HP", {"socket": "AM5", "ram_type": "DDR5", "format": "Micro-ATX", "chipset": "AMD B650",
                   "m2_slots": 2, "sata_ports": 4, "slots_ram": 4, "wifi": "Non"}),
    "B0C4FNK1R5": ("MSI PRO B650M-P", {"socket": "AM5", "ram_type": "DDR5", "format": "Micro-ATX", "chipset": "AMD B650",
                   "m2_slots": 2, "sata_ports": 4, "slots_ram": 4, "wifi": "Non"}),
    "B0HCDYHQG1": ("MSI PRO B860M-A WIFI6E", {"socket": "LGA1851", "ram_type": "DDR5", "format": "Micro-ATX", "chipset": "Intel B860",
                   "m2_slots": 3, "sata_ports": 4, "slots_ram": 4, "wifi": "Wi-Fi 6E"}),
    "B0DQNRW5HP": ("GIGABYTE B860M DS3H", {"socket": "LGA1851", "ram_type": "DDR5", "format": "Micro-ATX", "chipset": "Intel B860",
                   "m2_slots": 2, "sata_ports": 4, "slots_ram": 4, "wifi": "Non"}),
    "B0BVPR7JKN": ("ASUS Prime B760M-K D4", {"socket": "LGA1700", "ram_type": "DDR4", "format": "Micro-ATX", "chipset": "Intel B760",
                   "m2_slots": 2, "sata_ports": 4, "slots_ram": 2, "wifi": "Non", "couleur": None}),
    "B0DGQ6RGD6": ("ASUS Prime X870-P WiFi", {"socket": "AM5", "ram_type": "DDR5", "format": "ATX", "chipset": "AMD X870",
                   "m2_slots": 4, "sata_ports": 2, "slots_ram": 4, "wifi": "Wi-Fi 7", "couleur": None}),
    # --- Mémoire ---
    "B0BF6ZQ8MY": ("G.Skill Trident Z5 Neo RGB 32 Go DDR5 6000", {"type": "DDR5", "capacite_go": 32, "barrettes": "2 x 16 Go",
                   "frequence_mt_s": 6000, "latence_cl": 30}),
    "B0DX6P486P": ("TEAMGROUP T-Force Delta RGB 32 Go DDR5 6000", {"type": "DDR5", "capacite_go": 32, "barrettes": "2 x 16 Go",
                   "frequence_mt_s": 6000, "latence_cl": 38}),
    "B097K5Q32R": ("Kingston FURY Beast 32 Go DDR4 3200", {"type": "DDR4", "capacite_go": 32, "barrettes": "2 x 16 Go",
                   "frequence_mt_s": 3200, "latence_cl": 16}),
    # --- Stockage ---
    "B0B7CKVCCV": ("WD_BLACK SN850X 1 To", {"type": "NVMe", "capacite_go": 1000, "format": "M.2 2280", "interface": "PCIe 4.0 x4",
                   "lecture_mo_s": 7300, "ecriture_mo_s": 6300, "couleur": None}),
    "B0D7MLHCQ7": ("WD Blue SN5000 1 To", {"type": "NVMe", "capacite_go": 1000, "format": "M.2 2280", "interface": "PCIe 4.0 x4",
                   "lecture_mo_s": 5150, "ecriture_mo_s": 4900, "couleur": None}),
    "B0DBR3DZWG": ("Kingston NV3 1 To", {"type": "NVMe", "capacite_go": 1000, "format": "M.2 2280", "interface": "PCIe 4.0 x4",
                   "lecture_mo_s": 6000, "ecriture_mo_s": 4000, "couleur": None}),
    "B09K7F5VJQ": ("Kingston KC3000 1 To", {"type": "NVMe", "capacite_go": 1024, "format": "M.2 2280", "interface": "PCIe 4.0 x4",
                   "lecture_mo_s": 7000, "ecriture_mo_s": 6000, "couleur": None}),
    "B08PC5DKZQ": ("Samsung 870 EVO 1 To", {"type": "SATA", "capacite_go": 1000, "format": "2,5 pouces", "interface": "SATA 6 Gb/s",
                   "lecture_mo_s": 560, "ecriture_mo_s": 530, "couleur": None}),
    "B01N0TQPQB": ("Kingston A400 480 Go", {"type": "SATA", "capacite_go": 480, "format": "2,5 pouces", "interface": "SATA 6 Gb/s",
                   "lecture_mo_s": 500, "ecriture_mo_s": 450, "couleur": None}),
    # --- Alimentations ---
    "B0DJV6JBPH": ("Seasonic Focus GX-750 V4 750W", {"wattage": 750, "certification": "80 PLUS Gold", "modularite": "Entièrement modulaire",
                   "format_alim": "ATX", "connecteur_12v_2x6": "Oui", "norme_atx": "ATX 3.1"}),
    "B0C5B888CM": ("Seasonic Focus GX-850 850W", {"wattage": 850, "certification": "80 PLUS Gold", "modularite": "Entièrement modulaire",
                   "format_alim": "ATX"}),
    "B0C2453ZNJ": ("Thermaltake Toughpower GF A3 850W", {"wattage": 850, "certification": "80 PLUS Gold", "modularite": "Entièrement modulaire",
                   "format_alim": "ATX", "connecteur_12v_2x6": "Oui", "norme_atx": "ATX 3.0"}),
    "B0D9C2K4VS": ("Corsair RM750x 750W", {"wattage": 750, "certification": "80 PLUS Gold", "modularite": "Entièrement modulaire",
                   "format_alim": "ATX", "connecteur_12v_2x6": "Oui", "norme_atx": "ATX 3.1", "couleur": None}),
    # --- Boîtiers ---
    "B09V878FXQ": ("Fractal Design North Noir", {"formats_supportes": ["ATX", "Micro-ATX", "Mini-ITX"], "gpu_max_length_mm": 355,
                   "cpu_cooler_max_height_mm": 170, "radiateur_max_mm": 360, "ventilateurs_inclus": 2, "couleur": None}),
    "B09Y9FSZFX": ("Fractal Design North Blanc", {"formats_supportes": ["ATX", "Micro-ATX", "Mini-ITX"], "gpu_max_length_mm": 355,
                   "cpu_cooler_max_height_mm": 170, "radiateur_max_mm": 360, "ventilateurs_inclus": 2, "couleur": None}),
    "B08SR7LPCD": ("Fractal Design Pop Air Noir", {"formats_supportes": ["ATX", "Micro-ATX", "Mini-ITX"], "gpu_max_length_mm": 405,
                   "cpu_cooler_max_height_mm": 170, "radiateur_max_mm": 360, "ventilateurs_inclus": 3, "couleur": None}),
    "B0BRP58KHT": ("Lian Li Lancool 216", {"formats_supportes": ["E-ATX", "ATX", "Micro-ATX", "Mini-ITX"], "gpu_max_length_mm": 392,
                   "cpu_cooler_max_height_mm": 180, "radiateur_max_mm": 360, "ventilateurs_inclus": 3, "couleur": None}),
    "B0F64S2P7G": ("Lian Li Lancool 207 Digital", {"formats_supportes": ["ATX", "Micro-ATX", "Mini-ITX"], "gpu_max_length_mm": 375,
                   "cpu_cooler_max_height_mm": 170, "radiateur_max_mm": 360, "ventilateurs_inclus": 4}),
    "B0CT5RG9LJ": ("Phanteks XT Pro Ultra", {"formats_supportes": ["E-ATX", "ATX", "Micro-ATX", "Mini-ITX"], "gpu_max_length_mm": 415,
                   "cpu_cooler_max_height_mm": 184, "radiateur_max_mm": 360, "ventilateurs_inclus": 4, "couleur": None}),
    "B0C98RRPXL": ("Montech AIR 903 MAX", {"formats_supportes": ["E-ATX", "ATX", "Micro-ATX", "Mini-ITX"], "gpu_max_length_mm": 400,
                   "cpu_cooler_max_height_mm": 180, "radiateur_max_mm": 360, "ventilateurs_inclus": 4, "couleur": None}),
    "B087D7DBW6": ("be quiet! Pure Base 500DX", {"formats_supportes": ["ATX", "Micro-ATX", "Mini-ITX"], "gpu_max_length_mm": 369,
                   "cpu_cooler_max_height_mm": 190, "radiateur_max_mm": 360, "ventilateurs_inclus": 3, "couleur": None}),
    # --- Refroidissement ---
    "B08WPDD6GD": ("Noctua NH-U12S redux", {"type_refroidissement": "Ventirad", "hauteur_mm": 158, "ventilateurs": "1 x 120 mm",
                   "sockets_supportes": AMD_SOCKETS + INTEL_SOCKETS + ["LGA1151"]}),
    "B0DWZF6VVQ": ("be quiet! Pure Rock 3 LX", {"type_refroidissement": "Ventirad", "hauteur_mm": 154, "ventilateurs": "1 x 120 mm",
                   "sockets_supportes": AMD_SOCKETS + INTEL_SOCKETS + ["LGA1151"]}),
    "B0D93ZQH36": ("Thermalright Phantom Spirit 120 SE Noir", {"type_refroidissement": "Ventirad", "hauteur_mm": 154, "ventilateurs": "2 x 120 mm",
                   "sockets_supportes": AMD_SOCKETS + INTEL_SOCKETS + ["LGA1151"], "couleur": None}),
}

changes = 0
for asin, (nom, valeurs) in FICHES.items():
    r = db.execute("select id, nom, specs_json from components where asin = ? collate nocase", (asin,)).fetchone()
    if not r:
        print(f"!! {asin} introuvable")
        continue
    cid, ancien, specs_json = r
    specs = json.loads(specs_json or "{}")
    merged = {k: v for k, v in {**specs, **valeurs}.items() if v is not None}
    if merged == specs and nom == ancien:
        continue
    changes += 1
    diff = {k: v for k, v in valeurs.items() if specs.get(k) != v and not (v is None and k not in specs)}
    print(f"{cid} | {ancien[:45]}{'  ->  ' + nom if nom != ancien else ''} | {diff}")
    if APPLY:
        db.execute("update components set nom = ?, specs_json = ? where id = ?", (nom, json.dumps(merged, ensure_ascii=False), cid))
if APPLY:
    db.commit()
print(f"\n{changes} fiche(s) {'MODIFIÉE(S)' if APPLY else 'à modifier (simulation, rien écrit)'}")
