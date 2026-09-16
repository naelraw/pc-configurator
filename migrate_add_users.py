"""
Migration ponctuelle : crée la table users pour les comptes (inscription,
connexion, builds liés à un compte plutôt qu'ouverts à tout le monde).

À lancer UNE SEULE FOIS :
    python migrate_add_users.py

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
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        print("Table 'users' prête.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
