"""
Environnement de test : base SQLite neuve (schéma identique à la production,
16 composants cohérents), jamais la vraie base. Lancer : python -m pytest
"""
import json
import os
import sqlite3
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="pcradar-tests-")
DB = os.path.join(TMP, "test.db")

os.environ.update({
    "TURSO_DATABASE_URL": "file:" + DB.replace("\\", "/"),
    "SESSION_HTTPS_ONLY": "0",
    "SESSION_SECRET": "secret-de-test",
    "ADMIN_SECRET": "admin-de-test",
    "PCRADAR_LOCK_DIR": TMP,
    "PCRADAR_ACCESS_LOG_GLOB": os.path.join(TMP, "access.log*"),
})
for key in ("GROQ_API_KEY", "GEMINI_API_KEY", "BRIGHTDATA_API_TOKEN", "APIFY_API_TOKEN", "ZENROWS_API_KEY", "SMTP_HOST"):
    os.environ[key] = ""

SCHEMA = """
CREATE TABLE components (
    id INTEGER PRIMARY KEY AUTOINCREMENT, categorie TEXT NOT NULL, nom TEXT NOT NULL,
    specs_json TEXT NOT NULL, prix_indicatif REAL, prix_marche_json TEXT, image_url TEXT, asin TEXT,
    amazon_details_json TEXT, description TEXT, has_image INTEGER DEFAULT 0, en_stock INTEGER NOT NULL DEFAULT 1);
CREATE TABLE builds (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id_optionnel TEXT, nom TEXT NOT NULL, composants_json TEXT NOT NULL,
    date TEXT NOT NULL, est_officielle INTEGER DEFAULT 0, prix_total_sauvegarde REAL);
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE link_corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT, component_id INTEGER NOT NULL, vendeur TEXT NOT NULL, ancien_lien TEXT,
    nouveau_lien TEXT NOT NULL, user_id INTEGER NOT NULL, user_email TEXT NOT NULL,
    statut TEXT NOT NULL DEFAULT 'pending', date TEXT NOT NULL);
"""

COMPONENTS = [
    ("CPU", "AMD Ryzen 5 5600", {"socket": "AM4", "tdp": 65}, 130),
    ("CPU", "Intel Core i5-14600K", {"socket": "LGA1700", "tdp": 125}, 250),
    ("Carte mère", "MSI B550 Tomahawk", {"socket": "AM4", "ram_type": "DDR4", "format": "ATX", "m2_slots": 2, "sata_ports": 6}, 100),
    ("Carte mère", "ASUS Prime B760M-A D4", {"socket": "LGA1700", "ram_type": "DDR4", "format": "Micro-ATX", "m2_slots": 2, "sata_ports": 4}, 110),
    ("RAM", "Corsair Vengeance LPX 16 Go DDR4 3200 MHz", {"type": "DDR4"}, 45),
    ("RAM", "Kingston FURY Beast 32 Go DDR5 6000 MT/s", {"type": "DDR5"}, 110),
    ("GPU", "MSI GeForce RTX 4060 Ventus 2X 8G", {"tdp": 115, "longueur_mm": 199}, 300),
    ("GPU", "Sapphire Pulse Radeon RX 7600 8 Go", {"tdp": 165, "longueur_mm": 240}, 280),
    ("Refroidissement", "Thermalright Peerless Assassin 120 SE", {"sockets_supportes": ["AM4", "AM5", "LGA1700", "LGA1851"], "hauteur_mm": 155}, 40),
    ("Refroidissement", "ARCTIC Freezer 36", {"sockets_supportes": ["AM4", "AM5", "LGA1700", "LGA1851"], "hauteur_mm": 159}, 30),
    ("Stockage", "Crucial P3 Plus 1 To NVMe", {"type": "NVMe"}, 70),
    ("Stockage", "Samsung 870 EVO 500 Go SATA", {"type": "SATA"}, 55),
    ("Alimentation", "Corsair RM750e 750W", {"wattage": 750}, 95),
    ("Alimentation", "be quiet! Pure Power 12 650W", {"wattage": 650}, 80),
    ("Boîtier", "Fractal Design North", {"formats_supportes": ["ATX", "Micro-ATX", "Mini-ITX"], "gpu_max_length_mm": 355, "cpu_cooler_max_height_mm": 170}, 130),
    ("Boîtier", "NZXT H5 Flow", {"formats_supportes": ["ATX", "Micro-ATX"], "gpu_max_length_mm": 365}, 90),
]


def _create_db():
    db = sqlite3.connect(DB)
    db.executescript(SCHEMA)
    for i, (cat, nom, specs, prix) in enumerate(COMPONENTS):
        asin = f"B0TEST{i:04d}"
        offers = [{"vendeur": "Amazon", "prix": prix, "lien": f"https://www.amazon.fr/dp/{asin}", "date_releve": "2026-09-24"}]
        db.execute(
            "INSERT INTO components (categorie, nom, specs_json, prix_indicatif, prix_marche_json, image_url, asin, has_image, en_stock) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1)",
            (cat, nom, json.dumps(specs), prix, json.dumps(offers), f"https://m.media-amazon.com/images/I/{asin}.jpg", asin),
        )
    db.commit()
    db.close()


_create_db()
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import main  # noqa: E402  (l'environnement doit être prêt avant l'import)


@pytest.fixture(scope="session")
def app_main():
    return main


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def new_client():
    """Client neuf (sans cookie) ; chaque test peut prendre sa propre adresse IP."""
    from fastapi.testclient import TestClient
    clients = []

    def make(ip="203.0.113.1"):
        c = TestClient(main.app, headers={"X-Real-IP": ip})
        clients.append(c)
        return c
    yield make
    for c in clients:
        c.close()


@pytest.fixture(scope="session")
def catalog(client):
    return [c for items in client.get("/api/components").json()["components"].values() for c in items]


def component(catalog, nom_part):
    return next(c for c in catalog if nom_part in c["nom"])
