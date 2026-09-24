"""
Version sans interface graphique de la surveillance automatique — même
logique que le bouton "Démarrer la surveillance automatique" de app.py,
pour pouvoir la lancer directement en arrière-plan sans avoir à cliquer
dans la fenêtre. Journalise dans la console.
"""

import time

import app


def main():
    print("Surveillance automatique démarrée (Ctrl+C pour arrêter).")
    failed_ids = set()
    while True:
        try:
            client = app.get_db_client()
            try:
                result = client.execute(
                    "SELECT id, nom, image_url FROM components WHERE image_url LIKE 'http%'"
                )
                rows = result.rows
            finally:
                client.close()

            todo = [row for row in rows if row[0] not in failed_ids]
            for component_id, nom, image_url in todo:
                print(f"[{time.strftime('%H:%M:%S')}] Détourage : {nom} (id {component_id})…")
                try:
                    raw = app.load_image_bytes(image_url)
                    output_bytes = app.remove_background_birefnet(raw)
                    data_url = app.image_bytes_to_data_url(output_bytes)
                except Exception as error:
                    failed_ids.add(component_id)
                    print(f"  échec ({error}) — ignoré désormais.")
                    continue

                client = app.get_db_client()
                try:
                    client.execute(
                        "UPDATE components SET image_url = ?, has_image = 1 WHERE id = ?",
                        [data_url, component_id],
                    )
                finally:
                    client.close()
                print(f"  enregistré sur le site.")
        except Exception as error:
            print(f"Erreur de surveillance : {error}")

        time.sleep(20)


if __name__ == "__main__":
    main()
