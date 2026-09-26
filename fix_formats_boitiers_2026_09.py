"""Boîtiers : ajoute à formats_supportes les formats de carte mère plus petits
que le plus grand déjà listé (un boîtier ATX accepte aussi Micro-ATX et
Mini-ITX). Lecture seule sans --appliquer."""
import json, sqlite3, sys

ORDRE = ["Mini-ITX", "Micro-ATX", "ATX", "E-ATX"]
# Boîtiers Micro-ATX dont la fiche citait « ATX » à tort (vérifié : fiches fabricant).
MICRO_ATX = {2575: "msi mag pano m100l", 2585: "msi mag forge m100r", 2597: "nzxt h3 flow"}
db = sqlite3.connect("data/pcradar.db", timeout=10)
for i, garde in MICRO_ATX.items():
    nom, sj = db.execute("SELECT nom, specs_json FROM components WHERE id = ?", (i,)).fetchone()
    assert nom.lower().startswith(garde), nom
    if "--appliquer" in sys.argv:
        specs = json.loads(sj)
        specs["formats_supportes"] = ["Micro-ATX", "Mini-ITX"]
        db.execute("UPDATE components SET specs_json = ? WHERE id = ?", (json.dumps(specs, ensure_ascii=False), i))
n = 0
for i, nom, sj in db.execute("SELECT id, nom, specs_json FROM components WHERE categorie = 'Boîtier'").fetchall():
    specs = json.loads(sj or "{}")
    formats = specs.get("formats_supportes")
    if not isinstance(formats, list) or not any(f in ORDRE for f in formats):
        continue
    plus_grand = max(ORDRE.index(f) for f in formats if f in ORDRE)
    complets = [f for f in reversed(ORDRE[:plus_grand + 1])]
    complets += [f for f in formats if f not in complets]
    if set(complets) == set(formats):
        continue
    n += 1
    print(f"{i:>5} {nom[:50]:50} {formats} -> {complets}")
    if "--appliquer" in sys.argv:
        specs["formats_supportes"] = complets
        db.execute("UPDATE components SET specs_json = ? WHERE id = ?", (json.dumps(specs, ensure_ascii=False), i))
db.commit()
print(n, "boîtier(s)", "MODIFIÉ(S)" if "--appliquer" in sys.argv else "à modifier")
