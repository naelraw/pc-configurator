import asyncio
import base64
import concurrent.futures
import hashlib
import html
import ipaddress
import json
import os
import re
import secrets
import socket
import threading
import time
import unicodedata
from datetime import datetime
from urllib.parse import urlparse
import requests
from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from groq import Groq
import libsql_client
from pydantic import BaseModel
from compatibility import (
    check_alimentation,
    check_carte_mere_boitier,
    check_carte_mere_ram,
    check_cpu_carte_mere,
    check_gpu_boitier,
    check_refroidissement,
    check_stockage,
)
from schema import REQUIRED_FIELDS, validate_component

try:
    import google.generativeai as genai
except ImportError:
    genai = None

try:
    from google import genai as genai_new
    from google.genai import types as genai_types
except ImportError:
    genai_new = None
    genai_types = None

load_dotenv()

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")

# Clé de signature des cookies de session (comptes utilisateurs). À définir
# dans .env / fly secrets — si absente, on en génère une aléatoire au
# démarrage : les sessions ne survivront pas à un redémarrage du serveur,
# mais l'app reste utilisable plutôt que de planter.
SESSION_SECRET = os.getenv("SESSION_SECRET") or secrets.token_hex(32)

# Tag Amazon Associates (programme d'affiliation officiel — pas de scraping).
# Non sensible : un tag est de toute façon visible en clair dans chaque lien.
AMAZON_ASSOCIATE_TAG = os.getenv("AMAZON_ASSOCIATE_TAG", "")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")  # Fallback optionnel

# Plusieurs projets Gemini possibles (chacun a son propre quota gratuit
# journalier, complètement indépendant des autres) : si le premier est à
# court de crédit, on bascule sur le suivant, et ainsi de suite. Optionnel :
# seul GEMINI_API_KEY est requis, les autres n'existent que s'ils sont
# définis dans .env.
GEMINI_API_KEYS = [
    key for key in (
        os.getenv("GEMINI_API_KEY"),
        os.getenv("GEMINI_API_KEY_2"),
        os.getenv("GEMINI_API_KEY_3"),
    ) if key
]

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
if genai and GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Récupération auto des infos produit Amazon par ASIN, via le dataset
# "Amazon Products" de Bright Data (5000 requêtes gratuites/mois, jamais de
# scraping fait par ce serveur lui-même — Bright Data s'en charge et renvoie
# des données déjà structurées).
BRIGHTDATA_API_TOKEN = os.getenv("BRIGHTDATA_API_TOKEN", "")
BRIGHTDATA_AMAZON_DATASET_ID = os.getenv("BRIGHTDATA_AMAZON_DATASET_ID", "gd_l7q7dkf244hwjntr0")
AMAZON_DOMAIN_TLD = os.getenv("AMAZON_DOMAIN_TLD", "fr")

# Détourage (suppression d'arrière-plan) des photos produit, via un service
# rembg auto-hébergé sur un VM Oracle Cloud personnel — gratuit, illimité.
REMBG_SERVICE_URL = os.getenv("REMBG_SERVICE_URL", "").rstrip("/")
REMBG_API_KEY = os.getenv("REMBG_API_KEY", "")


class SuggestConfigRequest(BaseModel):
    user_input: str

app = FastAPI()

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # v1 : simple, on restreindra plus tard si besoin
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static", html=True), name="static")

def get_client():
    url = os.getenv("TURSO_DATABASE_URL").replace("libsql://", "https://")
    token = os.getenv("TURSO_AUTH_TOKEN")
    return libsql_client.create_client_sync(url=url, auth_token=token)


def get_all_components():
    client = get_client()
    try:
        result = client.execute(
            "SELECT id, categorie, nom, specs_json, prix_indicatif, prix_marche_json, image_url, asin, "
            "amazon_details_json, description FROM components ORDER BY categorie, nom"
        )
        components = []
        for row in result.rows:
            component = {
                "id": row[0],
                "categorie": row[1],
                "nom": row[2],
                "specs_json": row[3],
                "prix_indicatif": row[4],
                "image_url": row[6],
                "asin": row[7],
                "description": row[9],
            }
            try:
                component["specs"] = json.loads(row[3])
            except (TypeError, json.JSONDecodeError):
                component["specs"] = {}
            try:
                component["prix_marche"] = json.loads(row[5]) if row[5] else []
            except (TypeError, json.JSONDecodeError):
                component["prix_marche"] = []
            try:
                component["caracteristiques_amazon"] = json.loads(row[8]) if row[8] else []
            except (TypeError, json.JSONDecodeError):
                component["caracteristiques_amazon"] = []
            components.append(component)
        return components
    except Exception:
        return []
    finally:
        client.close()


def check_compatibility(config_list):
    by_category = {component["categorie"]: component["specs"] for component in config_list}
    errors = []

    cpu = by_category.get("CPU")
    motherboard = by_category.get("Carte mère")
    ram = by_category.get("RAM")
    case = by_category.get("Boîtier")
    psu = by_category.get("Alimentation")
    gpu = by_category.get("GPU")
    storage = [
        component["specs"]
        for component in config_list
        if component["categorie"] == "Stockage"
    ]
    cooler = by_category.get("Refroidissement")

    if cpu and motherboard:
        ok, message = check_cpu_carte_mere(cpu, motherboard)
        if not ok:
            errors.append(message)
    if motherboard and ram:
        ok, message = check_carte_mere_ram(motherboard, ram)
        if not ok:
            errors.append(message)
    if motherboard and case:
        ok, message = check_carte_mere_boitier(motherboard, case)
        if not ok:
            errors.append(message)
    if cpu and psu:
        ok, message = check_alimentation(cpu, gpu, psu)
        if not ok:
            errors.append(message)
    if gpu and case:
        ok, message = check_gpu_boitier(gpu, case)
        if not ok:
            errors.append(message)
    if motherboard and storage:
        ok, message = check_stockage(motherboard, storage)
        if not ok:
            errors.append(message)
    if cpu and case and cooler:
        ok, message = check_refroidissement(cpu, case, cooler)
        if not ok:
            errors.append(message)

    return {"compatible": not errors, "errors": errors}


def verify_compatibility(suggestion):
    """
    Vérifie qu'une suggestion de l'IA contient bien tous les composants requis
    ET qu'ils sont compatibles entre eux. Une suggestion incomplète, avec des
    IDs inconnus, ou dont un ID pointe vers la mauvaise catégorie (ex: gpu_id
    qui résout vers un composant catégorisé "gpu" au lieu de "GPU") est
    TOUJOURS rejetée explicitement — on ne déduit jamais "compatible" de
    l'absence de données ou d'une catégorie mal alignée.
    """
    field_to_category = {
        "cpu_id": "CPU",
        "motherboard_id": "Carte mère",
        "ram_id": "RAM",
        "gpu_id": "GPU",
        "psu_id": "Alimentation",
        "storage_id": "Stockage",
        "case_id": "Boîtier",
    }
    required_fields = tuple(field_to_category.keys())

    if not isinstance(suggestion, dict):
        return {"compatible": False, "errors": ["Réponse de l'IA invalide (pas un objet JSON)."]}

    missing = [field for field in required_fields if not suggestion.get(field)]
    if missing:
        return {
            "compatible": False,
            "errors": [f"Champs manquants dans la suggestion de l'IA : {', '.join(missing)}"],
        }

    components = get_all_components()
    components_by_id = {component["id"]: component for component in components}

    unknown = [field for field in required_fields if suggestion[field] not in components_by_id]
    if unknown:
        return {
            "compatible": False,
            "errors": [f"IDs de composants inconnus pour : {', '.join(unknown)}"],
        }

    mismatched = [
        field
        for field in required_fields
        if components_by_id[suggestion[field]]["categorie"] != field_to_category[field]
    ]
    if mismatched:
        details = ", ".join(
            f"{field} (attendu: {field_to_category[field]}, trouvé: "
            f"{components_by_id[suggestion[field]]['categorie']})"
            for field in mismatched
        )
        return {
            "compatible": False,
            "errors": [f"Catégorie de composant incohérente pour : {details}"],
        }

    config_list = [components_by_id[suggestion[field]] for field in required_fields]
    return check_compatibility(config_list)


@app.get("/")
def root():
    return FileResponse("static/index.html")


@app.get("/api/config")
def api_config():
    """Config publique consommée par le frontend (rien de sensible ici)."""
    return {"amazon_tag": AMAZON_ASSOCIATE_TAG}


@app.get("/configurateur")
def configurateur_page():
    return FileResponse("static/configurateur.html")


@app.get("/assistant")
def assistant_page():
    return FileResponse("static/assistant.html")


@app.get("/comparateur")
def comparateur_page():
    return FileResponse("static/comparateur.html")


@app.get("/estimer-fps")
def estimer_fps_page():
    return FileResponse("static/estimer-fps.html")


@app.get("/compte")
def compte_page():
    return FileResponse("static/compte.html")


@app.get("/build/{build_id}")
def build_view_page(build_id: int):
    """
    Page publique de visualisation d'un build partagé par lien. Injecte des
    meta Open Graph dynamiques (titre, description, image) dans le HTML
    statique pour un aperçu correct quand le lien est partagé sur
    WhatsApp/Discord/etc. — ces outils ne lisent que le HTML initial, jamais
    le contenu ajouté ensuite par le JavaScript côté client.
    """
    with open("static/build-view.html", encoding="utf-8") as f:
        page_html = f.read()

    client = get_client()
    try:
        result = client.execute("SELECT nom, composants_json FROM builds WHERE id = ?", [build_id])
    finally:
        client.close()

    if result.rows:
        nom = result.rows[0][0]
        try:
            composants_json = json.loads(result.rows[0][1])
        except (TypeError, json.JSONDecodeError):
            composants_json = {}

        components_by_id = {c["id"]: c for c in get_all_components()}
        # composants_json est censé être {catégorie: id}, mais d'anciennes
        # builds (avant ce format) peuvent contenir tout autre chose (ex: des
        # objets specs imbriqués) — on ignore silencieusement toute valeur
        # qui n'est pas un identifiant valide plutôt que de planter en 500
        # sur un `dict` non hashable utilisé comme clé.
        component_ids = [cid for cid in composants_json.values() if isinstance(cid, (int, str))]
        noms_composants = [components_by_id[cid]["nom"] for cid in component_ids if cid in components_by_id]
        image_url = next(
            (components_by_id[cid]["image_url"] for cid in component_ids
             if cid in components_by_id and components_by_id[cid].get("image_url")),
            None,
        )
        title = f"{nom} — PC Configurator"
        description = ", ".join(noms_composants)[:200] or "Une configuration PC partagée depuis PC Configurator."
    else:
        title = "Configuration introuvable — PC Configurator"
        description = "Ce lien ne correspond à aucune configuration (peut-être supprimée)."
        image_url = None

    # Toujours échapper : le nom de la build est saisi par un utilisateur,
    # jamais fiable tel quel dans du HTML.
    og_title = html.escape(title)
    og_description = html.escape(description)
    og_image_tag = f'<meta property="og:image" content="{html.escape(image_url)}">' if image_url else ""

    meta_tags = f"""<title>{og_title}</title>
<meta property="og:title" content="{og_title}">
<meta property="og:description" content="{og_description}">
<meta property="og:type" content="website">
{og_image_tag}
<meta name="twitter:card" content="{'summary_large_image' if image_url else 'summary'}">"""

    page_html = page_html.replace(
        "<title>Configuration partagée — PC Configurator</title>", meta_tags, 1
    )
    return HTMLResponse(content=page_html)


@app.get("/components")
def list_components():
    """Liste tous les composants, triés par catégorie."""
    return {"components": get_all_components()}


@app.get("/api/components")
def api_components():
    """Liste les composants regroupés par catégorie pour l'interface web."""
    grouped = {}
    for component in get_all_components():
        grouped.setdefault(component["categorie"], []).append(component)
    return {"components": grouped}


@app.post("/api/check-compatibility")
def check_compatibility_route(payload: dict = Body(...)):
    """
    Vérifie la compatibilité d'une sélection de composants, même partielle —
    conçu pour être appelé "en direct" pendant que l'utilisateur choisit
    encore ses composants dans le configurateur.

    Payload : { "components": [ {"categorie": "CPU", "specs": {...}}, ... ] }
    Les catégories absentes sont simplement ignorées (pas d'erreur) : seules
    les paires de composants réellement sélectionnées sont vérifiées.
    """
    components = payload.get("components", [])
    if not isinstance(components, list):
        raise HTTPException(status_code=400, detail="'components' doit être une liste.")

    result = check_compatibility(components)
    return {"compatible": result["compatible"], "erreurs": result["errors"]}


