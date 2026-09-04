import os
from dotenv import load_dotenv
import libsql_client

load_dotenv()

url = os.getenv("TURSO_DATABASE_URL")
token = os.getenv("TURSO_AUTH_TOKEN")

# Conversion de l'URL libsql:// en https:// pour le mode sync HTTP
http_url = url.replace("libsql://", "https://")

client = libsql_client.create_client_sync(url=http_url, auth_token=token)

# Création des tables
client.execute("""
CREATE TABLE IF NOT EXISTS components (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    categorie TEXT NOT NULL,
    nom TEXT NOT NULL,
    specs_json TEXT NOT NULL,
    prix_indicatif REAL
)
""")

client.execute("""
CREATE TABLE IF NOT EXISTS builds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id_optionnel TEXT,
    nom TEXT NOT NULL,
    composants_json TEXT NOT NULL,
    date TEXT NOT NULL
)
""")

print("✅ Tables créées avec succès sur Turso !")

# Test d'insertion
client.execute(
    "INSERT INTO components (categorie, nom, specs_json, prix_indicatif) VALUES (?, ?, ?, ?)",
    ["CPU", "Test CPU", '{"socket": "AM5"}', 199.99]
)

print("✅ Insertion test réussie !")

# Test de lecture
result = client.execute("SELECT * FROM components")
print("📋 Contenu de la table components :")
for row in result.rows:
    print(row)

client.close()