"""
Migration ponctuelle : ajoute la colonne amazon_details_json à la table
components, pour conserver le tableau complet "Détails du produit" Amazon
(mémoire, socket, dimensions...) et pouvoir l'afficher dans la modale de
détail publique — jusqu'ici cette donnée n'était utilisée qu'à l'écran dans
l'admin, jamais enregistrée.

À lancer UNE SEULE FOIS :
    python migrate_add_amazon_details.py

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
        columns = [row[1] for row in result.rows]

        if "amazon_details_json" in columns:
            print("La colonne 'amazon_details_json' existe déjà. Rien à faire.")
            return

        client.execute("ALTER TABLE components ADD COLUMN amazon_details_json TEXT")
        print("Colonne 'amazon_details_json' ajoutée avec succès à la table components.")

    finally:
        client.close()


if __name__ == "__main__":
    main()