def hash_password(password: str) -> str:
    """PBKDF2-HMAC-SHA256 avec sel aléatoire par mot de passe. Format stocké : "sel$hash" (hex)."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 260_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest_hex = stored.split("$", 1)
    except ValueError:
        return False
    computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 260_000)
    return secrets.compare_digest(computed.hex(), digest_hex)


def get_current_user(request: Request):
    """Retourne {'id':..., 'email':...} si connecté, sinon None. Ne lève jamais d'erreur."""
    return request.session.get("user")


def require_login(request: Request):
    """Dépendance FastAPI : lève 401 si personne n'est connecté."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Connexion requise.")
    return user


@app.post("/api/auth/register")
def register(request: Request, payload: dict = Body(...)):
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Adresse e-mail invalide.")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Le mot de passe doit faire au moins 8 caractères.")

    client = get_client()
    try:
        existing = client.execute("SELECT id FROM users WHERE email = ?", [email])
        if existing.rows:
            raise HTTPException(status_code=409, detail="Un compte existe déjà avec cet e-mail.")

        password_hash = hash_password(password)
        created_at = datetime.utcnow().isoformat()
        client.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            [email, password_hash, created_at],
        )
        new_user = client.execute("SELECT id FROM users WHERE email = ?", [email])
        user_id = new_user.rows[0][0]
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur base de données : {error}. As-tu lancé 'python migrate_add_users.py' ?",
        )
    finally:
        client.close()

    request.session["user"] = {"id": user_id, "email": email}
    return {"status": "ok", "email": email}


@app.post("/api/auth/login")
def login(request: Request, payload: dict = Body(...)):
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    client = get_client()
    try:
        result = client.execute("SELECT id, password_hash FROM users WHERE email = ?", [email])
    finally:
        client.close()

    # Message volontairement générique : ne pas révéler si l'e-mail existe ou non.
    if not result.rows or not verify_password(password, result.rows[0][1]):
        raise HTTPException(status_code=401, detail="E-mail ou mot de passe incorrect.")

    user_id = result.rows[0][0]
    request.session["user"] = {"id": user_id, "email": email}
    return {"status": "ok", "email": email}


@app.post("/api/auth/logout")
def logout(request: Request):
    request.session.pop("user", None)
    return {"status": "ok"}


@app.get("/api/auth/me")
def me(request: Request):
    user = get_current_user(request)
    return {"logged_in": user is not None, "user": user}


@app.post("/api/builds")
def save_build(payload: dict = Body(...), user=Depends(require_login)):
    """Sauvegarde une configuration dans la table builds, liée au compte connecté."""
    nom = payload.get("nom", "Configuration sans nom")
    composants_json = json.dumps(payload.get("composants_json", {}))
    date = datetime.utcnow().isoformat()

    client = get_client()
    try:
        client.execute(
            "INSERT INTO builds (user_id_optionnel, nom, composants_json, date) "
            "VALUES (?, ?, ?, ?)",
            [user["id"], nom, composants_json, date],
        )
        result = client.execute("SELECT last_insert_rowid()")
        build_id = result.rows[0][0]
        return {"status": "ok", "message": "Build sauvegardée", "id": build_id}
    finally:
        client.close()


@app.put("/api/builds/{build_id}")
def update_build(build_id: int, payload: dict = Body(...), user=Depends(require_login)):
    """
    Met à jour le nom et/ou les composants d'une build déjà sauvegardée,
    au lieu d'en créer une nouvelle. Vérifie que la build appartient bien au
    compte connecté avant toute modification — jamais de confiance dans un
    ID envoyé par le client sans vérifier son propriétaire.
    """
    nom = payload.get("nom", "Configuration sans nom")
    composants_json = json.dumps(payload.get("composants_json", {}))

    client = get_client()
    try:
        existing = client.execute(
            "SELECT user_id_optionnel FROM builds WHERE id = ?",
            [build_id],
        )
        if not existing.rows:
            raise HTTPException(status_code=404, detail="Configuration introuvable.")
        # user_id_optionnel est une colonne TEXT (schéma existant) — SQLite
        # applique son affinité dans les comparaisons SQL (ex: list_builds),
        # mais pas ici en Python, donc on compare en texte des deux côtés
        # plutôt que de comparer une str ('5') à un int (5) qui ne matchent
        # jamais et rejetteraient à tort le propriétaire légitime.
        if str(existing.rows[0][0]) != str(user["id"]):
            raise HTTPException(status_code=403, detail="Cette configuration ne t'appartient pas.")

        client.execute(
            "UPDATE builds SET nom = ?, composants_json = ?, date = ? WHERE id = ?",
            [nom, composants_json, datetime.utcnow().isoformat(), build_id],
        )
        return {"status": "ok", "message": "Configuration mise à jour", "id": build_id}
    finally:
        client.close()


@app.delete("/api/builds/{build_id}")
def delete_build(build_id: int, user=Depends(require_login)):
    """
    Supprime définitivement une configuration sauvegardée — vérifie qu'elle
    appartient bien au compte connecté avant toute suppression, même
    principe que update_build (comparaison en texte des deux côtés, la
    colonne user_id_optionnel est en TEXT).
    """
    client = get_client()
    try:
        existing = client.execute(
            "SELECT user_id_optionnel FROM builds WHERE id = ?",
            [build_id],
        )
        if not existing.rows:
            raise HTTPException(status_code=404, detail="Configuration introuvable.")
        if str(existing.rows[0][0]) != str(user["id"]):
            raise HTTPException(status_code=403, detail="Cette configuration ne t'appartient pas.")

        client.execute("DELETE FROM builds WHERE id = ?", [build_id])
        return {"status": "ok", "message": "Configuration supprimée."}
    finally:
        client.close()


@app.get("/api/builds")
def list_builds(user=Depends(require_login)):
    """Retourne UNIQUEMENT les builds du compte connecté, les plus récents d'abord."""
    client = get_client()
    try:
        result = client.execute(
            "SELECT id, user_id_optionnel, nom, composants_json, date "
            "FROM builds WHERE user_id_optionnel = ? ORDER BY date DESC",
            [user["id"]],
        )
        builds = [
            {
                "id": row[0],
                "user_id_optionnel": row[1],
                "nom": row[2],
                "composants_json": json.loads(row[3]),
                "date": row[4],
            }
            for row in result.rows
        ]
        return {"status": "ok", "count": len(builds), "builds": builds}
    finally:
        client.close()


@app.get("/api/builds/recommandees")
def list_recommended_builds():
    """
    Configurations "recommandées" — des builds normales, sauvegardées par un
    compte comme n'importe quelle autre, que l'admin a choisi de mettre en
    avant publiquement (voir /api/admin/builds). Public, aucune identité de
    propriétaire renvoyée, comme pour la lecture d'un build par lien.

    Déclarée AVANT /api/builds/{build_id} : FastAPI fait correspondre les
    routes dans l'ordre où elles sont définies, donc une route dynamique
    déclarée en premier intercepterait "recommandees" en essayant de le
    parser comme un ID de build.
    """
    client = get_client()
    try:
        result = client.execute(
            "SELECT id, nom, composants_json, date FROM builds WHERE est_officielle = 1 ORDER BY date DESC"
        )
        builds = [
            {"id": row[0], "nom": row[1], "composants_json": json.loads(row[2]), "date": row[3]}
            for row in result.rows
        ]
        return {"status": "ok", "builds": builds}
    finally:
        client.close()


@app.get("/api/builds/{build_id}")
def get_build_public(build_id: int):
    """
    Lecture publique d'un build par ID — volontairement SANS authentification,
    c'est ce qui permet le partage par simple lien. Ne renvoie que le nom, les
    composants et la date : jamais l'e-mail ou l'identité du propriétaire.
    """
    client = get_client()
    try:
        result = client.execute(
            "SELECT nom, composants_json, date FROM builds WHERE id = ?",
            [build_id],
        )
        if not result.rows:
            raise HTTPException(status_code=404, detail="Configuration introuvable.")

        row = result.rows[0]
        return {
            "status": "ok",
            "nom": row[0],
            "composants_json": json.loads(row[1]),
            "date": row[2],
        }
    finally:
        client.close()


def require_admin(x_admin_secret: str = Header(default="")):
    """
    Dépendance FastAPI : protège les routes admin avec un secret partagé
    (ADMIN_SECRET dans .env / fly secrets). Fail-closed : si le secret n'est
    pas configuré côté serveur, l'accès est refusé plutôt qu'ouvert à tous.
    """
    if not ADMIN_SECRET or x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Accès admin refusé.")


@app.get("/admin")
def admin_page():
    """Page d'administration pour coller et ajouter des composants."""
    return FileResponse("static/admin.html")


@app.get("/api/admin/verify")
def admin_verify(_admin=Depends(require_admin)):
    """Simple endpoint pour vérifier le mot de passe admin avant d'afficher le formulaire."""
    return {"status": "ok"}


@app.get("/api/admin/builds")
def admin_list_builds(_admin=Depends(require_admin)):
    """
    Liste toutes les configurations sauvegardées (par n'importe quel compte),
    avec l'e-mail du propriétaire — pour que l'admin choisisse lesquelles
    mettre en avant comme "recommandées" sur /estimer-fps. Contrairement aux
    lectures publiques de build, on montre bien l'e-mail ici puisque c'est
    une vue strictement réservée à l'admin.
    """
    client = get_client()
    try:
        result = client.execute("""
            SELECT builds.id, builds.nom, builds.date, builds.est_officielle, users.email
            FROM builds
            LEFT JOIN users ON CAST(builds.user_id_optionnel AS INTEGER) = users.id
            ORDER BY builds.date DESC
        """)
        builds = [
            {
                "id": row[0],
                "nom": row[1],
                "date": row[2],
                "est_officielle": bool(row[3]),
                "user_email": row[4] or "compte supprimé",
            }
            for row in result.rows
        ]
        return {"status": "ok", "builds": builds}
    finally:
        client.close()


@app.post("/api/admin/builds/{build_id}/toggle-officielle")
def admin_toggle_official_build(build_id: int, _admin=Depends(require_admin)):
    """Bascule le statut "recommandée" (publique sur /estimer-fps) d'une configuration."""
    client = get_client()
    try:
        result = client.execute("SELECT est_officielle FROM builds WHERE id = ?", [build_id])
        if not result.rows:
            raise HTTPException(status_code=404, detail="Configuration introuvable.")
        new_value = 0 if result.rows[0][0] else 1
        client.execute("UPDATE builds SET est_officielle = ? WHERE id = ?", [new_value, build_id])
        return {"status": "ok", "est_officielle": bool(new_value)}
    finally:
        client.close()


