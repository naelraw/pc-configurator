"""
Migration ponctuelle : ajoute la colonne est_officielle à la table builds,
pour marquer certaines configurations comme "recommandées" — mises en avant
publiquement (visibles sans compte) sur la page /estimer-fps, sélectionnées
à la main par l'admin parmi les configs déjà sauvegardées normalement.

À lancer UNE SEULE FOIS :
    python migrate_add_official_builds.py

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
        result = client.execute("PRAGMA table_info(builds)")
        columns = [row[1] for row in result.rows]

        if "est_officielle" in columns:
            print("La colonne 'est_officielle' existe déjà. Rien à faire.")
            return

        client.execute("ALTER TABLE builds ADD COLUMN est_officielle INTEGER DEFAULT 0")
        print("Colonne 'est_officielle' ajoutée avec succès à la table builds.")

    finally:
        client.close()


if __name__ == "__main__":
    main()
