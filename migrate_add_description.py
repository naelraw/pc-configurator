"""
Migration ponctuelle : ajoute la colonne description à la table components,
pour conserver le texte descriptif du produit renvoyé par Bright Data et
l'afficher dans la modale de détail publique.

À lancer UNE SEULE FOIS :
    python migrate_add_description.py

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

        if "description" in columns:
            print("La colonne 'description' existe déjà. Rien à faire.")
            return

        client.execute("ALTER TABLE components ADD COLUMN description TEXT")
        print("Colonne 'description' ajoutée avec succès à la table components.")

    finally:
        client.close()


if __name__ == "__main__":
    main()