@app.post("/api/admin/components")
def admin_add_components(payload: dict = Body(...), _admin=Depends(require_admin)):
    """
    Ajoute/met à jour un ou plusieurs composants collés depuis la page admin.
    Payload attendu : { "components": [ {categorie, nom, prix_indicatif, specs}, ... ] }
    (ou une seule liste directement, on gère les deux formats par confort).

    Même logique de sécurité que seed_components.py : TOUT est validé d'abord.
    S'il y a la moindre erreur sur un seul composant, RIEN n'est écrit en base.
    """
    components = payload.get("components", payload if isinstance(payload, list) else None)
    if not isinstance(components, list) or not components:
        raise HTTPException(status_code=400, detail="Aucun composant fourni (liste vide ou format invalide).")

    all_errors = []
    for i, component in enumerate(components, start=1):
        all_errors.extend(validate_component(component, i))

    if all_errors:
        return {"status": "error", "message": "Erreurs de validation, rien n'a été écrit en base.", "errors": all_errors}

    client = get_client()
    try:
        # Un seul aller-retour pour savoir quels composants existent déjà
        # (par catégorie+nom), plutôt qu'une requête SELECT par composant —
        # indispensable pour tenir la charge sur plusieurs centaines de
        # composants d'un coup (un SELECT + un INSERT/UPDATE par composant,
        # en série, prenait ~50s pour 300 composants ; en un seul batch,
        # c'est quasi instantané).
        existing_result = client.execute("SELECT id, categorie, nom FROM components")
        existing_ids = {(row[1], row[2]): row[0] for row in existing_result.rows}

        # Si le fichier envoyé contient deux fois le même (categorie, nom),
        # on ne garde que la dernière occurrence — même comportement que
        # l'ancien code séquentiel, qui aurait mis à jour la même ligne au
        # 2e passage plutôt que de la dupliquer.
        deduped = {}
        for component in components:
            deduped[(component["categorie"], component["nom"])] = component

        statements = []
        created, updated = 0, 0
        for (categorie, nom), component in deduped.items():
            specs_json = json.dumps(component["specs"], ensure_ascii=False)
            prix_marche_json = json.dumps(component.get("prix_marche", []), ensure_ascii=False)
            image_url = component.get("image_url")
            asin = component.get("asin")
            amazon_details_json = json.dumps(component.get("caracteristiques_amazon", []), ensure_ascii=False)
            description = component.get("description")
            prix = component["prix_indicatif"]

            existing_id = existing_ids.get((categorie, nom))
            if existing_id is not None:
                statements.append((
                    "UPDATE components SET specs_json = ?, prix_indicatif = ?, prix_marche_json = ?, image_url = ?, asin = ?, amazon_details_json = ?, description = ? WHERE id = ?",
                    [specs_json, prix, prix_marche_json, image_url, asin, amazon_details_json, description, existing_id],
                ))
                updated += 1
            else:
                statements.append((
                    "INSERT INTO components (categorie, nom, specs_json, prix_indicatif, prix_marche_json, image_url, asin, amazon_details_json, description) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [categorie, nom, specs_json, prix, prix_marche_json, image_url, asin, amazon_details_json, description],
                ))
                created += 1

        if statements:
            client.batch(statements)
    finally:
        client.close()

    return {"status": "ok", "created": created, "updated": updated}


@app.put("/api/admin/components/{component_id}")
def admin_update_component(component_id: int, payload: dict = Body(...), _admin=Depends(require_admin)):
    """
    Remplace intégralement un composant existant (nom, catégorie, specs,
    prix, image, prix de marché), identifié par son ID plutôt que par
    nom+catégorie — contrairement à /api/admin/components (utilisé pour le
    collage en masse), ça permet de renommer un composant ou de changer sa
    catégorie sans créer accidentellement un doublon.
    """
    errors = validate_component(payload, 1)
    if errors:
        return {"status": "error", "message": "Erreurs de validation, rien n'a été modifié.", "errors": errors}

    client = get_client()
    try:
        existing = client.execute("SELECT id FROM components WHERE id = ?", [component_id])
        if not existing.rows:
            raise HTTPException(status_code=404, detail="Composant introuvable.")

        # Un autre composant (pas celui qu'on édite) porte déjà ce nom dans
        # cette catégorie : on refuse plutôt que de fusionner silencieusement
        # deux fiches différentes.
        duplicate = client.execute(
            "SELECT id FROM components WHERE categorie = ? AND nom = ? AND id != ?",
            [payload["categorie"], payload["nom"], component_id],
        )
        if duplicate.rows:
            return {
                "status": "error",
                "message": f"Un autre composant existe déjà sous le nom \"{payload['nom']}\" dans la catégorie \"{payload['categorie']}\".",
            }

        specs_json = json.dumps(payload["specs"], ensure_ascii=False)
        prix_marche_json = json.dumps(payload.get("prix_marche", []), ensure_ascii=False)
        image_url = payload.get("image_url")
        asin = payload.get("asin")
        amazon_details_json = json.dumps(payload.get("caracteristiques_amazon", []), ensure_ascii=False)
        description = payload.get("description")

        client.execute(
            "UPDATE components SET categorie = ?, nom = ?, specs_json = ?, prix_indicatif = ?, "
            "prix_marche_json = ?, image_url = ?, asin = ?, amazon_details_json = ?, description = ? WHERE id = ?",
            [payload["categorie"], payload["nom"], specs_json, payload["prix_indicatif"],
             prix_marche_json, image_url, asin, amazon_details_json, description, component_id],
        )
        return {"status": "ok", "message": "Composant mis à jour."}
    finally:
        client.close()


@app.delete("/api/admin/components/{component_id}")
def admin_delete_component(component_id: int, _admin=Depends(require_admin)):
    """Supprime définitivement un composant. Ne touche pas aux builds qui le référencent déjà (ils afficheront "composant introuvable")."""
    client = get_client()
    try:
        existing = client.execute("SELECT id FROM components WHERE id = ?", [component_id])
        if not existing.rows:
            raise HTTPException(status_code=404, detail="Composant introuvable.")
        client.execute("DELETE FROM components WHERE id = ?", [component_id])
        return {"status": "ok", "message": "Composant supprimé."}
    finally:
        client.close()


@app.delete("/api/admin/components")
def admin_delete_all_components(_admin=Depends(require_admin)):
    """
    Supprime TOUS les composants de la base — action destructive et
    irréversible (utilisée par le bouton "danger" de /admin, avec double
    confirmation côté interface). Les builds déjà sauvegardés qui
    référencent ces composants ne sont pas touchés, ils afficheront juste
    "composant introuvable".
    """
    client = get_client()
    try:
        result = client.execute("SELECT COUNT(*) FROM components")
        count = result.rows[0][0]
        client.execute("DELETE FROM components")
        return {"status": "ok", "deleted": count}
    finally:
        client.close()


@app.post("/api/admin/find-image")
def admin_find_image(payload: dict = Body(...), _admin=Depends(require_admin)):
    """
    Cherche une URL d'image pour un composant via recherche web (groq/compound
    en priorité, Gemini + Google Search en secours si Groq est indisponible
    ou en quota) — même convention que les autres recherches web du projet.
    Ne sauvegarde RIEN — renvoie juste une proposition que l'admin doit
    valider (bouton "Utiliser cette image") avant que /api/admin/components
    ne l'enregistre. Jamais d'image inventée : si aucune des deux recherches
    n'a de source vérifiable, on ne renvoie rien.
    """
    nom = (payload.get("nom") or "").strip()
    categorie = (payload.get("categorie") or "").strip()
    if not nom:
        raise HTTPException(status_code=400, detail="'nom' manquant.")

    prompt = f"""Cherche une image produit officielle (packshot ou photo produit) pour ce composant PC :
"{nom}" (catégorie : {categorie}).

Réponds UNIQUEMENT avec un JSON valide (pas de markdown) de cette forme :
{{"image_url": "<url directe vers un fichier image .jpg/.png/.webp>", "source": "<url de la page où tu as trouvé cette image>"}}

Si tu ne trouves aucune image fiable avec une source vérifiable, réponds avec :
{{"error": "aucune image trouvée avec une source fiable"}}"""

    try:
        result_text = call_groq_compound(prompt, max_tokens=300)
    except Exception as e_groq:
        print(f"Recherche d'image via Groq échouée, tentative Gemini: {e_groq}")
        try:
            result_text = call_gemini_grounded(prompt)
        except Exception as e_gemini:
            raise HTTPException(
                status_code=502,
                detail=f"Recherche d'image échouée (Groq et Gemini indisponibles) : {e_gemini}",
            )

    parsed = parse_ai_json(result_text)
    if parsed is None:
        raise HTTPException(status_code=502, detail=f"Réponse IA invalide : {result_text}")
    if "error" in parsed:
        return {"status": "error", "message": parsed["error"]}
    if not parsed.get("image_url", "").startswith(("http://", "https://")):
        return {"status": "error", "message": "L'IA n'a pas renvoyé d'URL d'image valide."}

    return {"status": "ok", "image_url": parsed["image_url"], "source": parsed.get("source")}


@app.post("/api/admin/find-component-info")
def admin_find_component_info(payload: dict = Body(...), _admin=Depends(require_admin)):
    """
    Assistant "nouveau composant" : à partir d'un simple nom + catégorie,
    cherche sur le web (Groq/compound, puis Gemini + Google Search en
    secours) un brouillon complet — specs, prix, un premier lien de
    revendeur, une image — pour éviter de tout ressaisir à la main.

    Ne sauvegarde RIEN : la proposition doit être relue et validée par
    l'admin dans le formulaire avant d'être enregistrée (même logique que
    /api/admin/find-image). Consigne stricte à l'IA : mettre null plutôt que
    d'inventer une valeur qu'elle ne trouve pas.
    """
    nom = (payload.get("nom") or "").strip()
    categorie = (payload.get("categorie") or "").strip()
    if not nom:
        raise HTTPException(status_code=400, detail="'nom' manquant.")
    if categorie not in REQUIRED_FIELDS:
        raise HTTPException(status_code=400, detail=f"'categorie' invalide. Valeurs valides : {list(REQUIRED_FIELDS.keys())}")

    required_specs = REQUIRED_FIELDS[categorie]
    specs_template = ", ".join(f'"{k}": <{t}>' for k, t in required_specs.items())
    today = datetime.utcnow().date().isoformat()

    prompt = f"""Cherche des informations réelles et vérifiables sur ce composant PC :
"{nom}" (catégorie : {categorie}).

Réponds UNIQUEMENT avec un JSON valide (pas de markdown) de cette forme exacte :
{{
  "prix_indicatif": <prix moyen constaté en euros, nombre, ou null>,
  "specs": {{ {specs_template} }},
  "prix_marche": [{{"vendeur": "<revendeur>", "prix": <nombre>, "lien": "<URL produit réelle>", "date_releve": "{today}"}}],
  "image_url": <URL directe vers une image produit, ou null>,
  "source": "<URL de la page où tu as trouvé ces informations>"
}}

RÈGLES STRICTES :
- N'invente RIEN. Si une information précise n'est pas trouvée de façon fiable, mets sa
  valeur à null plutôt que de deviner (y compris pour un champ de "specs").
- Le champ "specs" doit contenir EXACTEMENT les clés indiquées ci-dessus, avec les bons types
  ("str" = texte, "number" = nombre, "list[str]" = liste de textes).
- "prix_marche" peut être une liste vide si aucun lien de vente vérifiable n'est trouvé.
- Si tu ne trouves RIEN de fiable sur ce composant précis, réponds avec :
  {{"error": "aucune information fiable trouvée pour ce composant"}}"""

    try:
        result_text = call_groq_compound(prompt, max_tokens=700)
    except Exception as e_groq:
        print(f"Recherche d'infos composant via Groq échouée, tentative Gemini: {e_groq}")
        try:
            result_text = call_gemini_grounded(prompt)
        except Exception as e_gemini:
            raise HTTPException(
                status_code=502,
                detail=f"Recherche échouée (Groq et Gemini indisponibles) : {e_gemini}",
            )

    parsed = parse_ai_json(result_text)
    if parsed is None:
        raise HTTPException(status_code=502, detail=f"Réponse IA invalide : {result_text}")
    if "error" in parsed:
        return {"status": "error", "message": parsed["error"]}

    return {
        "status": "ok",
        "prix_indicatif": parsed.get("prix_indicatif"),
        "specs": parsed.get("specs") or {},
        "prix_marche": parsed.get("prix_marche") or [],
        "image_url": parsed.get("image_url"),
        "source": parsed.get("source"),
    }


# Mots-clés (accents normalisés) à chercher dans les libellés "Détails du
# produit" d'Amazon, par (catégorie, champ) — UNIQUEMENT pour les champs de
# type "str" dans schema.REQUIRED_FIELDS. Les champs "number" et "list[str]"
# (tdp, wattage, m2_slots, sata_ports, et TOUTES les dimensions en mm) ne
# sont JAMAIS déduits d'Amazon, quelle que soit la catégorie : ce sont
# exactement les champs où une valeur imprécise (ex: dimensions du COLIS
# plutôt que du produit) créerait un faux "compatible" dangereux.
AMAZON_SPEC_KEYWORDS = {
    ("CPU", "socket"): ["socket"],
    ("Carte mère", "socket"): ["socket"],
    ("Carte mère", "ram_type"): ["type de memoire", "technologie de memoire compatible", "memoire compatible"],
    ("Carte mère", "format"): ["facteur de forme"],
    ("RAM", "type"): ["generation de memoire", "technologie de memoire vive", "technologie de memoire ram", "type de memoire"],
    ("Stockage", "type"): ["interface", "type de connexion", "type de memoire flash"],
}


