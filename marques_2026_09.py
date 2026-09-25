"""Écriture uniforme des marques dans les noms (demandé par l'utilisateur le 2026-09-25).
Usage : python marques_2026_09.py <base> [--appliquer]   (sans --appliquer : simulation)

« CORSAIR CX650 » -> « Corsair CX650 », « Gigabyte » -> « GIGABYTE », etc. (écriture
officielle, voir variantes.MARQUES_CANONIQUES), plus quelques noms dont le début
n'est pas la marque (« Processeur Intel Intel Core... », « SP Silicon Power... »)."""
import sqlite3, sys

from variantes import MARQUES_CANONIQUES

db = sqlite3.connect(sys.argv[1], timeout=10)
APPLY = "--appliquer" in sys.argv

# id -> (nom actuel attendu, nouveau nom)
RENOMMER = {
    2015: ("Processeur Intel Intel Core I5-14600KF", "Intel Core i5-14600KF 3,5 GHz"),
    2635: ("SP Silicon Power 32 Go DDR5 6000", "Silicon Power 32 Go DDR5 6000"),
}

changes = []
for cid, nom in db.execute("select id, nom from components"):
    if cid in RENOMMER:
        attendu, nouveau = RENOMMER[cid]
        if nom == attendu:
            changes.append((cid, nom, nouveau))
        else:
            print(f"!! {cid} : attendu « {attendu} », trouvé « {nom} » -> ignoré")
        continue
    premier, _, reste = nom.strip().partition(" ")
    canon = MARQUES_CANONIQUES.get(premier.lower())
    if canon and premier != canon:
        changes.append((cid, nom, f"{canon} {reste}".strip()))

for cid, avant, apres in changes:
    print(f"{cid} | {avant}  ->  {apres}")
if APPLY and changes:
    db.executemany("update components set nom=? where id=?", [(apres, cid) for cid, _, apres in changes])
    db.commit()
print(f"\n{len(changes)} nom(s) {'CORRIGÉ(S)' if APPLY else 'à corriger (simulation, rien écrit)'}")
