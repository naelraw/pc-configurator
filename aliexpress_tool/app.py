"""
Outil de bureau LOCAL pour chercher un produit dans le feed AliExpress
(export Awin "Bestsellers CSS", ~427 000 produits, voir feed.csv à côté de
ce fichier) sans avoir à demander à Claude à chaque fois.

Le feed AliExpress n'a pas d'équivalent à un ASIN Amazon propre : les noms
de marque et descriptions sont en vrac, et une recherche automatique fiable
type "fetch-asin" n'est pas possible dessus. Cet outil sert donc à CHERCHER
un produit par mot-clé et à récupérer son lien d'affiliation Awin déjà prêt
(champ aw_deep_link, tracking déjà inclus) — ensuite tu colles nom/prix/lien
à la main dans l'admin du site (ligne de prix, vendeur = "AliExpress").

Utilisation :
    1. pip install -r requirements.txt
    2. python app.py
    3. "Charger le feed" (une fois, prend quelques secondes — ~320 Mo,
       427 000 lignes)
    4. Tape un ou plusieurs mots-clés (ex: "ventilateur rgb"), "Rechercher"
    5. Clique un résultat pour voir l'aperçu, puis "Copier le lien" ou
       "Copier tout (nom + prix + lien)"

Pour rafraîchir le feed plus tard : retélécharge-le depuis Awin (Toolbox >
Create-a-Feed > advertiser-based feed > AliExpress FR > Bestsellers CSS) et
remplace feed.csv dans ce dossier.
"""

import csv
import io
import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import requests
from PIL import Image, ImageTk

FEED_PATH = os.path.join(os.path.dirname(__file__), "feed.csv")
csv.field_size_limit(sys.maxsize)