def _strip_accents(text):
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def derive_specs_from_amazon(categorie, caracteristiques_amazon):
    """
    Pré-remplit UNIQUEMENT les champs "str" requis pour cette catégorie
    (schema.REQUIRED_FIELDS) à partir du tableau "Détails du produit"
    d'Amazon, en cherchant des libellés connus. Ne renvoie jamais un champ
    "number" ou "list[str]" — voir AMAZON_SPEC_KEYWORDS ci-dessus. Un champ
    non trouvé (ou dont la valeur ne ressemble pas à ce qu'on attend, ex:
    "type" de Stockage qui doit être NVMe/SATA) est simplement absent du
    résultat, à compléter à la main comme avant.
    """
    required = REQUIRED_FIELDS.get(categorie, {})
    str_fields = [field for field, expected_type in required.items() if expected_type == "str"]
    if not str_fields or not caracteristiques_amazon:
        return {}

    normalized_details = [
        (_strip_accents(entry["type"]).lower(), entry["value"])
        for entry in caracteristiques_amazon
        if entry.get("type") and entry.get("value")
    ]

    derived = {}
    for field in str_fields:
        keywords = AMAZON_SPEC_KEYWORDS.get((categorie, field))
        if not keywords:
            continue
        for label, value in normalized_details:
            if any(keyword in label for keyword in keywords):
                if categorie == "Stockage" and field == "type":
                    normalized_value = _strip_accents(value).upper()
                    if "NVME" in normalized_value:
                        derived[field] = "NVMe"
                    elif "SATA" in normalized_value:
                        derived[field] = "SATA"
                    continue
                if categorie == "RAM" and field == "type" and "ddr" not in _strip_accents(value).lower():
                    continue
                derived[field] = value.strip()
                break

    return derived


def clean_name_and_specs_with_ai(categorie, nom_brut, marque, caracteristiques_amazon, description, missing_fields):
    """
    Un seul appel IA qui fait deux choses à partir des données Amazon déjà
    récupérées (titre, description, détails produit) — AUCUNE recherche web,
    juste de l'extraction/reformulation de texte sur des données qu'on a
    déjà. Utilise call_ai_model() (Groq qwen, repli Gemini SANS recherche)
    plutôt que call_groq_compound/call_gemini_grounded : ça reste utilisable
    même quand le quota de recherche web est à zéro, puisqu'il n'y a
    justement aucune recherche à faire.

    1. Propose un nom de produit court ("nom_propre") — le titre Amazon brut
       est souvent bourré de mots-clés SEO ("Corsair Mémoire de Bureau
       Corsair Vengeance LPX 64 Go DDR4 3200 C16 1,35 V") ; l'IA en tire
       juste "Marque + Gamme + caractéristique principale".
    2. Déduit les champs techniques encore manquants après
       derive_specs_from_amazon (missing_fields), le cas échéant.

    Toujours un brouillon à valider avant enregistrement, comme le reste de
    cette page — si l'IA se trompe (notamment sur une dimension physique,
    ou un nom mal résumé), l'admin le voit et corrige avant "Enregistrer".
    Retourne (nom_propre_ou_None, dict_des_specs_deduites).
    """
    details_text = "\n".join(
        f"- {d['type']} : {d['value']}"
        for d in (caracteristiques_amazon or [])
        if d.get("type") and d.get("value")
    ) or "aucun"
    champs_text = (
        "\n".join(f'- "{field}" ({expected_type})' for field, expected_type in missing_fields.items())
        if missing_fields else "(aucun, tous déjà connus)"
    )

    prompt = f"""Voici les informations réelles trouvées sur Amazon pour ce composant PC (catégorie : {categorie}) :

Titre Amazon brut : {nom_brut or "inconnu"}
Marque : {marque or "inconnue"}
Description : {description or "aucune"}

Détails produit Amazon :
{details_text}

TÂCHE 1 : propose un nom de produit court et propre, au format "Marque + Gamme/Modèle + caractéristique
principale" (ex: "Corsair Vengeance LPX 64 Go DDR4 3200", "ASUS ROG Strix X870E-E Gaming WiFi"). Retire tout
le superflu : mention de catégorie générique ("Mémoire de Bureau", "Carte mère Gaming AMD Ryzen..."),
tension, latence CAS, garantie, contenu de la boîte, etc. Ne mentionne PAS la couleur (c'est un champ séparé).
Mets ce texte dans le champ "nom_propre".

TÂCHE 2 : à partir UNIQUEMENT des informations ci-dessus (n'invente rien, ne cherche rien d'autre), déduis la
valeur de ces champs techniques :
{champs_text}

RÈGLES STRICTES :
- Si une information demandée en tâche 2 n'est pas clairement présente ci-dessus, réponds null pour ce champ
  plutôt que de deviner.
- Pour toute dimension physique en mm : n'utilise QUE des informations qui décrivent explicitement le
  produit lui-même, JAMAIS des dimensions d'expédition/de colis/d'emballage. Au moindre doute, réponds null.
- Réponds UNIQUEMENT avec un objet JSON valide (pas de markdown) de la forme
  {{"nom_propre": "...", "champ1": ... }}"""

    try:
        result_text = call_ai_model(prompt)
    except Exception as error:
        print(f"Nettoyage IA du nom / déduction des specs échoué (non bloquant) : {error}")
        return None, {}

    parsed = parse_ai_json(result_text)
    if not isinstance(parsed, dict):
        return None, {}

    nom_propre = parsed.get("nom_propre")
    nom_propre = nom_propre.strip() if isinstance(nom_propre, str) and nom_propre.strip() else None

    derived = {}
    for field, expected_type in missing_fields.items():
        value = parsed.get(field)
        if value is None:
            continue
        if expected_type == "number" and isinstance(value, (int, float)):
            derived[field] = value
        elif expected_type == "str" and isinstance(value, str) and value.strip():
            derived[field] = value.strip()
        elif expected_type == "list[str]" and isinstance(value, list) and all(isinstance(v, str) for v in value):
            derived[field] = value

    return nom_propre, derived


# Mots de couleur courants (français + anglais, tel qu'on les trouve dans un
# titre de produit) — utilisé uniquement en dernier recours si Amazon ne
# précise pas de champ "Couleur" explicite dans les détails produit.
COLOR_KEYWORDS = {
    "noir": "Noir", "black": "Noir",
    "blanc": "Blanc", "blanche": "Blanc", "white": "Blanc",
    "rouge": "Rouge", "red": "Rouge",
    "gris": "Gris", "grise": "Gris", "grey": "Gris", "gray": "Gris",
    "bleu": "Bleu", "bleue": "Bleu", "blue": "Bleu",
    "rose": "Rose", "pink": "Rose",
    "argent": "Argent", "silver": "Argent",
    "vert": "Vert", "verte": "Vert", "green": "Vert",
    "violet": "Violet", "purple": "Violet",
    "rgb": "RGB",
}


def derive_color_from_amazon(nom, caracteristiques_amazon):
    """
    Déduit la couleur d'un produit — purement informatif (aide à composer un
    montage esthétiquement cohérent, tout noir ou tout blanc), jamais utilisé
    pour la compatibilité. Contrairement aux champs de derive_specs_from_amazon,
    Amazon ne précise pas toujours un champ "Couleur" explicite (surtout
    quand le produit n'existe qu'en une seule couleur) : on tente d'abord le
    tableau de détails, puis on cherche un mot de couleur directement dans le
    titre en dernier recours — une déduction imparfaite ici n'a aucune
    conséquence fonctionnelle, contrairement aux specs de compatibilité.
    """
    for entry in caracteristiques_amazon or []:
        label = _strip_accents(str(entry.get("type") or "")).lower()
        if "couleur" in label or "color" in label:
            value = str(entry.get("value") or "").strip()
            if value:
                return value

    normalized_nom = _strip_accents(nom or "").lower()
    for keyword, label in COLOR_KEYWORDS.items():
        if re.search(rf"\b{keyword}\b", normalized_nom):
            return label

    return None



# Marqueurs qui introduisent typiquement, dans un titre Amazon, une
# description générique ou un détail secondaire plutôt que le nom du
# produit lui-même — on coupe au premier trouvé (celui qui apparaît le plus
# tôt dans le titre), quel qu'il soit.
_TITLE_CUT_MARKERS = [
    r"\s+[-–—]\s+",              # tiret entouré d'espaces
    r"\s+[Jj]usqu['’]?\s*[aà]\s+",    # "Jusqu'à" / "jusqu a"
]


def clean_amazon_title(titre):
    """
    Simplifie un titre Amazon (souvent une longue phrase marketing) en un nom
    de produit plus court et lisible : retire le contenu entre parenthèses
    (généralement une liste de caractéristiques, ex: "(DDR5, 5 x M.2, WiFi
    7...)"), puis coupe au premier marqueur de _TITLE_CUT_MARKERS rencontré
    (tiret introduisant une description générique de catégorie, ex: "... –
    Carte mère Gaming AMD Ryzen AM5 ATX", ou qualificatif du type "Jusqu'à
    3200MHz C16").
    """
    if not titre:
        return titre
    sans_parentheses = re.sub(r"\s*\([^)]*\)", "", titre)

    cut_at = len(sans_parentheses)
    for pattern in _TITLE_CUT_MARKERS:
        match = re.search(pattern, sans_parentheses)
        if match and match.start() < cut_at:
            cut_at = match.start()

    return sans_parentheses[:cut_at].strip()


def build_component_name(nom_brut, marque):
    """
    Construit un nom de composant lisible : titre Amazon nettoyé
    (clean_amazon_title), préfixé par la marque si elle n'y figure pas déjà
    — "Marque + Modèle", plutôt que la phrase marketing complète d'Amazon.
    La couleur n'est volontairement pas ajoutée ici : elle reste un champ
    spec séparé ("couleur"), pas une répétition dans le nom.
    """
    nom = clean_amazon_title(nom_brut) or nom_brut or ""
    if marque and marque.lower() not in nom.lower():
        nom = f"{marque} {nom}".strip()
    return nom


class FetchAsinRequest(BaseModel):
    asin: str
    categorie: str | None = None


@app.post("/api/admin/fetch-asin")
def admin_fetch_asin(request: FetchAsinRequest, _admin=Depends(require_admin)):
    """
    Récupère nom/marque/prix/image/disponibilité pour un ASIN (ou une URL
    Amazon complète) via Bright Data. Ne sauvegarde RIEN — l'admin doit
    relire et valider dans le formulaire avant d'enregistrer.

    Si `categorie` est fournie, pré-remplit aussi les champs de specs "str"
    qu'on peut déduire avec confiance des détails produit Amazon (type de
    mémoire, socket, format...) — voir derive_specs_from_amazon(). Les
    champs numériques et dimensions restent TOUJOURS à saisir à la main,
    Amazon n'étant pas fiable dessus (dimensions du colis, pas du produit).

    L'image récupérée est automatiquement détourée (service rembg
    auto-hébergé) avant d'être renvoyée. Si le détourage échoue, on garde
    l'image d'origine plutôt que de faire échouer toute la récupération
    pour un problème purement cosmétique.
    """
    asin = extract_asin_from_input(request.asin)
    if not asin:
        raise HTTPException(
            status_code=400,
            detail="ASIN invalide : attendu 10 caractères alphanumériques, ou une URL Amazon contenant /dp/<ASIN>.",
        )

    t0 = time.time()
    try:
        info = fetch_amazon_product(asin)
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error))
    print(f"[fetch-asin] Bright Data : {time.time() - t0:.1f}s")

    missing_fields = {}
    if request.categorie in REQUIRED_FIELDS:
        specs = derive_specs_from_amazon(request.categorie, info.get("caracteristiques_amazon") or [])
        missing_fields = {
            field: expected_type
            for field, expected_type in REQUIRED_FIELDS[request.categorie].items()
            if field not in specs
        }

    def _run_ai():
        # Un seul appel IA pour le nom nettoyé + les specs encore
        # manquantes (jamais de recherche web, juste de la reformulation
        # sur les données Amazon déjà récupérées ci-dessus).
        if request.categorie not in REQUIRED_FIELDS:
            return None, {}
        return clean_name_and_specs_with_ai(
            request.categorie, info.get("nom"), info.get("marque"),
            info.get("caracteristiques_amazon") or [], info.get("description"),
            missing_fields,
        )

    def _run_bg_removal():
        if not info.get("image_url"):
            return None, None
        try:
            return remove_background(info["image_url"]), None
        except RuntimeError as error:
            return None, str(error)

    # L'appel IA et le détourage d'image sont indépendants l'un de l'autre
    # (tous deux ne dépendent que des données Bright Data déjà récupérées
    # ci-dessus) — les lancer en parallèle plutôt qu'en série évite d'ajouter
    # betement leurs deux durées l'une à l'autre.
    t1 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        ai_future = executor.submit(_run_ai)
        bg_future = executor.submit(_run_bg_removal)
        ai_nom_propre, ai_specs = ai_future.result()
        new_image_url, bg_error = bg_future.result()
    print(f"[fetch-asin] IA + détourage (en parallèle) : {time.time() - t1:.1f}s")

    if request.categorie in REQUIRED_FIELDS:
        specs.update(ai_specs)
        info["specs"] = specs

    couleur = derive_color_from_amazon(info.get("nom"), info.get("caracteristiques_amazon") or [])
    if couleur:
        info.setdefault("specs", {})["couleur"] = couleur

    info["nom"] = ai_nom_propre or build_component_name(info.get("nom"), info.get("marque"))

    if new_image_url:
        info["image_url"] = new_image_url
    if bg_error:
        info["bg_removal_error"] = bg_error

    print(f"[fetch-asin] TOTAL : {time.time() - t0:.1f}s")
    return {"status": "ok", **info}


