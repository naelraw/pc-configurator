"""Erreurs du catalogue repérées par le test de fiabilité d'auto_catalogue
(2026-09-30). Simulation sans --appliquer."""
import json, sqlite3, sys

FIX = {
    2788: ("AMD Ryzen 5 5600", {"tdp": 65}),                     # AMD : 65 W (100 W saisi par erreur)
    1987: ("AMD Ryzen 7 7700", {"tdp": 65}),                     # AMD : 65 W (95 W = 7700X)
    2919: ("AMD Ryzen 5 8400F", {"socket": "AM5", "coeurs": 6, "threads": 12, "frequence_base_ghz": 4.2,
                                 "frequence_boost_ghz": 4.7, "cache_l3_mo": 16, "memoire": "DDR5", "igpu": "Aucune"}),
    2531: ("ASRock Taichi RX 9070 XT", {"tdp": 304}),            # 850 W = alim recommandée ; 304 W = valeur AMD
}
db = sqlite3.connect("data/pcradar.db", timeout=10)
for i, (garde, ajout) in FIX.items():
    nom, sj = db.execute("SELECT nom, specs_json FROM components WHERE id = ?", (i,)).fetchone()
    if not nom.lower().startswith(garde.lower()):
        sys.exit(f"GARDE {i} : {nom}")
    specs = json.loads(sj or "{}")
    avant = {k: specs.get(k) for k in ajout}
    specs.update(ajout)
    print(i, nom, "|", avant, "→", ajout)
    if "--appliquer" in sys.argv:
        db.execute("UPDATE components SET specs_json = ? WHERE id = ?", (json.dumps(specs, ensure_ascii=False), i))
db.commit()
print("MODIFIÉ" if "--appliquer" in sys.argv else "simulation")