class App:
    def __init__(self, root):
        self.root = root
        root.title("PC Radar — Recherche AliExpress (feed Awin)")
        root.geometry("1000x650")

        top = ttk.Frame(root, padding=8)
        top.pack(fill="x")
        self.load_btn = ttk.Button(top, text="Charger le feed", command=self.load_feed)
        self.load_btn.pack(side="left")
        self.feed_status_var = tk.StringVar(value="Feed non chargé.")
        ttk.Label(top, textvariable=self.feed_status_var).pack(side="left", padx=10)

        search_frame = ttk.Frame(root, padding=(8, 0))
        search_frame.pack(fill="x")
        ttk.Label(search_frame, text="Mots-clés :").pack(side="left")
        self.query_var = tk.StringVar()
        query_entry = ttk.Entry(search_frame, textvariable=self.query_var, width=50)
        query_entry.pack(side="left", padx=6)
        query_entry.bind("<Return>", lambda e: self.search())
        ttk.Button(search_frame, text="Rechercher", command=self.search).pack(side="left")
        self.results_count_var = tk.StringVar(value="")
        ttk.Label(search_frame, textvariable=self.results_count_var).pack(side="left", padx=10)

        body = ttk.Frame(root)
        body.pack(fill="both", expand=True, padx=8, pady=8)

        list_frame = ttk.Frame(body)
        list_frame.pack(side="left", fill="both", expand=True)
        columns = ("nom", "marque", "prix", "categorie", "stock")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")
        headers = {"nom": 420, "marque": 120, "prix": 70, "categorie": 160, "stock": 60}
        for col, width in headers.items():
            self.tree.heading(col, text=col.capitalize())
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        detail_frame = ttk.Frame(body, width=300)
        detail_frame.pack(side="left", fill="y", padx=(8, 0))
        detail_frame.pack_propagate(False)
        self.image_label = tk.Label(detail_frame, bg="#222")
        self.image_label.pack(fill="x", pady=(0, 8))
        self.detail_text = tk.Text(detail_frame, height=10, wrap="word", state="disabled")
        self.detail_text.pack(fill="x", pady=(0, 8))
        ttk.Button(detail_frame, text="Copier le lien d'affiliation", command=self.copy_link).pack(fill="x", pady=2)
        ttk.Button(detail_frame, text="Copier tout (nom + prix + lien)", command=self.copy_all).pack(fill="x", pady=2)

        self.status_var = tk.StringVar(value="Prêt.")
        ttk.Label(root, textvariable=self.status_var, padding=6).pack(fill="x", side="bottom")

        self.rows = []            # tous les produits du feed, chargés une fois
        self.filtered_rows = []   # résultats de la dernière recherche
        self.selected_row = None

    def set_status(self, text):
        self.status_var.set(text)
        self.root.update_idletasks()

    def load_feed(self):
        if not os.path.exists(FEED_PATH):
            messagebox.showerror("Fichier introuvable", f"feed.csv introuvable à côté de app.py :\n{FEED_PATH}")
            return

        self.load_btn.configure(state="disabled")
        self.feed_status_var.set("Chargement en cours…")

        def work():
            rows = []
            try:
                with open(FEED_PATH, encoding="utf-8", newline="") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        rows.append(row)
            except Exception as error:
                self.root.after(0, lambda: messagebox.showerror("Erreur de lecture", str(error)))
                self.root.after(0, lambda: self.load_btn.configure(state="normal"))
                return
            self.rows = rows
            self.root.after(0, lambda: self.feed_status_var.set(f"{len(rows):,} produits chargés.".replace(",", " ")))
            self.root.after(0, lambda: self.load_btn.configure(state="normal"))

        threading.Thread(target=work, daemon=True).start()

    def search(self):
        if not self.rows:
            messagebox.showinfo("Feed non chargé", "Clique d'abord \"Charger le feed\".")
            return

        query = self.query_var.get().strip().lower()
        keywords = query.split()
        if not keywords:
            self.filtered_rows = []
            self.tree.delete(*self.tree.get_children())
            self.results_count_var.set("")
            return

        self.set_status("Recherche…")

        def matches(row):
            haystack = " ".join([
                row.get("product_name", ""),
                row.get("merchant_category", ""),
                row.get("category_name", ""),
                row.get("brand_name", ""),
            ]).lower()
            return all(kw in haystack for kw in keywords)

        results = [row for row in self.rows if matches(row)][:500]
        self.filtered_rows = results

        self.tree.delete(*self.tree.get_children())
        for i, row in enumerate(results):
            self.tree.insert("", "end", iid=str(i), values=(
                row.get("product_name", "")[:100],
                row.get("brand_name", "") or "—",
                row.get("display_price", "") or row.get("search_price", ""),
                row.get("merchant_category", "") or row.get("category_name", "") or "—",
                "oui" if row.get("in_stock") == "1" else "non",
            ))

        suffix = " (limité à 500 affichés)" if len(results) == 500 else ""
        self.results_count_var.set(f"{len(results)} résultat(s){suffix}")
        self.set_status("Prêt.")

    def on_select(self, _event):
        selection = self.tree.selection()
        if not selection:
            return
        index = int(selection[0])
        row = self.filtered_rows[index]
        self.selected_row = row

        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("end",
            f"{row.get('product_name', '')}\n\n"
            f"Prix : {row.get('display_price', '')} (avant réduction : {row.get('rrp_price', '') or '—'})\n"
            f"Livraison : {row.get('delivery_cost', '') or '—'} — délai : {row.get('delivery_time', '') or '—'}\n"
            f"Marque : {row.get('brand_name', '') or '—'}\n"
            f"En stock : {'oui' if row.get('in_stock') == '1' else 'non'}\n"
        )
        self.detail_text.configure(state="disabled")

        image_url = row.get("aw_image_url") or row.get("merchant_image_url")
        if image_url:
            threading.Thread(target=self._load_image, args=(image_url,), daemon=True).start()
        else:
            self.image_label.configure(image="")

    def _load_image(self, image_url):
        try:
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()
            img = Image.open(io.BytesIO(response.content)).convert("RGB")
            img.thumbnail((260, 260))
            photo = ImageTk.PhotoImage(img)
        except Exception:
            return
        def apply():
            self.image_label.image = photo
            self.image_label.configure(image=photo)
        self.root.after(0, apply)

    def copy_link(self):
        if not self.selected_row:
            messagebox.showinfo("Rien de sélectionné", "Clique d'abord un résultat dans la liste.")
            return
        link = self.selected_row.get("aw_deep_link", "")
        self.root.clipboard_clear()
        self.root.clipboard_append(link)
        self.set_status("Lien copié dans le presse-papiers.")

    def copy_all(self):
        if not self.selected_row:
            messagebox.showinfo("Rien de sélectionné", "Clique d'abord un résultat dans la liste.")
            return
        row = self.selected_row
        text = (
            f"{row.get('product_name', '')}\n"
            f"Prix : {row.get('display_price', '')}\n"
            f"Lien : {row.get('aw_deep_link', '')}"
        )
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.set_status("Nom + prix + lien copiés dans le presse-papiers.")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