@app.post("/api/admin/refresh-prices")
def admin_refresh_prices(_admin=Depends(require_admin)):
    """
    Rafraîchit prix + image + relevé "Amazon" pour tous les composants ayant
    un ASIN renseigné. Ne touche JAMAIS aux relevés des autres revendeurs
    (LDLC, Materiel.net...) : seul le relevé dont vendeur == "Amazon" est
    remplacé ou ajouté. Envoie tous les ASIN en UNE seule collecte Bright
    Data (plutôt qu'un appel par composant) : c'est ce que permet leur API
    par lots, et ça évite d'attendre une collecte asynchrone par composant.
    """
    client = get_client()
    try:
        result = client.execute(
            "SELECT id, nom, asin, prix_marche_json, image_url FROM components "
            "WHERE asin IS NOT NULL AND asin != ''"
        )
        rows = result.rows
    finally:
        client.close()

    if not rows:
        return {"status": "ok", "updated": 0, "errors": [], "message": "Aucun composant avec un ASIN renseigné."}

    items = [{"url": f"https://www.amazon.{AMAZON_DOMAIN_TLD}/dp/{row[2]}"} for row in rows]

    try:
        # Une grosse collecte prend plus de temps qu'un seul produit : délai
        # plus généreux qu'un fetch-asin individuel (90s).
        results = _brightdata_scrape_sync(items, timeout=280)
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=f"Rafraîchissement échoué : {error}")

    # Indexés par ASIN pour rattacher chaque résultat au bon composant —
    # Bright Data ne garantit pas de renvoyer les résultats dans le même
    # ordre que les items envoyés. Le champ "asin" n'étant pas garanti dans
    # la réponse, on retombe sur l'ASIN extrait de l'URL renvoyée.
    results_by_asin = {}
    for result_item in (results or []):
        item_asin = _find_field_recursive(result_item, ["asin"])
        if not isinstance(item_asin, str):
            item_url = _find_field_recursive(result_item, ["url", "link"])
            item_asin = extract_asin_from_input(item_url) if isinstance(item_url, str) else None
        if isinstance(item_asin, str):
            results_by_asin[item_asin.upper()] = result_item

    updated = 0
    errors = []
    client = get_client()
    try:
        for row in rows:
            component_id, nom, asin, prix_marche_json, image_url = row[0], row[1], row[2], row[3], row[4]

            result_item = results_by_asin.get(asin.upper())
            if result_item is None:
                errors.append(f"{nom} ({asin}) : aucun résultat renvoyé par Bright Data.")
                continue

            info = _normalize_brightdata_item(result_item, asin)

            try:
                prix_marche = json.loads(prix_marche_json) if prix_marche_json else []
            except (TypeError, json.JSONDecodeError):
                prix_marche = []

            prix_marche = [p for p in prix_marche if p.get("vendeur") != "Amazon"]
            if info.get("prix") is not None:
                prix_marche.append({
                    "vendeur": "Amazon",
                    "prix": info["prix"],
                    "lien": info.get("lien"),
                    "date_releve": datetime.utcnow().date().isoformat(),
                })
            else:
                errors.append(f"{nom} ({asin}) : prix introuvable dans la réponse Bright Data.")

            new_image_url = image_url
            if info.get("image_url"):
                # Détourage automatique — seulement sur une image FRAÎCHEMENT
                # récupérée depuis Amazon (une data URL déjà détourée n'est
                # de toute façon pas une URL récupérable par le service).
                try:
                    new_image_url = remove_background(info["image_url"])
                except RuntimeError as error:
                    new_image_url = info["image_url"]
                    errors.append(f"{nom} ({asin}) : détourage échoué ({error}), image originale conservée.")

            client.execute(
                "UPDATE components SET prix_marche_json = ?, image_url = ? WHERE id = ?",
                [json.dumps(prix_marche, ensure_ascii=False), new_image_url, component_id],
            )
            updated += 1
    finally:
        client.close()

    return {"status": "ok", "updated": updated, "errors": errors}


class RemoveBackgroundRequest(BaseModel):
    image_url: str


@app.post("/api/admin/remove-background")
def admin_remove_background(request: RemoveBackgroundRequest, _admin=Depends(require_admin)):
    """
    Retire l'arrière-plan d'une image produit (via Poof.bg). Ne sauvegarde
    RIEN — renvoie juste la version détourée pour que l'admin la voie et
    clique "Utiliser cette image" avant qu'elle ne soit enregistrée (même
    convention que les autres assistants IA de cette page).
    """
    if not is_safe_external_url(request.image_url):
        raise HTTPException(status_code=400, detail="URL d'image publique valide requise.")

    try:
        image_data_url = remove_background(request.image_url)
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error))

    return {"status": "ok", "image_data_url": image_data_url}


MAX_AI_ATTEMPTS = 3


def call_ai_model(prompt):
    """Appelle Groq (primaire) puis Gemini (fallback) avec le prompt donné. Retourne le texte brut."""
    try:
        if groq_client is None:
            raise RuntimeError("GROQ_API_KEY absente")
        message = groq_client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=800,
            reasoning_effort="low",  # un peu de réflexion pour respecter le budget correctement
        )
        return message.choices[0].message.content
    except Exception as e_groq:
        print(f"Groq échoué, fallback Gemini: {e_groq}")
        if genai is None or not GEMINI_API_KEY:
            raise RuntimeError("Groq et Gemini ne sont pas configurés") from e_groq
        model = genai.GenerativeModel("gemini-3.5-flash-lite")
        response = model.generate_content(prompt)
        return response.text


def call_groq_compound(prompt, max_tokens=400):
    """
    Appelle groq/compound (recherche web réelle). Si Groq répond qu'on est
    seulement temporairement rate-limité (quota par minute, pas par jour —
    Groq indique lui-même le délai avant que ça se libère), on retente UNE
    fois après avoir attendu ce délai plutôt que d'échouer immédiatement :
    en pratique cette limite se lève en quelques secondes. Sans ça, plusieurs
    fonctionnalités du site (vérification IA, FPS, recherche d'image...)
    partagent le même quota Groq et se bloquent mutuellement pour rien.
    """
    if groq_client is None:
        raise RuntimeError("GROQ_API_KEY absente")

    def _call():
        response = groq_client.chat.completions.create(
            model="groq/compound",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content

    try:
        return _call()
    except Exception as error:
        message = str(error)
        if "rate_limit_exceeded" not in message and "429" not in message:
            raise
        match = re.search(r"try again in ([\d.]+)s", message)
        wait_seconds = min(float(match.group(1)), 20) + 0.5 if match else 5
        print(f"Groq temporairement rate-limité, nouvel essai dans {wait_seconds:.1f}s...")
        time.sleep(wait_seconds)
        return _call()


def call_gemini_grounded(prompt):
    """
    Fallback de call_groq_compound : recherche web via Gemini + Google
    Search. Essaie chaque projet Gemini configuré (GEMINI_API_KEY,
    GEMINI_API_KEY_2, GEMINI_API_KEY_3...) l'un après l'autre — le quota
    gratuit de recherche est par PROJET, pas par site, donc si le premier
    est épuisé pour la journée on passe directement au suivant plutôt que
    d'échouer, jusqu'à ce que le premier récupère son quota le lendemain.
    """
    if genai_new is None:
        raise RuntimeError("Gemini (nouveau SDK) non disponible")
    if not GEMINI_API_KEYS:
        raise RuntimeError("Aucune clé Gemini configurée")

    last_error = None
    for api_key in GEMINI_API_KEYS:
        try:
            gemini_client = genai_new.Client(api_key=api_key)
            gemini_response = gemini_client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())]
                ),
            )
            return gemini_response.text
        except Exception as error:
            last_error = error
            print(f"Projet Gemini indisponible, tentative suivante : {error}")

    raise last_error


def _normalize_key(key):
    return str(key).lower().replace("_", "").replace("-", "")


def _find_field_recursive(data, candidate_keys, _depth=0, _matches=None):
    """
    Cherche récursivement, dans un JSON de forme quelconque, la valeur dont
    la clé correspond à l'un des noms candidats (comparaison insensible à la
    casse, tirets/underscores ignorés). Nécessaire car la forme exacte des
    réponses des fournisseurs Amazon n'est pas documentée publiquement —
    plutôt que de supposer un schéma fixe qui casserait au moindre
    changement, on cherche le champ où qu'il soit dans l'objet.

    Priorité : si plusieurs candidats correspondent à des endroits
    différents de l'objet, c'est le PREMIER de candidate_keys qui gagne (ex:
    on préfère toujours "final_price" à "initial_price" si les deux sont
    présents). Retourne None si rien n'est trouvé.
    """
    top_level = _matches is None
    if top_level:
        _matches = {}

    if _depth <= 8:
        if isinstance(data, dict):
            for key, value in data.items():
                nk = _normalize_key(key)
                if nk not in _matches and value not in (None, "", [], {}):
                    _matches[nk] = value
            for value in data.values():
                _find_field_recursive(value, candidate_keys, _depth + 1, _matches)
        elif isinstance(data, list):
            for item in data:
                _find_field_recursive(item, candidate_keys, _depth + 1, _matches)

    if not top_level:
        return None

    for key in candidate_keys:
        nk = _normalize_key(key)
        if nk in _matches:
            return _matches[nk]
    return None


