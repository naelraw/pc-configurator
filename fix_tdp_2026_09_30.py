"""Consommations fausses repérées par l'audit complet du catalogue (2026-09-30).
RTX 3050 6 Go : 70 W selon NVIDIA (130 W, c'est la version 8 Go).
RX 7600 : 165 W selon AMD. Simulation sans --appliquer."""
import json, sqlite3, sys

RTX_3050_6GO = [2300, 2301, 2302, 2303, 2304, 2305, 2308, 2309, 2313, 2318]
FIX = {i: ("3050", {"tdp": 70}, 6) for i in RTX_3050_6GO}
FIX[2541] = ("RX 7600", {"tdp": 165}, 8)

db = sqlite3.connect("data/pcradar.db", timeout=10)
for i, (garde, ajout, vram) in FIX.items():
    nom, sj = db.execute("SELECT nom, specs_json FROM components WHERE id = ?", (i,)).fetchone()
    specs = json.loads(sj or "{}")
    if garde not in nom or specs.get("vram_go") != vram:
        sys.exit(f"GARDE {i} : {nom} ({specs.get('vram_go')} Go)")
    avant = {k: specs.get(k) for k in ajout}
    specs.update(ajout)
    print(i, nom, "|", avant, "→", ajout)
    if "--appliquer" in sys.argv:
        db.execute("UPDATE components SET specs_json = ? WHERE id = ?", (json.dumps(specs, ensure_ascii=False), i))
db.commit()
print("MODIFIÉ" if "--appliquer" in sys.argv else "simulation")
