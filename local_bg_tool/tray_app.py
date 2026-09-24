"""
Version "icône dans la zone de notification" de la surveillance
automatique — tourne en fond au démarrage de Windows, sans fenêtre ni
console visible (lancé via pythonw.exe, voir install_startup.py). Clic
droit sur l'icône dans les icônes cachées (barre des tâches) pour voir le
statut ou quitter.

Même logique de détourage que app.py / watch_headless.py.
"""

import threading
import time

import app
from PIL import Image, ImageDraw

try:
    import pystray
except ImportError:
    pystray = None


STATE = {"status": "Démarrage…", "processed": 0, "running": True}


def make_icon_image(color):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), fill=color)
    return img


def watcher_loop():
    failed_ids = set()
    while STATE["running"]:
        try:
            components = app.fetch_pending_components()

            todo = [c for c in components if c["id"] not in failed_ids]
            if todo:
                STATE["status"] = f"Détourage en cours ({len(todo)})…"
            for component in todo:
                component_id, nom, image_url = component["id"], component["nom"], component["image_url"]
                try:
                    raw = app.load_image_bytes(image_url)
                    output_bytes = app.remove_background_birefnet(raw)
                    data_url = app.image_bytes_to_data_url(output_bytes)
                    app.save_processed_image(component_id, data_url)
                except Exception:
                    failed_ids.add(component_id)
                    continue
                STATE["processed"] += 1

            STATE["status"] = f"En veille — {STATE['processed']} image(s) traitée(s) au total"
        except Exception as error:
            STATE["status"] = f"Erreur : {error}"

        for _ in range(20):
            if not STATE["running"]:
                return
            time.sleep(1)


def quit_app(icon, _item):
    STATE["running"] = False
    icon.stop()


def build_menu():
    return pystray.Menu(
        pystray.MenuItem(lambda item: STATE["status"], None, enabled=False),
        pystray.MenuItem("Quitter", quit_app),
    )


def main():
    if pystray is None:
        # Environnement sans support de zone de notification (rare) :
        # on retombe sur la boucle simple sans icône.
        watcher_loop()
        return

    threading.Thread(target=watcher_loop, daemon=True).start()
    icon = pystray.Icon(
        "pc-radar-detourage",
        icon=make_icon_image((45, 212, 191, 255)),
        title="PC Radar — Détourage auto",
        menu=build_menu(),
    )
    icon.run()


if __name__ == "__main__":
    main()