def parse_amazon_price(raw):
    """
    Parseur de prix tolérant : accepte un nombre, une chaîne ("299,99 €",
    "$1,299.99"), ou un objet imbriqué ({"value": 299.99} ou
    {"displayString": "..."}). Retourne None si rien d'exploitable — jamais
    de valeur inventée.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, dict):
        for key in ("value", "amount", "displayString", "display", "raw", "price"):
            if key in raw:
                parsed = parse_amazon_price(raw[key])
                if parsed is not None:
                    return parsed
        return None
    if isinstance(raw, str):
        cleaned = re.sub(r"[^\d,.\-]", "", raw)
        if not cleaned:
            return None
        # "299,99" (virgule décimale FR) vs "1,299.99" (virgule = séparateur
        # de milliers) : si les deux séparateurs sont présents, la virgule
        # est forcément un séparateur de milliers à supprimer.
        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def extract_asin_from_input(raw):
    """
    Accepte soit un ASIN nu (10 caractères alphanumériques), soit une URL
    Amazon complète (on extrait le code après /dp/ ou /gp/product/). Retourne
    None si rien de valide n'est trouvé.
    """
    raw = (raw or "").strip()
    match = re.search(r"/(?:dp|gp/product)/([A-Za-z0-9]{10})", raw)
    if match:
        return match.group(1).upper()
    if re.fullmatch(r"[A-Za-z0-9]{10}", raw):
        return raw.upper()
    return None


def _brightdata_scrape_sync(urls, timeout):
    """
    Appelle le dataset "Amazon Products" de Bright Data en mode SYNCHRONE
    (endpoint /datasets/v3/scrape, mode "temps réel" du tableau de bord) :
    une seule requête, les résultats reviennent directement dans la
    réponse — pas de déclenchement + attente séparée nécessaire pour ce
    dataset précis. urls : liste de dicts {"url": "https://www.amazon..."}.
    """
    try:
        response = requests.post(
            "https://api.brightdata.com/datasets/v3/scrape",
            params={"dataset_id": BRIGHTDATA_AMAZON_DATASET_ID, "notify": "false", "include_errors": "true"},
            headers={"Authorization": f"Bearer {BRIGHTDATA_API_TOKEN}", "Content-Type": "application/json"},
            json={"input": urls},
            timeout=timeout,
        )
    except requests.exceptions.Timeout:
        raise RuntimeError("Délai dépassé en contactant Bright Data (problème réseau).")
    except requests.exceptions.RequestException as error:
        raise RuntimeError(f"Erreur réseau en contactant Bright Data : {error}")

    if response.status_code == 401:
        raise RuntimeError("Jeton API Bright Data invalide (401).")
    if not response.ok:
        raise RuntimeError(f"Bright Data a répondu une erreur ({response.status_code}) : {response.text[:300]}")

    try:
        return response.json()
    except ValueError:
        raise RuntimeError("Réponse Bright Data invalide (pas du JSON).")


def _normalize_brightdata_item(item, asin):
    """
    Normalise un item de résultat Bright Data (forme non documentée
    publiquement, d'où l'extraction tolérante) en dict {nom, marque, prix,
    image_url, disponibilite, lien}. NE renvoie AUCUNE spec technique :
    Amazon n'a pas de champ fiable pour socket/tdp/etc., et ses "dimensions
    produit" sont en réalité les dimensions du COLIS, pas du composant —
    jamais utilisables pour gpu_max_length_mm ou cpu_cooler_max_height_mm
    sous peine de créer un faux "compatible" pour du matériel qui ne rentre
    pas.
    """
    nom = _find_field_recursive(item, ["title", "name", "productTitle"])
    marque = _find_field_recursive(item, ["brand", "manufacturer", "brandName"])
    prix_raw = _find_field_recursive(item, ["final_price", "price", "initial_price", "currentPrice"])
    disponibilite = _find_field_recursive(item, ["availability", "inStock", "stockStatus", "availabilityStatus"])
    lien = _find_field_recursive(item, ["url", "link", "productUrl"])

    image_url = _find_field_recursive(item, ["image_url", "imageUrl", "main_image", "image", "images", "thumbnail"])
    if isinstance(image_url, list) and image_url:
        image_url = image_url[0]
    if isinstance(image_url, dict):
        image_url = image_url.get("url") or image_url.get("link") or image_url.get("value")
    if not isinstance(image_url, str):
        image_url = None

    fallback_lien = f"https://www.amazon.{AMAZON_DOMAIN_TLD}/dp/{asin}"

    # Tableau "Détails du produit" d'Amazon (mémoire, socket, etc. selon la
    # catégorie) — une vraie donnée fournie par le fabricant, PAS les
    # "dimensions produit" (qui sont celles du colis). Affiché comme simple
    # référence pour l'admin, jamais écrit automatiquement dans les specs :
    # les libellés varient trop d'une fiche à l'autre pour être mappés de
    # façon fiable sur nos champs (socket, tdp...) sans risque d'erreur.
    caracteristiques_amazon = []
    seen_types = set()
    raw_details = item.get("product_details") if isinstance(item, dict) else None
    if isinstance(raw_details, list):
        for entry in raw_details:
            if not isinstance(entry, dict):
                continue
            detail_type = entry.get("type")
            detail_value = entry.get("value")
            if not detail_type or not detail_value or detail_type in seen_types:
                continue
            seen_types.add(detail_type)
            caracteristiques_amazon.append({"type": str(detail_type), "value": str(detail_value)})

    # "description" est un vrai texte descriptif du produit (contrairement à
    # "product_description"/"from_the_brand", qui sont en réalité des listes
    # d'images du contenu enrichi Amazon, pas du texte).
    description = _find_field_recursive(item, ["description"])

    return {
        "asin": asin,
        "nom": nom if isinstance(nom, str) else None,
        "marque": marque if isinstance(marque, str) else None,
        "prix": parse_amazon_price(prix_raw),
        "image_url": image_url,
        "disponibilite": disponibilite if isinstance(disponibilite, (str, bool)) else None,
        "lien": lien if isinstance(lien, str) else fallback_lien,
        "caracteristiques_amazon": caracteristiques_amazon,
        "description": description if isinstance(description, str) else None,
    }


def fetch_amazon_product(asin, timeout=90):
    """
    Récupère nom/marque/prix/image/disponibilité pour un ASIN via le dataset
    "Amazon Products" de Bright Data en mode synchrone (5000 requêtes
    gratuites/mois, jamais de scraping fait par ce serveur lui-même — Bright
    Data collecte et renvoie des données déjà structurées).
    """
    if not BRIGHTDATA_API_TOKEN:
        raise RuntimeError("BRIGHTDATA_API_TOKEN absente")

    url = f"https://www.amazon.{AMAZON_DOMAIN_TLD}/dp/{asin}"
    results = _brightdata_scrape_sync([{"url": url}], timeout)

    if not results:
        raise RuntimeError(f"Aucun résultat renvoyé par Bright Data pour l'ASIN {asin}.")
    item = results[0] if isinstance(results, list) else results

    info = _normalize_brightdata_item(item, asin)
    info["_raw_preview"] = json.dumps(item, ensure_ascii=False)[:1500]
    return info


def remove_background(image_url):
    """
    Retire l'arrière-plan d'une image produit via un service auto-hébergé
    (rembg, sur un VM Oracle Cloud personnel) — gratuit et illimité,
    contrairement à un service en ligne payant au-delà d'un quota mensuel.
    Renvoie une data URL (data:image/png;base64,...) plutôt qu'un lien
    externe : le site n'a pas de stockage de fichiers permanent (le disque
    du serveur ne survit pas à un redéploiement), donc l'image traitée est
    encodée directement dans le champ image_url en base.
    """
    if not REMBG_SERVICE_URL or not REMBG_API_KEY:
        raise RuntimeError("REMBG_SERVICE_URL / REMBG_API_KEY absente(s)")

    try:
        response = requests.post(
            f"{REMBG_SERVICE_URL}/remove-background",
            headers={"X-API-Key": REMBG_API_KEY, "Content-Type": "application/json"},
            json={"image_url": image_url},
            timeout=60,
        )
    except requests.exceptions.Timeout:
        raise RuntimeError("Délai dépassé en contactant le service de détourage (problème réseau).")
    except requests.exceptions.RequestException as error:
        raise RuntimeError(f"Erreur réseau en contactant le service de détourage : {error}")

    if response.status_code == 401:
        raise RuntimeError("Clé API du service de détourage invalide (401).")
    if not response.ok:
        raise RuntimeError(f"Le service de détourage a répondu une erreur ({response.status_code}) : {response.text[:200]}")

    encoded = base64.b64encode(response.content).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def parse_ai_json(suggestion_text):
    """
    Cherche la première accolade ouvrante et décode uniquement le premier objet
    JSON valide à partir de là. Contrairement à une regex gourmande, ça ignore
    proprement tout ce que l'IA peut ajouter après (explications, raisonnement).
    Retourne None si aucun JSON valide n'a pu être extrait.
    """
    start = suggestion_text.find("{")
    if start == -1:
        return None
    try:
        parsed, _ = json.JSONDecoder().raw_decode(suggestion_text[start:])
        return parsed
    except json.JSONDecodeError:
        return None


def compute_real_total(suggestion_json, components_by_id):
    """
    Recalcule le prix total réel à partir des prix stockés en base — jamais
    confiance dans un total que l'IA pourrait annoncer elle-même.
    """
    fields = ("cpu_id", "motherboard_id", "ram_id", "gpu_id", "psu_id", "storage_id", "case_id")
    total = 0.0
    for field in fields:
        component = components_by_id.get(suggestion_json.get(field))
        if component:
            total += float(component["prix_indicatif"] or 0)
    return total


# Anti-abus sur les routes publiques qui consomment du quota Groq/Gemini
# partagé (chaque suggestion peut déjà déclencher jusqu'à 3 tentatives + 1
# vérification web) — sans ce garde-fou, une seule personne qui spam le
# bouton peut épuiser le quota pour tous les visiteurs du site. Compteur en
# mémoire (pas de nouvelle dépendance) : suffisant pour un seul processus,
# ce qui correspond au déploiement actuel.
_last_ai_request_by_ip = {}
AI_RATE_LIMIT_SECONDS = 15


def enforce_ai_rate_limit(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    last = _last_ai_request_by_ip.get(client_ip, 0)
    elapsed = now - last
    if elapsed < AI_RATE_LIMIT_SECONDS:
        wait = round(AI_RATE_LIMIT_SECONDS - elapsed)
        raise HTTPException(
            status_code=429,
            detail=f"Trop de demandes à l'assistant IA depuis cette adresse. Réessaie dans {wait}s.",
        )
    _last_ai_request_by_ip[client_ip] = now


@app.post("/suggest-config")
def suggest_config(request: SuggestConfigRequest, _rate_limit=Depends(enforce_ai_rate_limit)):
    """Route IA : suggère une config basée sur la description utilisateur"""
    try:
        # Récupère tous les composants
        components = get_all_components()
        if not components:
            return {"status": "error", "message": "Aucun composant disponible"}

        components_by_id = {c["id"]: c for c in components}

        # Crée le prompt — l'ID de chaque composant DOIT être visible ici,
        # sinon l'IA ne peut que deviner/halluciner des IDs, ce qui donne des
        # suggestions rejetées à tort par verify_compatibility.
        components_list = "\n".join([
            f"- id {c['id']}: [{c['categorie']}] {c['nom']} (specs: {c['specs_json']}, {c['prix_indicatif']}€)"
            for c in components
        ])

        base_prompt = f"""Tu es un expert en configuration PC. L'utilisateur décrit son besoin en langage naturel.
Suggère une configuration complète en JSON strict (pas de markdown, juste du JSON valide).

Composants disponibles (utilise EXACTEMENT les "id" indiqués ci-dessous, ne les invente jamais) :
{components_list}

Besoin utilisateur: {request.user_input}

