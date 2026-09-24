"""
Migration ponctuelle : ajoute la colonne en_stock (0/1, défaut 1) à la table
components.

Pourquoi : jusqu'ici, un composant dont la fiche Amazon n'a plus de prix
(rupture de stock, fin de série...) était soit affiché avec "aucun prix"
soit supprimé manuellement — aucun état intermédiaire "épuisé, à surveiller"
qui permette de le remettre en ligne automatiquement dès qu'il redevient
disponible. en_stock sert cet état : mis à jour par le job de fond qui
revérifie les ASIN (voir check_stock_status() dans main.py), jamais modifié
manuellement autrement que via ce backfill.

À lancer UNE SEULE FOIS, sur le serveur où tourne l'app (le fichier SQLite
local, pas Turso — voir get_client() dans main.py) :
    python migrate_add_en_stock.py

Sans danger si relancé plusieurs fois : vérifie d'abord si la colonne existe.
"""

import os
import sys

from dotenv import load_dotenv
import libsql_client

load_dotenv()


def get_client():
    url = os.getenv("TURSO_DATABASE_URL")
    if not url:
        print("Erreur : TURSO_DATABASE_URL manquant dans .env")
        sys.exit(1)
    if url.startswith("file:"):
        return libsql_client.create_client_sync(url=url)
    token = os.getenv("TURSO_AUTH_TOKEN")
    return libsql_client.create_client_sync(url=url.replace("libsql://", "https://"), auth_token=token)


def main():
    client = get_client()
    try:
        result = client.execute("PRAGMA table_info(components)")
        columns = [row[1] for row in result.rows]

        if "en_stock" not in columns:
            client.execute("ALTER TABLE components ADD COLUMN en_stock INTEGER NOT NULL DEFAULT 1")
            print("Colonne 'en_stock' ajoutée (défaut 1 = en stock pour l'existant).")
        else:
            print("La colonne 'en_stock' existe déjà.")

    finally:
        client.close()


if __name__ == "__main__":
    main()
