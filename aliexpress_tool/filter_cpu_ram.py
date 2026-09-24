"""
Filtre feed.csv (427 000 produits, tous univers confondus) pour ne garder
qu'un sous-ensemble plausible de vrais CPU et RAM desktop, à déployer sur
le serveur (fichier bien plus petit, gère pour l'instant seulement ces deux
catégories — voir la demande explicite de limiter AliExpress à CPU/RAM).

Les colonnes merchant_category/category_name sont vides sur 100% des lignes
de ce feed (vérifié) : le filtre se fait donc uniquement sur le nom du
produit, avec une liste de mots-clés d'inclusion et d'exclusion. Précision
imparfaite par nature (ex: on ne peut pas parfaitement éliminer les mini-PC
qui mentionnent un CPU/de la RAM) — le but est de réduire le fichier à un
pool plausible, pas d'être parfait ; la recherche par mot-clé du site fait
le tri fin ensuite.
"""

import csv
import sys

csv.field_size_limit(sys.maxsize)

INCLUDE_KEYWORDS = [
    "ryzen", "processeur", "processor", "cpu ", " cpu",
    "intel core", "core i3", "core i5", "core i7", "core i9",
    "ram ddr", "barrette de ram", "barrette ram", "mémoire ram",
    "memoire ram", "ram gaming", "ram desktop", "kingston fury",
    "hyperx fury", "corsair vengeance", "g.skill", "gskill",
    "crucial ram", "teamgroup",
]

EXCLUDE_KEYWORDS = [
    "ordinateur portable", "laptop", "notebook", "mini pc", "mini-pc",
    "tablette", "tablet", "téléphone", "telephone", "smartphone",
    "carte mère", "carte mere", "motherboard", "refroidisseur",
    "dissipateur", "gilet de refroidissement", "adaptateur", "adapter",
    "souris", "clavier", "casque", "nas ", "caméra", "camera",
    "voiture", "auto radio", "montre", "watch", "console de jeu",
]


def is_relevant(product_name):
    name = product_name.lower()
    if not any(keyword in name for keyword in INCLUDE_KEYWORDS):
        return False
    if any(keyword in name for keyword in EXCLUDE_KEYWORDS):
        return False
    return True


def main():
    kept = []
    with open("feed.csv", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if is_relevant(row.get("product_name", "")):
                kept.append(row)

    with open("feed_cpu_ram.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept)

    print(f"{len(kept)} lignes retenues (sur 427089) -> feed_cpu_ram.csv")


if __name__ == "__main__":
    main()