RÈGLES IMPORTANTES :
- Si l'utilisateur mentionne un budget, indique-le dans le champ "budget_max" (nombre, en euros)
  et la somme des prix des 7 composants choisis ne doit JAMAIS dépasser ce budget. Si aucune
  combinaison compatible ne rentre dans ce budget avec les composants disponibles, ne force pas
  une config trop chère : réponds plutôt avec {{"error": "explication claire de pourquoi ça ne
  rentre pas dans le budget"}}.
- Si l'utilisateur ne mentionne aucun budget, mets "budget_max": null.
- Adapte vraiment le choix à l'USAGE décrit (gaming, montage vidéo, bureautique, etc.), pas
  juste au budget : ne prends pas systématiquement les composants les moins chers si l'usage
  demande plus de performance, et ne prends pas les plus chers si l'usage ne le justifie pas.
- Si la demande est trop vague pour choisir intelligemment (aucun usage, aucun budget, aucun
  indice), réponds avec {{"error": "demande de précisions à l'utilisateur sur l'usage ou le budget"}}
  plutôt que de deviner au hasard.

Réponds UNIQUEMENT avec un JSON valide de cette forme, où chaque valeur d'id est l'"id" réel
d'un composant pris dans la liste ci-dessus (pas un numéro de ligne, pas un exemple) :
{{"cpu_id": <id réel>, "motherboard_id": <id réel>, "ram_id": <id réel>, "gpu_id": <id réel>, "psu_id": <id réel>, "storage_id": <id réel>, "case_id": <id réel>, "budget_max": <nombre ou null>}}"""

        # Boucle de correction : si la suggestion est incompatible ou dépasse le
        # budget, on renvoie les erreurs précises à l'IA pour qu'elle corrige,
        # jusqu'à MAX_AI_ATTEMPTS tentatives — jamais de confiance aveugle dans
        # l'IA, ni pour la compatibilité ni pour le respect du budget (le total
        # réel est toujours recalculé côté serveur à partir des prix en base).
        current_prompt = base_prompt
        suggestion_json = None
        last_errors = None

        for attempt in range(1, MAX_AI_ATTEMPTS + 1):
            suggestion_text = call_ai_model(current_prompt)

            parsed = parse_ai_json(suggestion_text)
            if parsed is None:
                return {"status": "error", "message": f"IA a renvoyé du JSON invalide: {suggestion_text}"}

            # Si l'IA ne peut pas produire une config (ex: aucun composant ne
            # correspond à la demande), elle répond avec un champ "error" au lieu
            # du schéma attendu. On relaie ce message tel quel plutôt que de
            # tomber sur "champs manquants", moins clair pour l'utilisateur.
            if isinstance(parsed, dict) and "error" in parsed:
                return {"status": "error", "message": parsed["error"]}

            compatibility_result = verify_compatibility(parsed)
            errors = list(compatibility_result["errors"])

            budget_max = parsed.get("budget_max") if isinstance(parsed, dict) else None
            if compatibility_result["compatible"] and isinstance(budget_max, (int, float)) and budget_max > 0:
                real_total = compute_real_total(parsed, components_by_id)
                if real_total > budget_max:
                    errors.append(
                        f"Le total réel de cette configuration ({real_total:.2f}€) dépasse le "
                        f"budget indiqué ({budget_max}€)."
                    )

            if not errors:
                suggestion_json = parsed
                break

            last_errors = errors
            if attempt < MAX_AI_ATTEMPTS:
                errors_text = "\n".join(f"- {e}" for e in errors)
                current_prompt = f"""{base_prompt}

Ta tentative précédente {json.dumps(parsed)} est invalide pour les raisons suivantes :
{errors_text}

Corrige ta réponse en tenant compte de ces erreurs. Réponds UNIQUEMENT avec le JSON demandé."""

        if suggestion_json is None:
            return {
                "status": "error",
                "message": (
                    f"L'assistant n'a pas trouvé de configuration compatible et respectant le "
                    f"budget après {MAX_AI_ATTEMPTS} tentatives. Dernières erreurs : {'; '.join(last_errors)}"
                ),
            }

        # Vérification par recherche web réelle : on demande à un modèle avec
        # accès web (groq/compound) si cette config précise convient vraiment
        # à l'usage décrit. Systématique à chaque suggestion (demandé
        # explicitement, malgré le coût en requêtes API). Purement informatif
        # — ne bloque jamais l'affichage de la suggestion si ça échoue.
        verification_text = None
        try:
            chosen_components = [
                components_by_id[suggestion_json[field]]
                for field in ("cpu_id", "motherboard_id", "ram_id", "gpu_id", "psu_id", "storage_id", "case_id")
                if suggestion_json.get(field) in components_by_id
            ]
            chosen_list = "\n".join(f"- {c['nom']} ({c['categorie']})" for c in chosen_components)

            verification_prompt = f"""Besoin exprimé par l'utilisateur : "{request.user_input}"

Configuration proposée :
{chosen_list}

Fais une recherche rapide pour vérifier si cette configuration est réellement adaptée à
l'usage décrit (performances attendues, points d'attention éventuels). Réponds en français,
en 3-4 phrases maximum, factuel et concret. Si tu ne trouves rien de spécifique sur ces
composants précis, base-toi sur leurs caractéristiques générales plutôt que d'inventer."""

            verification_text = call_groq_compound(verification_prompt, max_tokens=400)
        except Exception as e_verif:
            print(f"Vérification web via Groq échouée, tentative Gemini: {e_verif}")
            try:
                verification_text = call_gemini_grounded(verification_prompt)
            except Exception as e_gemini_verif:
                print(f"Vérification Gemini échouée aussi (non bloquant): {e_gemini_verif}")

        return {
            "status": "ok",
            "suggestion": suggestion_json,
            "compatible": True,
            "verification": verification_text,
        }

    except Exception as error:
        return {"status": "error", "message": str(error)}


class EstimateFpsRequest(BaseModel):
    composants_json: dict  # {"CPU": id, "GPU": id, ...}
    jeux: list[str]


# Catégories qui doivent toutes être choisies avant de pouvoir estimer les
# FPS — une config partielle (ex: juste un GPU) donnerait une estimation
# trompeuse, notamment pour le goulot d'étranglement qui compare CPU et GPU.
REQUIRED_BUILD_CATEGORIES = ("CPU", "Carte mère", "RAM", "GPU", "Alimentation", "Stockage", "Boîtier")

# Regroupés en un seul appel IA plutôt qu'un par jeu : sinon sélectionner 5
# jeux consommerait 5x le quota Groq/Gemini partagé par tout le site pour
# une seule action utilisateur.
MAX_FPS_GAMES_PER_REQUEST = 5


@app.post("/api/estimate-fps")
def estimate_fps(request: EstimateFpsRequest, _rate_limit=Depends(enforce_ai_rate_limit)):
    """
    Estimation FPS pour un ou plusieurs jeux + détection de goulot
    d'étranglement, en UN SEUL appel IA (pas un par jeu, pour ménager le
    quota partagé). Pas d'API de benchmarks publique fiable disponible, et
    le scraping est interdit par le projet — on réutilise donc le pipeline
    de recherche web (groq/compound puis Gemini + Google Search). AUCUN
    filet de secours sans recherche : si les deux échouent, on le dit
    clairement plutôt que d'inventer un chiffre.
    """
    components = get_all_components()
    components_by_id = {c["id"]: c for c in components}

    chosen = [
        components_by_id[cid]
        for cid in request.composants_json.values()
        if cid in components_by_id
    ]
    if not chosen:
        raise HTTPException(status_code=400, detail="Aucun composant valide dans cette configuration.")

    present_categories = {c["categorie"] for c in chosen}
    missing = [cat for cat in REQUIRED_BUILD_CATEGORIES if cat not in present_categories]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Configuration incomplète pour estimer les FPS. Catégories manquantes : {', '.join(missing)}.",
        )

    jeux = [j.strip() for j in (request.jeux or []) if j and j.strip()]
    jeux = list(dict.fromkeys(jeux))  # dédoublonne en gardant l'ordre
    if not jeux:
        raise HTTPException(status_code=400, detail="Choisis au moins un jeu avant de lancer l'estimation.")
    if len(jeux) > MAX_FPS_GAMES_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"Choisis au maximum {MAX_FPS_GAMES_PER_REQUEST} jeux à la fois.",
        )

    chosen_list = "\n".join(f"- {c['nom']} ({c['categorie']})" for c in chosen)
    jeux_lines = "\n".join(f"{jeu} (1080p) : XX FPS\n{jeu} (1440p) : XX FPS" for jeu in jeux)
    jeux_listes = ", ".join(f'"{jeu}"' for jeu in jeux)
    output_format = f"""Réponds STRICTEMENT dans ce format, une ligne par élément, RIEN d'autre
(pas de phrase d'intro, pas de conclusion) :
{jeux_lines}
Goulot d'étranglement : <composant qui limite le plus les performances, ou "aucun notable">

Remplace XX par un nombre entier basé sur de VRAIS benchmarks trouvés en ligne pour des
composants identiques ou très proches. Le goulot d'étranglement se juge en comparant le niveau
de gamme du CPU et du GPU l'un par rapport à l'autre, et ne se donne qu'une seule fois pour
toute la configuration (pas par jeu).

Pour un jeu où tu ne trouves AUCUN benchmark fiable, écris "Non trouvé" à la place du nombre
UNIQUEMENT pour ce jeu-là (ne bloque pas les lignes des autres jeux)."""

    prompt = f"""Configuration PC :
{chosen_list}

Jeux à tester : {jeux_listes}

Fais une VRAIE recherche web pour trouver des benchmarks réels de chacun de ces jeux avec un
CPU et un GPU identiques ou très proches de ceux de cette configuration. N'invente aucun chiffre.

{output_format}"""

    try:
        return {"status": "ok", "estimation": call_gemini_grounded(prompt)}
    except Exception as e_gemini_first:
        print(f"Estimation FPS via Gemini échouée, tentative Groq: {e_gemini_first}")
        try:
            return {"status": "ok", "estimation": call_groq_compound(prompt, max_tokens=120 * len(jeux) + 100)}
        except Exception as e_groq:
            # Volontairement AUCUN filet de secours sans recherche ici : une
            # estimation FPS sans recherche réelle serait un chiffre inventé,
            # ce que le projet interdit explicitement.
            return {
                "status": "error",
                "message": "Impossible de faire une recherche web pour le moment (Groq et Gemini indisponibles). Réessaie dans quelques minutes.",
            }


LINK_CHECK_INTERVAL_SECONDS = 24 * 60 * 60

# Marqueurs de page "introuvable" observés sur Amazon — Amazon répond souvent
# en 200 OK même pour un produit retiré, donc le code HTTP seul ne suffit pas :
# il faut regarder le contenu de la page.
DEAD_LINK_MARKERS = (
    "page introuvable",
    "looking for something",
    "nous sommes désolés",
    "sorry, we couldn't find that page",
    "page not found",
)


# Marqueurs d'une page anti-bot (captcha / vérification humaine) — à ne
# JAMAIS confondre avec une vraie page "introuvable" : un lien bloqué par un
# anti-bot n'est pas un lien mort, juste un lien qu'on n'a pas pu vérifier.
BOT_CHECK_MARKERS = (
    "robot check",
    "servicing your request",
    "enter the characters you see below",
    "captcha",
    "vérification de sécurité",
)

