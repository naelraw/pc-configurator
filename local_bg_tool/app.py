"""
Outil de bureau LOCAL (tourne sur ton PC, jamais sur le VM) pour détourer les
images de composants avec BiRefNet (le modèle IA de segmentation qui donnait
la meilleure qualité en test cette session, mais qui plantait/était trop lent
sur le petit VM Oracle ARM — sur ce PC, avec plus de RAM et éventuellement un
GPU, il tourne normalement).

Utilisation :
    1. pip install -r requirements.txt   (dans ce dossier)
    2. python app.py
    3. Soit à la main : charge la liste, sélectionne, "Détourer la
       sélection" puis "Enregistrer sur le site".
       Soit en automatique : "Démarrer la surveillance" — l'outil vérifie
       le site toutes les 20s, et détoure + enregistre tout seul chaque
       nouveau composant ajouté depuis l'admin web (identifié par une image
       encore sous forme d'URL Amazon brute, pas encore une data URL
       détourée). Laisse la fenêtre ouverte (peut être réduite) tant que tu
       veux que ça tourne.

Le premier détourage télécharge le modèle BiRefNet (~1 Go) — normal, une
seule fois, rembg le met en cache dans ~/.u2net/.

Passe par l'API du site (https://pcradar.tech/api/admin/...), PAS par un
accès direct à la base de données : depuis que la base est un fichier
SQLite local sur le VM (plus Turso), elle n'est plus accessible depuis
l'extérieur — l'API est le seul point d'entrée, exactement comme
l'utilise déjà l'admin web lui-même.

Pourquoi la surveillance se fait par sondage (le PC interroge le site toutes
les 20s) plutôt que par un signal envoyé depuis le site : ça évite d'exposer
ce PC sur internet (pas de port à ouvrir, pas de risque côté sécurité) — le
VM n'a jamais besoin de savoir que ce PC existe.
"""

import base64
import io
import os
import threading
import time
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

import requests
from dotenv import load_dotenv
from PIL import Image, ImageTk

# Cherche le .env du projet (ce script vit dans pc-configurator/local_bg_tool/).
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

SITE_BASE_URL = os.getenv("SITE_BASE_URL", "https://pcradar.tech")
ADMIN_SECRET = os.getenv("ADMIN_SECRET")
ADMIN_HEADERS = {"X-Admin-Secret": ADMIN_SECRET}

# Import différé : rembg + son modèle ne se chargent qu'au premier détourage,
# pour que la fenêtre s'ouvre instantanément même si le modèle doit encore
# être téléchargé.
_session = None


def get_birefnet_session():
    global _session
    if _session is None:
        from rembg import new_session
        _session = new_session("birefnet-general")
    return _session


def fetch_pending_components():
    """Composants dont l'image n'est pas encore détourée (URL Amazon brute)."""
    response = requests.get(
        f"{SITE_BASE_URL}/api/admin/pending-images", headers=ADMIN_HEADERS, timeout=30
    )
    response.raise_for_status()
    data = response.json()
    return data["components"]


def save_processed_image(component_id, data_url):
    response = requests.post(
        f"{SITE_BASE_URL}/api/admin/components/{component_id}/set-image",
        headers=ADMIN_HEADERS,
        json={"image_data_url": data_url},
        timeout=30,
    )
    response.raise_for_status()


