"""
Migration ponctuelle : les 12 composants ci-dessous sont en réalité de la RAM
(DDR4/DDR5) mais avaient été catalogués par erreur dans "Accessoire" (le
matcher automatique guess_categorie_from_amazon() ne reconnaissait pas leurs
titres). On les repasse dans la vraie catégorie "RAM" et on complète
specs.type (DDR4/DDR5, déduit du nom) pour que compatibility.py puisse
vérifier leur compatibilité avec les cartes mères comme pour toute autre RAM.

À lancer UNE SEULE FOIS, sur le serveur où tourne l'app :
    python fix_accessoire_ram_category.py

Sans danger si relancé plusieurs fois : les composants déjà passés en RAM
avec un specs.type rempli ne sont plus modifiés.
"""

import json
import os
import re
import sys

from dotenv import load_dotenv
import libsql_client

load_dotenv()

IDS = [2852, 2814, 2818, 2853, 2817, 2800, 2809, 2854, 2843, 2841, 2815, 2845]


def get_client():
    url = os.getenv("TURSO_DATABASE_URL")
    if not url:
        print("Erreur : TURSO_DATABASE_URL manquant dans .env")
        sys.exit(1)
    if url.startswith("file:"):
        return libsql_client.create_client_sync(url=url)
    token = os.getenv("TURSO_AUTH_TOKEN")
    return libsql_client.create_client_sync(url=url.replace("libsql://", "https://"), auth_token=token)


def guess_ddr_type(nom):
    match = re.search(r"ddr\s*([45])", nom, re.IGNORECASE)
    if match:
        return f"DDR{match.group(1)}"
    return None


def main():
    client = get_client()
    try:
        for component_id in IDS:
            result = client.execute(
                "SELECT nom, categorie, specs_json FROM components WHERE id = ?", [component_id]
            )
            if not result.rows:
                print(f"id={component_id} introuvable, ignoré.")
                continue

            nom, categorie, specs_json = result.rows[0]
            try:
                specs = json.loads(specs_json) if specs_json else {}
            except json.JSONDecodeError:
                specs = {}

            if categorie == "RAM" and specs.get("type"):
                print(f"id={component_id} '{nom}' déjà migré, ignoré.")
                continue

            ddr_type = guess_ddr_type(nom)
            if ddr_type:
                specs["type"] = ddr_type
            else:
                print(f"id={component_id} '{nom}' : type DDR non détecté depuis le nom, specs.type laissé tel quel.")

            client.execute(
                "UPDATE components SET categorie = 'RAM', specs_json = ? WHERE id = ?",
                [json.dumps(specs, ensure_ascii=False), component_id],
            )
            print(f"id={component_id} '{nom}' -> catégorie RAM, specs.type={specs.get('type')}")

    finally:
        client.close()


if __name__ == "__main__":
    main()
