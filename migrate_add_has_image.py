"""
Migration ponctuelle : ajoute la colonne has_image (0/1) à la table
components.

Pourquoi : la colonne image_url stocke une image détourée encodée en base64,
souvent plusieurs centaines de Ko voire plus par composant. Il s'est avéré
que TOUTE requête qui référence cette colonne dans sa clause SELECT ou
WHERE — même juste pour un test "IS NOT NULL" — force Turso à transférer la
valeur complète, rendant une simple liste de composants extrêmement lente
(15-20+ secondes pour une poignée de lignes). has_image permet de savoir
si une image existe sans jamais toucher à la colonne image_url elle-même
dans la requête de listing publique (voir get_all_components_light()).

À lancer UNE SEULE FOIS :
    python migrate_add_has_image.py

Sans danger si relancé plusieurs fois : le script vérifie d'abord si la
colonne existe déjà, et le backfill est idempotent (recalcule la même
valeur à chaque fois).
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

        if "has_image" not in columns:
            client.execute("ALTER TABLE components ADD COLUMN has_image INTEGER DEFAULT 0")
            print("Colonne 'has_image' ajoutée.")
        else:
            print("La colonne 'has_image' existe déjà.")

        print("Backfill en cours (peut prendre du temps, une seule fois)...")
        client.execute("UPDATE components SET has_image = (image_url IS NOT NULL)")
        print("Backfill terminé.")

    finally:
        client.close()


if __name__ == "__main__":
    main()
