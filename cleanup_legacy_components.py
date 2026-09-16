"""
Nettoie les composants "legacy" en base — ceux dont la catégorie n'est PAS
une des 8 catégories canoniques utilisées par compatibility.py et le
configurateur. Typiquement des restes de tests précédents avec des noms de
catégorie en minuscules/underscore ("carte_mere", "gpu", "ram"...) au lieu
des vraies catégories ("Carte mère", "GPU", "RAM"...).

Utilisation :
    python cleanup_legacy_components.py           # affiche ce qui serait supprimé (dry-run)
    python cleanup_legacy_components.py --confirm  # supprime réellement
"""

import os
import sys

from dotenv import load_dotenv
import libsql_client

load_dotenv()

VALID_CATEGORIES = {
    "CPU",
    "Carte mère",
    "RAM",
    "Boîtier",
    "Alimentation",
    "GPU",
    "Stockage",
    "Refroidissement",
}


def get_client():
    url = os.getenv("TURSO_DATABASE_URL")
    token = os.getenv("TURSO_AUTH_TOKEN")
    if not url or not token:
        print("Erreur : TURSO_DATABASE_URL / TURSO_AUTH_TOKEN manquants dans .env")
        sys.exit(1)
    url = url.replace("libsql://", "https://")
    return libsql_client.create_client_sync(url=url, auth_token=token)


def main():
    confirm = "--confirm" in sys.argv

    client = get_client()
    try:
        result = client.execute(
            "SELECT id, categorie, nom, prix_indicatif FROM components ORDER BY categorie, nom"
        )
        rows = result.rows

        legacy_rows = [row for row in rows if row[1] not in VALID_CATEGORIES]

        if not legacy_rows:
            print("Rien à nettoyer : toutes les catégories sont valides.")
            return

        print(f"{len(legacy_rows)} composant(s) avec une catégorie non reconnue :\n")
        for row in legacy_rows:
            print(f"  - id {row[0]} | catégorie: {row[1]!r} | nom: {row[2]} | prix: {row[3]}€")

        if not confirm:
            print("\nAucune suppression effectuée (mode aperçu).")
            print("Relance avec --confirm pour supprimer ces composants :")
            print("    python cleanup_legacy_components.py --confirm")
            return

        for row in legacy_rows:
            client.execute("DELETE FROM components WHERE id = ?", [row[0]])

        print(f"\n{len(legacy_rows)} composant(s) supprimé(s).")

    finally:
        client.close()


if __name__ == "__main__":
    main()
