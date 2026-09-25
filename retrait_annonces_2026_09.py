"""Retrait d'annonces aberrantes du catalogue (demandé par l'utilisateur le 2026-09-25).
Usage : python retrait_annonces_2026_09.py <base> [--appliquer]   (sans --appliquer : simulation)

Avant suppression, chaque fiche (et son historique de prix) est exportée dans
data/annonces_retirees_2026_09.json pour pouvoir la restaurer."""
import json, sqlite3, sys
from pathlib import Path

db = sqlite3.connect(sys.argv[1], timeout=10)
db.row_factory = sqlite3.Row
APPLY = "--appliquer" in sys.argv

RETRAITS = {
    2560: ("MSI Radeon RX 6750 XT Mech 2X", "prix aberrant : 1 834 € chez un vendeur tiers (les RX 6750 XT sont vers 690 €)"),
    2796: ("AGI STORAGE TURBOJET", "lot RAM + SSD rangé dans les SSD : ni un SSD, ni comparable"),
    2865: ("Acer Predator GM9 M.2", "doublon de l'annonce 2858 (même ASIN)"),
    2860: ("Lexar EQ790 SSD 1To", "doublon de l'annonce 2857 (même ASIN)"),
}

export = []
for cid, (debut, raison) in RETRAITS.items():
    row = db.execute("select * from components where id=?", (cid,)).fetchone()
    if not row or not row["nom"].startswith(debut):
        print(f"!! {cid} : attendu « {debut} », trouvé {row['nom'] if row else 'rien'} -> ignoré")
        continue
    hist = [dict(h) for h in db.execute("select * from price_history where component_id=?", (cid,))]
    export.append({"raison": raison, "composant": dict(row), "price_history": hist})
    print(f"{cid} | {row['nom'][:50]} | {raison}")

if APPLY and export:
    out = Path(sys.argv[1]).with_name("annonces_retirees_2026_09.json")
    out.write_text(json.dumps(export, ensure_ascii=False, indent=1), encoding="utf-8")
    for e in export:
        cid = e["composant"]["id"]
        db.execute("delete from price_history where component_id=?", (cid,))
        db.execute("delete from components where id=?", (cid,))
    db.commit()
    print(f"export : {out}")
print(f"\n{len(export)} annonce(s) {'RETIRÉE(S)' if APPLY else 'à retirer (simulation, rien écrit)'}")