REALISTIC_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def is_safe_external_url(url):
    """
    Rejette toute URL dont l'hôte ne résout pas vers une adresse IP publique
    — un lien de prix vient soit de l'admin, soit (via une correction) d'un
    simple utilisateur connecté, et est ensuite récupéré côté SERVEUR par le
    vérificateur de liens. Sans ce garde-fou, quelqu'un pourrait soumettre un
    lien pointant vers une adresse interne ou de métadonnées cloud
    (ex: 169.254.169.254) et faire faire une requête interne au serveur en
    son nom (SSRF).
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False

        for info in socket.getaddrinfo(hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                return False
        return True
    except Exception:
        return False


def check_link_dead(url):
    """
    Fait une simple requête HTTP pour voir si un lien de prix est mort (404,
    ou redirigé vers une page "introuvable"). Ce n'est PAS du scraping de
    données produit — juste une vérification technique de disponibilité du
    lien, pas d'extraction de prix/specs. Retourne True/False, ou None si on
    n'a pas pu conclure avec certitude (timeout, réseau, ou page anti-bot qui
    ressemble à une erreur sans en être une) — dans ce cas on ne marque
    JAMAIS le lien comme mort par défaut, ni vivant : on laisse l'état
    précédent inchangé plutôt que de deviner.
    """
    if not url or not is_safe_external_url(url):
        return None

    try:
        response = requests.get(
            url,
            timeout=10,
            headers={
                "User-Agent": REALISTIC_USER_AGENT,
                "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            },
            allow_redirects=True,
        )
    except requests.RequestException:
        return None

    if response.status_code == 404:
        return True

    if response.status_code in (403, 429, 503):
        # Bloqué par une protection anti-bot — on ne peut pas conclure.
        return None

    lowered = response.text.lower()
    if any(marker in lowered for marker in BOT_CHECK_MARKERS):
        return None

    return any(marker in lowered for marker in DEAD_LINK_MARKERS)


def update_prix_marche(client, component_id, prix_marche):
    client.execute(
        "UPDATE components SET prix_marche_json = ? WHERE id = ?",
        [json.dumps(prix_marche, ensure_ascii=False), component_id],
    )


# État de la dernière vérification, gardé en mémoire pour être affiché tel
# quel dans /admin — notamment le nombre de liens qu'on n'a PAS pu vérifier
# (bloqués par la protection anti-bot d'Amazon), pour être honnête sur la
# couverture réelle plutôt que de laisser croire que "pas dans la liste des
# morts" veut dire "confirmé vivant".
LAST_LINK_CHECK_STATUS = {
    "dernier_lancement": None,
    "liens_testes": 0,
    "liens_mis_a_jour": 0,
    "liens_non_verifiables": 0,
    "liens_corriges_auto": 0,
}

# Empêche deux vérifications de tourner en même temps (ex: la boucle
# quotidienne et un clic sur "Revérifier maintenant" qui se chevauchent) —
# inutile de doubler le travail et les requêtes vers les revendeurs.
LINK_CHECK_LOCK = threading.Lock()


def check_all_links():
    if not LINK_CHECK_LOCK.acquire(blocking=False):
        print("Vérification des liens déjà en cours, cette demande est ignorée.")
        return
    try:
        _run_link_check()
    finally:
        LINK_CHECK_LOCK.release()


def _run_link_check():
    """
    Vérifie tous les liens de prix stockés et met à jour, pour chaque relevé,
    'lien_mort' (bool) et 'dernier_check' (date ISO) directement dans le JSON
    prix_marche existant — pas de nouvelle table nécessaire.

    Correction automatique : si le relevé mort est celui d'Amazon ET que le
    composant a un ASIN enregistré, on retente immédiatement via Bright Data
    (même source que /api/admin/refresh-prices) plutôt que de se contenter
    de marquer le lien mort — la plupart des liens Amazon cassés le sont
    juste parce que l'URL a changé de forme, pas parce que le produit a
    disparu. Si ça échoue (produit vraiment retiré, Bright Data indisponible,
    pas d'ASIN...), on retombe sur le comportement normal (marqué mort, à
    corriger manuellement).

    Chaque composant est vérifié et sauvegardé indépendamment (connexion DB
    et try/except dédiés) : un problème réseau ou une erreur sur UN composant
    n'interrompt jamais la vérification des suivants, pour que la boucle
    couvre vraiment TOUS les composants à chaque passage.
    """
    components = get_all_components()
    checked_count = 0
    updated_count = 0
    error_count = 0
    unverifiable_count = 0
    auto_fixed_count = 0

    for component in components:
        prix_marche = component.get("prix_marche") or []
        if not prix_marche:
            continue

        try:
            updated_any = False
            for releve in prix_marche:
                is_dead = check_link_dead(releve.get("lien", ""))
                checked_count += 1
                time.sleep(0.5)  # politesse : pas de rafale de requêtes

                if is_dead is None:
                    unverifiable_count += 1
                    continue

                if is_dead and releve.get("vendeur") == "Amazon" and component.get("asin"):
                    try:
                        fresh = fetch_amazon_product(component["asin"])
                    except RuntimeError as error:
                        fresh = None
                        print(f"Correction auto du lien Amazon échouée pour '{component.get('nom')}' : {error}")

                    if fresh and fresh.get("prix") is not None:
                        releve["prix"] = fresh["prix"]
                        releve["lien"] = fresh.get("lien") or releve.get("lien")
                        releve["date_releve"] = datetime.utcnow().date().isoformat()
                        releve["lien_mort"] = False
                        releve["dernier_check"] = datetime.utcnow().isoformat()
                        auto_fixed_count += 1
                        updated_any = True
                        continue

                releve["lien_mort"] = is_dead
                releve["dernier_check"] = datetime.utcnow().isoformat()
                updated_any = True

            if updated_any:
                client = get_client()
                try:
                    update_prix_marche(client, component["id"], prix_marche)
                    updated_count += 1
                finally:
                    client.close()
        except Exception as error:
            error_count += 1
            print(f"Vérification des liens : erreur sur '{component.get('nom')}' (ignorée, on continue) : {error}")

    LAST_LINK_CHECK_STATUS.update({
        "dernier_lancement": datetime.utcnow().isoformat(),
        "liens_testes": checked_count,
        "liens_mis_a_jour": updated_count,
        "liens_non_verifiables": unverifiable_count,
        "liens_corriges_auto": auto_fixed_count,
    })
    print(
        f"Vérification des liens terminée : {checked_count} testé(s), "
        f"{unverifiable_count} non vérifiable(s) (anti-bot), {auto_fixed_count} corrigé(s) auto (Amazon), "
        f"{error_count} erreur(s)."
    )


async def link_checker_loop():
    """Boucle de fond : vérifie tous les liens une fois par jour."""
    while True:
        try:
            await asyncio.to_thread(check_all_links)
        except Exception as error:
            print(f"Vérification automatique des liens échouée : {error}")
        await asyncio.sleep(LINK_CHECK_INTERVAL_SECONDS)


@app.on_event("startup")
async def start_link_checker():
    asyncio.create_task(link_checker_loop())


@app.get("/api/admin/broken-links")
def admin_broken_links(_admin=Depends(require_admin)):
    """Liste les liens détectés morts par la dernière vérification — affiché en bandeau dans /admin."""
    components = get_all_components()
    broken = []
    for component in components:
        for releve in component.get("prix_marche") or []:
            if releve.get("lien_mort"):
                broken.append({
                    "component_id": component["id"],
                    "categorie": component["categorie"],
                    "nom": component["nom"],
                    "vendeur": releve.get("vendeur"),
                    "lien": releve.get("lien"),
                    "dernier_check": releve.get("dernier_check"),
                })
    return {"status": "ok", "broken_links": broken, "check_status": LAST_LINK_CHECK_STATUS}


@app.post("/api/admin/check-links")
def admin_check_links_now(_admin=Depends(require_admin)):
    """
    Déclenche une vérification immédiate en arrière-plan (en plus de la boucle
    automatique quotidienne). Lancée dans un thread séparé plutôt qu'en
    bloquant la requête : avec le délai de politesse entre chaque lien, un
    catalogue de plusieurs centaines de liens prendrait plusieurs minutes,
    largement au-delà d'un timeout HTTP raisonnable. Le frontend sonde
    /api/admin/broken-links pour savoir quand c'est terminé.
    """
    threading.Thread(target=check_all_links, daemon=True).start()
    return {"status": "ok", "message": "Vérification lancée en arrière-plan."}


@app.post("/api/admin/fix-link")
def admin_fix_link(payload: dict = Body(...), _admin=Depends(require_admin)):
    """
    Corrige directement un lien de prix (utilisé par le bouton "Éditer" à
    côté de chaque lien mort dans /admin) — contrairement à
    /api/link-corrections (proposition d'un utilisateur, en attente de
    modération), ici l'admin agit directement, sans file d'attente.
    """
    component_id = payload.get("component_id")
    vendeur = payload.get("vendeur")
    nouveau_lien = payload.get("nouveau_lien", "")

    if not isinstance(nouveau_lien, str) or not is_safe_external_url(nouveau_lien):
        raise HTTPException(status_code=400, detail="Le lien doit être une URL publique valide (http(s)://...).")

    components_by_id = {c["id"]: c for c in get_all_components()}
    component = components_by_id.get(component_id)
    if not component:
        raise HTTPException(status_code=404, detail="Composant introuvable.")

    prix_marche = component.get("prix_marche") or []
    found = False
    for releve in prix_marche:
        if releve.get("vendeur") == vendeur:
            releve["lien"] = nouveau_lien
            releve["lien_mort"] = False
            releve["dernier_check"] = datetime.utcnow().isoformat()
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail="Revendeur introuvable pour ce composant.")

    client = get_client()
    try:
        update_prix_marche(client, component_id, prix_marche)
    finally:
        client.close()

    return {"status": "ok", "message": "Lien mis à jour."}


class LinkCorrectionRequest(BaseModel):
    component_id: int
    vendeur: str
    nouveau_lien: str


@app.post("/api/link-corrections")
def submit_link_correction(request: LinkCorrectionRequest, user=Depends(require_login)):
    """
    Un utilisateur connecté propose un nouveau lien pour un revendeur d'un
    composant. Ne modifie RIEN directement — la proposition part dans une
    file de modération que seul un admin peut approuver depuis /admin.
    """
    if not is_safe_external_url(request.nouveau_lien):
        raise HTTPException(status_code=400, detail="Le lien proposé doit être une URL publique valide (http(s)://...).")

    components_by_id = {c["id"]: c for c in get_all_components()}
    component = components_by_id.get(request.component_id)
    if not component:
        raise HTTPException(status_code=404, detail="Composant introuvable.")

    ancien_lien = next(
        (r.get("lien") for r in (component.get("prix_marche") or []) if r.get("vendeur") == request.vendeur),
        None,
    )

    client = get_client()
    try:
        client.execute(
            "INSERT INTO link_corrections "
            "(component_id, vendeur, ancien_lien, nouveau_lien, user_id, user_email, statut, date) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
            [
                request.component_id, request.vendeur, ancien_lien, request.nouveau_lien,
                user["id"], user["email"], datetime.utcnow().isoformat(),
            ],
        )
    finally:
        client.close()

    return {"status": "ok", "message": "Correction envoyée, en attente de validation par un admin."}


@app.get("/api/admin/link-corrections")
def admin_list_link_corrections(_admin=Depends(require_admin)):
    """Liste les propositions de correction en attente, pour la modération dans /admin."""
    client = get_client()
    try:
        result = client.execute(
            "SELECT id, component_id, vendeur, ancien_lien, nouveau_lien, user_email, statut, date "
            "FROM link_corrections WHERE statut = 'pending' ORDER BY date ASC"
        )
        components_by_id = {c["id"]: c for c in get_all_components()}
        corrections = []
        for row in result.rows:
            component = components_by_id.get(row[1])
            corrections.append({
                "id": row[0],
                "component_id": row[1],
                "component_nom": component["nom"] if component else "Composant supprimé",
                "component_categorie": component["categorie"] if component else "?",
                "vendeur": row[2],
                "ancien_lien": row[3],
                "nouveau_lien": row[4],
                "user_email": row[5],
                "statut": row[6],
                "date": row[7],
            })
        return {"status": "ok", "corrections": corrections}
    finally:
        client.close()


def get_link_correction(client, correction_id):
    result = client.execute(
        "SELECT id, component_id, vendeur, nouveau_lien, statut FROM link_corrections WHERE id = ?",
        [correction_id],
    )
    if not result.rows:
        return None
    row = result.rows[0]
    return {"id": row[0], "component_id": row[1], "vendeur": row[2], "nouveau_lien": row[3], "statut": row[4]}


@app.post("/api/admin/link-corrections/{correction_id}/approve")
def admin_approve_link_correction(correction_id: int, _admin=Depends(require_admin)):
    """Approuve une correction : applique le nouveau lien au composant ET marque la proposition traitée."""
    client = get_client()
    try:
        correction = get_link_correction(client, correction_id)
        if not correction:
            raise HTTPException(status_code=404, detail="Correction introuvable.")
        if correction["statut"] != "pending":
            raise HTTPException(status_code=409, detail="Cette correction a déjà été traitée.")

        components_by_id = {c["id"]: c for c in get_all_components()}
        component = components_by_id.get(correction["component_id"])
        if not component:
            raise HTTPException(status_code=404, detail="Composant introuvable.")

        prix_marche = component.get("prix_marche") or []
        found = False
        for releve in prix_marche:
            if releve.get("vendeur") == correction["vendeur"]:
                releve["lien"] = correction["nouveau_lien"]
                releve["lien_mort"] = False
                releve["dernier_check"] = datetime.utcnow().isoformat()
                found = True
                break

        if not found:
            # Le revendeur n'existe plus dans la liste (ex: supprimé entre
            # temps) — on l'ajoute plutôt que de perdre la correction.
            prix_marche.append({
                "vendeur": correction["vendeur"],
                "prix": component["prix_indicatif"] or 0,
                "lien": correction["nouveau_lien"],
                "date_releve": datetime.utcnow().date().isoformat(),
                "lien_mort": False,
                "dernier_check": datetime.utcnow().isoformat(),
            })

        update_prix_marche(client, component["id"], prix_marche)
        client.execute("UPDATE link_corrections SET statut = 'approved' WHERE id = ?", [correction_id])
        return {"status": "ok", "message": "Correction appliquée."}
    finally:
        client.close()


@app.post("/api/admin/link-corrections/{correction_id}/reject")
def admin_reject_link_correction(correction_id: int, _admin=Depends(require_admin)):
    client = get_client()
    try:
        correction = get_link_correction(client, correction_id)
        if not correction:
            raise HTTPException(status_code=404, detail="Correction introuvable.")
        client.execute("UPDATE link_corrections SET statut = 'rejected' WHERE id = ?", [correction_id])
        return {"status": "ok", "message": "Correction rejetée."}
    finally:
        client.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)