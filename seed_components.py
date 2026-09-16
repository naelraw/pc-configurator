"""
Script d'ajout automatique de composants dans Turso.

Utilisation :
    python seed_components.py components_seed.json

Le fichier JSON contient une LISTE de composants, ex:

[
  {
    "categorie": "CPU",
    "nom": "AMD Ryzen 5 7600",
    "prix_indicatif": 210.0,
    "specs": { "socket": "AM5", "tdp": 65 }
  },
  {
    "categorie": "Carte mère",
    "nom": "MSI B650M",
    "prix_indicatif": 140.0,
    "specs": { "socket": "AM5", "ram_type": "DDR5", "format": "mATX", "m2_slots": 2, "sata_ports": 4 }
  }
]

Comportement :
  1. TOUS les composants du fichier sont validés d'abord (schema.py).
     S'il y a la moindre erreur, RIEN n'est écrit en base — le script
     affiche la liste complète des erreurs et s'arrête.
  2. Si tout est valide : upsert par (categorie, nom) — un composant déjà
     présent est mis à jour (specs/prix), un nouveau est inséré. Le script
     est donc rejouable sans jamais créer de doublons.
"""

import json
import os
import sys

from dotenv import load_dotenv
import libsql_client

from schema import validate_component

load_dotenv()


def get_client():
    url = os.getenv("TURSO_DATABASE_URL")
    token = os.getenv("TURSO_AUTH_TOKEN")
    if not url or not token:
        print("Erreur : TURSO_DATABASE_URL / TURSO_AUTH_TOKEN manquants dans .env")
        sys.exit(1)
    url = url.replace("libsql://", "https://")
    return libsql_client.create_client_sync(url=url, auth_token=token)


def load_seed_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Erreur : fichier introuvable : {path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Erreur : fichier JSON invalide : {e}")
        sys.exit(1)

    if not isinstance(data, list):
        print("Erreur : le fichier doit contenir une liste de composants ([...]).")
        sys.exit(1)

    return data


def validate_all(components):
    all_errors = []
    for i, component in enumerate(components, start=1):
        all_errors.extend(validate_component(component, i))
    return all_errors


def upsert_component(client, component):
    """
    Retourne "created" ou "updated".
    """
    categorie = component["categorie"]
    nom = component["nom"]
    prix = component["prix_indicatif"]
    specs_json = json.dumps(component["specs"], ensure_ascii=False)
    prix_marche_json = json.dumps(component.get("prix_marche", []), ensure_ascii=False)

    existing = client.execute(
        "SELECT id FROM components WHERE categorie = ? AND nom = ?",
        [categorie, nom],
    )

    if existing.rows:
        component_id = existing.rows[0][0]
        client.execute(
            "UPDATE components SET specs_json = ?, prix_indicatif = ?, prix_marche_json = ? WHERE id = ?",
            [specs_json, prix, prix_marche_json, component_id],
        )
        return "updated"

    client.execute(
        "INSERT INTO components (categorie, nom, specs_json, prix_indicatif, prix_marche_json) VALUES (?, ?, ?, ?, ?)",
        [categorie, nom, specs_json, prix, prix_marche_json],
    )
    return "created"


def main():
    if len(sys.argv) != 2:
        print("Utilisation : python seed_components.py <fichier.json>")
        sys.exit(1)

    path = sys.argv[1]
    components = load_seed_file(path)

    print(f"{len(components)} composant(s) trouvé(s) dans {path}. Validation en cours...")
    errors = validate_all(components)

    if errors:
        print(f"\n{len(errors)} erreur(s) trouvée(s) — AUCUNE écriture en base n'a été faite :\n")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)

    print("Tous les composants sont valides. Écriture en base...")

    client = get_client()
    created, updated = 0, 0
    try:
        for component in components:
            result = upsert_component(client, component)
            if result == "created":
                created += 1
            else:
                updated += 1
    finally:
        client.close()

    print(f"\nTerminé : {created} composant(s) ajouté(s), {updated} mis à jour.")


if __name__ == "__main__":
    main()