def load_image_bytes(image_url):
    """Accepte aussi bien une URL externe (Amazon) qu'une data URL déjà en base."""
    if image_url.startswith("data:"):
        header, b64data = image_url.split(",", 1)
        return base64.b64decode(b64data)
    response = requests.get(image_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    return response.content


def remove_background_birefnet(image_bytes):
    """
    Détoure avec BiRefNet, puis corrige deux erreurs de segmentation
    constatées en usage réel sur certains visuels (boîtes AMD Ryzen à
    motifs graphiques sombres notamment), où le modèle rend transparente
    une partie du produit lui-même, pas juste le fond autour :

    1. Un vrai fond ne peut être atteint qu'en partant d'un bord de l'image
       — toute zone transparente qui n'est reliée au bord que par un pont
       fin (anti-aliasing, bord d'un motif graphique) est presque
       certainement une erreur. Une ouverture morphologique coupe ce pont
       avant de vérifier la connexion au bord.
    2. Un vrai fond Amazon est (quasi) toujours clair/blanc. Si le pixel
       d'ORIGINE à cet endroit est sombre, ce n'est pas un fond réel, même
       si BiRefNet le juge "relié au bord" (arrive quand le modèle efface
       une zone large et contiguë du produit, pas juste un pont fin — vu
       en pratique sur un panneau gris foncé entier).

    Les deux zones fautives sont rebouchées : forcées à redevenir opaques
    avec leur couleur d'origine.

    3. L'alpha final est BINAIRE (0 ou 255), sans dégradé — BiRefNet renvoie
    normalement un alpha progressif sur 1-3 px au bord du produit, mais ces
    pixels semi-transparents gardent leur couleur d'origine (souvent un
    reste de blanc/gris clair du fond ou de l'anti-aliasing) : affichés sur
    un fond de couleur (au lieu du carton blanc utilisé pour les images pas
    encore détourées), ce reste de couleur apparaît comme un léger liseré
    clair tout autour du produit. Couper net évite ce liseré, au prix d'un
    bord légèrement moins lissé (imperceptible à la taille d'affichage
    réelle).
    """
    import numpy as np
    from PIL import Image
    from rembg import remove
    from scipy import ndimage

    session = get_birefnet_session()
    output_bytes = remove(image_bytes, session=session)

    result = Image.open(io.BytesIO(output_bytes)).convert("RGBA")
    result_arr = np.array(result)
    alpha = result_arr[:, :, 3]

    original = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    original_arr = np.array(original)
    if original_arr.shape[:2] != alpha.shape:
        original = original.resize((alpha.shape[1], alpha.shape[0]))
        original_arr = np.array(original)

    is_transparent = alpha < 128

    # Une "ouverture" morphologique (érosion puis dilatation) avant de
    # vérifier la connexion au bord : sans ça, un trou erroné qui touche le
    # vrai fond par un pont fin de seulement 1-2 pixels (anti-aliasing,
    # bord d'un motif graphique) serait à tort considéré comme "relié au
    # bord" donc gardé transparent. L'érosion coupe ce pont fin ; la
    # dilatation restaure ensuite la forme du vrai fond sans le reconnecter
    # au trou (le pont, lui, a disparu pour de bon).
    structure = np.ones((3, 3), dtype=bool)
    opened = ndimage.binary_opening(is_transparent, structure=structure, iterations=2)

    labeled, _ = ndimage.label(opened)
    border_labels = (
        set(labeled[0, :].tolist())
        | set(labeled[-1, :].tolist())
        | set(labeled[:, 0].tolist())
        | set(labeled[:, -1].tolist())
    )
    border_labels.discard(0)
    connected_to_border = np.isin(labeled, list(border_labels))

    is_light_enough = original_arr.mean(axis=2) > 190
    real_background = connected_to_border & is_light_enough

    # Ombres portées : BiRefNet garde souvent ces pixels comme "produit"
    # (alpha > 200, donc jamais examinés ci-dessus), alors que ce sont des
    # dégradés gris clair neutres (R≈G≈B) du carton, pas une vraie couleur
    # de produit. On les fait disparaître en fondu (plus sombre = plus
    # opaque) au lieu d'un tout-ou-rien, pour éviter la tache grise nette
    # que laissait le seuil binaire à 190.
    gray = original_arr.mean(axis=2)
    spread = original_arr.max(axis=2).astype(np.int16) - original_arr.min(axis=2).astype(np.int16)
    is_shadow_like = (~real_background) & (alpha > 200) & (spread < 20) & (gray > 150) & (gray < 250)
    shadow_fade_alpha = np.clip((255 - gray) / (255 - 150) * 255, 0, 255)

    fixed_alpha = np.where(real_background, 0, 255).astype(np.float64)
    fixed_alpha = np.where(is_shadow_like, shadow_fade_alpha, fixed_alpha).astype(np.uint8)
    fixed_rgb = np.where(real_background[..., None], result_arr[:, :, :3], original_arr)

    fixed = np.dstack([fixed_rgb.astype(np.uint8), fixed_alpha])
    out = Image.fromarray(fixed, mode="RGBA")
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def image_bytes_to_data_url(png_bytes):
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")


class App:
    def __init__(self, root):
        self.root = root
        root.title("PC Radar — Détourage local (BiRefNet)")
        root.geometry("900x600")

        top = ttk.Frame(root, padding=8)
        top.pack(fill="x")
        ttk.Button(top, text="Charger les composants en attente", command=self.load_components).pack(side="left")
        ttk.Button(top, text="Tout sélectionner", command=self.select_all).pack(side="left", padx=6)
        ttk.Button(top, text="Détourer la sélection", command=self.process_selected).pack(side="left", padx=6)
        ttk.Button(top, text="Enregistrer sur le site", command=self.save_selected).pack(side="left", padx=6)

        auto_frame = ttk.Frame(root, padding=(8, 0, 8, 8))
        auto_frame.pack(fill="x")
        self.auto_button = ttk.Button(
            auto_frame, text="▶ Démarrer la surveillance automatique", command=self.toggle_auto_mode
        )
        self.auto_button.pack(side="left")
        ttk.Label(
            auto_frame,
            text="— traite automatiquement tout nouveau composant ajouté depuis l'admin web, sans y toucher.",
        ).pack(side="left", padx=8)

        filter_frame = ttk.Frame(root, padding=(8, 0))
        filter_frame.pack(fill="x")
        ttk.Label(filter_frame, text="Filtre (nom contient) :").pack(side="left")
        self.filter_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.filter_var, width=40).pack(side="left", padx=6)
        ttk.Button(filter_frame, text="Appliquer", command=self.apply_filter).pack(side="left")

        body = ttk.Frame(root)
        body.pack(fill="both", expand=True, padx=8, pady=8)

        list_frame = ttk.Frame(body)
        list_frame.pack(side="left", fill="both", expand=True)
        columns = ("id", "nom", "statut")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="extended")
        for col, width in zip(columns, (60, 420, 120)):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_select_preview)

        preview_frame = ttk.Frame(body, width=260)
        preview_frame.pack(side="left", fill="y", padx=(8, 0))
        preview_frame.pack_propagate(False)
        ttk.Label(preview_frame, text="Avant").pack()
        self.before_label = tk.Label(preview_frame, bg="#222")
        self.before_label.pack(fill="both", expand=True, pady=(0, 8))
        ttk.Label(preview_frame, text="Après").pack()
        self.after_label = tk.Label(preview_frame, bg="#222")
        self.after_label.pack(fill="both", expand=True)

        log_frame = ttk.Frame(root, padding=(8, 0, 8, 8))
        log_frame.pack(fill="x", side="bottom")
        ttk.Label(log_frame, text="Journal de la surveillance automatique :").pack(anchor="w")
        self.log_text = scrolledtext.ScrolledText(log_frame, height=6, state="disabled", wrap="word")
        self.log_text.pack(fill="x")

        self.status_var = tk.StringVar(value="Prêt.")
        ttk.Label(root, textvariable=self.status_var, padding=6).pack(fill="x", side="bottom")

        self.rows = {}          # component_id -> {"nom", "image_url"}
        self.results = {}       # component_id -> processed PNG bytes
        self.all_rows_cache = []

        self.auto_running = False
        self.auto_stop_event = threading.Event()
        self.auto_failed_ids = set()

    def set_status(self, text):
        self.status_var.set(text)
        self.root.update_idletasks()

    def load_components(self):
        self.set_status("Chargement depuis le site…")

        def work():
            try:
                components = fetch_pending_components()
            except Exception as error:
                self.root.after(0, lambda: self.set_status(f"Chargement échoué : {error}"))
                return
            self.root.after(0, lambda: self._populate(components))

        threading.Thread(target=work, daemon=True).start()

    def _populate(self, components):
        self.all_rows_cache = components
        self.apply_filter()
        self.set_status(f"{len(components)} composant(s) en attente de détourage.")

    def apply_filter(self):
        needle = self.filter_var.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        self.rows.clear()
        for component in self.all_rows_cache:
            component_id, nom, image_url = component["id"], component["nom"], component["image_url"]
            if needle and needle not in nom.lower():
                continue
            self.rows[component_id] = {"nom": nom, "image_url": image_url}
            statut = "détouré ✓" if component_id in self.results else ""
            self.tree.insert("", "end", iid=str(component_id), values=(component_id, nom, statut))

    def select_all(self):
        self.tree.selection_set(self.tree.get_children())

    def selected_ids(self):
        return [int(iid) for iid in self.tree.selection()]

    def on_select_preview(self, _event):
        ids = self.selected_ids()
        if len(ids) != 1:
            return
        component_id = ids[0]
        row = self.rows.get(component_id)
        if not row:
            return

        def work():
            try:
                raw = load_image_bytes(row["image_url"])
                before_img = Image.open(io.BytesIO(raw)).convert("RGB")
            except Exception as error:
                self.root.after(0, lambda: self.set_status(f"Aperçu impossible : {error}"))
                return
            self.root.after(0, lambda: self._show_preview(self.before_label, before_img))
            if component_id in self.results:
                after_img = Image.open(io.BytesIO(self.results[component_id])).convert("RGBA")
                bg = Image.new("RGBA", after_img.size, (34, 34, 34, 255))
                after_img = Image.alpha_composite(bg, after_img).convert("RGB")
                self.root.after(0, lambda: self._show_preview(self.after_label, after_img))
            else:
                self.root.after(0, lambda: self.after_label.configure(image="", text=""))

        threading.Thread(target=work, daemon=True).start()

    def _show_preview(self, label, pil_img):
        pil_img = pil_img.copy()
        pil_img.thumbnail((240, 240))
        photo = ImageTk.PhotoImage(pil_img)
        label.image = photo
        label.configure(image=photo)

    def process_selected(self):
        ids = self.selected_ids()
        if not ids:
            messagebox.showinfo("Rien à faire", "Sélectionne au moins un composant dans la liste.")
            return

        def work():
            total = len(ids)
            for index, component_id in enumerate(ids, start=1):
                row = self.rows[component_id]
                self.root.after(0, lambda i=index, t=total, n=row["nom"]: self.set_status(
                    f"Détourage {i}/{t} : {n} (premier lancement = téléchargement du modèle, patience)"
                ))
                try:
                    raw = load_image_bytes(row["image_url"])
                    output_bytes = remove_background_birefnet(raw)
                    self.results[component_id] = output_bytes
                    self.root.after(0, lambda cid=component_id: self._mark_done(cid))
                except Exception as error:
                    self.root.after(0, lambda n=row["nom"], e=error: self.set_status(f"Échec sur {n} : {e}"))
            self.root.after(0, lambda: self.set_status(f"Détourage terminé ({total} image(s))."))

        threading.Thread(target=work, daemon=True).start()

    def _mark_done(self, component_id):
        if self.tree.exists(str(component_id)):
            values = list(self.tree.item(str(component_id), "values"))
            values[2] = "détouré ✓"
            self.tree.item(str(component_id), values=values)
        if len(self.selected_ids()) == 1 and self.selected_ids()[0] == component_id:
            self.on_select_preview(None)

    def save_selected(self):
        ids = [cid for cid in self.selected_ids() if cid in self.results]
        if not ids:
            messagebox.showinfo(
                "Rien à enregistrer",
                "Sélectionne des composants déjà détourés (colonne « statut ») avant d'enregistrer.",
            )
            return
        if not messagebox.askyesno(
            "Confirmer",
            f"Envoyer {len(ids)} image(s) détourée(s) sur le site de production ?",
        ):
            return

        def work():
            for component_id in ids:
                data_url = image_bytes_to_data_url(self.results[component_id])
                try:
                    save_processed_image(component_id, data_url)
                except Exception as error:
                    self.root.after(0, lambda n=self.rows[component_id]["nom"], e=error: self.set_status(f"Échec sur {n} : {e}"))
                    continue
                self.root.after(0, lambda n=self.rows[component_id]["nom"]: self.set_status(f"Enregistré : {n}"))
            self.root.after(0, lambda: self.set_status(f"{len(ids)} image(s) enregistrée(s) sur le site."))
            self.root.after(0, lambda: messagebox.showinfo("Terminé", f"{len(ids)} image(s) mise(s) à jour sur pcradar.tech."))

        threading.Thread(target=work, daemon=True).start()

    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def toggle_auto_mode(self):
        if self.auto_running:
            self.auto_stop_event.set()
            self.auto_running = False
            self.auto_button.configure(text="▶ Démarrer la surveillance automatique")
            self.log("Surveillance arrêtée.")
        else:
            self.auto_stop_event.clear()
            self.auto_running = True
            self.auto_button.configure(text="⏸ Arrêter la surveillance")
            self.log("Surveillance démarrée — vérification toutes les 20s.")
            threading.Thread(target=self._auto_loop, daemon=True).start()

    def _auto_loop(self, interval_seconds=20):
        while not self.auto_stop_event.is_set():
            try:
                self._auto_check_once()
            except Exception as error:
                self.root.after(0, lambda e=error: self.log(f"Erreur de surveillance : {e}"))
            self.auto_stop_event.wait(interval_seconds)

    def _auto_check_once(self):
        components = fetch_pending_components()
        todo = [c for c in components if c["id"] not in self.auto_failed_ids]
        if not todo:
            return

        for component in todo:
            if self.auto_stop_event.is_set():
                return
            component_id, nom, image_url = component["id"], component["nom"], component["image_url"]
            self.root.after(0, lambda n=nom: self.log(f"Nouveau composant détecté : {n} — détourage…"))
            try:
                raw = load_image_bytes(image_url)
                output_bytes = remove_background_birefnet(raw)
                data_url = image_bytes_to_data_url(output_bytes)
                save_processed_image(component_id, data_url)
            except Exception as error:
                self.auto_failed_ids.add(component_id)
                self.root.after(0, lambda n=nom, e=error: self.log(f"Échec sur {n} ({e}) — ignoré désormais."))
                continue
            self.root.after(0, lambda n=nom: self.log(f"Enregistré sur le site : {n}"))


if __name__ == "__main__":
    if not ADMIN_SECRET:
        raise SystemExit(
            "ADMIN_SECRET introuvable — vérifie que le fichier .env du projet "
            "(pc-configurator/.env) existe bien un dossier au-dessus de celui-ci."
        )
    root = tk.Tk()
    App(root)
    root.mainloop()
