"""Complète les 3 fiches incomplètes du 2026-09-30 (ajoutées via l'extension).
Sources : MSI (fiche G506T-8V2CP), AMD / ASUS (RX 9070), fiche du Ryzen 5 5500
déjà au catalogue. Simulation sans --appliquer."""
import json, sqlite3, sys

FICHES = {
    2920: ("AMD Ryzen 5 5500", "AMD Ryzen 5 5500 (MPK)", {
        "socket": "AM4", "tdp": 65, "coeurs": 6, "threads": 12, "frequence_base_ghz": 3.6,
        "frequence_boost_ghz": 4.2, "cache_l3_mo": 16, "memoire": "DDR4", "igpu": "Aucune"}),
    2922: ("ASUS Prime Radeon RX 9070 OC", None, {
        "tdp": 220, "puce": "RX 9070", "vram_go": 16, "type_memoire": "GDDR6",
        "bus_memoire_bits": 256, "connecteur_alim": "2 x 8 broches"}),
    2916: ("MSI GeForce RTX 5060 Ti 8G Ventus 2X OC Plus", None, {
        "tdp": 180, "longueur_mm": 227, "puce": "RTX 5060 Ti", "vram_go": 8, "type_memoire": "GDDR7",
        "bus_memoire_bits": 128, "connecteur_alim": "1 x 8 broches"}),
}
db = sqlite3.connect("data/pcradar.db", timeout=10)
for i, (garde, nouveau_nom, ajout) in FICHES.items():
    nom, sj = db.execute("SELECT nom, specs_json FROM components WHERE id = ?", (i,)).fetchone()
    if not nom.lower().startswith(garde.lower()):
        sys.exit(f"GARDE {i} : {nom}")
    specs = json.loads(sj or "{}")
    specs.update(ajout)
    print(i, nom, "→", nouveau_nom or nom, "|", json.dumps(specs, ensure_ascii=False))
    if "--appliquer" in sys.argv:
        db.execute("UPDATE components SET nom = ?, specs_json = ? WHERE id = ?",
                   (nouveau_nom or nom, json.dumps(specs, ensure_ascii=False), i))
db.commit()
print("MODIFIÉ" if "--appliquer" in sys.argv else "simulation")
