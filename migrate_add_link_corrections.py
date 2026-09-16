"""
Migration ponctuelle : crée la table link_corrections, qui stocke les
propositions de correction de lien de prix envoyées par les utilisateurs
connectés (un lien Amazon détecté mort par la vérification automatique, ou
signalé manuellement). Chaque proposition reste "pending" tant qu'un admin
ne l'a pas validée ou rejetée depuis /admin — jamais appliquée directement.

À lancer UNE SEULE FOIS :
    python migrate_add_link_corrections.py

Sans danger si relancé (CREATE TABLE IF NOT EXISTS).
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
        client.execute("""
            CREATE TABLE IF NOT EXISTS link_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                component_id INTEGER NOT NULL,
                vendeur TEXT NOT NULL,
                ancien_lien TEXT,
                nouveau_lien TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                user_email TEXT NOT NULL,
                statut TEXT NOT NULL DEFAULT 'pending',
                date TEXT NOT NULL
            )
        """)
        print("Table 'link_corrections' prête.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
