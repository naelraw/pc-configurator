"""
Migration ponctuelle : ajoute la colonne asin à la table components, pour
relier un composant à un produit Amazon (récupération auto via Canopy API).

À lancer UNE SEULE FOIS :
    python migrate_add_asin.py

Sans danger si relancé plusieurs fois : le script vérifie d'abord si la
colonne existe déjà.
"""

import os
import sys

from dotenv import load_dotenv
import libsql_client

load_dotenv()


def get_client():
    url = os.getenv("TURSO_DATABASE_URL")
    token = os.getenv("TURSO_AUTH_TOKEN")
    if not url or not token:
        print("Erreur : TURSO_DATABASE_URL / TURSO_AUTH_TOKEN manquants dans .env")
        sys.exit(1)
    url = url.replace("libsql://", "https://")
    return libsql_client.create_client_sync(url=url, auth_token=token)


def main():
    client = get_client()
    try:
        result = client.execute("PRAGMA table_info(components)")
        columns = [row[1] for row in result.rows]  # row[1] = nom de la colonne

        if "asin" in columns:
            print("La colonne 'asin' existe déjà. Rien à faire.")
            return

        client.execute("ALTER TABLE components ADD COLUMN asin TEXT")
        print("Colonne 'asin' ajoutée avec succès à la table components.")

    finally:
        client.close()


if __name__ == "__main__":
    main()
