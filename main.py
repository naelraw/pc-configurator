import asyncio
import base64
import concurrent.futures
import csv
import gzip
import hashlib
import html
import ipaddress
import json
import os
import re
import secrets
import socket
import threading

try:
    import fcntl  # verrous entre processus (Linux) ; absent sous Windows en local
except ImportError:
    fcntl = None
import time
import unicodedata
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlparse
import requests
from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.gzip import GZipMiddleware
from groq import Groq
import libsql_client
import sqlite3
from libsql_client.sqlite3_utils import _execute_stmt as _libsql_execute_stmt
from pydantic import BaseModel, Field
from compatibility import (
    check_alimentation,
    check_carte_mere_boitier,
    check_carte_mere_ram,
    check_cpu_carte_mere,
    check_gpu_boitier,
    check_refroidissement,
    check_cable_alimentation,
    check_stockage,
)
from schema import REQUIRED_FIELDS, validate_component
import fps_data
import featured_builds
import guides
import component_pages
import comparisons
import variantes
import controle_catalogue
import site_stats

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

# Awin : réseau d'affiliation utilisé pour les revendeurs hors Amazon (LDLC,
# Materiel.net, Rue du Commerce...). AWIN_PUBLISHER_ID est l'identifiant du
# compte affilié (le même pour tous les marchands). AWIN_MERCHANT_IDS associe
# chaque nom de revendeur (tel qu'utilisé dans "vendeur" en base) à son
# identifiant marchand Awin ("Advertiser ID", différent par revendeur, visible
# dans le dashboard Awin une fois le programme du revendeur rejoint) — ex.
# AWIN_MERCHANT_IDS='{"LDLC": "1234", "Materiel.net": "5678"}'. Un revendeur
# absent de ce mapping n'est tout simplement pas transformé : son lien reste
# tel quel, jamais d'erreur ni de lien cassé.
AWIN_PUBLISHER_ID = os.getenv("AWIN_PUBLISHER_ID", "")
try:
    AWIN_MERCHANT_IDS = json.loads(os.getenv("AWIN_MERCHANT_IDS", "{}"))
except json.JSONDecodeError:
    print("AWIN_MERCHANT_IDS invalide (JSON mal formé) — ignoré, aucun lien Awin ne sera généré.")
    AWIN_MERCHANT_IDS = {}

# Sous-ensemble du feed produit AliExpress (export Awin "Bestsellers CSS",
# ~427 000 produits) filtré à l'avance sur CPU + RAM uniquement (voir
# aliexpress_tool/filter_cpu_ram.py) — les seules catégories où ce feed
# contient de vrais produits de marque exploitables (testé : les GPU/cartes
# mères de marque n'y existent quasiment jamais, contrairement aux CPU et
# barrettes de RAM). Chargé une fois en mémoire au démarrage : 574 lignes,
# recherche instantanée, pas de round-trip réseau ni de scraping en direct.
ALIEXPRESS_CPU_RAM_FEED_PATH = os.path.join(os.path.dirname(__file__), "data", "aliexpress_cpu_ram.csv")
ALIEXPRESS_CPU_RAM_FEED = []
try:
    with open(ALIEXPRESS_CPU_RAM_FEED_PATH, encoding="utf-8", newline="") as _feed_file:
        ALIEXPRESS_CPU_RAM_FEED = list(csv.DictReader(_feed_file))
except FileNotFoundError:
    print(f"Feed AliExpress CPU/RAM introuvable ({ALIEXPRESS_CPU_RAM_FEED_PATH}) — recherche AliExpress désactivée.")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")  # Fallback optionnel

# Troisième fournisseur pour call_ai_model (voir plus bas) : palier gratuit
# permanent Mistral (~1 milliard de tokens/mois), quota indépendant de
# Gemini et Groq — sert de filet quand les deux autres échouent en même
# temps (constaté en pratique le 2026-09-22).
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MISTRAL_MODEL = "mistral-small-latest"

# Plusieurs projets Gemini possibles (chacun a son propre quota, complètement
# indépendant des autres) : si le premier est à court de crédit, on bascule
# sur le suivant, et ainsi de suite. Optionnel : seules les clés définies
# dans .env comptent.
#
# 5 clés gratuites (500 requêtes/jour chacune sur gemini-3.5-flash-lite,
# quota Google indépendant par projet) : l'ancienne clé facturée à crédit
# prépayé à 0€ a été remplacée par ces 5 nouvelles clés fraîches plutôt que
# de dépendre d'un crédit à recharger — 2500 requêtes/jour combinées au
# lieu de 1500 (3 clés), pour réduire le risque de retomber sur le repli
# Groq (plus lent, limite de taille de prompt plus stricte).
GEMINI_API_KEYS = [
    key for key in (
        os.getenv("GEMINI_API_KEY"),
        os.getenv("GEMINI_API_KEY_2"),
        os.getenv("GEMINI_API_KEY_3"),
        os.getenv("GEMINI_API_KEY_4"),
        os.getenv("GEMINI_API_KEY_5"),
    ) if key
]

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Récupération auto des infos produit Amazon par ASIN, via le dataset
# "Amazon Products" de Bright Data (5000 requêtes gratuites/mois, jamais de
# scraping fait par ce serveur lui-même — Bright Data s'en charge et renvoie
# des données déjà structurées).
BRIGHTDATA_API_TOKEN = os.getenv("BRIGHTDATA_API_TOKEN", "")
BRIGHTDATA_AMAZON_DATASET_ID = os.getenv("BRIGHTDATA_AMAZON_DATASET_ID", "gd_l7q7dkf244hwjntr0")
AMAZON_DOMAIN_TLD = os.getenv("AMAZON_DOMAIN_TLD", "fr")

# Second fournisseur pour le rafraîchissement quotidien prix/stock (voir
# _run_daily_price_refresh_rotation) : ZenRows scrape directement le HTML
# Amazon (contrairement à Bright Data, pas de dataset structuré), 5000
# crédits gratuits/mois. Une requête Amazon simple (1 crédit) est bloquée
# par leur protection anti-bot — testé en pratique, ça renvoit une page
# "automated access" vide — il faut premium_proxy=true (10 crédits), ce qui
# limite ce fournisseur à ~500 fiches/mois gratuites, en complément de
# Bright Data plutôt qu'à sa place.
ZENROWS_API_KEY = os.getenv("ZENROWS_API_KEY", "")
ZENROWS_CREDITS_PER_REQUEST = 10

# Troisième fournisseur, le plus généreux des trois : l'actor Apify
# "memo23/free-amazon-product-scraper" (autonome, pas de clé tierce requise
# contrairement à d'autres actors du marketplace Apify qui ne font que
# revendre l'accès à une API payante externe — vérifié avant d'intégrer).
# Facturé à l'usage plateforme Apify (temps de calcul), pas au résultat :
# ~0,0002$/produit mesuré en pratique, ce qui donne largement plus de
# 5000 fiches/mois avec les 5$ de crédit gratuit mensuel (renouvelé chaque
# mois, contrairement à un essai unique) — d'où le rôle de fournisseur
# principal de la rotation quotidienne plutôt que de simple complément.
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN", "")
APIFY_AMAZON_ACTOR_ID = "memo23~free-amazon-product-scraper"

# Détourage (suppression d'arrière-plan) des photos produit, via un service
# rembg auto-hébergé sur un VM Oracle Cloud personnel — gratuit, illimité.
REMBG_SERVICE_URL = os.getenv("REMBG_SERVICE_URL", "").rstrip("/")
REMBG_API_KEY = os.getenv("REMBG_API_KEY", "")


# Au-delà de quelques phrases, un message ne sert qu'à gonfler le prompt (et
# les quotas gratuits des IA) : 2000 caractères suffisent largement.
MAX_USER_INPUT = 2000


class SuggestConfigRequest(BaseModel):
    user_input: str = Field(max_length=MAX_USER_INPUT)

# Pas de documentation d'API publique (/docs, /redoc, /openapi.json) : elle
# listait toutes les routes, admin comprises, à n'importe quel visiteur.
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# Cookie de session marqué Secure (jamais envoyé en HTTP clair). En local sans
# HTTPS, mettre SESSION_HTTPS_ONLY=0 dans .env.
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    https_only=os.getenv("SESSION_HTTPS_ONLY", "1") != "0",
    same_site="lax",
    max_age=30 * 24 * 3600,  # rester connecté 30 jours
)
# /api/components pèse ~2,8 Mo en JSON brut : compressé, il transite
# plusieurs fois plus vite. Seuil bas pour couvrir aussi les autres routes JSON.
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Seul le site lui-même appelle l'API depuis un navigateur. L'extension passe
# par son script d'arrière-plan (host_permissions), non soumis au CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://pcradar.tech", "https://www.pcradar.tech"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-Admin-Secret"],
)

SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    # Aucun script inline autorisé : le JS des pages vit dans /static/pages/ et
    # les onclick="" sont remplacés par data-onclick="" (static/csp-handlers.js).
    # Une injection HTML ne peut donc plus exécuter de JavaScript. Les styles
    # inline restent permis (attributs style="" partout, sans risque d'exécution).
    "Content-Security-Policy": "; ".join([
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net",
        "font-src 'self' data: https://fonts.gstatic.com https://cdn.jsdelivr.net",
        "img-src 'self' data: blob: https:",
        "connect-src 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "object-src 'none'",
        "form-action 'self'",
        "upgrade-insecure-requests",
    ]),
}


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    # Toute écriture admin peut toucher le catalogue : il sera relu en base
    # à la prochaine demande (les autres processus suivent sous 60 s).
    if request.method != "GET" and request.url.path.startswith("/api/admin/"):
        invalidate_catalog()
    return response


# Limitation des tentatives, mémorisée en base (table auth_attempts) pour
# survivre aux redémarrages : freine le devinage de mots de passe et du secret
# admin sans service externe.


# Le serveur fait tourner plusieurs processus uvicorn (--workers) : un
# threading.Lock ne protège qu'à l'intérieur d'un seul d'entre eux. Ce verrou
# ajoute un fichier verrouillé (flock), partagé par tous les processus.
class ProcessLock:
    def __init__(self, name):
        self._path = os.path.join(os.getenv("PCRADAR_LOCK_DIR", "/tmp"), f"pcradar-{name}.lock")
        self._thread_lock = threading.Lock()
        self._fd = None

    def acquire(self, blocking=True):
        if not self._thread_lock.acquire(blocking):
            return False
        if fcntl is None:
            return True
        fd = os.open(self._path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except OSError:
            os.close(fd)
            self._thread_lock.release()
            return False
        self._fd = fd
        return True

    def release(self):
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None
        self._thread_lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()


# Un seul processus exécute les tâches de fond (prix, liens) : sinon chaque
# processus consommerait les quotas Bright Data / Apify / ZenRows en double.
# Le verrou reste tenu toute la vie du processus ; s'il s'arrête, uvicorn en
# relance un autre, qui le reprend au démarrage.
_BACKGROUND_LEADER = ProcessLock("taches-de-fond")
_IS_BACKGROUND_LEADER = None


def is_background_leader():
    global _IS_BACKGROUND_LEADER
    if _IS_BACKGROUND_LEADER is None:
        _IS_BACKGROUND_LEADER = _BACKGROUND_LEADER.acquire(blocking=False)
    return _IS_BACKGROUND_LEADER


def _client_ip(request: Request) -> str:
    # nginx écrase X-Real-IP avec l'adresse réelle du visiteur.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "?")


def _too_many_attempts(bucket: str, request: Request, limit: int, window_seconds: int) -> bool:
    client = get_client()
    try:
        count = client.execute(
            "SELECT COUNT(*) FROM auth_attempts WHERE bucket = ? AND ip = ? AND ts > ?",
            [bucket, _client_ip(request), time.time() - window_seconds],
        ).rows[0][0]
    except Exception as err:
        print(f"Limitation des tentatives indisponible : {err}")
        return False
    finally:
        client.close()
    return count >= limit


def _record_attempt(bucket: str, request: Request):
    client = get_client()
    try:
        now = time.time()
        client.execute("INSERT INTO auth_attempts (bucket, ip, ts) VALUES (?, ?, ?)",
                       [bucket, _client_ip(request), now])
        # Rien ne sert au-delà d'une heure (plus longue fenêtre utilisée).
        client.execute("DELETE FROM auth_attempts WHERE ts < ?", [now - 3600])
    except Exception as err:
        print(f"Tentative non mémorisée : {err}")
    finally:
        client.close()


def _check_rate_limit(bucket: str, request: Request, limit: int, window_seconds: int):
    if _too_many_attempts(bucket, request, limit, window_seconds):
        raise HTTPException(status_code=429, detail="Trop de tentatives. Réessaie dans quelques minutes.")

class NoCacheStaticFiles(StaticFiles):
    """
    Sans Cache-Control explicite, les navigateurs appliquent un cache
    "heuristique" basé sur Last-Modified qui peut durer des jours — après un
    redéploiement (CSS/JS modifiés), certains visiteurs continuaient de voir
    l'ancienne version sans même refaire de requête réseau. "no-cache" force
    une revalidation à chaque chargement (ETag/If-None-Match, toujours rapide
    via un 304 si rien n'a changé) sans perdre le bénéfice du cache.
    """
    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/static", NoCacheStaticFiles(directory="static", html=True), name="static")


def _sqlite_path(url):
    path = url[len("file:"):]
    return path[2:] if path.startswith("//") else path


class LocalSqliteClient:
    """
    Accès direct au fichier SQLite, même interface que le client libsql
    (execute / batch / close, lignes identiques). libsql_client lançait un
    thread et une boucle asyncio pour CHAQUE client, rouvrait une connexion
    par requête SQL et n'attendait jamais (timeout=0) : deux écritures
    simultanées échouaient aussitôt en "database is locked". Ici : une
    connexion par client, attente jusqu'à 10 s en cas de verrou.
    """

    def __init__(self, path):
        self._db = sqlite3.connect(path, isolation_level=None, check_same_thread=False, timeout=10)
        self._db.execute("PRAGMA synchronous=NORMAL")

    def execute(self, stmt, args=None):
        return _libsql_execute_stmt(self._db, stmt, args)

    def batch(self, stmts):
        self._db.execute("BEGIN IMMEDIATE")
        try:
            results = [_libsql_execute_stmt(self._db, stmt) for stmt in stmts]
        except Exception:
            self._db.execute("ROLLBACK")
            raise
        self._db.execute("COMMIT")
        return results

    def close(self):
        self._db.close()


def _enable_sqlite_wal():
    """
    Mode WAL (réglage conservé dans le fichier) : les lectures ne bloquent
    plus les écritures ni l'inverse, indispensable avec plusieurs processus.
    """
    url = os.getenv("TURSO_DATABASE_URL") or ""
    if not url.startswith("file:"):
        return
    try:
        db = sqlite3.connect(_sqlite_path(url), timeout=10)
        try:
            db.execute("PRAGMA journal_mode=WAL")
        finally:
            db.close()
    except sqlite3.Error as err:
        print(f"Mode WAL non activé : {err}")


_enable_sqlite_wal()


def get_client():
    """
    Base SQLite locale sur le VM (fichier "file:...") par défaut — tout au
    même endroit, plus de dépendance à un service externe (Turso), plus de
    latence de "réveil" après inactivité. TURSO_DATABASE_URL peut encore
    pointer vers une vraie base Turso (libsql://... ou https://...) si
    besoin de revenir en arrière ou pour un environnement de dev séparé.
    """
    url = os.getenv("TURSO_DATABASE_URL")
    if url.startswith("file:"):
        return LocalSqliteClient(_sqlite_path(url))
    url = url.replace("libsql://", "https://")
    token = os.getenv("TURSO_AUTH_TOKEN")
    return libsql_client.create_client_sync(url=url, auth_token=token)


def get_all_components():
    client = get_client()
    try:
        result = client.execute(
            "SELECT id, categorie, nom, specs_json, prix_indicatif, prix_marche_json, image_url, asin, "
            "amazon_details_json, description, en_stock FROM components ORDER BY categorie, nom"
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
                "en_stock": bool(row[10]),
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


def get_all_components_light():
    """
    Version allégée de get_all_components(), pour l'endpoint public très
    sollicité /api/components : ne récupère PAS le CONTENU de la colonne
    image_url (une image détourée est encodée en base64 en base, souvent
    plusieurs centaines de Ko par composant), juste un booléen indiquant si
    une image existe. Le contenu réel est de toute façon récupéré à part par
    chaque <img> via /api/components/{id}/image (mis en cache par le
    navigateur). Sans ça, le simple fait de FAIRE TRANSITER cette colonne
    depuis Turso pour chaque composant pouvait à elle seule prendre 15-20+
    secondes, même pour une poignée de composants — pas un problème de
    traitement Python, un problème de volume réseau vers la base (propre à
    Turso ; le SUBSTR() ci-dessous reste léger sur SQLite local, il ne fait
    pas transiter le contenu complet de la colonne).

    "image_processed" indique si l'image stockée est déjà détourée
    (data:...) ou encore l'URL Amazon brute pas encore traitée par la
    surveillance locale — sert côté front à choisir l'habillage adapté
    (transparence réelle sur fond thème vs image brute sur fond blanc, le
    temps que le détourage automatique passe dessus).
    """
    client = get_client()
    try:
        result = client.execute(
            "SELECT id, categorie, nom, specs_json, prix_indicatif, prix_marche_json, "
            "has_image, asin, amazon_details_json, description, "
            "SUBSTR(image_url, 1, 5) = 'data:' AS image_processed, en_stock "
            "FROM components ORDER BY categorie, nom"
        )
        components = []
        for row in result.rows:
            component = {
                "id": row[0],
                "categorie": row[1],
                "nom": row[2],
                "specs_json": row[3],
                "prix_indicatif": row[4],
                "image_url": f"/api/components/{row[0]}/image" if row[6] else None,
                "image_processed": bool(row[10]),
                "asin": row[7],
                "description": row[9],
                "en_stock": bool(row[11]),
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
            # perf_index : indice de performance réel (voir GPU/CPU_PERFORMANCE_INDEX
            # plus bas dans le fichier) pour trier "meilleur d'abord" côté front sur
            # une base objective plutôt que sur le prix. None pour les catégories
            # sans indice de performance connu (RAM, Stockage, Boîtier...).
            if component["categorie"] == "GPU":
                component["perf_index"] = _match_performance_index(component["nom"], GPU_PERFORMANCE_INDEX)
            elif component["categorie"] == "CPU":
                component["perf_index"] = _match_performance_index(component["nom"], CPU_PERFORMANCE_INDEX)
            elif component["categorie"] == "RAM":
                ram_specs = _parse_ram_specs(component["nom"])
                capacite, frequence = ram_specs["capacite_go"], ram_specs["frequence_mhz"]
                component["perf_index"] = capacite * frequence if capacite and frequence else None
            elif component["categorie"] == "Alimentation":
                wattage = component["specs"].get("wattage")
                component["perf_index"] = wattage if isinstance(wattage, (int, float)) else None
            else:
                component["perf_index"] = None
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
    if cooler:
        # Sans processeur ou sans boîtier, les contrôles qui en dépendent sont
        # simplement sautés ; « ventilateur de boîtier choisi comme
        # refroidisseur » est signalé dans tous les cas.
        ok, message = check_refroidissement(cpu or {}, case or {}, cooler)
        if not ok:
            errors.append(message)

    return {"compatible": not errors, "errors": errors, "warnings": check_cable_alimentation(gpu, psu)}


def verify_compatibility(suggestion):
    """
    Vérifie qu'une suggestion de l'IA contient bien les composants requis ET
    qu'ils sont compatibles entre eux. Une suggestion incomplète (sur les
    champs requis), avec des IDs inconnus, ou dont un ID pointe vers la
    mauvaise catégorie (ex: gpu_id qui résout vers un composant catégorisé
    "gpu" au lieu de "GPU") est TOUJOURS rejetée explicitement — on ne
    déduit jamais "compatible" de l'absence de données ou d'une catégorie
    mal alignée.

    Seuls cpu_id/ram_id/gpu_id sont REQUIS — le prompt de /suggest-config
    demande maintenant à l'IA de remplir aussi carte mère / alimentation /
    stockage / boîtier quand des composants existent pour ces catégories,
    mais ça reste une consigne, pas une garantie : les exiger ici en dur
    rejetterait TOUTE la suggestion si l'IA en oublie un par erreur, plutôt
    que d'accepter une config partielle mais déjà utile. Les 4 autres champs
    restent vérifiés normalement si l'IA en fournit un ; un null pour eux
    n'est pas une erreur en soi.
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
    required_fields = ("cpu_id", "ram_id", "gpu_id")

    if not isinstance(suggestion, dict):
        return {"compatible": False, "errors": ["Réponse de l'IA invalide (pas un objet JSON)."]}

    missing = [field for field in required_fields if not suggestion.get(field)]
    if missing:
        return {
            "compatible": False,
            "errors": [f"Champs manquants dans la suggestion de l'IA : {', '.join(missing)}"],
        }

    provided_fields = [field for field in field_to_category if suggestion.get(field)]

    components = get_catalog()
    components_by_id = {component["id"]: component for component in components}

    unknown = [field for field in provided_fields if suggestion[field] not in components_by_id]
    if unknown:
        return {
            "compatible": False,
            "errors": [f"IDs de composants inconnus pour : {', '.join(unknown)}"],
        }

    mismatched = [
        field
        for field in provided_fields
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

    config_list = [components_by_id[suggestion[field]] for field in provided_fields]
    return check_compatibility(config_list)


@app.get("/")
def root():
    return FileResponse("static/index.html")


@app.get("/favicon.ico")
def favicon():
    """
    Certains navigateurs et crawlers (dont celui de Google pour l'icône
    affichée dans les résultats de recherche) demandent /favicon.ico même
    quand <link rel="icon"> pointe ailleurs, ET s'attendent à du PNG/ICO
    directement en 200 — jamais une redirection vers du SVG, mal supporté
    par ces crawlers (constaté en pratique : favicon absent du résultat
    Google alors qu'il s'affiche bien dans l'onglet du navigateur, qui lui
    suit correctement les <link rel="icon">). FileResponse plutôt que
    RedirectResponse : sert le fichier directement, sans redirection à suivre.
    Vrai fichier ICO (16, 32 et 48 px) : Bing, qui affiche l'icône dans ses
    résultats, attend un .ico ou une taille multiple de 48 px.
    """
    return FileResponse("static/favicon.ico", media_type="image/x-icon")


@app.get("/apple-touch-icon.png")
@app.get("/apple-touch-icon-precomposed.png")
def apple_touch_icon():
    """Demandées à la racine par iOS et certains crawlers, même sans <link>."""
    return FileResponse("static/apple-touch-icon.png", media_type="image/png")


@app.get("/sw.js")
def service_worker():
    """Servi à la racine : un service worker ne contrôle que les pages sous son propre dossier."""
    return FileResponse("static/sw.js", media_type="application/javascript", headers={"Cache-Control": "no-cache"})


SITE_URL = "https://pcradar.tech"

# IndexNow (Bing, Yandex...) : ce fichier public prouve que le site est bien le
# nôtre quand on signale des pages à revisiter. La clé n'est pas un secret.
INDEXNOW_KEY = "6f5a431a2e404283eb5c4ec0a53f7f63"


@app.get(f"/{INDEXNOW_KEY}.txt")
def indexnow_key_file():
    return Response(content=INDEXNOW_KEY, media_type="text/plain")


@app.get("/robots.txt")
def robots_txt():
    """
    Autorise l'indexation de tout le site public, bloque explicitement
    l'admin (déjà protégé par mot de passe, mais aucune raison de le laisser
    apparaître dans un moteur de recherche) et pointe vers le sitemap.
    """
    content = f"""User-agent: *
Allow: /
Disallow: /static/admin.html
Disallow: /api/

Sitemap: {SITE_URL}/sitemap.xml
"""
    return Response(content=content, media_type="text/plain")


@app.get("/sitemap.xml")
def sitemap_xml():
    """
    Sitemap des pages "évergreen" du site (pas les /build/{{id}} générés par
    les utilisateurs : leur nombre et leur contenu changent en permanence,
    inutile de les maintenir ici — ils restent crawlables normalement via
    les liens qui pointent vers eux, juste pas listés explicitement).
    """
    pages = [
        ("/", "1.0", "daily"),
        ("/configurateur", "0.9", "daily"),
        ("/assistant", "0.9", "weekly"),
        ("/comparateur", "0.8", "weekly"),
        ("/estimer-fps", "0.8", "weekly"),
        ("/guides", "0.8", "daily"),
    ] + [(f"/guides/{slug}", "0.8", "daily") for slug in guides.GUIDES]
    pages += [("/composants", "0.7", "daily")]
    pages += [(component_pages.category_url(cat), "0.7", "daily") for cat in component_pages.CATEGORY_SLUGS]
    pages += [(component_pages.page_url(c), "0.6", "daily") for c in get_catalog()]
    pages += [("/comparer", "0.7", "daily")]
    pages += [(f"/comparer/{p['slug']}", "0.6", "daily") for p in comparisons.pairs(get_catalog())]
    urls = "\n".join(
        f"""  <url>
    <loc>{SITE_URL}{path}</loc>
    <changefreq>{freq}</changefreq>
    <priority>{priority}</priority>
  </url>"""
        for path, priority, freq in pages
    )
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls}
</urlset>
"""
    return Response(content=content, media_type="application/xml")


@app.get("/llms.txt")
def llms_txt():
    """
    Convention récente (non normalisée, mais de plus en plus suivie) pour
    donner aux agents IA un résumé direct du site en langage simple, plutôt
    que de les laisser deviner depuis le HTML — complète robots.txt (qui ne
    fait qu'autoriser/interdire le crawl) sans le remplacer.
    """
    content = f"""# PC Radar

> Comparateur et configurateur de composants PC, gratuit, sans inscription obligatoire.

PC Radar aide à choisir des composants informatiques compatibles entre eux
(CPU, carte mère, RAM, GPU, boîtier, alimentation, stockage, refroidissement)
et à comparer leurs prix chez différents revendeurs. Le site ne vend rien
directement : chaque lien produit redirige vers le site marchand concerné
(notamment Amazon), où l'achat a lieu. PC Radar se rémunère uniquement via
des liens d'affiliation (sans surcoût pour l'acheteur).

## Pages principales
- [Accueil]({SITE_URL}/) : présentation du site
- [Configurateur]({SITE_URL}/configurateur) : sélection de composants avec vérification de compatibilité automatique
- [Assistant IA]({SITE_URL}/assistant) : suggestion de configuration à partir d'une description en langage naturel
- [Comparateur de prix]({SITE_URL}/comparateur) : comparaison de prix d'un composant entre revendeurs
- [Estimateur FPS]({SITE_URL}/estimer-fps) : estimation de performances en jeu pour une configuration donnée

## Données et confidentialité
- [Mentions légales]({SITE_URL}/mentions-legales)
- [Politique de confidentialité]({SITE_URL}/confidentialite)
- [Conditions d'utilisation]({SITE_URL}/cgu)
- [Politique de cookies]({SITE_URL}/cookies)

Les informations de prix, stock et compatibilité affichées sont fournies à
titre indicatif et peuvent différer de la réalité au moment de l'achat.
"""
    return Response(content=content, media_type="text/plain")


@app.get("/api/config")
def api_config():
    """Config publique consommée par le frontend (rien de sensible ici)."""
    return {
        "amazon_tag": AMAZON_ASSOCIATE_TAG,
        "awin_publisher_id": AWIN_PUBLISHER_ID,
        "awin_merchant_ids": AWIN_MERCHANT_IDS,
    }


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


@app.get("/mentions-legales")
def mentions_legales_page():
    return FileResponse("static/mentions-legales.html")


@app.get("/confidentialite")
def confidentialite_page():
    return FileResponse("static/confidentialite.html")


@app.get("/cgu")
def cgu_page():
    return FileResponse("static/cgu.html")


@app.get("/cookies")
def cookies_page():
    return FileResponse("static/cookies.html")


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

        components_by_id = {c["id"]: c for c in get_catalog()}
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
        title = f"{nom} — PC Radar"
        description = ", ".join(noms_composants)[:200] or "Une configuration PC partagée depuis PC Radar."
    else:
        title = "Configuration introuvable — PC Radar"
        description = "Ce lien ne correspond à aucune configuration (peut-être supprimée)."
        image_url = None

    # Toujours échapper : le nom de la build est saisi par un utilisateur,
    # jamais fiable tel quel dans du HTML.
    og_title = html.escape(title)
    og_description = html.escape(description)
    canonical_url = f"https://pcradar.tech/build/{build_id}"
    if image_url and image_url.startswith("/"):
        image_url = SITE_URL + image_url
    og_image_tag = f'<meta property="og:image" content="{html.escape(image_url)}">' if image_url else ""

    meta_tags = f"""<title>{og_title}</title>
<meta name="description" content="{og_description}">
<link rel="canonical" href="{canonical_url}">
<meta property="og:title" content="{og_title}">
<meta property="og:description" content="{og_description}">
<meta property="og:type" content="website">
<meta property="og:url" content="{canonical_url}">
<meta property="og:site_name" content="PC Radar">
{og_image_tag}
<meta name="twitter:card" content="{'summary_large_image' if image_url else 'summary'}">"""

    page_html = page_html.replace(
        '<title>Configuration partagée — PC Radar</title>\n'
        '<meta name="description" content="Découvrez cette configuration PC partagée sur PC Radar, avec vérification de compatibilité automatique.">',
        meta_tags, 1,
    )
    return HTMLResponse(content=page_html)


# Catalogue léger (sans le contenu des images) gardé en mémoire : relu en
# base au plus toutes les CATALOG_CACHE_SECONDS. Avant, chaque visite du
# configurateur relisait la base, sérialisait ~2,8 Mo de JSON et les
# compressait : 3 requêtes/s au mieux, 13 s d'attente à 40 visiteurs
# simultanés. Le JSON est préparé une fois, déjà compressé, avec un ETag.
CATALOG_CACHE_SECONDS = 60
_CATALOG = {"at": 0.0, "components": None, "body": b"", "gzip": b"", "etag": ""}
_CATALOG_LOCK = threading.Lock()


def _state_get(cle, defaut):
    """Valeur JSON gardée dans app_state (corrections admin...), ou `defaut`."""
    client = get_client()
    try:
        rows = client.execute("SELECT valeur FROM app_state WHERE cle = ?", [cle]).rows
        return json.loads(rows[0][0]) if rows and rows[0][0] else defaut
    except Exception:
        return defaut
    finally:
        client.close()


def _state_set(cle, valeur):
    client = get_client()
    try:
        client.execute(
            "INSERT INTO app_state (cle, valeur) VALUES (?, ?) ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur",
            [cle, json.dumps(valeur, ensure_ascii=False)],
        )
    finally:
        client.close()


def get_catalog():
    """
    Liste légère des composants (voir get_all_components_light), partagée :
    les appelants la LISENT seulement — ne jamais modifier les dicts reçus.
    """
    if _CATALOG["components"] is not None and time.time() - _CATALOG["at"] < CATALOG_CACHE_SECONDS:
        return _CATALOG["components"]
    with _CATALOG_LOCK:
        if _CATALOG["components"] is not None and time.time() - _CATALOG["at"] < CATALOG_CACHE_SECONDS:
            return _CATALOG["components"]
        components = get_all_components_light()
        trends = _price_trends()
        for component in components:
            component["page"] = component_pages.page_url(component)
            component["tendance_prix"] = trends.get(component["id"])
        # Annonces d'un même produit regroupées en variantes (voir variantes.py),
        # avec les corrections faites depuis la page admin.
        variantes.annoter(
            components,
            rattacher={int(k): v for k, v in _state_get("variantes_rattacher", {}).items()},
            separer=set(_state_get("variantes_separer", [])),
        )
        if not components and _CATALOG["components"]:
            # Base momentanément indisponible : on garde la dernière version.
            return _CATALOG["components"]
        grouped = {}
        for component in components:
            grouped.setdefault(component["categorie"], []).append(component)
        body = json.dumps({"components": grouped}, ensure_ascii=False, separators=(",", ":")).encode()
        _CATALOG.update(
            at=time.time(), components=components, body=body,
            gzip=gzip.compress(body, compresslevel=6),
            etag='"' + hashlib.md5(body).hexdigest() + '"',
        )
        return components


def _price_trends():
    """
    Pour les badges de prix du configurateur : plus bas prix et nombre de
    relevés sur 30 jours, et dernier prix relevé avant aujourd'hui.
    """
    client = get_client()
    try:
        month = client.execute(
            "SELECT component_id, MIN(prix), COUNT(*) FROM price_history "
            "WHERE date >= date('now', '-30 days') AND prix > 0 GROUP BY component_id"
        ).rows
        previous = client.execute(
            "SELECT h.component_id, h.prix FROM price_history h "
            "JOIN (SELECT component_id, MAX(date) AS d FROM price_history WHERE date < date('now') GROUP BY component_id) last "
            "ON last.component_id = h.component_id AND last.d = h.date"
        ).rows
    except Exception as err:
        print(f"Tendances de prix indisponibles : {err}")
        return {}
    finally:
        client.close()
    trends = {row[0]: {"min_30j": row[1], "releves_30j": row[2], "precedent": None} for row in month}
    for component_id, prix in previous:
        trends.setdefault(component_id, {"min_30j": None, "releves_30j": 0, "precedent": None})["precedent"] = prix
    return trends


def invalidate_catalog():
    """Après une modification du catalogue : la prochaine lecture repasse par la base."""
    _CATALOG["at"] = 0.0


@app.get("/components")
def list_components():
    """Liste tous les composants, triés par catégorie."""
    return {"components": get_catalog()}


@app.get("/api/components")
def api_components(request: Request):
    """
    Liste les composants regroupés par catégorie pour l'interface web.

    Les images détourées sont stockées en base64 en base (souvent plusieurs
    centaines de Ko chacune) : les renvoyer inline dans ce JSON, ou même
    simplement les FAIRE TRANSITER depuis la base pour les jeter aussitôt,
    ralentit fortement cette route. Le catalogue léger ne contient donc
    jamais ce contenu — chaque composant pointe directement vers
    /api/components/{id}/image, chargée séparément (en parallèle, avec mise
    en cache navigateur) par chaque <img>.
    """
    get_catalog()
    headers = {
        "ETag": _CATALOG["etag"],
        "Cache-Control": "public, max-age=60, stale-while-revalidate=300",
        "Vary": "Accept-Encoding",
    }
    if request.headers.get("if-none-match") == _CATALOG["etag"]:
        return Response(status_code=304, headers=headers)
    if "gzip" in request.headers.get("accept-encoding", ""):
        headers["Content-Encoding"] = "gzip"
        return Response(content=_CATALOG["gzip"], media_type="application/json", headers=headers)
    return Response(content=_CATALOG["body"], media_type="application/json", headers=headers)


@app.get("/api/components/{component_id}/prix-historique")
def component_price_history(component_id: int, jours: int = 90):
    """
    Historique du prix d'un composant (un point par jour, relevé par la mise
    à jour automatique des prix), pour le graphique de la fiche détail.
    """
    jours = max(7, min(jours, 365))
    depuis = (datetime.utcnow().date() - timedelta(days=jours)).isoformat()
    client = get_client()
    try:
        rows = client.execute(
            "SELECT date, prix FROM price_history WHERE component_id = ? AND date >= ? AND prix > 0 ORDER BY date",
            [component_id, depuis],
        ).rows
        plus_bas = client.execute(
            "SELECT MIN(prix) FROM price_history WHERE component_id = ? AND prix > 0", [component_id]
        ).rows[0][0]
    finally:
        client.close()
    points = [{"date": r[0], "prix": r[1]} for r in rows]
    prix = [p["prix"] for p in points]
    return JSONResponse(
        {
            "points": points,
            "min": min(prix) if prix else None,
            "max": max(prix) if prix else None,
            "plus_bas_historique": plus_bas,
            "jours": jours,
        },
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/api/components/by-asin/{asin}")
def api_component_by_asin(asin: str):
    """
    Lookup léger par ASIN — utilisé par l'extension navigateur pour savoir
    si un produit Amazon est déjà catalogué avant de proposer de l'ajouter.
    Une requête SQL ciblée plutôt que de faire transiter tout le catalogue
    (/api/components) juste pour vérifier un seul ASIN : ça reste rapide
    même quand le catalogue grossit, contrairement à un filtrage côté
    client sur la liste complète.
    """
    client = get_client()
    try:
        result = client.execute(
            "SELECT id, categorie, nom, prix_indicatif, en_stock FROM components "
            "WHERE asin = ? COLLATE NOCASE LIMIT 1",
            [asin],
        )
    finally:
        client.close()

    if not result.rows:
        return {"exists": False}

    row = result.rows[0]
    # Infos de produit (variantes, prix suspect) tirées du catalogue en mémoire :
    # l'extension les affiche sur la page Amazon.
    produit = next((c for c in get_catalog() if c["id"] == row[0]), None) or {}
    suspect = next((p for p in _controle_courant()["prix_suspects"] if p["id"] == row[0]), None)
    return {
        "exists": True,
        "component": {
            "id": row[0],
            "categorie": row[1],
            "nom": row[2],
            "prix_indicatif": row[3],
            "en_stock": bool(row[4]),
            "variante": produit.get("variante"),
            "nb_variantes": produit.get("nb_variantes") or 1,
            "page": produit.get("page"),
            "prix_suspect": suspect,
        },
    }


# Jeton de taille des URLs d'images Amazon ("._AC_SL1500_.jpg") : le CDN
# Amazon sert n'importe quelle largeur si on le remplace, ce qui évite de
# télécharger une photo de 1500px pour une vignette de 112px.
AMAZON_SIZE_TOKEN = re.compile(r"\._[A-Za-z0-9_,]+_(\.(?:jpe?g|png|webp))$", re.IGNORECASE)
AMAZON_PLAIN_EXT = re.compile(r"(\.(?:jpe?g|png|webp))$", re.IGNORECASE)


def resize_amazon_image_url(url: str, width: int) -> str:
    if "media-amazon.com/images/" not in url:
        return url
    token = f"._AC_SL{width}_"
    if AMAZON_SIZE_TOKEN.search(url):
        return AMAZON_SIZE_TOKEN.sub(token + r"\1", url)
    return AMAZON_PLAIN_EXT.sub(token + r"\1", url)


@app.get("/api/components/{component_id}/image")
def api_component_image(component_id: int, w: int | None = None):
    """
    Sert l'image d'un composant à part, pour ne pas alourdir /api/components.
    ?w=<largeur> (vignettes) : demande à Amazon une version réduite plutôt
    que l'originale en 1500px ; sans paramètre, l'image pleine taille
    (modale de détail, zoom).
    """
    client = get_client()
    try:
        result = client.execute("SELECT image_url FROM components WHERE id = ?", [component_id])
    finally:
        client.close()

    if not result.rows or not result.rows[0][0]:
        raise HTTPException(status_code=404, detail="Image introuvable.")

    image_url = result.rows[0][0]

    if image_url.startswith("data:image/"):
        header, _, b64_data = image_url.partition(",")
        media_type = header[len("data:"):].split(";")[0] or "image/png"
        try:
            raw = base64.b64decode(b64_data)
        except ValueError:
            raise HTTPException(status_code=500, detail="Image corrompue.")
        return Response(content=raw, media_type=media_type, headers={"Cache-Control": "public, max-age=604800, immutable"})

    if image_url.startswith(("http://", "https://")):
        if w:
            image_url = resize_amazon_image_url(image_url, max(64, min(w, 1500)))
        # Cache court (1 jour) : l'URL cible peut changer si l'admin
        # remplace l'image, mais évite de refaire la redirection à chaque visite.
        return RedirectResponse(image_url, headers={"Cache-Control": "public, max-age=86400"})

    raise HTTPException(status_code=404, detail="Image introuvable.")


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
    return {"compatible": result["compatible"], "erreurs": result["errors"], "avertissements": result["warnings"]}


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
    _check_rate_limit("register", request, limit=5, window_seconds=3600)
    _record_attempt("register", request)
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
        print(f"Inscription impossible : {error}")
        raise HTTPException(status_code=500, detail="Erreur serveur, réessaie plus tard.")
    finally:
        client.close()

    request.session["user"] = {"id": user_id, "email": email}
    return {"status": "ok", "email": email}


@app.post("/api/auth/login")
def login(request: Request, payload: dict = Body(...)):
    _check_rate_limit("login", request, limit=10, window_seconds=15 * 60)
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    client = get_client()
    try:
        result = client.execute("SELECT id, password_hash FROM users WHERE email = ?", [email])
    finally:
        client.close()

    # Message volontairement générique : ne pas révéler si l'e-mail existe ou non.
    if not result.rows or not verify_password(password, result.rows[0][1]):
        _record_attempt("login", request)
        raise HTTPException(status_code=401, detail="E-mail ou mot de passe incorrect.")

    user_id = result.rows[0][0]
    request.session["user"] = {"id": user_id, "email": email}
    return {"status": "ok", "email": email}


@app.post("/api/auth/logout")
def logout(request: Request):
    request.session.pop("user", None)
    return {"status": "ok"}


def _table_exists(client, name):
    return bool(client.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", [name]).rows)


def _user_build_filter(user_id):
    # builds.user_id_optionnel est une colonne TEXT : on compare aux deux formes.
    return "(user_id_optionnel = ? OR user_id_optionnel = ?)", [user_id, str(user_id)]


@app.get("/api/auth/export")
def export_my_data(user=Depends(require_login)):
    """
    Droit à la portabilité (RGPD) : toutes les données liées au compte, en
    JSON téléchargeable. Jamais le mot de passe, même haché.
    """
    where, args = _user_build_filter(user["id"])
    client = get_client()
    try:
        def rows(sql, params):
            result = client.execute(sql, params)
            return [dict(zip(result.columns, row)) for row in result.rows]

        account = rows("SELECT email, created_at FROM users WHERE id = ?", [user["id"]])
        data = {
            "compte": account[0] if account else {"email": user["email"]},
            "configurations": rows(f"SELECT id, nom, composants_json, date FROM builds WHERE {where}", args),
            "favoris": rows("SELECT component_id, prix_ajout, prix_cible, created_at FROM favorites WHERE user_id = ?", [user["id"]]),
            "alertes_de_configuration": rows(
                "SELECT build_id, prix_reference, prix_cible, created_at FROM build_alerts WHERE user_id = ?", [user["id"]]
            ),
            "signalements_de_liens": rows(
                "SELECT component_id, vendeur, nouveau_lien, statut, date FROM link_corrections WHERE user_id = ?", [user["id"]]
            ) if _table_exists(client, "link_corrections") else [],
        }
    finally:
        client.close()
    return Response(
        content=json.dumps(data, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="mes-donnees-pc-radar.json"'},
    )


@app.delete("/api/auth/account")
def delete_my_account(request: Request, user=Depends(require_login)):
    """
    Droit à l'effacement (RGPD) : supprime le compte et tout ce qui lui est
    rattaché. Les signalements de liens déjà envoyés sont gardés pour
    l'historique de modération, mais anonymisés.
    """
    where, args = _user_build_filter(user["id"])
    client = get_client()
    try:
        build_ids = [r[0] for r in client.execute(f"SELECT id FROM builds WHERE {where}", args).rows]
        statements = [
            ("DELETE FROM favorites WHERE user_id = ?", [user["id"]]),
            ("DELETE FROM build_alerts WHERE user_id = ?", [user["id"]]),
            (f"DELETE FROM builds WHERE {where}", args),
            ("DELETE FROM users WHERE id = ?", [user["id"]]),
        ]
        statements += [("DELETE FROM build_alerts WHERE build_id = ?", [bid]) for bid in build_ids]
        if _table_exists(client, "link_corrections"):
            statements.append(
                ("UPDATE link_corrections SET user_id = 0, user_email = 'compte supprimé' WHERE user_id = ?", [user["id"]])
            )
        client.batch(statements)
    finally:
        client.close()
    request.session.clear()
    return {"status": "ok"}


@app.get("/api/auth/me")
def me(request: Request):
    user = get_current_user(request)
    return {"logged_in": user is not None, "user": user}


# ---------------------------------------------------------------------------
# Connexion avec Google (OAuth 2.0 / OpenID Connect, flux "authorization code")
#
# Aucune bibliothèque en plus : deux appels HTTP (échange du code, puis lecture
# du profil). Un compte Google se RELIE au compte existant de même e-mail
# plutôt que d'en créer un doublon : Google garantit que l'adresse lui
# appartient (email_verified), c'est la même preuve qu'une connexion par mot
# de passe. Un compte créé via Google n'a pas de mot de passe utilisable
# (marqueur GOOGLE_ONLY_PASSWORD, que verify_password() rejette toujours).
# ---------------------------------------------------------------------------
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
PUBLIC_BASE_URL = (os.getenv("PUBLIC_BASE_URL") or SITE_URL).rstrip("/")
GOOGLE_ONLY_PASSWORD = "!google"


def _safe_next_path(next_path: str | None) -> str:
    """N'accepte qu'un chemin interne ("/compte"), jamais une URL externe (redirection ouverte)."""
    if next_path and next_path.startswith("/") and not next_path.startswith("//"):
        return next_path
    return "/compte"


@app.get("/api/auth/providers")
def auth_providers():
    """Le front n'affiche le bouton Google que si les identifiants OAuth sont configurés."""
    return {"google": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)}


@app.get("/api/auth/google/login")
def google_login(request: Request, next: str | None = None):
    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET):
        raise HTTPException(status_code=503, detail="Connexion Google non configurée.")
    state = secrets.token_urlsafe(24)
    request.session["google_oauth_state"] = state
    request.session["google_oauth_next"] = _safe_next_path(next)
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": f"{PUBLIC_BASE_URL}/api/auth/google/callback",
        "response_type": "code",
        "scope": "openid email",
        "state": state,
        "prompt": "select_account",
    }
    return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))


@app.get("/api/auth/google/callback")
def google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    expected_state = request.session.pop("google_oauth_state", None)
    next_path = _safe_next_path(request.session.pop("google_oauth_next", None))

    # Refus de l'utilisateur sur l'écran Google, ou state absent/différent
    # (lien rejoué, session expirée, tentative CSRF) : retour au compte avec
    # un code d'erreur que la page affiche, jamais une page d'erreur brute.
    if error or not code or not expected_state or not secrets.compare_digest(state, expected_state):
        return RedirectResponse("/compte?google=erreur")

    try:
        token_res = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": f"{PUBLIC_BASE_URL}/api/auth/google/callback",
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
        token_res.raise_for_status()
        access_token = token_res.json().get("access_token")
        profile_res = requests.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        profile_res.raise_for_status()
        profile = profile_res.json()
    except (requests.RequestException, ValueError) as err:
        print(f"Connexion Google échouée : {err}")
        return RedirectResponse("/compte?google=erreur")

    email = (profile.get("email") or "").strip().lower()
    if not email or not profile.get("email_verified"):
        return RedirectResponse("/compte?google=non-verifie")

    client = get_client()
    try:
        existing = client.execute("SELECT id FROM users WHERE email = ?", [email])
        if existing.rows:
            user_id = existing.rows[0][0]
        else:
            client.execute(
                "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                [email, GOOGLE_ONLY_PASSWORD, datetime.utcnow().isoformat()],
            )
            user_id = client.execute("SELECT id FROM users WHERE email = ?", [email]).rows[0][0]
    finally:
        client.close()

    request.session["user"] = {"id": user_id, "email": email}
    return RedirectResponse(next_path)


# ---------------------------------------------------------------------------
# Favoris, suivi de prix et alertes
#
# - favorites : un composant suivi par un compte, avec le prix au moment de
#   l'ajout (pour afficher l'évolution) et un prix cible optionnel (alerte).
# - price_history : un point par composant et par jour, alimenté par le
#   rafraîchissement des prix (_apply_amazon_price_info).
# - builds.prix_total_sauvegarde : total au moment de la sauvegarde, pour
#   afficher "−42 € depuis ta sauvegarde".
# Tables créées au démarrage si absentes : pas de migration manuelle à lancer.
# ---------------------------------------------------------------------------
# Vrai seulement une fois la colonne builds.prix_total_sauvegarde confirmée :
# sans elle, les routes builds gardent leurs requêtes d'origine plutôt que
# de casser la sauvegarde (fonction centrale) pour une information bonus.
BUILDS_HAVE_SAVED_TOTAL = False


@app.on_event("startup")
def ensure_account_feature_tables():
    with ProcessLock("demarrage"):
        _ensure_account_feature_tables()


def _ensure_account_feature_tables():
    global BUILDS_HAVE_SAVED_TOTAL
    client = get_client()
    try:
        client.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                component_id INTEGER NOT NULL,
                prix_ajout REAL,
                prix_cible REAL,
                derniere_alerte_prix REAL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, component_id)
            )
        """)
        client.execute("""
            CREATE TABLE IF NOT EXISTS auth_attempts (
                bucket TEXT NOT NULL,
                ip TEXT NOT NULL,
                ts REAL NOT NULL
            )
        """)
        client.execute("CREATE INDEX IF NOT EXISTS idx_auth_attempts ON auth_attempts (bucket, ip, ts)")
        client.execute("""
            CREATE TABLE IF NOT EXISTS app_state (
                cle TEXT PRIMARY KEY,
                valeur TEXT
            )
        """)
        client.execute("""
            CREATE TABLE IF NOT EXISTS api_usage (
                mois TEXT NOT NULL,
                fournisseur TEXT NOT NULL,
                appels INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (mois, fournisseur)
            )
        """)
        client.execute("""
            CREATE TABLE IF NOT EXISTS build_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                build_id INTEGER NOT NULL,
                prix_reference REAL,
                prix_cible REAL,
                derniere_alerte_prix REAL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, build_id)
            )
        """)
        client.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                component_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                prix REAL NOT NULL,
                PRIMARY KEY (component_id, date)
            )
        """)
        build_columns = [row[1] for row in client.execute("PRAGMA table_info(builds)").rows]
        if build_columns and "prix_total_sauvegarde" not in build_columns:
            client.execute("ALTER TABLE builds ADD COLUMN prix_total_sauvegarde REAL")
        BUILDS_HAVE_SAVED_TOTAL = bool(build_columns)
    except Exception as err:
        # Ne bloque jamais le démarrage du site pour une fonction secondaire.
        print(f"Préparation des tables favoris/historique échouée : {err}")
    finally:
        client.close()


def _component_price(client, component_id: int):
    result = client.execute("SELECT prix_indicatif FROM components WHERE id = ?", [component_id])
    if not result.rows:
        return None
    prix = result.rows[0][0]
    return float(prix) if prix else None


def _parse_price(value):
    if value in (None, ""):
        return None
    try:
        prix = round(float(value), 2)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Prix invalide.")
    if prix <= 0:
        raise HTTPException(status_code=400, detail="Le prix doit être positif.")
    return prix


@app.get("/api/favorites")
def list_favorites(user=Depends(require_login)):
    client = get_client()
    try:
        rows = client.execute(
            "SELECT f.component_id, f.prix_ajout, f.prix_cible, f.created_at, "
            "c.nom, c.categorie, c.prix_indicatif, c.has_image, c.en_stock, c.prix_marche_json, "
            "(SELECT MIN(h.prix) FROM price_history h "
            " WHERE h.component_id = f.component_id AND h.date >= substr(f.created_at, 1, 10)) "
            "FROM favorites f JOIN components c ON c.id = f.component_id "
            "WHERE f.user_id = ? ORDER BY f.created_at DESC",
            [user["id"]],
        ).rows
    finally:
        client.close()

    favorites = []
    for row in rows:
        prix_marche = json.loads(row[9]) if row[9] else []
        prix_valides = [p for p in prix_marche if p.get("prix") and not p.get("lien_mort")]
        meilleur = min(prix_valides, key=lambda p: p["prix"]) if prix_valides else None
        prix_actuel = float(row[6]) if row[6] else None
        plus_bas = min(p for p in (row[10], prix_actuel) if p) if (row[10] or prix_actuel) else None
        favorites.append({
            "component_id": row[0],
            "prix_ajout": row[1],
            "prix_cible": row[2],
            "suivi_depuis": row[3],
            "nom": row[4],
            "categorie": row[5],
            "prix_actuel": prix_actuel,
            "prix_plus_bas": plus_bas,
            "image_url": f"/api/components/{row[0]}/image" if row[7] else None,
            "en_stock": bool(row[8]),
            "meilleure_offre": meilleur,
        })
    return {"favorites": favorites}


@app.post("/api/favorites")
def add_favorite(payload: dict = Body(...), user=Depends(require_login)):
    try:
        component_id = int(payload.get("component_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="component_id invalide.")
    prix_cible = _parse_price(payload.get("prix_cible"))

    client = get_client()
    try:
        exists = client.execute("SELECT 1 FROM components WHERE id = ?", [component_id])
        if not exists.rows:
            raise HTTPException(status_code=404, detail="Composant introuvable.")
        client.execute(
            "INSERT OR IGNORE INTO favorites (user_id, component_id, prix_ajout, prix_cible, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [user["id"], component_id, _component_price(client, component_id), prix_cible, datetime.utcnow().isoformat()],
        )
    finally:
        client.close()
    return {"status": "ok"}


@app.patch("/api/favorites/{component_id}")
def update_favorite(component_id: int, payload: dict = Body(...), user=Depends(require_login)):
    """Change (ou retire, avec null) le prix cible. Réarme l'alerte au passage."""
    prix_cible = _parse_price(payload.get("prix_cible"))
    client = get_client()
    try:
        client.execute(
            "UPDATE favorites SET prix_cible = ?, derniere_alerte_prix = NULL WHERE user_id = ? AND component_id = ?",
            [prix_cible, user["id"], component_id],
        )
    finally:
        client.close()
    return {"status": "ok", "prix_cible": prix_cible}


@app.delete("/api/favorites/{component_id}")
def delete_favorite(component_id: int, user=Depends(require_login)):
    client = get_client()
    try:
        client.execute("DELETE FROM favorites WHERE user_id = ? AND component_id = ?", [user["id"], component_id])
    finally:
        client.close()
    return {"status": "ok"}


# Envoi d'e-mails : n'importe quel SMTP (Gmail avec mot de passe
# d'application, Brevo gratuit...). Non configuré = alertes simplement
# désactivées, le reste du suivi de prix fonctionne quand même.
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "") or SMTP_USER


def send_email(to: str, subject: str, text: str, html_body: str | None = None) -> bool:
    if not (SMTP_HOST and SMTP_FROM):
        return False
    import smtplib
    from email.message import EmailMessage

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"PC Radar <{SMTP_FROM}>"
    message["To"] = to
    message.set_content(text)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
            smtp.starttls()
            if SMTP_USER:
                smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.send_message(message)
        return True
    except Exception as err:
        print(f"Envoi d'e-mail à {to} échoué : {err}")
        return False


def _affiliate_amazon_link(url: str | None) -> str | None:
    if not url or "amazon." not in url or not AMAZON_ASSOCIATE_TAG:
        return url
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query))
    query["tag"] = AMAZON_ASSOCIATE_TAG
    return parsed._replace(query=urlencode(query)).geturl()


def record_price_and_notify(client, component_id: int, nom: str, prix: float, lien: str | None):
    """
    Appelé après chaque nouveau prix relevé : ajoute le point du jour à
    l'historique, puis prévient les comptes dont le prix cible est atteint.
    Une alerte n'est renvoyée que si le prix baisse ENCORE sous le dernier
    prix signalé (pas un e-mail par jour tant qu'il reste sous la cible) ;
    si le prix remonte au-dessus de la cible, l'alerte est réarmée.
    Ne lève jamais d'erreur : le rafraîchissement des prix passe avant.
    """
    try:
        client.execute(
            "INSERT OR REPLACE INTO price_history (component_id, date, prix) VALUES (?, ?, ?)",
            [component_id, datetime.utcnow().date().isoformat(), prix],
        )
        client.execute(
            "UPDATE favorites SET derniere_alerte_prix = NULL "
            "WHERE component_id = ? AND prix_cible IS NOT NULL AND ? > prix_cible",
            [component_id, prix],
        )
        due = client.execute(
            "SELECT f.id, u.email, f.prix_cible FROM favorites f JOIN users u ON u.id = f.user_id "
            "WHERE f.component_id = ? AND f.prix_cible IS NOT NULL AND ? <= f.prix_cible "
            "AND (f.derniere_alerte_prix IS NULL OR ? < f.derniere_alerte_prix)",
            [component_id, prix, prix],
        ).rows
    except Exception as err:
        print(f"Historique/alertes de prix ignorés pour {component_id} : {err}")
        return

    lien_affilie = _affiliate_amazon_link(lien)
    prix_txt = f"{prix:.2f}".replace(".", ",") + " €"
    for favorite_id, email, prix_cible in due:
        cible_txt = f"{prix_cible:.2f}".replace(".", ",") + " €"
        text = (
            f"Bonne nouvelle : {nom} est passé à {prix_txt}, sous ton prix cible de {cible_txt}.\n\n"
            + (f"Voir l'offre : {lien_affilie}\n\n" if lien_affilie else "")
            + f"Gérer tes alertes : {PUBLIC_BASE_URL}/compte\n"
            "Les prix changent vite, vérifie-le sur la page du vendeur avant d'acheter."
        )
        html_body = (
            f"<p>Bonne nouvelle : <strong>{html.escape(nom)}</strong> est passé à "
            f"<strong>{prix_txt}</strong>, sous ton prix cible de {cible_txt}.</p>"
            + (f'<p><a href="{html.escape(lien_affilie)}">Voir l\'offre</a></p>' if lien_affilie else "")
            + f'<p style="color:#666;font-size:13px">Les prix changent vite, vérifie-le avant d\'acheter. '
            f'<a href="{PUBLIC_BASE_URL}/compte">Gérer mes alertes</a></p>'
        )
        if send_email(email, f"Baisse de prix : {nom} à {prix_txt}", text, html_body):
            try:
                client.execute("UPDATE favorites SET derniere_alerte_prix = ? WHERE id = ?", [prix, favorite_id])
            except Exception as err:
                print(f"Alerte envoyée mais non enregistrée ({favorite_id}) : {err}")


def _build_total(client, composants: dict):
    """Somme des prix actuels (prix_indicatif) des composants d'un build, calculée côté serveur."""
    ids = []
    for value in (composants or {}).values():
        for item in (value if isinstance(value, list) else [value]):
            try:
                ids.append(int(item))
            except (TypeError, ValueError):
                pass
    if not ids:
        return None
    placeholders = ",".join("?" for _ in ids)
    rows = client.execute(f"SELECT id, prix_indicatif FROM components WHERE id IN ({placeholders})", ids).rows
    prix_par_id = {row[0]: float(row[1] or 0) for row in rows}
    return round(sum(prix_par_id.get(i, 0) for i in ids), 2)


# ---------------------------------------------------------------------------
# Suivi du prix d'une configuration entière (alerte e-mail sur le TOTAL)
# ---------------------------------------------------------------------------
def _owned_build(client, build_id: int, user_id):
    """Composants d'un build appartenant au compte, ou HTTPException."""
    rows = client.execute("SELECT user_id_optionnel, composants_json FROM builds WHERE id = ?", [build_id]).rows
    if not rows:
        raise HTTPException(status_code=404, detail="Configuration introuvable.")
    if str(rows[0][0]) != str(user_id):
        raise HTTPException(status_code=403, detail="Cette configuration ne t'appartient pas.")
    return json.loads(rows[0][1] or "{}")


@app.put("/api/builds/{build_id}/alerte")
def set_build_alert(build_id: int, payload: dict = Body(...), user=Depends(require_login)):
    """Active (ou modifie) le suivi du prix total d'une configuration. Réarme l'alerte."""
    prix_cible = _parse_price(payload.get("prix_cible"))
    if prix_cible is None:
        raise HTTPException(status_code=400, detail="Indique un prix cible pour la configuration.")
    client = get_client()
    try:
        composants = _owned_build(client, build_id, user["id"])
        total = _build_total(client, composants)
        client.execute(
            "INSERT INTO build_alerts (user_id, build_id, prix_reference, prix_cible, created_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id, build_id) DO UPDATE SET prix_cible = excluded.prix_cible, derniere_alerte_prix = NULL",
            [user["id"], build_id, total, prix_cible, datetime.utcnow().isoformat()],
        )
    finally:
        client.close()
    return {"status": "ok", "prix_cible": prix_cible, "prix_actuel": total}


@app.delete("/api/builds/{build_id}/alerte")
def delete_build_alert(build_id: int, user=Depends(require_login)):
    client = get_client()
    try:
        client.execute("DELETE FROM build_alerts WHERE user_id = ? AND build_id = ?", [user["id"], build_id])
    finally:
        client.close()
    return {"status": "ok"}


def check_build_alerts():
    """
    Après une mise à jour des prix : prévient les comptes dont une
    configuration suivie est passée sous son prix cible. Même logique que les
    alertes par composant : un e-mail par nouvelle baisse, réarmé si le total
    remonte au-dessus de la cible. Ne lève jamais d'erreur.
    """
    client = get_client()
    try:
        alerts = client.execute(
            "SELECT a.id, a.prix_cible, a.derniere_alerte_prix, u.email, b.id, b.nom, b.composants_json "
            "FROM build_alerts a JOIN users u ON u.id = a.user_id JOIN builds b ON b.id = a.build_id"
        ).rows
        sent = 0
        for alert_id, prix_cible, derniere, email, build_id, nom, composants_json in alerts:
            composants = json.loads(composants_json or "{}")
            total = _build_total(client, composants)
            if total is None:
                continue
            if total > prix_cible:
                if derniere is not None:
                    client.execute("UPDATE build_alerts SET derniere_alerte_prix = NULL WHERE id = ?", [alert_id])
                continue
            if derniere is not None and total >= derniere:
                continue
            ids = [int(i) for v in composants.values() for i in (v if isinstance(v, list) else [v]) if str(i).isdigit()]
            pieces = []
            if ids:
                placeholders = ",".join("?" for _ in ids)
                pieces = client.execute(
                    f"SELECT categorie, nom, prix_indicatif FROM components WHERE id IN ({placeholders}) ORDER BY categorie",
                    ids,
                ).rows
            euros = lambda v: f"{v:.2f}".replace(".", ",") + " €"
            lignes = "\n".join(f"  - {cat} : {n} ({euros(p or 0)})" for cat, n, p in pieces)
            lien_build = f"{PUBLIC_BASE_URL}/build/{build_id}"
            text = (
                f"Bonne nouvelle : ta configuration « {nom} » coûte maintenant {euros(total)}, "
                f"sous ton prix cible de {euros(prix_cible)}.\n\n{lignes}\n\n"
                f"Voir la configuration : {lien_build}\n"
                f"Gérer tes alertes : {PUBLIC_BASE_URL}/compte\n"
                "Les prix changent vite, vérifie-les sur la page du vendeur avant d'acheter."
            )
            html_body = (
                f"<p>Bonne nouvelle : ta configuration <strong>{html.escape(nom)}</strong> coûte maintenant "
                f"<strong>{euros(total)}</strong>, sous ton prix cible de {euros(prix_cible)}.</p><ul>"
                + "".join(f"<li>{html.escape(cat)} : {html.escape(n)} ({euros(p or 0)})</li>" for cat, n, p in pieces)
                + f'</ul><p><a href="{lien_build}">Voir la configuration</a></p>'
                f'<p style="color:#666;font-size:13px">Les prix changent vite, vérifie-les avant d\'acheter. '
                f'<a href="{PUBLIC_BASE_URL}/compte">Gérer mes alertes</a></p>'
            )
            if send_email(email, f"Baisse de prix : ta config « {nom} » à {euros(total)}", text, html_body):
                client.execute("UPDATE build_alerts SET derniere_alerte_prix = ? WHERE id = ?", [total, alert_id])
                sent += 1
        if sent:
            print(f"Alertes configurations : {sent} e-mail(s) envoyé(s).")
    except Exception as err:
        print(f"Vérification des alertes de configurations échouée : {err}")
    finally:
        client.close()


def _build_payload(payload: dict):
    """Nom et composants d'une build envoyée par un visiteur, bornés : une
    build tient en quelques centaines d'octets, rien ne justifie d'en stocker
    davantage."""
    nom = str(payload.get("nom") or "Configuration sans nom").strip()[:120] or "Configuration sans nom"
    composants = payload.get("composants_json", {})
    if not isinstance(composants, dict):
        raise HTTPException(status_code=400, detail="Composants invalides.")
    composants_json = json.dumps(composants)
    if len(composants_json) > 20000:
        raise HTTPException(status_code=413, detail="Configuration trop volumineuse.")
    return nom, composants_json


@app.post("/api/builds")
def save_build(payload: dict = Body(...), user=Depends(require_login)):
    """Sauvegarde une configuration dans la table builds, liée au compte connecté."""
    nom, composants_json = _build_payload(payload)
    date = datetime.utcnow().isoformat()

    client = get_client()
    try:
        # RETURNING plutôt qu'un SELECT last_insert_rowid() séparé après
        # coup : constaté en pratique que ce dernier renvoie 0 (pas l'ID
        # réel) sur cette connexion Turso distante — chaque .execute() peut
        # ne pas partager le même état de session SQLite, alors que
        # last_insert_rowid() est justement une fonction PAR CONNEXION. Le
        # bug se traduisait par un lien "Voir la fiche partageable" pointant
        # vers un ID inexistant (souvent 0), d'où le "Configuration
        # introuvable" au clic. RETURNING élimine le problème à la racine :
        # l'ID vient de la MÊME requête que l'insertion.
        if BUILDS_HAVE_SAVED_TOTAL:
            result = client.execute(
                "INSERT INTO builds (user_id_optionnel, nom, composants_json, date, prix_total_sauvegarde) "
                "VALUES (?, ?, ?, ?, ?) RETURNING id",
                [user["id"], nom, composants_json, date, _build_total(client, payload.get("composants_json", {}))],
            )
        else:
            result = client.execute(
                "INSERT INTO builds (user_id_optionnel, nom, composants_json, date) "
                "VALUES (?, ?, ?, ?) RETURNING id",
                [user["id"], nom, composants_json, date],
            )
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
    nom, composants_json = _build_payload(payload)

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

        if BUILDS_HAVE_SAVED_TOTAL:
            client.execute(
                "UPDATE builds SET nom = ?, composants_json = ?, date = ?, prix_total_sauvegarde = ? WHERE id = ?",
                [nom, composants_json, datetime.utcnow().isoformat(),
                 _build_total(client, payload.get("composants_json", {})), build_id],
            )
        else:
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
        client.execute("DELETE FROM build_alerts WHERE build_id = ?", [build_id])
        return {"status": "ok", "message": "Configuration supprimée."}
    finally:
        client.close()


@app.get("/api/builds")
def list_builds(user=Depends(require_login)):
    """Retourne UNIQUEMENT les builds du compte connecté, les plus récents d'abord."""
    client = get_client()
    try:
        result = client.execute(
            "SELECT id, user_id_optionnel, nom, composants_json, date, "
            + ("prix_total_sauvegarde " if BUILDS_HAVE_SAVED_TOTAL else "NULL ")
            + "FROM builds WHERE user_id_optionnel = ? ORDER BY date DESC",
            [user["id"]],
        )
        alertes = {}
        try:
            for build_id, prix_cible, prix_reference in client.execute(
                "SELECT build_id, prix_cible, prix_reference FROM build_alerts WHERE user_id = ?", [user["id"]]
            ).rows:
                alertes[build_id] = {"prix_cible": prix_cible, "prix_reference": prix_reference}
        except Exception:
            pass  # table absente : le suivi est simplement inactif
        builds = [
            {
                "id": row[0],
                "user_id_optionnel": row[1],
                "nom": row[2],
                "composants_json": json.loads(row[3]),
                "date": row[4],
                "prix_total_sauvegarde": row[5],
                "alerte": alertes.get(row[0]),
            }
            for row in result.rows
        ]
        return {"status": "ok", "count": len(builds), "builds": builds}
    finally:
        client.close()


FEATURED_CACHE = {"at": 0.0, "data": None}
FEATURED_CACHE_SECONDS = 30 * 60
FEATURED_LOCK = threading.Lock()


@app.get("/api/configs-vedette")
def featured_configs():
    """
    Configurations de la page d'accueil, recalculées depuis le catalogue en
    stock et ses prix du moment (voir featured_builds.py). Le calcul parcourt
    toutes les paires CPU/GPU (quelques secondes) : une fois le cache rempli,
    un visiteur reçoit toujours la dernière version tout de suite, et le
    recalcul se fait en arrière-plan quand elle a plus de 30 min.
    """
    if FEATURED_CACHE["data"] is not None:
        if time.time() - FEATURED_CACHE["at"] >= FEATURED_CACHE_SECONDS and FEATURED_LOCK.acquire(blocking=False):
            def refresh():
                try:
                    _compute_featured_configs()
                finally:
                    FEATURED_LOCK.release()
            threading.Thread(target=refresh, daemon=True).start()
        return FEATURED_CACHE["data"]
    with FEATURED_LOCK:
        if FEATURED_CACHE["data"] is None:
            _compute_featured_configs()
    return FEATURED_CACHE["data"] or {"status": "ok", "nb_composants": 0, "configs": []}


def _compute_featured_configs():
    components = get_catalog()
    configs = []
    for profile in featured_builds.PROFILES:
        try:
            built = featured_builds.build_profile(components, profile)
        except Exception as error:
            print(f"Config vedette {profile['id']} impossible : {error}")
            built = None
        if not built:
            continue
        parts = built["parts"]
        fps = []
        estimation = _run_fps_estimation(list(parts.values()), featured_builds.SHOWCASE_GAMES, profile["qualite"])
        for r in (estimation or {}).get("resultats", []):
            if r.get("couvert"):
                fps.append({"jeu": r["jeu"], "fps": r["resolutions"][profile["resolution"]]["fps"]})
        configs.append({
            "id": profile["id"],
            "titre": profile["titre"],
            "onglet": profile["onglet"],
            "guide": f"/guides/{guides.SLUG_BY_PROFILE[profile['id']]}",
            "usage": profile["usage"],
            "budget": profile["budget"],
            "resolution": profile["resolution"],
            "qualite": fps_data.QUALITY_PRESETS[profile["qualite"]]["label"],
            "total": built["total"],
            "compatible": built["compatible"],
            "fps": fps,
            "composants_json": {cat: c["id"] for cat, c in parts.items()},
            "composants": [
                {"categorie": cat, "id": c["id"], "nom": c["nom"], "prix": c["prix_indicatif"],
                 "image_url": c.get("image_url"), "image_processed": c.get("image_processed", False)}
                for cat, c in parts.items()
            ],
        })
    data = {"status": "ok", "nb_composants": len(components), "configs": configs}
    if configs:
        FEATURED_CACHE.update(at=time.time(), data=data)


def _component_price_stats(component_id):
    client = get_client()
    try:
        row = client.execute(
            "SELECT MIN(prix), COUNT(*), MIN(date) FROM price_history WHERE component_id = ? AND prix > 0",
            [component_id],
        ).rows[0]
    finally:
        client.close()
    if not row[1]:
        return None
    y, m, d = row[2].split("-")
    return {"min": row[0], "n": row[1], "depuis": f"{d}/{m}/{y}"}


def _component_fps_block(component, catalog):
    """FPS d'une carte graphique avec le meilleur processeur en stock (et inversement)."""
    cat = component["categorie"]
    if cat not in ("CPU", "GPU"):
        return None
    other_cat = "GPU" if cat == "CPU" else "CPU"
    partners = [c for c in catalog if c["categorie"] == other_cat and c.get("en_stock") and c.get("perf_index")]
    if not partners:
        return None
    partner = max(partners, key=lambda c: c["perf_index"])
    result = _run_fps_estimation([component, partner], component_pages.FPS_GAMES, "ultra")
    if not result or not any(r.get("couvert") for r in result.get("resultats", [])):
        return None
    result["contexte"] = (
        f"Avec un {partner['nom']}, processeur haut de gamme qui ne bride pas la carte graphique."
        if cat == "GPU" else
        f"Avec une {partner['nom']}, pour montrer la limite propre au processeur (surtout visible en 1080p)."
    )
    return result


def _affiliate(url, vendeur):
    return component_pages.affiliate_url(url, vendeur, AMAZON_ASSOCIATE_TAG, AWIN_PUBLISHER_ID, AWIN_MERCHANT_IDS)


@app.get("/composants")
def components_index_page():
    return HTMLResponse(component_pages.render_index(get_catalog()))


@app.get("/composants/{category_slug}")
def components_category_page(category_slug: str):
    categorie = component_pages.CATEGORY_BY_SLUG.get(category_slug)
    if not categorie:
        raise HTTPException(status_code=404, detail="Catégorie introuvable.")
    items = [c for c in get_catalog() if c["categorie"] == categorie]
    return HTMLResponse(component_pages.render_category(categorie, items))


@app.get("/composant/{id_slug}")
def component_page(id_slug: str):
    """Fiche d'un composant ; l'adresse canonique contient son nom (redirection sinon)."""
    match = re.match(r"^(\d+)", id_slug)
    catalog = get_catalog()
    component = next((c for c in catalog if match and c["id"] == int(match.group(1))), None)
    if not component:
        raise HTTPException(status_code=404, detail="Composant introuvable.")
    canonical = component_pages.page_url(component)
    if f"/composant/{id_slug}" != canonical:
        return RedirectResponse(canonical, status_code=301)
    return HTMLResponse(component_pages.render_component(
        component, catalog, _component_fps_block(component, catalog),
        _component_price_stats(component["id"]), _affiliate,
    ))


def _best_in_stock(catalog, categorie):
    pool = [c for c in catalog if c["categorie"] == categorie and c.get("en_stock") and c.get("perf_index")]
    return max(pool, key=lambda c: c["perf_index"]) if pool else None


@app.get("/comparer")
def comparisons_index_page():
    return HTMLResponse(comparisons.render_index(comparisons.pairs(get_catalog())))


@app.get("/comparer/{slug}")
def comparison_page(slug: str):
    catalog = get_catalog()
    all_pairs = comparisons.pairs(catalog)
    pair = next((p for p in all_pairs if p["slug"] == slug), None)
    if not pair:
        raise HTTPException(status_code=404, detail="Comparatif introuvable.")
    partner = _best_in_stock(catalog, "CPU" if pair["kind"] == "GPU" else "GPU")
    fps_for = lambda component, other: (
        _run_fps_estimation([component, other], component_pages.FPS_GAMES, "ultra") if other else None
    )
    return HTMLResponse(comparisons.render_pair(pair, all_pairs, fps_for, partner))


@app.get("/guides")
def guides_index_page():
    configs = featured_configs().get("configs", [])
    if not configs:
        raise HTTPException(status_code=503, detail="Guides momentanément indisponibles.")
    return HTMLResponse(guides.render_index(configs))


@app.get("/guides/{slug}")
def guide_page(slug: str):
    """Guide d'achat d'une config du moment, rendu côté serveur (voir guides.py)."""
    profile_id = guides.GUIDES.get(slug)
    if not profile_id:
        raise HTTPException(status_code=404, detail="Guide introuvable.")
    configs = featured_configs().get("configs", [])
    config = next((c for c in configs if c["id"] == profile_id), None)
    if not config:
        raise HTTPException(status_code=503, detail="Guide momentanément indisponible.")
    catalog_by_id = {c["id"]: c for c in get_catalog()}
    return HTMLResponse(guides.render_guide(config, configs, catalog_by_id))


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


def require_admin(request: Request, x_admin_secret: str = Header(default="")):
    """
    Dépendance FastAPI : protège les routes admin avec un secret partagé
    (ADMIN_SECRET dans .env / fly secrets). Fail-closed : si le secret n'est
    pas configuré côté serveur, l'accès est refusé plutôt qu'ouvert à tous.
    """
    _check_rate_limit("admin", request, limit=10, window_seconds=15 * 60)
    if not ADMIN_SECRET or not secrets.compare_digest(x_admin_secret.encode(), ADMIN_SECRET.encode()):
        _record_attempt("admin", request)
        raise HTTPException(status_code=401, detail="Accès admin refusé.")


@app.get("/admin")
def admin_page():
    """Page d'administration pour coller et ajouter des composants."""
    return FileResponse("static/admin.html")


@app.get("/api/admin/verify")
def admin_verify(_admin=Depends(require_admin)):
    """Simple endpoint pour vérifier le mot de passe admin avant d'afficher le formulaire."""
    return {"status": "ok"}


EXTENSION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser-extension")


@app.get("/api/admin/extension.zip")
def admin_extension_zip(_admin=Depends(require_admin)):
    """L'extension PC Radar en .zip, construite à la volée depuis
    browser-extension/ : toujours la version déployée, sans fichier à tenir
    à jour à la main."""
    import io, zipfile
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for root, _dirs, files in os.walk(EXTENSION_DIR):
            for name in sorted(files):
                path = os.path.join(root, name)
                archive.write(path, os.path.relpath(path, EXTENSION_DIR))
    try:
        with open(os.path.join(EXTENSION_DIR, "manifest.json"), encoding="utf-8") as f:
            version = json.load(f).get("version", "")
    except Exception:
        version = ""
    filename = f"pc-radar-extension-{version}.zip" if version else "pc-radar-extension.zip"
    return Response(buffer.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})


@app.get("/api/admin/components")
def admin_list_components(_admin=Depends(require_admin)):
    """
    Version admin de /api/components : renvoie la VRAIE image_url stockée
    (http(s)://... ou data:image/...), jamais le chemin proxy
    (/api/components/{id}/image) que renvoie la version publique allégée
    pour ménager la bande passante des cartes produit. Sans cette distinction,
    le panneau admin préremplissait son champ "image_url" à l'édition avec
    ce chemin proxy — une valeur qui ne passe PAS la validation stricte de
    schema.validate_component (elle exige http(s):// ou data:image/), d'où
    un rejet ("Erreurs de validation, rien n'a été modifié") dès qu'on
    modifiait un composant sans re-choisir son image à chaque fois.
    """
    infos = {c["id"]: c for c in get_catalog()}
    suspects = {x["id"] for x in _controle_courant()["prix_suspects"]}
    components = get_all_components()
    for c in components:
        info = infos.get(c["id"], {})
        c["variante"] = info.get("variante")
        c["nb_variantes"] = info.get("nb_variantes") or 1
        c["groupe_id"] = info.get("groupe_id", c["id"])
        c["page"] = info.get("page")
        c["prix_suspect"] = c["id"] in suspects
    return {"components": components}


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

            has_image = 1 if image_url else 0

            # Un ASIN renseigné mais sans le moindre relevé "Amazon" dans
            # prix_marche veut dire que la fiche était indisponible au
            # moment de la récupération (voir fetchAndSaveOneAsin côté
            # admin.html) — le composant doit démarrer épuisé plutôt
            # qu'"en stock" par défaut. Sans ASIN (composant saisi
            # entièrement à la main, sans passer par Amazon), ce signal ne
            # s'applique pas : on laisse en_stock à 1.
            en_stock = 0 if asin and not component.get("prix_marche") else 1

            existing_id = existing_ids.get((categorie, nom))
            if existing_id is not None:
                statements.append((
                    "UPDATE components SET specs_json = ?, prix_indicatif = ?, prix_marche_json = ?, image_url = ?, has_image = ?, asin = ?, amazon_details_json = ?, description = ?, en_stock = ? WHERE id = ?",
                    [specs_json, prix, prix_marche_json, image_url, has_image, asin, amazon_details_json, description, en_stock, existing_id],
                ))
                updated += 1
            else:
                statements.append((
                    "INSERT INTO components (categorie, nom, specs_json, prix_indicatif, prix_marche_json, image_url, has_image, asin, amazon_details_json, description, en_stock) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [categorie, nom, specs_json, prix, prix_marche_json, image_url, has_image, asin, amazon_details_json, description, en_stock],
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

        # Même règle qu'à la création (voir admin_add_components) : un ASIN
        # sans le moindre relevé "Amazon" veut dire fiche indisponible au
        # dernier passage, pas "en stock" par défaut.
        en_stock = 0 if asin and not payload.get("prix_marche") else 1

        client.execute(
            "UPDATE components SET categorie = ?, nom = ?, specs_json = ?, prix_indicatif = ?, "
            "prix_marche_json = ?, image_url = ?, has_image = ?, asin = ?, amazon_details_json = ?, description = ?, en_stock = ? WHERE id = ?",
            [payload["categorie"], payload["nom"], specs_json, payload["prix_indicatif"],
             prix_marche_json, image_url, 1 if image_url else 0, asin, amazon_details_json, description, en_stock, component_id],
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


# Le tableau "Détails du produit" Amazon écrit le même socket de façons
# différentes selon le vendeur ("AM4", "Socket AM4", "LGA 1700", "LGA1700"...)
# — sans normalisation ici, ces variantes cassaient silencieusement la
# comparaison stricte cpu["socket"] != carte_mere["socket"] de
# compatibility.py (constaté en pratique : un vrai faux-positif "socket
# incompatible" sur une paire AM4/AM4, la valeur brute Amazon pour la CM
# valant "Socket AM4" au lieu de "AM4"). Toute valeur de socket dérivée
# depuis Amazon passe maintenant par cette normalisation avant d'être
# stockée, pour que les futurs imports n'introduisent plus cet écart.
def _normalize_socket_value(raw):
    sl = raw.strip().lower()
    if "am4" in sl: return "AM4"
    if "am5" in sl: return "AM5"
    if "str5" in sl: return "sTR5"
    if "1151" in sl: return "LGA1151"
    if "1200" in sl: return "LGA1200"
    if "1700" in sl: return "LGA1700"
    if "1851" in sl: return "LGA1851"
    return raw.strip()  # forme inconnue : gardée telle quelle plutôt que perdue


def _normalize_format_value(raw):
    sl = raw.strip().lower().replace("-", " ")
    if "micro" in sl or sl == "matx": return "Micro-ATX"
    if "mini" in sl: return "Mini-ITX"
    if "e atx" in sl or sl == "eatx": return "E-ATX"
    if sl == "atx": return "ATX"
    return raw.strip()


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
                if field == "socket":
                    derived[field] = _normalize_socket_value(value)
                elif categorie == "Carte mère" and field == "format":
                    derived[field] = _normalize_format_value(value)
                else:
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
- Pour le champ "type" d'un Stockage : réponds UNIQUEMENT "NVMe" ou "SATA" (jamais "SSD", "HDD", ou toute
  autre valeur) — si tu ne peux pas déterminer lequel des deux avec certitude, réponds null.
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


# Liste ORDONNÉE (et non un dict) car l'ordre sert à lever les ambiguïtés :
# ex. un GPU peut mentionner "GDDR6" dans son titre, ce qui contiendrait
# "ddr" si on cherchait la RAM en premier — GPU est donc vérifié avant RAM.
# Chaque mot-clé est cherché comme mot entier (\b) dans le titre nettoyé des
# accents, jamais en sous-chaîne brute (évite par ex. "ram" dans "trame").
CATEGORY_KEYWORDS = [
    # CPU AVANT GPU : beaucoup de processeurs AMD ont des graphiques intégrés
    # et mentionnent "Radeon Graphics" dans leur propre titre/détails Amazon
    # (ex: "AMD Ryzen 7 7700X... Integrated Graphics Radeon") — vérifier GPU
    # en premier les ferait classer à tort comme carte graphique.
    ("CPU", ["processeur", "ryzen", "threadripper", "core i3", "core i5", "core i7", "core i9"]),
    ("GPU", ["carte graphique", "geforce", "radeon rx", "rtx", "gtx", "rx "]),
    ("Carte mère", ["carte mere", "motherboard"]),
    ("RAM", ["memoire vive", "barrette memoire", "ram ddr", "dimm", "sodimm",
             "ddr4 ram", "ddr5 ram", "ram ddr4", "ram ddr5", "memoire ddr4", "memoire ddr5"]),
    ("Stockage", ["ssd", "disque dur", "disque ssd", "nvme", "hdd", "m.2"]),
    ("Alimentation", ["alimentation pc", "bloc d'alimentation", "bloc dalimentation", "80 plus", "psu",
                      "alimentation", "alimentation modulaire"]),
    ("Refroidissement", ["ventirad", "watercooling", "aio", "refroidisseur", "ventilateur cpu",
                         "liquid freezer", "air cooler", "cpu cooler", "caloducs", "heat pipes", "refroidissement liquide"]),
    ("Boîtier", ["boitier pc", "boitier gaming", "tour pc", "case pc",
                 "boitier", "moyen tour", "tour median", "mid tower", "mid-tower", "full tower"]),
    # Catégorie "Accessoire" unique — vérifiée après les composants internes
    # ci-dessus pour éviter les faux positifs (ex: "ventilateur cpu" est
    # capté par Refroidissement avant d'atteindre "ventilateur"). Tous les
    # mots-clés périphériques/accessoires pointent vers la même catégorie
    # plutôt que vers une catégorie par type d'accessoire.
    ("Accessoire", [
        "moniteur", "ecran pc", "ecran gaming", "ecran incurve",
        "clavier mecanique", "clavier gaming", "clavier sans fil", "keyboard",
        "souris gaming", "souris sans fil", "souris filaire", "mouse",
        "casque gaming", "casque sans fil", "casque filaire", "micro-casque", "headset",
        "webcam",
        "manette de jeu", "manette sans fil", "controller", "gamepad",
        "microphone", "micro usb", "micro de streaming", "micro cravate",
        "chaise gaming", "chaise de bureau", "fauteuil gaming",
        "ventilateur boitier", "ventilateur pc", "ventilateur argb", "ventilateur 120mm", "ventilateur 140mm",
        "onduleur",
    ]),
]


# Chipsets de carte mère (B650, X870E, Z790, H610M, A520M...) : souvent le
# seul indice dans un titre court ("ASRock X870E Challenger WiFi"). Séries A
# limitées à A320/A520/A620 pour ne pas capter les cartes Intel Arc A770.
MOTHERBOARD_CHIPSET = re.compile(r"\b(a[3-6]20|b[3-8]\d0e?|x[3-8]\d0e?|z[3-8]\d0|h[3-8]\d0)m?\b")


def _guess_categorie_in_title(normalized_nom):
    """
    Catégorie dont un mot-clé apparaît LE PLUS TÔT dans le titre : le produit
    est nommé d'abord, ses compatibilités ensuite ("【DDR4 RAM】 ... Intel XMP
    2.0 AMD Ryzen" est de la RAM, pas un processeur). À position égale,
    l'ordre de CATEGORY_KEYWORDS départage ; "Accessoire" ne sert que si aucun
    composant interne n'est reconnu.
    """
    best = None  # (position, rang, catégorie)
    for rank, (categorie, keywords) in enumerate(CATEGORY_KEYWORDS):
        if categorie == "Accessoire":
            continue
        positions = []
        for keyword in keywords:
            match = re.search(rf"\b{re.escape(keyword.strip())}\b", normalized_nom)
            if match:
                positions.append(match.start())
        if categorie == "Carte mère":
            match = MOTHERBOARD_CHIPSET.search(normalized_nom)
            if match:
                positions.append(match.start())
        if positions and (best is None or (min(positions), rank) < best[:2]):
            best = (min(positions), rank, categorie)
    if best:
        return best[2]
    for categorie, keywords in CATEGORY_KEYWORDS:
        if categorie == "Accessoire" and any(
            re.search(rf"\b{re.escape(keyword.strip())}\b", normalized_nom) for keyword in keywords
        ):
            return categorie
    return None


def guess_categorie_from_amazon(nom, caracteristiques_amazon):
    """
    Devine la catégorie du composant depuis son titre Amazon (et, en repli,
    ses caractéristiques produit), pour éviter à l'admin de la sélectionner
    à la main avant chaque import. Pure heuristique de confort : reste
    toujours modifiable dans le formulaire, contrairement aux specs de
    compatibilité qui doivent rester fiables.
    """
    normalized_nom = _strip_accents(nom or "").lower()
    categorie = _guess_categorie_in_title(normalized_nom)
    if categorie:
        return categorie

    details_text = _strip_accents(" ".join(
        f"{entry.get('type') or ''} {entry.get('value') or ''}" for entry in (caracteristiques_amazon or [])
    )).lower()
    for categorie, keywords in CATEGORY_KEYWORDS:
        for keyword in keywords:
            if re.search(rf"\b{re.escape(keyword.strip())}\b", details_text):
                return categorie

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

    L'image renvoyée est celle d'Amazon telle quelle, sans détourage
    automatique (voir le commentaire plus bas sur pourquoi) — un détourage
    manuel reste possible depuis le formulaire si besoin.

    Le champ `asin` accepte aussi un simple nom de produit : si ce n'est ni
    un ASIN nu ni une URL Amazon, on tente de retrouver la fiche produit via
    une recherche web réelle (find_asin_by_title) avant d'abandonner —
    permet d'ajouter un produit sans avoir à aller chercher soi-même le lien.
    """
    asin = extract_asin_from_input(request.asin)
    titre_recherche = None
    if not asin:
        titre_recherche = (request.asin or "").strip()
        if titre_recherche:
            asin = find_asin_by_title(titre_recherche, request.categorie)
    if not asin:
        detail = (
            f"Aucune fiche Amazon trouvée pour \"{titre_recherche}\"."
            if titre_recherche
            else "ASIN invalide : attendu 10 caractères alphanumériques, une URL Amazon contenant /dp/<ASIN>, ou un nom de produit."
        )
        raise HTTPException(status_code=400, detail=detail)

    t0 = time.time()
    try:
        info = fetch_amazon_product(asin)
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error))
    print(f"[fetch-asin] Bright Data : {time.time() - t0:.1f}s")

    # Catégorie devinée automatiquement depuis le titre/les détails Amazon
    # quand l'admin n'en a pas choisi une — reste modifiable côté formulaire,
    # ce n'est qu'un gain de confort, jamais une valeur de compatibilité.
    categorie = request.categorie if request.categorie in REQUIRED_FIELDS else None
    categorie_devinee = False
    if categorie is None:
        categorie = guess_categorie_from_amazon(info.get("nom"), info.get("caracteristiques_amazon") or [])
        categorie_devinee = categorie is not None

    missing_fields = {}
    if categorie in REQUIRED_FIELDS:
        specs = derive_specs_from_amazon(categorie, info.get("caracteristiques_amazon") or [])
        missing_fields = {
            field: expected_type
            for field, expected_type in REQUIRED_FIELDS[categorie].items()
            if field not in specs
        }

    def _run_ai():
        # Un seul appel IA pour le nom nettoyé + les specs encore
        # manquantes (jamais de recherche web, juste de la reformulation
        # sur les données Amazon déjà récupérées ci-dessus).
        if categorie not in REQUIRED_FIELDS:
            return None, {}
        return clean_name_and_specs_with_ai(
            categorie, info.get("nom"), info.get("marque"),
            info.get("caracteristiques_amazon") or [], info.get("description"),
            missing_fields,
        )

    # Le détourage automatique par flood-fill a été abandonné : trop de
    # photos produit ont des dégradés (ombre portée dessinée sous la boîte,
    # halo lumineux marketing...) impossibles à distinguer de façon fiable
    # d'une vraie surface de produit par simple seuil de couleur — chaque
    # correctif pour un cas cassait un autre cas déjà corrigé. On garde
    # l'image Amazon d'origine telle quelle ; c'est le CSS d'affichage
    # (mix-blend-mode: multiply sur un fond clair, voir style.css) qui rend
    # le fond blanc de la photo invisible, sans dépendre d'une découpe pixel
    # par pixel. Le détourage manuel reste possible depuis la fiche produit
    # de l'admin si besoin (bouton "Détourer cette image").
    t1 = time.time()
    ai_nom_propre, ai_specs = _run_ai()
    print(f"[fetch-asin] IA : {time.time() - t1:.1f}s")

    if categorie in REQUIRED_FIELDS:
        specs.update(ai_specs)
        # Même normalisation que côté derive_specs_from_amazon (voir son
        # commentaire) : l'IA peut tout aussi bien renvoyer "Socket AM4"
        # qu'"AM4" pour le champ manquant qu'on lui a demandé de déduire.
        if "socket" in specs:
            specs["socket"] = _normalize_socket_value(specs["socket"])
        if categorie == "Carte mère" and "format" in specs:
            specs["format"] = _normalize_format_value(specs["format"])
        info["specs"] = specs

    couleur = derive_color_from_amazon(info.get("nom"), info.get("caracteristiques_amazon") or [])
    if couleur:
        info.setdefault("specs", {})["couleur"] = couleur

    info["nom"] = ai_nom_propre or build_component_name(info.get("nom"), info.get("marque"))

    info["categorie"] = categorie
    info["categorie_devinee"] = categorie_devinee

    print(f"[fetch-asin] TOTAL : {time.time() - t0:.1f}s")
    return {"status": "ok", **info}


# Protège contre un chevauchement entre le rafraîchissement automatique
# quotidien et un clic manuel sur "Rafraîchir les prix" pendant qu'il tourne
# déjà — même souci et même solution que LINK_CHECK_LOCK plus bas.
PRICE_REFRESH_LOCK = ProcessLock("mise-a-jour-prix")


def _run_price_refresh():
    """
    Rafraîchit prix + image + relevé "Amazon" + statut en_stock pour TOUS
    les composants ayant un ASIN renseigné (pas seulement ceux qui ont déjà
    un prix — c'est justement ce qui permet à un composant épuisé de
    redevenir visible tout seul). Ne touche jamais aux relevés des autres
    revendeurs (LDLC, Materiel.net...) : seul le relevé "Amazon" est
    remplacé ou ajouté. Envoie tous les ASIN en UNE seule collecte Bright
    Data (plutôt qu'un appel par composant) : c'est ce que permet leur API
    par lots, et ça évite d'attendre une collecte asynchrone par composant.

    en_stock passe à 0 dès que Bright Data ne renvoie plus de prix pour
    l'ASIN (fiche "Actuellement indisponible") : le composant reste en base
    avec son dernier prix connu, mais n'est plus proposé par défaut dans le
    configurateur (voir /api/components et son filtre côté front). Il
    repasse à 1 tout seul, au prochain passage où un prix redevient
    disponible — jamais de suppression automatique ici, une rupture de
    stock n'étant pas la même chose qu'une fin de vie définitive (celle-ci
    reste une décision manuelle de l'admin, via le bouton Supprimer).
    """
    client = get_client()
    try:
        result = client.execute(
            "SELECT id, nom, asin, prix_marche_json, image_url, en_stock FROM components "
            "WHERE asin IS NOT NULL AND asin != ''"
        )
        rows = result.rows
    finally:
        client.close()

    if not rows:
        return {"updated": 0, "errors": [], "remis_en_stock": 0, "passes_epuises": 0}

    # Jamais au-delà de ce qui reste hors réserve des ajouts : les fiches
    # vérifiées depuis le plus longtemps passent en premier.
    allowance = refresh_allowance("brightdata", per_day=False)
    if allowance <= 0:
        raise RuntimeError(
            "Quota Bright Data du mois réservé aux ajouts de composants : "
            "la mise à jour complète reprendra le mois prochain (la mise à jour quotidienne continue via Apify)."
        )
    rows = sorted(rows, key=lambda row: _last_amazon_check_date(row[3]))[:allowance]

    items = [{"url": f"https://www.amazon.{AMAZON_DOMAIN_TLD}/dp/{row[2]}"} for row in rows]

    # Une grosse collecte prend plus de temps qu'un seul produit : délai
    # plus généreux qu'un fetch-asin individuel (90s).
    results = _brightdata_scrape_sync(items, timeout=280)

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
    remis_en_stock = 0
    passes_epuises = 0
    errors = []
    client = get_client()
    try:
        for row in rows:
            component_id, nom, asin, prix_marche_json, image_url, was_en_stock = (
                row[0], row[1], row[2], row[3], row[4], bool(row[5]),
            )

            result_item = results_by_asin.get(asin.upper())
            if result_item is None:
                errors.append(f"{nom} ({asin}) : aucun résultat renvoyé par Bright Data.")
                continue

            info = _normalize_brightdata_item(result_item, asin)
            outcome = _apply_amazon_price_info(
                client, component_id, nom, asin, prix_marche_json, image_url, was_en_stock, info,
                source_label="Bright Data",
            )
            if outcome["error"]:
                errors.append(outcome["error"])
            if outcome["remis_en_stock"]:
                remis_en_stock += 1
            if outcome["passe_epuise"]:
                passes_epuises += 1
            updated += 1
    finally:
        client.close()

    return {"updated": updated, "errors": errors, "remis_en_stock": remis_en_stock, "passes_epuises": passes_epuises}


def _apply_amazon_price_info(client, component_id, nom, asin, prix_marche_json, image_url, was_en_stock, info, source_label):
    """
    Applique un résultat de collecte (Bright Data ou ZenRows, forme déjà
    normalisée par _normalize_brightdata_item / _parse_zenrows_amazon_html) à
    un composant : même logique de mise à jour utilisée par le rafraîchissement
    manuel (bouton admin) et par la rotation quotidienne, pour éviter que les
    deux chemins divergent silencieusement.
    """
    try:
        prix_marche = json.loads(prix_marche_json) if prix_marche_json else []
    except (TypeError, json.JSONDecodeError):
        prix_marche = []

    prix_marche = [p for p in prix_marche if p.get("vendeur") != "Amazon"]
    prix_trouve = info.get("prix") is not None
    error = None
    if prix_trouve:
        prix_marche.append({
            "vendeur": "Amazon",
            "prix": info["prix"],
            "lien": info.get("lien"),
            "date_releve": datetime.utcnow().date().isoformat(),
        })
    else:
        error = f"{nom} ({asin}) : prix introuvable via {source_label} (probablement épuisé)."

    remis_en_stock = prix_trouve and not was_en_stock
    passe_epuise = not prix_trouve and was_en_stock

    # Pas de détourage automatique (voir le commentaire dans
    # admin_fetch_asin) : on prend l'image fraîchement récupérée telle
    # quelle, ou on garde l'ancienne si la nouvelle collecte n'en renvoie pas.
    new_image_url = info.get("image_url") or image_url

    # prix_indicatif est LE prix affiché partout sur le site (cartes
    # produit, total de l'assistant IA, tri par prix...) : sans cette mise à
    # jour, un prix_indicatif resté à 0/faux à la création (import raté,
    # ancien bug de récupération...) ne se corrige JAMAIS tout seul même
    # quand prix_marche redevient exact au fil des rafraîchissements
    # suivants — vu en pratique sur une RTX 4060 Ti à prix_indicatif=0 alors
    # que son prix_marche Amazon était juste, ce qui faussait le total d'une
    # suggestion IA.
    update_fields = ["prix_marche_json = ?", "image_url = ?", "has_image = ?", "en_stock = ?"]
    update_values = [
        json.dumps(prix_marche, ensure_ascii=False), new_image_url,
        1 if new_image_url else 0, 1 if prix_trouve else 0,
    ]
    if prix_trouve:
        update_fields.append("prix_indicatif = ?")
        update_values.append(info["prix"])
    update_values.append(component_id)

    client.execute(
        f"UPDATE components SET {', '.join(update_fields)} WHERE id = ?",
        update_values,
    )

    if prix_trouve:
        record_price_and_notify(client, component_id, nom, float(info["prix"]), info.get("lien"))

    return {"error": error, "remis_en_stock": remis_en_stock, "passe_epuise": passe_epuise}


@app.post("/api/admin/refresh-prices")
def admin_refresh_prices(_admin=Depends(require_admin)):
    if not PRICE_REFRESH_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Un rafraîchissement des prix est déjà en cours.")
    try:
        stats = _run_price_refresh()
        check_build_alerts()
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=f"Rafraîchissement échoué : {error}")
    finally:
        PRICE_REFRESH_LOCK.release()

    return {"status": "ok", **stats}


# Avant le 1er octobre 2026, un _run_price_refresh() complet quotidien
# (l'ancien comportement de cette boucle) dépassait largement le quota
# gratuit Bright Data (5000/mois) dès que le catalogue a franchi ~165
# composants — d'où le passage à une rotation par tranches sur TROIS
# fournisseurs combinés (voir _run_daily_price_refresh_rotation). Apify
# porte l'essentiel du volume (le moins cher des trois de loin, voir
# fetch_amazon_products_apify) ; Bright Data et ZenRows comblent le reste
# dans la limite de LEURS quotas gratuits respectifs, en pur bonus de
# redondance plutôt que par nécessité.
DAILY_ROTATION_START = datetime(2026, 10, 1)
BRIGHTDATA_DAILY_BUDGET = 160  # ~4800/mois, sous le quota gratuit de 5000
ZENROWS_DAILY_BUDGET = 15      # ~450/mois à 10 crédits/requête, sous le quota gratuit de 5000 crédits
# ~0,0002$/produit mesuré en pratique sur cet actor (voir
# fetch_amazon_products_apify) : 600/jour ≈ 18000/mois ≈ 3,6$/mois, avec
# une marge confortable sous les 5$ de crédit gratuit mensuel pour absorber
# les variations réelles (retries, pages plus lourdes...) sans jamais
# dépasser le quota. Couvre à lui seul le reste du catalogue chaque jour.
APIFY_DAILY_BUDGET = 600
# La version gratuite de l'actor ne renvoie que 50 lignes par exécution
# (page de l'actor sur Apify) : au-delà, les ASIN en trop reviennent vides.
APIFY_MAX_ROWS_PER_RUN = 50

# --- Quotas mensuels gratuits et réserve pour les ajouts --------------------
# Chaque appel payant est compté (table api_usage, par mois). La mise à jour
# quotidienne ne consomme que ce qui reste APRÈS la réserve, étalé sur les
# jours restants du mois ; la réserve Bright Data sert aux ajouts de
# composants par ASIN (et à la réparation des liens morts), qui passent aussi
# par Bright Data. Sans elle, 160 fiches/jour x 31 jours = 4960 sur 5000 : plus
# aucun ajout possible en fin de mois.
BRIGHTDATA_MONTHLY_QUOTA = 5000       # fiches
BRIGHTDATA_ADDITION_RESERVE = 100     # fiches gardées pour les ajouts (~3 par jour)
ZENROWS_MONTHLY_CREDITS = 5000        # crédits (10 par fiche Amazon)
APIFY_MONTHLY_ITEMS = 20000           # ~4 $ sur les 5 $ offerts chaque mois


def _current_month():
    return datetime.utcnow().strftime("%Y-%m")


def record_api_usage(provider: str, amount: int):
    """Ajoute `amount` à la consommation du mois. Ne lève jamais d'erreur."""
    if amount <= 0:
        return
    client = get_client()
    try:
        client.execute(
            "INSERT INTO api_usage (mois, fournisseur, appels) VALUES (?, ?, ?) "
            "ON CONFLICT(mois, fournisseur) DO UPDATE SET appels = appels + excluded.appels",
            [_current_month(), provider, amount],
        )
    except Exception as err:
        print(f"Comptage d'usage {provider} impossible : {err}")
    finally:
        client.close()


def api_usage_this_month(provider: str) -> int:
    client = get_client()
    try:
        rows = client.execute(
            "SELECT appels FROM api_usage WHERE mois = ? AND fournisseur = ?", [_current_month(), provider]
        ).rows
        return int(rows[0][0]) if rows else 0
    except Exception:
        return 0
    finally:
        client.close()


def _days_left_in_month() -> int:
    now = datetime.utcnow()
    next_month = datetime(now.year + (now.month == 12), now.month % 12 + 1, 1)
    return max(1, (next_month - datetime(now.year, now.month, now.day)).days)


def refresh_allowance(provider: str, per_day: bool = True) -> int:
    """
    Nombre de fiches que la mise à jour des prix peut encore demander à ce
    fournisseur : ce qui reste du mois APRÈS la réserve, étalé sur les jours
    restants (per_day) ou en une fois (mise à jour complète lancée à la main).
    """
    if provider == "brightdata":
        remaining = BRIGHTDATA_MONTHLY_QUOTA - BRIGHTDATA_ADDITION_RESERVE - api_usage_this_month("brightdata")
        cap = BRIGHTDATA_DAILY_BUDGET
    elif provider == "zenrows":
        remaining = (ZENROWS_MONTHLY_CREDITS - api_usage_this_month("zenrows")) // ZENROWS_CREDITS_PER_REQUEST
        cap = ZENROWS_DAILY_BUDGET
    else:
        remaining = APIFY_MONTHLY_ITEMS - api_usage_this_month("apify")
        cap = APIFY_DAILY_BUDGET
    remaining = max(0, remaining)
    if not per_day:
        return remaining
    return min(cap, remaining // _days_left_in_month())


def brightdata_remaining_total() -> int:
    """Fiches Bright Data restantes ce mois, réserve comprise (ajouts)."""
    return max(0, BRIGHTDATA_MONTHLY_QUOTA - api_usage_this_month("brightdata"))


_STATS_CACHE = {"at": 0.0, "data": None}


@app.get("/api/admin/stats")
def admin_site_stats(_admin=Depends(require_admin)):
    """
    Statistiques de visite des 14 derniers jours, tirées des journaux nginx
    (voir site_stats.py) : aucune donnée collectée en plus. Cache 10 min.
    """
    if _STATS_CACHE["data"] is None or time.time() - _STATS_CACHE["at"] > 600:
        _STATS_CACHE.update(at=time.time(), data=site_stats.compute(excluded_ips={"127.0.0.1", "10.0.0.79", "88.96.49.31"}))
    return _STATS_CACHE["data"]


@app.get("/api/admin/quotas")
def admin_quotas(_admin=Depends(require_admin)):
    """Consommation du mois par fournisseur, affichée dans l'admin."""
    brightdata_used = api_usage_this_month("brightdata")
    return {
        "mois": _current_month(),
        "brightdata": {
            "utilise": brightdata_used,
            "quota": BRIGHTDATA_MONTHLY_QUOTA,
            "reserve_ajouts": BRIGHTDATA_ADDITION_RESERVE,
            "ajouts_restants": max(0, BRIGHTDATA_MONTHLY_QUOTA - brightdata_used),
            "mise_a_jour_du_jour": refresh_allowance("brightdata"),
        },
        "zenrows": {"credits_utilises": api_usage_this_month("zenrows"), "quota_credits": ZENROWS_MONTHLY_CREDITS},
        "apify": {"utilise": api_usage_this_month("apify"), "quota": APIFY_MONTHLY_ITEMS},
    }


def _last_amazon_check_date(prix_marche_json):
    try:
        prix_marche = json.loads(prix_marche_json) if prix_marche_json else []
    except (TypeError, json.JSONDecodeError):
        return ""
    for entry in prix_marche:
        if isinstance(entry, dict) and entry.get("vendeur") == "Amazon":
            return entry.get("date_releve") or ""
    return ""  # jamais vérifié : chaîne vide trie en premier (priorité maximale)


def _run_daily_price_refresh_rotation():
    """
    Rafraîchit prix/stock par tranche quotidienne tournante (les composants
    jamais vérifiés ou vérifiés depuis le plus longtemps passent en premier),
    en combinant TROIS fournisseurs (Apify en volume principal, Bright Data
    et ZenRows en complément) pour rester sous leurs quotas gratuits
    respectifs. Avec ~860 composants et Apify seul capable d'absorber
    APIFY_DAILY_BUDGET composants/jour, le catalogue entier peut être
    revérifié quasiment chaque jour plutôt qu'une fois par mois si on
    restait limité à un seul fournisseur.
    """
    if datetime.utcnow() < DAILY_ROTATION_START:
        return {"skipped": True, "updated": 0, "errors": [], "remis_en_stock": 0, "passes_epuises": 0}

    client = get_client()
    try:
        result = client.execute(
            "SELECT id, nom, asin, prix_marche_json, image_url, en_stock FROM components "
            "WHERE asin IS NOT NULL AND asin != ''"
        )
        rows = result.rows
    finally:
        client.close()

    if not rows:
        return {"updated": 0, "errors": [], "remis_en_stock": 0, "passes_epuises": 0}

    rows_sorted = sorted(rows, key=lambda row: _last_amazon_check_date(row[3]))

    brightdata_rows = rows_sorted[:refresh_allowance("brightdata")] if BRIGHTDATA_API_TOKEN else []
    reste = rows_sorted[len(brightdata_rows):]
    zenrows_rows = reste[:refresh_allowance("zenrows")] if ZENROWS_API_KEY else []
    reste = reste[len(zenrows_rows):]
    apify_rows = reste[:refresh_allowance("apify")] if APIFY_API_TOKEN else []

    updated = 0
    remis_en_stock = 0
    passes_epuises = 0
    errors = []
    client = get_client()
    try:
        if brightdata_rows:
            items = [{"url": f"https://www.amazon.{AMAZON_DOMAIN_TLD}/dp/{row[2]}"} for row in brightdata_rows]
            try:
                results = _brightdata_scrape_sync(items, timeout=180)
            except RuntimeError as error:
                results = []
                errors.append(f"Bright Data (tranche de {len(brightdata_rows)}) : {error}")

            results_by_asin = {}
            for result_item in (results or []):
                item_asin = _find_field_recursive(result_item, ["asin"])
                if not isinstance(item_asin, str):
                    item_url = _find_field_recursive(result_item, ["url", "link"])
                    item_asin = extract_asin_from_input(item_url) if isinstance(item_url, str) else None
                if isinstance(item_asin, str):
                    results_by_asin[item_asin.upper()] = result_item

            for row in brightdata_rows:
                component_id, nom, asin, prix_marche_json, image_url, was_en_stock = (
                    row[0], row[1], row[2], row[3], row[4], bool(row[5]),
                )
                result_item = results_by_asin.get(asin.upper())
                if result_item is None:
                    errors.append(f"{nom} ({asin}) : aucun résultat Bright Data.")
                    continue
                info = _normalize_brightdata_item(result_item, asin)
                outcome = _apply_amazon_price_info(
                    client, component_id, nom, asin, prix_marche_json, image_url, was_en_stock, info,
                    source_label="Bright Data",
                )
                if outcome["error"]:
                    errors.append(outcome["error"])
                if outcome["remis_en_stock"]:
                    remis_en_stock += 1
                if outcome["passe_epuise"]:
                    passes_epuises += 1
                updated += 1

        for row in zenrows_rows:
            component_id, nom, asin, prix_marche_json, image_url, was_en_stock = (
                row[0], row[1], row[2], row[3], row[4], bool(row[5]),
            )
            try:
                info = fetch_amazon_product_zenrows(asin)
            except Exception as error:
                errors.append(f"{nom} ({asin}) : ZenRows a échoué ({error}).")
                continue
            outcome = _apply_amazon_price_info(
                client, component_id, nom, asin, prix_marche_json, image_url, was_en_stock, info,
                source_label="ZenRows",
            )
            if outcome["error"]:
                errors.append(outcome["error"])
            if outcome["remis_en_stock"]:
                remis_en_stock += 1
            if outcome["passe_epuise"]:
                passes_epuises += 1
            updated += 1

        # Par lots de APIFY_MAX_ROWS_PER_RUN. Un lot en échec (panne, crédit
        # épuisé) ne touche à RIEN : ses composants seront repris à un prochain
        # passage. Un ASIN absent d'un lot réussi (recherche Amazon sans
        # correspondance exacte) n'est pas non plus déclaré épuisé : la
        # recherche par ASIN d'Apify peut simplement le manquer ; Bright Data
        # et ZenRows, qui lisent la fiche /dp/ elle-même, tranchent le stock
        # lors de leurs propres passages.
        for start in range(0, len(apify_rows), APIFY_MAX_ROWS_PER_RUN):
            batch = apify_rows[start:start + APIFY_MAX_ROWS_PER_RUN]
            try:
                results_by_asin = fetch_amazon_products_apify([row[2] for row in batch])
            except Exception as error:
                errors.append(f"Apify (lot de {len(batch)}, ignoré) : {error}")
                continue

            for row in batch:
                component_id, nom, asin, prix_marche_json, image_url, was_en_stock = (
                    row[0], row[1], row[2], row[3], row[4], bool(row[5]),
                )
                info = results_by_asin.get(asin)
                if info is None:
                    errors.append(f"{nom} ({asin}) : non trouvé par Apify, stock inchangé.")
                    continue
                outcome = _apply_amazon_price_info(
                    client, component_id, nom, asin, prix_marche_json, image_url, was_en_stock, info,
                    source_label="Apify",
                )
                if outcome["error"]:
                    errors.append(outcome["error"])
                if outcome["remis_en_stock"]:
                    remis_en_stock += 1
                if outcome["passe_epuise"]:
                    passes_epuises += 1
                updated += 1
    finally:
        client.close()

    return {"updated": updated, "errors": errors, "remis_en_stock": remis_en_stock, "passes_epuises": passes_epuises}


PRICE_REFRESH_INTERVAL_SECONDS = 24 * 60 * 60
# Les tâches quotidiennes vérifient leur échéance toutes les 30 minutes, à
# partir de l'heure de leur dernière exécution MÉMORISÉE EN BASE : un
# redémarrage du service (chaque déploiement) ne repousse plus la tâche de 24 h
# (avant, des redémarrages fréquents l'empêchaient de tourner du tout), et ne
# la relance pas non plus à chaque démarrage.
SCHEDULER_CHECK_SECONDS = 30 * 60


def _task_is_due(key: str, interval_seconds: int) -> bool:
    client = get_client()
    try:
        rows = client.execute("SELECT valeur FROM app_state WHERE cle = ?", [key]).rows
    except Exception:
        return False  # table indisponible : on ne déclenche rien à l'aveugle
    finally:
        client.close()
    if not rows or not rows[0][0]:
        return True
    try:
        last = datetime.fromisoformat(rows[0][0])
    except ValueError:
        return True
    return (datetime.utcnow() - last).total_seconds() >= interval_seconds - SCHEDULER_CHECK_SECONDS


def _mark_task_done(key: str):
    client = get_client()
    try:
        client.execute(
            "INSERT INTO app_state (cle, valeur) VALUES (?, ?) ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur",
            [key, datetime.utcnow().isoformat()],
        )
    except Exception as err:
        print(f"Échéance de {key} non mémorisée : {err}")
    finally:
        client.close()


async def price_refresh_loop():
    """Boucle de fond : rafraîchit une tranche du catalogue une fois par jour (voir _run_daily_price_refresh_rotation)."""
    await asyncio.sleep(5 * 60)  # laisse le service démarrer tranquillement
    while True:
        if datetime.utcnow() < DAILY_ROTATION_START or not await asyncio.to_thread(
            _task_is_due, "derniere_mise_a_jour_prix", PRICE_REFRESH_INTERVAL_SECONDS
        ):
            await asyncio.sleep(SCHEDULER_CHECK_SECONDS)
            continue
        if not PRICE_REFRESH_LOCK.acquire(blocking=False):
            print("Rafraîchissement automatique des prix ignoré (déjà en cours via un autre déclenchement).")
            continue
        try:
            stats = await asyncio.to_thread(_run_daily_price_refresh_rotation)
            if not stats.get("skipped"):
                await asyncio.to_thread(_mark_task_done, "derniere_mise_a_jour_prix")
                invalidate_catalog()
                await asyncio.to_thread(check_build_alerts)
            if stats.get("skipped"):
                print("Rafraîchissement automatique des prix : pas encore démarré (prévu à partir du 1er octobre 2026).")
            else:
                print(
                    f"Rafraîchissement automatique des prix : {stats['updated']} composant(s) revérifié(s), "
                    f"{stats['remis_en_stock']} remis en stock, {stats['passes_epuises']} passé(s) épuisé(s), "
                    f"{len(stats['errors'])} erreur(s)."
                )
        except Exception as error:
            print(f"Rafraîchissement automatique des prix échoué : {error}")
        finally:
            PRICE_REFRESH_LOCK.release()


@app.on_event("startup")
async def start_price_refresh_loop():
    if is_background_leader():
        asyncio.create_task(price_refresh_loop())


@app.on_event("startup")
async def warm_featured_configs():
    """Calcule les configs de la page d'accueil dès le démarrage, en fond."""
    asyncio.create_task(asyncio.to_thread(featured_configs))


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


@app.post("/api/admin/components/{component_id}/regenerate-image")
def admin_regenerate_image(component_id: int, _admin=Depends(require_admin)):
    """
    Repart d'une image Amazon fraîche pour ce composant (identifié par son
    ASIN) — utile quand l'image actuelle a un problème visible (mauvais
    recadrage, mauvaise photo, détourage raté...). Remet image_url à cette
    URL Amazon brute plutôt que de la détourer ici : la surveillance
    automatique locale (BiRefNet, voir local_bg_tool/) la détecte et la
    détoure elle-même dans les secondes qui suivent, exactement comme pour
    un nouveau composant.
    """
    client = get_client()
    try:
        result = client.execute("SELECT asin FROM components WHERE id = ?", [component_id])
        if not result.rows:
            raise HTTPException(status_code=404, detail="Composant introuvable.")
        asin = result.rows[0][0]
        if not asin:
            raise HTTPException(status_code=400, detail="Ce composant n'a pas d'ASIN associé — impossible de récupérer une nouvelle image automatiquement, modifie l'URL de l'image à la main.")

        try:
            info = fetch_amazon_product(asin)
        except RuntimeError as error:
            raise HTTPException(status_code=502, detail=str(error))

        if not info.get("image_url"):
            raise HTTPException(status_code=502, detail="Amazon n'a renvoyé aucune image pour cet ASIN.")

        client.execute(
            "UPDATE components SET image_url = ?, has_image = 1 WHERE id = ?",
            [info["image_url"], component_id],
        )
    finally:
        client.close()

    return {"status": "ok", "image_url": info["image_url"]}


@app.get("/api/admin/pending-images")
def admin_pending_images(_admin=Depends(require_admin)):
    """
    Liste les composants dont l'image n'est pas encore détourée (encore une
    URL Amazon brute) — utilisé par l'outil local de détourage (BiRefNet,
    voir local_bg_tool/) pour savoir quoi traiter. Depuis que la base est un
    fichier local sur le VM (plus Turso), ce fichier n'est plus accessible
    directement depuis un PC externe : l'outil local passe donc par cette
    API plutôt que par une connexion base de données directe.
    """
    client = get_client()
    try:
        result = client.execute(
            "SELECT id, nom, image_url FROM components WHERE image_url LIKE 'http%'"
        )
        return {
            "status": "ok",
            "components": [{"id": row[0], "nom": row[1], "image_url": row[2]} for row in result.rows],
        }
    finally:
        client.close()


class SetImageRequest(BaseModel):
    image_data_url: str


@app.post("/api/admin/components/{component_id}/set-image")
def admin_set_image(component_id: int, request: SetImageRequest, _admin=Depends(require_admin)):
    """
    Enregistre une image déjà détourée (data:image/...) pour ce composant —
    utilisé par l'outil local de détourage pour renvoyer son résultat, sans
    connexion base de données directe (voir admin_pending_images).
    """
    if not request.image_data_url.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="image_data_url doit être une data URL (data:image/...).")

    client = get_client()
    try:
        result = client.execute("SELECT id FROM components WHERE id = ?", [component_id])
        if not result.rows:
            raise HTTPException(status_code=404, detail="Composant introuvable.")
        client.execute(
            "UPDATE components SET image_url = ?, has_image = 1 WHERE id = ?",
            [request.image_data_url, component_id],
        )
    finally:
        client.close()

    return {"status": "ok"}


@app.get("/api/admin/aliexpress-search")
def admin_aliexpress_search(q: str, _admin=Depends(require_admin)):
    """
    Cherche dans le feed produit AliExpress (CPU + RAM uniquement, voir
    ALIEXPRESS_CPU_RAM_FEED) — une recherche par mots-clés (tous doivent
    apparaître dans le nom ou la marque), en mémoire, donc instantanée. Ne
    remplace pas fetch_amazon_product : ce feed n'a pas d'équivalent ASIN,
    juste une recherche approximative pour trouver un lien d'affiliation
    Awin déjà prêt à ajouter comme prix de comparaison.
    """
    keywords = [word for word in q.lower().split() if word]
    if not keywords:
        return {"status": "ok", "results": []}

    def matches(row):
        haystack = f"{row.get('product_name', '')} {row.get('brand_name', '')}".lower()
        return all(keyword in haystack for keyword in keywords)

    results = []
    for row in ALIEXPRESS_CPU_RAM_FEED:
        if matches(row):
            results.append({
                "nom": row.get("product_name"),
                "marque": row.get("brand_name") or None,
                "prix": parse_amazon_price(row.get("display_price")),
                "lien": row.get("aw_deep_link"),
                "image_url": row.get("aw_image_url") or row.get("merchant_image_url"),
                "en_stock": row.get("in_stock") == "1",
            })
        if len(results) >= 30:
            break

    return {"status": "ok", "results": results}


# Constaté en pratique (Gemini à quota épuisé, PUIS un vrai hang réseau de
# 100+ secondes sans la moindre erreur) : MAX_AI_ATTEMPTS (essais de
# correction) × [5 clés Gemini × GEMINI_CALL_TIMEOUT_SECONDS + retries Groq
# + retries Mistral] peut vite dépasser la marge nginx (150s) si on n'y
# prend pas garde — chaque seconde de timeout individuel est multipliée par
# ce nombre de tentatives extérieures. 3 tentatives avec les plafonds
# actuels reste sous ~150s dans le pire des cas (5×8s Gemini + ~12s Groq +
# ~8s Mistral ≈ 60s par tentative interne), au prix d'un peu moins de
# tentatives de correction — un léger risque de ne pas trouver LA config
# idéale valait mieux qu'un échec total par timeout. Le vrai risque (hang
# réseau infini) est maintenant borné par GEMINI_CALL_TIMEOUT_SECONDS — en
# pratique, un fournisseur en panne renvoie une erreur RAPIDE (503, 429...)
# sur la plupart des clés, le hang de 8s pile n'étant qu'un cas parmi
# d'autres, pas la norme. 3 tentatives reste donc réaliste sous la marge
# nginx (150s) tout en gardant assez de tentatives pour converger sur le
# budget après un premier dépassement — constaté en pratique qu'UNE seule
# tentative de correction ne suffisait pas toujours.
MAX_AI_ATTEMPTS = 3


# Filet de sécurité pour les appels Gemini : constaté en pratique qu'une
# requête peut rester bloquée PLUS DE 100 SECONDES sans la moindre erreur
# ni le moindre log (pas un 429, pas un 503 — juste rien), un vrai hang
# réseau plutôt qu'un refus propre. Le paramètre timeout du SDK Gemini
# (http_options) est censé éviter ça, mais un bug connu du SDK l'ignore
# parfois silencieusement (le client HTTP interne reçoit timeout=None
# malgré la config) — d'où ce filet AU NIVEAU APPLICATIF, qui coupe
# vraiment l'attente après GEMINI_CALL_TIMEOUT_SECONDS quoi qu'il arrive
# côté SDK.
GEMINI_CALL_TIMEOUT_SECONDS = 8
_gemini_call_executor = concurrent.futures.ThreadPoolExecutor(max_workers=8, thread_name_prefix="gemini-call")


def _call_gemini_with_hard_timeout(func):
    future = _gemini_call_executor.submit(func)
    try:
        return future.result(timeout=GEMINI_CALL_TIMEOUT_SECONDS)
    except concurrent.futures.TimeoutError:
        raise RuntimeError(f"délai de {GEMINI_CALL_TIMEOUT_SECONDS}s dépassé sans réponse (hang réseau)")


AI_MODEL_MAX_ATTEMPTS = 2


def call_ai_model(prompt, max_tokens=800, temperature=0.7, reasoning_effort="none"):
    """
    Appelle Gemini (primaire, sur toutes les clés configurées, voir
    GEMINI_API_KEYS) puis Groq qwen (repli) avec le prompt donné.

    L'ordre a été inversé par rapport à l'historique du projet (Groq
    d'abord) : qwen tourne en permanence à quota Groq épuisé ces derniers
    temps (usage cumulé du site), ce qui faisait perdre plusieurs dizaines
    de secondes de nouvelles tentatives à CHAQUE appel avant de finalement
    retomber sur Gemini de toute façon — inutile de payer ce coût en retard
    à chaque fois maintenant qu'une clé Gemini a un vrai quota disponible.
    Groq reste en repli si jamais toutes les clés Gemini échouent.

    qwen est un modèle "raisonneur" : avec reasoning_effort="low" (l'ancien
    défaut), une partie de max_tokens part dans un raisonnement interne
    invisible AVANT la réponse — et en pratique "low" consommait quand même
    TOUT le budget aussi souvent qu'un raisonnement poussé, coupant la
    réponse à vide (finish_reason="length", content="") sans lever d'erreur.
    reasoning_effort="none" désactive complètement ce raisonnement (réponse
    quasi instantanée, quelques dizaines de tokens au lieu de plusieurs
    centaines) : c'est maintenant le défaut, "low"/"medium"/"high" restent
    disponibles pour un appelant qui aurait vraiment besoin de plus de
    réflexion sur une tâche complexe.
    """
    if genai_new is not None and GEMINI_API_KEYS:
        last_error = None
        for api_key in GEMINI_API_KEYS:
            try:
                gemini_client = genai_new.Client(api_key=api_key)
                response = _call_gemini_with_hard_timeout(
                    lambda gc=gemini_client: gc.models.generate_content(model="gemini-3.5-flash-lite", contents=prompt)
                )
                if response.text and response.text.strip():
                    return response.text
                last_error = RuntimeError("réponse vide")
            except Exception as error:
                last_error = error
                print(f"Projet Gemini indisponible (call_ai_model), tentative suivante : {error}")
        print(f"Gemini échoué sur toutes les clés, repli Groq : {last_error}")

    if groq_client is None:
        raise RuntimeError("Gemini et Groq ne sont pas configurés") if last_error is None else last_error

    last_error = None
    for attempt in range(1, AI_MODEL_MAX_ATTEMPTS + 1):
        try:
            message = groq_client.chat.completions.create(
                model="qwen/qwen3.8-27b",
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
            )
            content = message.choices[0].message.content
            if not content or not content.strip():
                raise RuntimeError(
                    f"réponse vide (raisonnement interne a rempli tout le budget de "
                    f"{max_tokens} tokens, finish_reason={message.choices[0].finish_reason!r})"
                )
            return content
        except Exception as error:
            last_error = error
            message_text = str(error)
            if "rate_limit_exceeded" not in message_text and "429" not in message_text:
                break
            if attempt == AI_MODEL_MAX_ATTEMPTS:
                break
            match = re.search(r"try again in ([\d.]+)s", message_text)
            # Plafonné à 10s (pas 25) : cet appel est lui-même imbriqué dans
            # la boucle de correction de suggest-config/refine-config
            # (MAX_AI_ATTEMPTS tentatives), donc chaque seconde gagnée ici
            # est multipliée par ce nombre de tentatives extérieures — voir
            # le commentaire sur MAX_AI_ATTEMPTS pour le calcul complet.
            wait_seconds = min(float(match.group(1)), 10) + 0.5 if match else 5 * attempt
            print(f"Groq (qwen) rate-limité (essai {attempt}/{AI_MODEL_MAX_ATTEMPTS}), nouvel essai dans {wait_seconds:.1f}s...")
            time.sleep(wait_seconds)

    # Troisième repli : Mistral (~1 milliard de tokens/mois gratuits, quota
    # totalement indépendant de Gemini et Groq) — ajouté après avoir constaté
    # en pratique que Gemini et Groq peuvent tomber en panne EN MÊME TEMPS
    # (Gemini en 503 "high demand" pendant que Groq est à son plafond
    # quotidien), ce qui mettait l'assistant complètement hors service sans
    # ce troisième filet.
    if MISTRAL_API_KEY:
        try:
            return call_mistral(prompt, max_tokens=max_tokens, temperature=temperature)
        except Exception as error:
            print(f"Mistral indisponible (call_ai_model) : {error}")
            last_error = error

    raise last_error


MISTRAL_MAX_ATTEMPTS = 2


def call_mistral(prompt, max_tokens=800, temperature=0.7):
    """
    Appelle Mistral (API compatible OpenAI) — troisième repli de
    call_ai_model, voir son commentaire pour le contexte. Même style
    défensif que l'appel Groq juste au-dessus : retente une fois sur un
    429 avec un backoff court, jamais plus (ce filet est lui-même déjà en
    bout de chaîne, inutile d'ajouter beaucoup de latence ici).
    """
    if not MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY absente")

    last_error = None
    for attempt in range(1, MISTRAL_MAX_ATTEMPTS + 1):
        try:
            response = requests.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": MISTRAL_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=30,
            )
            if response.status_code == 429:
                raise RuntimeError(f"429 rate_limit_exceeded : {response.text}")
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not content or not content.strip():
                raise RuntimeError("réponse vide")
            return content
        except Exception as error:
            last_error = error
            if "429" not in str(error) or attempt == MISTRAL_MAX_ATTEMPTS:
                break
            print(f"Mistral rate-limité (essai {attempt}/{MISTRAL_MAX_ATTEMPTS}), nouvel essai dans 5s...")
            time.sleep(5)
    raise last_error


GROQ_COMPOUND_MAX_ATTEMPTS = 4


def call_groq_compound(prompt, max_tokens=400):
    """
    Appelle groq/compound (recherche web réelle). Le quota Groq de ce modèle
    est partagé par TOUTES les fonctionnalités du site qui font une vraie
    recherche web (vérification IA, FPS, recherche d'image, retrouver un
    produit par son nom...) : un pic d'usage sur l'une bloque temporairement
    les autres. Si Groq répond qu'on est seulement rate-limité par minute
    (pas par jour — Groq indique lui-même le délai avant que ça se libère,
    et ce compteur se réinitialise chaque minute), on retente plusieurs fois
    en attendant ce délai plutôt que d'abandonner après un seul essai : sur
    un pic ponctuel, la 2e ou 3e tentative passe presque toujours. Une erreur
    "requête trop grosse" (413, la recherche interne du modèle a ramené trop
    de contenu) n'est en revanche PAS une histoire de timing — la retenter à
    l'identique échouerait probablement pareil, donc on remonte tout de
    suite l'erreur pour laisser l'appelant basculer sur Gemini sans attendre.
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

    last_error = None
    for attempt in range(1, GROQ_COMPOUND_MAX_ATTEMPTS + 1):
        try:
            return _call()
        except Exception as error:
            last_error = error
            message = str(error)
            if "rate_limit_exceeded" not in message and "429" not in message:
                raise
            if attempt == GROQ_COMPOUND_MAX_ATTEMPTS:
                break
            match = re.search(r"try again in ([\d.]+)s", message)
            wait_seconds = min(float(match.group(1)), 25) + 0.5 if match else 8 * attempt
            print(f"Groq temporairement rate-limité (essai {attempt}/{GROQ_COMPOUND_MAX_ATTEMPTS}), nouvel essai dans {wait_seconds:.1f}s...")
            time.sleep(wait_seconds)

    raise last_error


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


def find_asin_by_title(titre, categorie=None):
    """
    Retrouve l'ASIN Amazon.{tld} d'un produit à partir de son seul nom, via
    une recherche web réelle — jamais une invention : l'IA doit citer l'URL
    Amazon exacte qu'elle a trouvée (on en extrait l'ASIN), ou répondre
    NON_TROUVE si rien ne correspond clairement. Permet d'ajouter un produit
    sans avoir à aller chercher soi-même le lien/ASIN sur Amazon.
    """
    categorie_hint = f" (catégorie : {categorie})" if categorie else ""
    prompt = f"""Cherche sur le web la fiche produit Amazon.{AMAZON_DOMAIN_TLD} qui correspond
exactement à ce produit{categorie_hint} : "{titre}"

Réponds UNIQUEMENT avec l'URL Amazon complète de cette fiche produit précise (pas un
produit similaire, pas un accessoire, pas un pack). Si aucune fiche Amazon.{AMAZON_DOMAIN_TLD}
ne correspond clairement et avec certitude à ce produit, réponds uniquement avec le mot
NON_TROUVE — n'invente jamais un lien approximatif."""

    try:
        response_text = call_groq_compound(prompt, max_tokens=200)
    except Exception as error:
        print(f"[find_asin_by_title] Groq échoué ({error}), tentative Gemini")
        try:
            response_text = call_gemini_grounded(prompt)
        except Exception as error2:
            print(f"[find_asin_by_title] Gemini échoué aussi : {error2}")
            return None

    return extract_asin_from_input(response_text)


def _parse_brightdata_response(text):
    """
    Le dataset "temps réel" de Bright Data ne renvoie pas un tableau JSON
    classique pour un lot de plusieurs URLs, mais du NDJSON (un objet JSON
    par ligne) — non documenté publiquement, découvert en inspectant une
    vraie réponse à 3 URLs (response.json() plante dessus avec "Extra data"
    dès le 2e objet). Le téléchargement d'un snapshot asynchrone (voir
    _brightdata_poll_snapshot), lui, renvoie un vrai tableau JSON — les deux
    formes sont acceptées ici.
    """
    text = text.strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            return json.loads(text)
        except ValueError:
            raise RuntimeError("Réponse Bright Data invalide (pas du JSON).")

    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except ValueError:
            raise RuntimeError("Réponse Bright Data invalide (pas du JSON).")
    return items


BRIGHTDATA_POLL_INTERVAL_SECONDS = 5


def _brightdata_poll_snapshot(snapshot_id, deadline):
    """
    Suit une collecte Bright Data passée en asynchrone (voir
    _brightdata_scrape_sync) jusqu'à ce qu'elle soit prête, puis télécharge
    le résultat. `deadline` est un timestamp absolu (time.time() + timeout
    du côté appelant) — pas un délai relatif, pour que le temps déjà passé
    à attendre compte dans le budget total plutôt que de le redémarrer à
    chaque appel.
    """
    while time.time() < deadline:
        try:
            status_response = requests.get(
                f"https://api.brightdata.com/datasets/v3/progress/{snapshot_id}",
                headers={"Authorization": f"Bearer {BRIGHTDATA_API_TOKEN}"},
                timeout=30,
            )
        except requests.exceptions.RequestException as error:
            raise RuntimeError(f"Erreur réseau en suivant la collecte Bright Data : {error}")

        if not status_response.ok:
            raise RuntimeError(f"Suivi de la collecte Bright Data en erreur ({status_response.status_code}).")

        status = status_response.json().get("status")
        if status == "ready":
            break
        if status in ("failed", "error"):
            raise RuntimeError(f"Collecte Bright Data échouée (statut : {status}).")
        time.sleep(BRIGHTDATA_POLL_INTERVAL_SECONDS)
    else:
        raise RuntimeError("Délai dépassé en attendant la fin de la collecte Bright Data.")

    try:
        download_response = requests.get(
            f"https://api.brightdata.com/datasets/v3/snapshot/{snapshot_id}",
            params={"format": "json"},
            headers={"Authorization": f"Bearer {BRIGHTDATA_API_TOKEN}"},
            timeout=60,
        )
    except requests.exceptions.RequestException as error:
        raise RuntimeError(f"Erreur réseau en téléchargeant la collecte Bright Data : {error}")

    if not download_response.ok:
        raise RuntimeError(f"Téléchargement de la collecte Bright Data en erreur ({download_response.status_code}).")

    return _parse_brightdata_response(download_response.text)


def _brightdata_scrape_sync(urls, timeout):
    """
    Appelle le dataset "Amazon Products" de Bright Data (endpoint
    /datasets/v3/scrape). Pour un petit lot, l'API répond directement (mode
    "temps réel"). Au-delà d'un certain nombre d'URLs par appel — non
    documenté précisément, constaté en pratique à partir d'une bonne
    centaine (voir /api/admin/refresh-prices) — elle bascule d'elle-même en
    traitement asynchrone : HTTP 202 avec un simple snapshot_id à suivre et
    télécharger séparément, plutôt que les résultats attendus. Les deux cas
    sont gérés ici de façon transparente pour l'appelant, qui reçoit toujours
    directement la liste des résultats. urls : liste de dicts
    {"url": "https://www.amazon..."}.
    """
    deadline = time.time() + timeout
    # Compté AVANT l'appel : une requête partie est facturée même si la
    # réponse n'arrive pas (délai dépassé, collecte asynchrone...).
    record_api_usage("brightdata", len(urls))
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

    if response.status_code == 202:
        try:
            snapshot_id = response.json()["snapshot_id"]
        except (ValueError, KeyError):
            raise RuntimeError("Bright Data a basculé en asynchrone sans snapshot_id exploitable.")
        return _brightdata_poll_snapshot(snapshot_id, deadline)

    if not response.ok:
        raise RuntimeError(f"Bright Data a répondu une erreur ({response.status_code}) : {response.text[:300]}")

    return _parse_brightdata_response(response.text)


def _find_own_variation_price(item, asin):
    """
    Certaines fiches Amazon ("styles"/tailles/couleurs multiples) exposent
    un tableau "variations" où CHAQUE entrée a son propre "asin" et son
    propre "price" — plusieurs produits pourtant différents partageant la
    même page parente. La recherche récursive générique
    (_find_field_recursive) descend aussi dans ce tableau et peut remonter
    le prix de la PREMIÈRE variante rencontrée plutôt que celle demandée :
    bug confirmé plusieurs fois cette session (plusieurs fiches de produits
    différents affichant exactement le même prix, suspect). Ici, on ne fait
    pas confiance à l'ordre du tableau : on cherche explicitement l'entrée
    dont l'asin correspond exactement à celui demandé, pour n'utiliser QUE
    son propre prix.
    """
    if not isinstance(item, dict):
        return None
    variations = item.get("variations")
    if not isinstance(variations, list):
        return None
    for variation in variations:
        if not isinstance(variation, dict):
            continue
        variation_asin = variation.get("asin")
        if isinstance(variation_asin, str) and variation_asin.upper() == asin.upper():
            return parse_amazon_price(variation.get("price"))
    return None


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
    # "variations" exclu de la recherche récursive générique (voir
    # _find_own_variation_price ci-dessus) : sans ça, le prix (ou l'image,
    # la dispo...) d'une variante SŒUR pourrait être pris par erreur pour
    # ceux du produit demandé.
    item_sans_variations = {k: v for k, v in item.items() if k != "variations"} if isinstance(item, dict) else item

    nom = _find_field_recursive(item_sans_variations, ["title", "name", "productTitle"])
    marque = _find_field_recursive(item_sans_variations, ["brand", "manufacturer", "brandName"])
    own_variation_price = _find_own_variation_price(item, asin)
    prix_raw = None if own_variation_price is not None else _find_field_recursive(item_sans_variations, ["final_price", "price", "initial_price", "currentPrice"])
    disponibilite = _find_field_recursive(item_sans_variations, ["availability", "inStock", "stockStatus", "availabilityStatus"])
    lien = _find_field_recursive(item_sans_variations, ["url", "link", "productUrl"])

    # is_available=False (champ Bright Data explicite) prime sur TOUT prix
    # trouvé ailleurs : constaté en pratique qu'une fiche sans offre Amazon
    # active affiche quand même un "prix" dans variations/other_sellers_prices
    # venant d'un simple REVENDEUR TIERS marketplace (ex: "OZGE UNIFORM" à
    # 2840€ pour une carte qui en vaut 450) — jamais le prix Amazon officiel.
    # Sans ce garde-fou, ces prix de spéculation tiers passaient pour de
    # vrais prix disponibles.
    is_available = item.get("is_available") if isinstance(item, dict) else None
    if is_available is False:
        own_variation_price = None
        prix_raw = None

    # Filtre "produits neufs uniquement" : une fiche reconditionnée/occasion
    # a presque toujours l'un de ces mots dans son titre Amazon (jamais un
    # champ "condition" structuré et fiable dans ce dataset) — mieux vaut ce
    # filtre imparfait sur le titre que d'importer du matériel d'occasion
    # sans le signaler.
    est_occasion = isinstance(nom, str) and bool(re.search(
        r"reconditionn|renewed|refurbish|remis\s*à\s*neuf|occasion|used\b|d['’]occasion",
        nom, re.IGNORECASE,
    ))

    # Le titre ne suffit pas : ce dataset n'a AUCUN champ "condition"
    # structuré, et le vendeur "Amazon Seconde main" (programme officiel
    # de reconditionné/occasion d'Amazon) peut très bien REMPORTER la Buy
    # Box sans que ça apparaisse nulle part ailleurs — constaté en pratique
    # sur un Ryzen 5 5500 vendu "D'occasion" à 85,12€ par ce vendeur, prix
    # qu'on aurait sinon importé comme un prix neuf normal. On regarde donc
    # aussi other_sellers_prices : si une offre de ce vendeur (ou "Amazon
    # Warehouse"/"reconditionné") a exactement le prix retenu, la Buy Box
    # est cette offre d'occasion.
    if not est_occasion:
        other_sellers = item.get("other_sellers_prices") if isinstance(item, dict) else None
        prix_retenu = own_variation_price if own_variation_price is not None else parse_amazon_price(prix_raw)
        if isinstance(other_sellers, list) and prix_retenu is not None:
            for offer in other_sellers:
                if not isinstance(offer, dict):
                    continue
                seller_name = offer.get("seller_name") or ""
                seller_url = offer.get("seller_url") or ""
                offer_price = offer.get("price")
                is_used_seller = bool(re.search(r"seconde main|warehouse|reconditionn|renewed|occasion", f"{seller_name} {seller_url}", re.IGNORECASE))
                if is_used_seller and isinstance(offer_price, (int, float)) and abs(offer_price - prix_retenu) < 0.01:
                    est_occasion = True
                    break

    if est_occasion:
        own_variation_price = None
        prix_raw = None

    image_url = _find_field_recursive(item_sans_variations, ["image_url", "imageUrl", "main_image", "image", "images", "thumbnail"])
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
    description = _find_field_recursive(item_sans_variations, ["description"])

    return {
        "asin": asin,
        "nom": nom if isinstance(nom, str) else None,
        "marque": marque if isinstance(marque, str) else None,
        "prix": own_variation_price if own_variation_price is not None else parse_amazon_price(prix_raw),
        "image_url": image_url,
        "disponibilite": disponibilite if isinstance(disponibilite, (str, bool)) else None,
        "lien": lien if isinstance(lien, str) else fallback_lien,
        "caracteristiques_amazon": caracteristiques_amazon,
        "description": description if isinstance(description, str) else None,
    }


BRIGHTDATA_SCRAPE_MAX_ATTEMPTS = 3


def fetch_amazon_product(asin, timeout=30):
    """
    Récupère nom/marque/prix/image/disponibilité pour un ASIN via le dataset
    "Amazon Products" de Bright Data en mode synchrone (5000 requêtes
    gratuites/mois, jamais de scraping fait par ce serveur lui-même — Bright
    Data collecte et renvoie des données déjà structurées).

    Sous charge (plusieurs ASIN en lot, même avec une faible concurrence),
    Bright Data renvoie parfois un résultat vide pour un ASIN pourtant
    valide — le même ASIN retenté juste après, seul, fonctionne. On retente
    donc quelques fois avant d'abandonner, comme pour les appels Groq/Gemini
    plus haut dans ce fichier.
    """
    if not BRIGHTDATA_API_TOKEN:
        raise RuntimeError("BRIGHTDATA_API_TOKEN absente")
    if brightdata_remaining_total() <= 0:
        raise RuntimeError(
            f"Quota gratuit Bright Data du mois atteint ({BRIGHTDATA_MONTHLY_QUOTA} fiches) : "
            "nouvel essai possible le 1er du mois prochain."
        )

    url = f"https://www.amazon.{AMAZON_DOMAIN_TLD}/dp/{asin}"

    last_error = None
    for attempt in range(1, BRIGHTDATA_SCRAPE_MAX_ATTEMPTS + 1):
        try:
            results = _brightdata_scrape_sync([{"url": url}], timeout)
        except RuntimeError as error:
            last_error = error
        else:
            if results:
                item = results[0] if isinstance(results, list) else results
                info = _normalize_brightdata_item(item, asin)
                info["_raw_preview"] = json.dumps(item, ensure_ascii=False)[:1500]
                return info
            last_error = RuntimeError(f"Aucun résultat renvoyé par Bright Data pour l'ASIN {asin}.")

        if attempt < BRIGHTDATA_SCRAPE_MAX_ATTEMPTS:
            wait_seconds = 2 * attempt
            print(f"[fetch_amazon_product] {asin} : échec (essai {attempt}/{BRIGHTDATA_SCRAPE_MAX_ATTEMPTS}), nouvel essai dans {wait_seconds}s…")
            time.sleep(wait_seconds)

    raise last_error


# Mots-clés de disponibilité observés sur les pages Amazon renvoyées par
# ZenRows (le proxy premium peut aboutir sur un nœud de sortie non-FR, la
# page peut donc s'afficher en anglais même sur amazon.fr — on reconnaît
# les deux langues plutôt que de forcer une locale non garantie).
_ZENROWS_INDISPONIBLE_PATTERNS = (
    "indisponible", "actuellement indisponible", "rupture de stock",
    "currently unavailable", "out of stock", "temporarily out of stock",
)


def _parse_zenrows_amazon_html(html, asin):
    """
    Extrait prix/disponibilité/image/titre d'une page produit Amazon brute
    (HTML), récupérée via ZenRows. Contrairement à Bright Data (dataset déjà
    structuré), ici c'est nous qui parsons le HTML — plus fragile (une
    refonte de page Amazon peut casser ces regex sans prévenir), d'où le
    style volontairement tolérant : un champ non trouvé reste None plutôt que
    de faire échouer tout l'appel.
    """
    titre_match = re.search(r'<span id="productTitle"[^>]*>\s*([^<]+?)\s*<', html)
    nom = titre_match.group(1).strip() if titre_match else None

    prix = None
    price_zone_match = re.search(r'corePriceDisplay_(?:desktop|mobile)_feature_div(.{0,8000})', html, re.DOTALL)
    if price_zone_match:
        zone = price_zone_match.group(1)
        whole_match = re.search(r'a-price-whole">\s*(\d[\d\s]*)', zone)
        frac_match = re.search(r'a-price-fraction">\s*(\d+)', zone)
        if whole_match:
            whole = whole_match.group(1).replace(" ", "").replace("\xa0", "")
            frac = frac_match.group(1) if frac_match else "00"
            try:
                prix = float(f"{whole}.{frac}")
            except ValueError:
                prix = None

    dispo_match = re.search(r'id="availability"[^>]*>(.*?)</div>', html, re.DOTALL)
    disponible = None
    if dispo_match:
        dispo_text = re.sub(r"<[^>]+>", " ", dispo_match.group(1)).strip().lower()
        if any(mot in dispo_text for mot in _ZENROWS_INDISPONIBLE_PATTERNS):
            disponible = False
        elif dispo_text:
            disponible = True
    if disponible is None:
        # Pas de bloc "availability" identifiable : on retombe sur la
        # présence d'un prix (mêmes limites que côté Bright Data — un prix
        # trouvé vaut "disponible", son absence vaut "épuisé").
        disponible = prix is not None

    image_match = re.search(r'"hiRes":"([^"]+)"', html)
    image_url = image_match.group(1) if image_match else None

    return {
        "asin": asin,
        "nom": nom,
        "marque": None,
        "prix": prix if disponible else None,
        "image_url": image_url,
        "disponibilite": disponible,
        "lien": f"https://www.amazon.{AMAZON_DOMAIN_TLD}/dp/{asin}",
        "caracteristiques_amazon": [],
        "description": None,
    }


ZENROWS_SCRAPE_MAX_ATTEMPTS = 2


def fetch_amazon_product_zenrows(asin, timeout=30):
    """
    Équivalent de fetch_amazon_product, via ZenRows plutôt que Bright Data —
    utilisé uniquement en complément pour le rafraîchissement quotidien
    prix/stock (voir _run_daily_price_refresh_rotation), jamais pour l'import
    d'un nouveau composant (pas de caractéristiques techniques détaillées
    disponibles par ce chemin).
    """
    if not ZENROWS_API_KEY:
        raise RuntimeError("ZENROWS_API_KEY absente")

    url = f"https://www.amazon.{AMAZON_DOMAIN_TLD}/dp/{asin}"
    last_error = None
    for attempt in range(1, ZENROWS_SCRAPE_MAX_ATTEMPTS + 1):
        record_api_usage("zenrows", ZENROWS_CREDITS_PER_REQUEST)
        try:
            response = requests.get(
                "https://api.zenrows.com/v1/",
                params={"apikey": ZENROWS_API_KEY, "url": url, "premium_proxy": "true"},
                timeout=timeout,
            )
            # Un 404 ZenRows ici veut dire que la fiche Amazon cible elle-même
            # renvoie 404 (produit retiré/dé-listé) — constaté en pratique sur
            # un Ryzen 5 5500 déjà marqué épuisé. Pas une panne à retenter :
            # un vrai signal "indisponible", traité pareil qu'un prix absent.
            if response.status_code == 404:
                return {
                    "asin": asin, "nom": None, "marque": None, "prix": None,
                    "image_url": None, "disponibilite": False, "lien": url,
                    "caracteristiques_amazon": [], "description": None,
                }
            response.raise_for_status()
            info = _parse_zenrows_amazon_html(response.text, asin)
            if info["nom"] is None and info["prix"] is None:
                raise RuntimeError(f"ZenRows : page renvoyée mais rien d'exploitable pour {asin} (bloqué par Amazon ?)")
            return info
        except Exception as error:
            last_error = error
            if attempt < ZENROWS_SCRAPE_MAX_ATTEMPTS:
                time.sleep(2 * attempt)

    raise last_error


APIFY_SCRAPE_MAX_ATTEMPTS = 2


def fetch_amazon_products_apify(asins, timeout=120):
    """
    Récupère prix/disponibilité/image pour PLUSIEURS ASIN en un seul appel
    (contrairement à ZenRows, cet actor accepte un lot de requêtes dans un
    même run — un seul coût de démarrage de run, pas un par ASIN). Renvoie
    un dict {ASIN: info normalisée}. Un ASIN absent du résultat (fiche
    introuvable en recherche Amazon — testé en pratique sur un produit
    dé-listé, l'actor renvoie simplement un tableau vide plutôt qu'un
    résultat erroné) est traité comme indisponible par l'appelant, pas
    comme une erreur.

    Recherche par ASIN plutôt que fetch direct de la page /dp/ (mode de
    fonctionnement propre à cet actor) : Amazon renvoie alors ce produit en
    position 1 des résultats de recherche dans l'immense majorité des cas
    (l'ASIN est un identifiant quasi unique pour leur moteur de recherche) —
    on vérifie quand même que l'ASIN renvoyé correspond exactement à celui
    demandé avant d'utiliser un résultat, pour ne jamais silencieusement
    associer le prix d'un AUTRE produit à la mauvaise fiche.
    """
    if not APIFY_API_TOKEN:
        raise RuntimeError("APIFY_API_TOKEN absente")
    if not asins:
        return {}

    payload = {
        "queries": list(asins),
        "marketplaces": [AMAZON_DOMAIN_TLD],
        "maxItems": len(asins),
    }

    last_error = None
    for attempt in range(1, APIFY_SCRAPE_MAX_ATTEMPTS + 1):
        record_api_usage("apify", len(asins))
        try:
            response = requests.post(
                f"https://api.apify.com/v2/acts/{APIFY_AMAZON_ACTOR_ID}/run-sync-get-dataset-items",
                params={"token": APIFY_API_TOKEN},
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            items = response.json()
            break
        except Exception as error:
            last_error = error
            items = None
            if attempt < APIFY_SCRAPE_MAX_ATTEMPTS:
                time.sleep(3 * attempt)
    else:
        raise last_error

    results_by_asin = {}
    for item in (items or []):
        if not isinstance(item, dict):
            continue
        item_asin = item.get("asin")
        # Demandé explicitement plus haut : jamais faire confiance à la
        # position, seulement à une correspondance exacte d'ASIN.
        if not isinstance(item_asin, str) or item_asin not in asins:
            continue
        prix = item.get("priceValue")
        results_by_asin[item_asin] = {
            "asin": item_asin,
            "nom": item.get("title"),
            "marque": None,
            "prix": prix if isinstance(prix, (int, float)) else None,
            "image_url": item.get("imageUrl"),
            "disponibilite": isinstance(prix, (int, float)),
            "lien": item.get("url") or f"https://www.amazon.{AMAZON_DOMAIN_TLD}/dp/{item_asin}",
            "caracteristiques_amazon": [],
            "description": None,
        }
    return results_by_asin


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
    client_ip = _client_ip(request)
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


# Le catalogue a grossi à plusieurs centaines de composants (ex: 210 GPU) :
# même sans les specs détaillées, les lister TOUS dépasse la limite de
# tokens d'ENTRÉE de Groq (7000 ITPM/minute, partagée par tout le site) en
# un seul appel — ce qui déclenchait des rate-limits en cascade et rendait
# l'assistant très lent, voire en échec complet. On échantillonne donc un
# sous-ensemble représentatif par catégorie, réparti sur TOUTE la gamme de
# prix (pas juste les moins chers) : l'IA voit toujours des options du bas,
# du milieu et du haut de gamme pour bien juger l'usage/budget, sans avoir
# besoin de connaître chaque variante quasi-identique d'un même modèle. On
# exclut aussi les composants épuisés : inutile de les proposer, et ça
# réduit encore la taille du prompt. Partagé entre /suggest-config et
# /api/refine-config (voir plus bas), pour que les deux voient exactement
# le même catalogue échantillonné.
# Testé en pratique à 25 : la liste catalogue à elle seule dépasse déjà la
# limite Groq (7000 tokens d'entrée/minute) dès le PREMIER essai — avant
# même la boucle de correction qui, elle, RÉ-INCLUT le prompt de base en
# entier en plus des erreurs, donc grossit encore plus vite. Avec Gemini
# potentiellement à quota épuisé (constaté : 500 requêtes/jour, vite
# atteint), Groq est alors le seul repli restant — et un repli qui échoue
# aussi sur la taille du prompt revient à ne plus avoir de repli du tout.
# 15 laisse une marge confortable sous la limite même après 2-3 tours de
# correction, tout en gardant une diversité de prix suffisante par
# catégorie (bas/milieu/haut de gamme).
MAX_ITEMS_PER_CATEGORY_IN_PROMPT = 15


def _sample_catalog_for_prompt(components):
    def _sample_by_price(items, max_items):
        items = sorted(items, key=lambda c: c.get("prix_indicatif") or 0)
        if len(items) <= max_items:
            return items
        step = len(items) / max_items
        return [items[int(i * step)] for i in range(max_items)]

    by_category = {}
    for c in components:
        if c.get("en_stock", True):
            by_category.setdefault(c["categorie"], []).append(c)

    sampled_components = [
        c
        for items in by_category.values()
        for c in _sample_by_price(items, MAX_ITEMS_PER_CATEGORY_IN_PROMPT)
    ]

    def _specs_suffix(c):
        # Sans ça, l'IA doit deviner la compatibilité (socket, format...)
        # rien qu'au NOM du produit — constaté en pratique : elle se trompe
        # de façon répétée sur des paires CPU/carte mère de socket différent
        # même après plusieurs tours de correction, l'info n'étant tout
        # simplement pas dans le prompt pour qu'elle vérifie. On expose donc
        # ici les seuls champs qui comptent pour la compatibilité (mêmes
        # champs que REQUIRED_FIELDS/compatibility.py), pas toutes les specs
        # (garderait le prompt inutilement gros).
        required = REQUIRED_FIELDS.get(c["categorie"], {})
        specs = c.get("specs") or {}
        parts = [f"{key}={specs[key]}" for key in required if key in specs]
        return f" {{{', '.join(parts)}}}" if parts else ""

    components_list = "\n".join([
        f"- id {c['id']}: [{c['categorie']}] {c['nom']}{_specs_suffix(c)} ({c['prix_indicatif']}€)"
        for c in sampled_components
    ])
    return components_list


# Champs de configuration partagés par /suggest-config et /api/refine-config
# — un seul endroit à mettre à jour si une catégorie s'ajoute un jour.
CONFIG_ID_FIELDS = ("cpu_id", "motherboard_id", "ram_id", "gpu_id", "psu_id", "storage_id", "case_id")
FIELD_TO_CATEGORY_BACKEND = {
    "cpu_id": "CPU", "motherboard_id": "Carte mère", "ram_id": "RAM", "gpu_id": "GPU",
    "psu_id": "Alimentation", "storage_id": "Stockage", "case_id": "Boîtier",
}

# Message générique renvoyé à l'utilisateur quand TOUS les fournisseurs IA
# (Gemini + repli Groq) échouent — jamais le texte brut de l'exception
# (erreur API en anglais, quotas, jargon technique), gardé uniquement dans
# les logs serveur pour le diagnostic.
AI_PROVIDERS_UNAVAILABLE_MESSAGE = "L'assistant IA est temporairement surchargé, réessayez dans quelques minutes."


def _generate_and_verify_suggestion(base_prompt, components_by_id, allow_advice=False):
    """
    Boucle de génération + correction partagée par /suggest-config (nouvelle
    config) et /api/refine-config (modification d'une config existante) :
    appelle l'IA, vérifie compatibilité + budget côté serveur (jamais de
    confiance aveugle dans l'IA pour ça), et si ça échoue, renvoie les
    erreurs précises à l'IA pour qu'elle corrige — jusqu'à MAX_AI_ATTEMPTS
    tentatives.

    allow_advice=True (utilisé seulement par /api/refine-config) : accepte
    aussi une réponse {"type": "advice", "message": "..."} quand la demande
    de l'utilisateur n'appelait aucun changement (une simple question), et
    la renvoie directement sans passer par la vérification de compatibilité
    (qui n'a pas de sens sur une réponse qui n'est pas une config).
    """
    current_prompt = base_prompt
    last_errors = None

    for attempt in range(1, MAX_AI_ATTEMPTS + 1):
        suggestion_text = call_ai_model(current_prompt)

        parsed = parse_ai_json(suggestion_text)
        if parsed is None:
            print(f"[assistant-ia] JSON invalide renvoyé par l'IA : {suggestion_text}")
            return {"status": "error", "message": "L'assistant n'a pas réussi à générer une réponse valide, réessayez."}

        # Si l'IA ne peut pas produire une config (ex: aucun composant ne
        # correspond à la demande), elle répond avec un champ "error" au lieu
        # du schéma attendu. On relaie ce message tel quel plutôt que de
        # tomber sur "champs manquants", moins clair pour l'utilisateur.
        if isinstance(parsed, dict) and "error" in parsed:
            return {"status": "error", "message": parsed["error"]}

        if allow_advice and isinstance(parsed, dict) and parsed.get("type") == "advice":
            return {"status": "advice", "message": parsed.get("message") or ""}

        compatibility_result = verify_compatibility(parsed)
        errors = list(compatibility_result["errors"])

        budget_max = parsed.get("budget_max") if isinstance(parsed, dict) else None
        if compatibility_result["compatible"] and isinstance(budget_max, (int, float)) and budget_max > 0:
            real_total = compute_real_total(parsed, components_by_id)
            if real_total > budget_max:
                overage = real_total - budget_max
                errors.append(
                    f"Le total réel de cette configuration ({real_total:.2f}€) dépasse le "
                    f"budget indiqué ({budget_max}€) de {overage:.2f}€ — remplace au moins un "
                    f"composant par une option moins chère de la liste (en priorité une "
                    f"catégorie secondaire comme boîtier, alimentation ou stockage plutôt que "
                    f"CPU/GPU si l'usage le permet) pour repasser sous le budget, ne garde "
                    f"surtout pas les mêmes choix."
                )

        if not errors:
            return {"status": "ok", "suggestion": parsed}

        last_errors = errors
        if attempt < MAX_AI_ATTEMPTS:
            errors_text = "\n".join(f"- {e}" for e in errors)
            current_prompt = f"""{base_prompt}

Ta tentative précédente {json.dumps(parsed)} est invalide pour les raisons suivantes :
{errors_text}

Corrige ta réponse en tenant compte de ces erreurs. Réponds UNIQUEMENT avec le JSON demandé."""

    print(f"[assistant-ia] échec après {MAX_AI_ATTEMPTS} tentatives : {last_errors}")
    return {
        "status": "error",
        "message": "Je n'ai pas trouvé de configuration compatible qui respecte votre budget. Essayez d'augmenter le budget ou de préciser votre besoin.",
    }


@app.post("/suggest-config")
def suggest_config(request: SuggestConfigRequest, _rate_limit=Depends(enforce_ai_rate_limit)):
    """Route IA : suggère une config basée sur la description utilisateur"""
    try:
        # Récupère tous les composants
        components = get_catalog()
        if not components:
            return {"status": "error", "message": "Aucun composant disponible"}

        components_by_id = {c["id"]: c for c in components}

        # Crée le prompt — l'ID de chaque composant DOIT être visible ici,
        # sinon l'IA ne peut que deviner/halluciner des IDs, ce qui donne des
        # suggestions rejetées à tort par verify_compatibility.
        components_list = _sample_catalog_for_prompt(components)

        base_prompt = f"""Tu es un expert en configuration PC. L'utilisateur décrit son besoin en langage naturel.
Suggère une configuration complète en JSON strict (pas de markdown, juste du JSON valide).

Composants disponibles (utilise EXACTEMENT les "id" indiqués ci-dessous, ne les invente jamais) :
{components_list}

Besoin utilisateur: {request.user_input}

RÈGLES IMPORTANTES :
- Le site vend maintenant CPU, Carte mère, RAM, GPU, Alimentation, Stockage et Boîtier :
  choisis un composant RÉEL de la liste ci-dessus pour CHAQUE catégorie qui y a au moins une
  option, en respectant la compatibilité entre eux. Ne mets un champ à null QUE si la liste
  ci-dessus ne contient VRAIMENT aucun composant de cette catégorie — jamais par défaut.
- Certains composants ont leurs specs de compatibilité entre accolades juste après leur nom
  (ex: "socket=AM5"). UTILISE ces valeurs pour vérifier toi-même la compatibilité (même socket
  CPU/carte mère, même type de RAM que la carte mère, format de carte mère supporté par le
  boîtier...) plutôt que de deviner à partir du nom du produit seul — c'est la cause la plus
  fréquente d'erreur de compatibilité.
- Si l'utilisateur mentionne un budget, indique-le dans le champ "budget_max" (nombre, en euros)
  et la somme des prix des composants choisis (parmi ceux non null) ne doit JAMAIS dépasser ce
  budget. Choisis TOUJOURS la meilleure configuration RÉELLEMENT achetable avec ce budget parmi
  les composants listés — n'utilise {{"error": "..."}} pour "budget insuffisant" QUE si la somme
  des composants les moins chers de chaque catégorie listée dépasse déjà ce budget à elle seule
  (donc strictement aucune combinaison n'est achetable, pas juste une combinaison "pas assez
  puissante" à ton goût). Un jeu exigeant avec un petit budget n'est PAS une raison de refuser :
  propose la meilleure config possible dans ce budget, quitte à jouer en réglages modérés avec
  upscaling (DLSS/FSR) plutôt qu'en ultra/ray-tracing — ne juge jamais un budget "insuffisant"
  sur la base du confort ou du niveau de réglages graphiques.
- Si l'utilisateur ne mentionne aucun budget, mets "budget_max": null.
- Adapte vraiment le CHOIX (quel CPU, quel GPU...) à l'USAGE décrit (gaming, montage vidéo,
  bureautique, etc.) DANS la limite du budget donné : à budget égal, privilégie les composants
  qui servent le mieux cet usage plutôt que systématiquement les moins chers — mais le budget
  reste la seule contrainte qui peut faire refuser une config, jamais l'usage à lui seul.
- Pour un usage gaming, choisis un CPU et un GPU de GAMME COMPARABLE (ni un GPU haut de gamme
  avec un CPU d'entrée de gamme qui le limiterait, ni l'inverse) : c'est à toi de choisir cette
  paire équilibrée dès le départ, pas à une vérification après coup de la corriger.
- Si l'utilisateur mentionne un ou plusieurs jeux vidéo précis (par leur nom), liste-les dans
  le champ "jeux" (liste de chaînes, noms tels que mentionnés par l'utilisateur, orthographe
  corrigée si besoin). Sinon, "jeux": [].
- Si la demande est trop vague pour choisir intelligemment (aucun usage, aucun budget, aucun
  indice), réponds avec {{"error": "..."}} pour demander des précisions à l'utilisateur.
- Le champ "error", quand tu l'utilises, doit être UNE SEULE phrase courte (15 mots maximum),
  simple et compréhensible par un utilisateur non-technique : dis juste POURQUOI ça ne marche
  pas (budget trop serré, besoin pas assez précis...), sans jamais mentionner d'ID, de nombre
  de composants en base, de nom de champ technique, ni détailler la liste des composants
  disponibles ou manquants. N'utilise JAMAIS ce champ juste parce qu'une catégorie n'a aucun
  composant disponible dans la liste — mets son id à null et continue normalement, ce n'est
  pas une erreur.

Réponds UNIQUEMENT avec un JSON valide de cette forme, où chaque valeur d'id est soit l'"id"
réel d'un composant pris dans la liste ci-dessus (pas un numéro de ligne, pas un exemple),
soit null si aucun composant n'est disponible pour cette catégorie :
{{"cpu_id": <id réel ou null>, "motherboard_id": <id réel ou null>, "ram_id": <id réel ou null>, "gpu_id": <id réel ou null>, "psu_id": <id réel ou null>, "storage_id": <id réel ou null>, "case_id": <id réel ou null>, "budget_max": <nombre ou null>, "jeux": [<noms de jeux ou liste vide>]}}"""

        # Jamais de confiance aveugle dans l'IA pour la compatibilité ou le
        # budget (le total réel est toujours recalculé côté serveur à partir
        # des prix en base) — voir _generate_and_verify_suggestion.
        result = _generate_and_verify_suggestion(base_prompt, components_by_id)
        if result["status"] != "ok":
            return result
        suggestion_json = result["suggestion"]

        # La vérification par recherche web (groq/compound) a été retirée du
        # chemin normal : c'était de loin l'étape la plus lente (recherche
        # web réelle après jusqu'à MAX_AI_ATTEMPTS appels de correction déjà
        # séquentiels), pour un paragraphe purement informatif. La
        # compatibilité et le budget restent, eux, toujours vérifiés
        # côté serveur ci-dessus — ce n'est que ce texte en plus qui saute.
        chosen_components = [
            components_by_id[suggestion_json[field]]
            for field in CONFIG_ID_FIELDS
            if suggestion_json.get(field) in components_by_id
        ]

        # Si l'utilisateur a cité un ou plusieurs jeux dans sa demande (champ
        # "jeux" rempli par l'IA dans le même appel que la suggestion, pas un
        # appel séparé), on estime directement les FPS pour cette config —
        # réutilise le même moteur (et le même cache) que /api/estimate-fps.
        jeux = suggestion_json.get("jeux") if isinstance(suggestion_json.get("jeux"), list) else []
        fps_estimation = _run_fps_estimation(chosen_components, jeux) if jeux else None

        return {
            "status": "ok",
            "suggestion": suggestion_json,
            "compatible": True,
            "fps_estimation": fps_estimation,
        }

    except Exception as error:
        # Le texte brut de l'exception (erreur API Gemini/Groq, jargon
        # technique en anglais, quotas...) n'est utile qu'en log serveur —
        # jamais montré tel quel à l'utilisateur, qui n'a besoin de savoir
        # que "réessaie plus tard", pas le détail de quel fournisseur a
        # échoué ni pourquoi.
        print(f"[suggest-config] échec inattendu : {error}")
        return {"status": "error", "message": AI_PROVIDERS_UNAVAILABLE_MESSAGE}


class RefineConfigRequest(BaseModel):
    current_suggestion: dict  # {"cpu_id": id ou null, ..., "jeux": [...]} — la dernière suggestion affichée
    user_input: str = Field(max_length=MAX_USER_INPUT)


@app.post("/api/refine-config")
def refine_config(request: RefineConfigRequest, _rate_limit=Depends(enforce_ai_rate_limit)):
    """
    Route IA : fait évoluer une configuration DÉJÀ suggérée à partir d'une
    demande en langage naturel — soit une modification ("remplace le GPU
    par moins cher", "j'aimerais plus de stockage"), soit une simple
    question de conseil ("quel ventirad pour ce CPU ?") qui n'appelle aucun
    changement. Le prompt laisse l'IA elle-même distinguer les deux cas
    (champ "type": "modification" ou "advice") plutôt que de le déduire
    côté serveur par des mots-clés, trop fragile face à la variété des
    formulations possibles en langage naturel.
    """
    try:
        components = get_catalog()
        if not components:
            return {"status": "error", "message": "Aucun composant disponible"}

        components_by_id = {c["id"]: c for c in components}
        components_list = _sample_catalog_for_prompt(components)

        current_lines = []
        for field in CONFIG_ID_FIELDS:
            category = FIELD_TO_CATEGORY_BACKEND[field]
            component = components_by_id.get(request.current_suggestion.get(field))
            if component:
                current_lines.append(f"- {category}: {component['nom']} ({component['prix_indicatif']}€) [id {component['id']}]")
            else:
                current_lines.append(f"- {category}: aucun composant choisi")
        current_config_text = "\n".join(current_lines)

        budget_max = request.current_suggestion.get("budget_max")
        jeux_actuels = request.current_suggestion.get("jeux") if isinstance(request.current_suggestion.get("jeux"), list) else []

        prompt = f"""Tu es un expert en configuration PC. Voici une configuration DÉJÀ choisie pour l'utilisateur :
{current_config_text}
Budget indiqué à l'origine : {budget_max if budget_max else "aucun"}
Jeux mentionnés à l'origine : {", ".join(jeux_actuels) if jeux_actuels else "aucun"}

Composants disponibles (utilise EXACTEMENT les "id" indiqués ci-dessous, ne les invente jamais) :
{components_list}

L'utilisateur te dit maintenant : {request.user_input}

Détermine d'abord s'il s'agit :
(a) d'une DEMANDE DE MODIFICATION de la configuration (remplacer/ajouter/retirer un composant,
    changer de budget, etc.) — même formulée indirectement (ex: "j'aimerais plus de stockage",
    "un truc moins cher pour le boîtier") ;
(b) d'une SIMPLE QUESTION ou demande de conseil qui n'appelle AUCUN changement de la config
    actuelle (ex: "quel ventirad me conseilles-tu ?", "pourquoi ce CPU ?", "c'est compatible avec X ?").

Si (a) : réponds avec le JSON de modification ci-dessous. Reprends TOUS les champs de la
configuration actuelle SANS LES CHANGER, sauf ceux concernés par la demande (et ceux qu'il faut
ajuster en cascade pour rester compatible, ex: changer d'alimentation si le nouveau GPU consomme
plus). Respecte les mêmes règles de compatibilité et de budget que pour une config initiale :
si "budget_max" était déjà fixé, le total ne doit jamais le dépasser (sauf si l'utilisateur
demande explicitement de changer ce budget).

Si (b) : réponds avec {{"type": "advice", "message": "<conseil clair et utile, quelques phrases
maximum, en te basant sur la configuration actuelle et les composants listés ci-dessus>"}}.

Format JSON pour une modification (reprends TOUS les champs) :
{{"type": "modification", "cpu_id": <id réel ou null>, "motherboard_id": <id réel ou null>, "ram_id": <id réel ou null>, "gpu_id": <id réel ou null>, "psu_id": <id réel ou null>, "storage_id": <id réel ou null>, "case_id": <id réel ou null>, "budget_max": <nombre ou null>, "jeux": [<noms de jeux ou liste vide>]}}

Réponds UNIQUEMENT avec un JSON valide, l'une des deux formes ci-dessus — jamais les deux, jamais de markdown."""

        result = _generate_and_verify_suggestion(prompt, components_by_id, allow_advice=True)
        if result["status"] != "ok":
            return result

        suggestion_json = result["suggestion"]
        chosen_components = [
            components_by_id[suggestion_json[field]]
            for field in CONFIG_ID_FIELDS
            if suggestion_json.get(field) in components_by_id
        ]
        jeux = suggestion_json.get("jeux") if isinstance(suggestion_json.get("jeux"), list) else []
        fps_estimation = _run_fps_estimation(chosen_components, jeux) if jeux else None

        return {
            "status": "ok",
            "suggestion": suggestion_json,
            "compatible": True,
            "fps_estimation": fps_estimation,
        }

    except Exception as error:
        print(f"[refine-config] échec inattendu : {error}")
        return {"status": "error", "message": AI_PROVIDERS_UNAVAILABLE_MESSAGE}


class EstimateFpsRequest(BaseModel):
    composants_json: dict  # {"CPU": id, "GPU": id, ...}
    jeux: list[str]
    qualite: str = "ultra"  # clé de fps_data.QUALITY_PRESETS


# Catégories qui doivent toutes être choisies avant de pouvoir estimer les
# FPS — le goulot d'étranglement se juge en comparant CPU et GPU, les autres
# catégories (RAM, alimentation, stockage, boîtier...) n'entrent pour rien
# dans une estimation FPS, inutile de forcer une config complète pour ça.
REQUIRED_BUILD_CATEGORIES = ("CPU", "GPU")

# Regroupés en un seul appel IA plutôt qu'un par jeu : sinon sélectionner 5
# jeux consommerait 5x le quota Groq/Gemini partagé par tout le site pour
# une seule action utilisateur.
MAX_FPS_GAMES_PER_REQUEST = 5


def _cheapest_price(component):
    """
    Prix le plus bas actuellement connu pour ce composant (le moins cher des
    offres prix_marche relevées), avec repli sur prix_indicatif si aucune
    offre n'est enregistrée — cohérent avec ce que l'utilisateur voit
    affiché comme prix sur les autres pages du site.
    """
    prix_marche = component.get("prix_marche") or []
    prix_releves = [p["prix"] for p in prix_marche if p.get("prix") is not None]
    if prix_releves:
        return min(prix_releves)
    return component.get("prix_indicatif") or 0


def _detect_bottleneck_category(estimation_text, chosen):
    """
    Cherche la ligne "Goulot d'étranglement : ..." dans le texte renvoyé par
    l'IA et en déduit la catégorie concernée (CPU ou GPU — les deux seules
    catégories jugées dans l'estimation FPS). L'IA répond parfois par le nom
    exact du composant, parfois juste par "CPU"/"GPU" : on gère les deux
    formes plutôt que d'imposer un format rigide qui casserait au moindre
    écart de formulation.
    """
    match = re.search(r"goulot d.?étranglement\s*:\s*(.+)", estimation_text, re.IGNORECASE)
    if not match:
        return None
    bottleneck_text = match.group(1).strip().splitlines()[0].lower()

    cpu_component = next((c for c in chosen if c["categorie"] == "CPU"), None)
    gpu_component = next((c for c in chosen if c["categorie"] == "GPU"), None)

    if cpu_component and cpu_component["nom"].lower() in bottleneck_text:
        return "CPU"
    if gpu_component and gpu_component["nom"].lower() in bottleneck_text:
        return "GPU"
    if "cpu" in bottleneck_text and "gpu" not in bottleneck_text:
        return "CPU"
    if "gpu" in bottleneck_text and "cpu" not in bottleneck_text:
        return "GPU"
    return None


def _suggest_upgrade_component(chosen, bottleneck_categorie):
    """
    Propose un composant RÉEL du catalogue (jamais inventé) pour remplacer
    celui identifié comme goulot d'étranglement (toujours "CPU" ou "GPU",
    voir _detect_bottleneck_category) — par calcul déterministe sur
    GPU_PERFORMANCE_INDEX/CPU_PERFORMANCE_INDEX (même indice que
    l'estimation FPS elle-même, voir plus haut) plutôt qu'un appel IA :
    parmi les candidats plus chers que l'actuel, celui qui offre le
    meilleur gain de performance PAR EURO dépensé en plus ("meilleur
    rapport qualité/prix" rendu concret et reproductible).
    """
    current = next((c for c in chosen if c["categorie"] == bottleneck_categorie), None)
    if not current:
        return None

    current_price = _cheapest_price(current)
    if not current_price:
        return None

    index_table = GPU_PERFORMANCE_INDEX if bottleneck_categorie == "GPU" else CPU_PERFORMANCE_INDEX
    current_index = _match_performance_index(current["nom"], index_table)
    if current_index is None:
        return None

    candidates = [
        c for c in get_catalog()
        if c["categorie"] == bottleneck_categorie
        and c["id"] != current["id"]
        and c.get("en_stock", True)
        and _cheapest_price(c) > current_price
    ]
    if not candidates:
        return None

    scored = []
    for c in candidates:
        idx = _match_performance_index(c["nom"], index_table)
        if idx is None or idx <= current_index:
            continue
        price_delta = _cheapest_price(c) - current_price
        value_score = (idx - current_index) / price_delta if price_delta > 0 else 0
        scored.append((value_score, c))
    if not scored:
        return None

    scored.sort(key=lambda pair: pair[0], reverse=True)
    upgrade = scored[0][1]
    return {
        "categorie": bottleneck_categorie,
        "component_id": upgrade["id"],
        "nom": upgrade["nom"],
        "prix_indicatif": upgrade.get("prix_indicatif"),
    }


def _build_fps_response(estimation_text, chosen):
    """
    Emballe le texte d'estimation renvoyé par l'IA dans la réponse API, en y
    ajoutant une suggestion de composant de remplacement RÉEL si un goulot
    d'étranglement CPU ou GPU a été identifié. La suggestion est un
    complément optionnel : son échec (aucun candidat, IA indisponible...)
    ne doit jamais faire échouer l'estimation FPS elle-même.
    """
    bottleneck_categorie = _detect_bottleneck_category(estimation_text, chosen)

    # La détection ci-dessus tourne sur le texte ORIGINAL (elle a besoin de
    # la ligne pour savoir s'il y a un goulot) — mais "aucun notable"
    # n'apporte rien à l'affichage (annoncer l'absence de problème) : on la
    # retire seulement du texte montré à l'utilisateur.
    displayed_text = re.sub(
        r"\n?Goulot d.?étranglement\s*:\s*aucun notable\.?",
        "",
        estimation_text,
        flags=re.IGNORECASE,
    ).strip()

    response = {"status": "ok", "estimation": displayed_text}
    if bottleneck_categorie:
        suggestion = _suggest_upgrade_component(chosen, bottleneck_categorie)
        if suggestion:
            response["suggestion"] = suggestion
    return response


# Résultats mis en cache par (CPU, GPU, jeux demandés) : la recherche web
# (Gemini/groq compound) est trop lente pour un usage interactif et donnait
# en plus un chiffre différent à chaque appel pour une même config. On
# interroge directement le modèle rapide (qwen, sans recherche), et on
# retient le résultat pour que la MÊME config + les MÊMES jeux renvoient
# toujours les mêmes chiffres ensuite, sans re-appeler l'IA. Volontairement
# en mémoire (pas de table dédiée) : le volume de configs/jeux distincts
# testés sur ce site reste minime, et un redémarrage (déploiement) est le
# seul cas qui vide le cache.
FPS_ESTIMATE_CACHE = {}


def _fps_cache_key(chosen, jeux):
    cpu_id = next((c["id"] for c in chosen if c["categorie"] == "CPU"), None)
    gpu_id = next((c["id"] for c in chosen if c["categorie"] == "GPU"), None)
    return (cpu_id, gpu_id, tuple(j.strip().lower() for j in jeux))


# --- Estimation FPS par formule, sans IA ---
#
# Calcul instantané et déterministe à partir de vrais tests publiés
# (TechPowerUp) : voir fps_data.py pour les données, les sources et la
# méthode (minimum entre limite GPU par résolution, limite CPU propre à
# chaque jeu et plafond du jeu). Remplace l'ancienne règle de trois sur
# une seule carte de référence, qui donnait des chiffres éloignés de la
# réalité (même plafond CPU pour tous les jeux, même écart entre cartes
# à toutes les résolutions, mémoire vidéo ignorée).
#
# Indice CPU : mesures TechPowerUp en 720p (voir fps_data.CPU_RELATIVE).

# Indice GPU unique (tri du configurateur, comparateur, suggestions de
# remplacement) : valeur 1440p des vrais tests TechPowerUp, voir
# fps_data.GPU_RELATIVE. Une seule source de vérité avec l'estimation FPS.
GPU_PERFORMANCE_INDEX = [
    (pattern, variants[default_vram][1])
    for pattern, variants, default_vram in fps_data.GPU_RELATIVE
]
# Plafond du score sur 100 affiché par le comparateur (voir compare_performance)
# — toujours la meilleure puce du tableau ci-dessus, jamais recalculé à la
# main pour ne jamais désynchroniser en cas de futur ajout/retrait de GPU.
GPU_PERFORMANCE_CEILING = max(value for _, value in GPU_PERFORMANCE_INDEX)

# Indice CPU en jeu (mesuré TechPowerUp, 9850X3D = 142), voir
# fps_data.CPU_RELATIVE : même source pour le tri, le comparateur et les FPS.
CPU_PERFORMANCE_INDEX = [(pattern, value) for pattern, value, _ in fps_data.CPU_RELATIVE]
CPU_PERFORMANCE_CEILING = max(value for _, value in CPU_PERFORMANCE_INDEX)


def _match_performance_index(nom, index_table, default=None):
    n = fps_data.normalize_cpu_name(nom)
    for pattern, value in index_table:
        if re.search(pattern, n):
            return value
    return default


def _estimate_fps_formula(chosen, jeux, qualite="ultra"):
    """
    Estimation FPS à partir de vrais tests publiés (voir fps_data.py) :
    pour chaque jeu et chaque résolution, FPS = minimum(limite carte
    graphique, limite processeur propre au jeu, plafond du jeu).

    Retourne (texte, résultats structurés). Le texte garde l'ancien format
    ligne par ligne (utilisé par l'assistant IA et _detect_bottleneck_category).
    """
    cpu = next((c for c in chosen if c["categorie"] == "CPU"), None)
    gpu = next((c for c in chosen if c["categorie"] == "GPU"), None)

    gpu_card, gpu_rel, vram = fps_data.match_gpu_full(gpu["nom"]) if gpu else (None, None, None)
    card_key = f"{gpu_card}|{vram}" if gpu_card else None
    cpu_index, cpu_origin = fps_data.match_cpu(cpu["nom"]) if cpu else (None, None)

    lines = []
    resultats = []
    cpu_limited_1440 = 0
    gpu_weak_1080 = 0
    covered = 0

    for jeu in jeux:
        key, data = fps_data.find_game(jeu)
        if key is None or gpu_rel is None:
            raison = data if isinstance(data, str) else (
                "carte graphique non reconnue" if gpu_rel is None else "jeu pas encore couvert"
            )
            resultats.append({"jeu": jeu, "couvert": False, "raison": raison})
            lines.append(f"{jeu} : non estimé ({raison})")
            continue

        covered += 1
        par_resolution = fps_data.estimate_game(key, data, card_key, gpu_rel, vram, cpu_index, qualite)
        origines = {r["origine"] for r in par_resolution.values()}
        resultats.append({
            "jeu": jeu,
            "couvert": True,
            # "mesuré" : cette carte testée dans ce jeu ; "déduit" : extrapolé
            # depuis les cartes testées dans ce même jeu ; "estimé" : pas de test.
            "source": "estimé" if "estimé" in origines else ("déduit" if "déduit" in origines else "mesuré"),
            "test": fps_data.game_source(key),
            "cpu_mesure": cpu_origin == "m",
            "plafond_jeu": data["cap"],
            "resolutions": par_resolution,
        })
        for res_label, res_key in (("1080p", "1080p"), ("1440p", "1440p"), ("4K", "4k")):
            lines.append(f"{jeu} ({res_label}) : {par_resolution[res_key]['fps']} FPS")
        if par_resolution["1440p"]["limite"] == "CPU":
            cpu_limited_1440 += 1
        if par_resolution["1080p"]["limite"] == "GPU" and par_resolution["1080p"]["fps"] < 50:
            gpu_weak_1080 += 1

    # Goulot d'étranglement de la CONFIG (pas d'un jeu isolé) : le processeur
    # bride même en 1440p dans la majorité des jeux, ou la carte graphique
    # reste sous 50 FPS en 1080p dans la majorité des jeux.
    if covered and cpu_limited_1440 * 2 >= covered and cpu:
        bottleneck = cpu["nom"]
    elif covered and gpu_weak_1080 * 2 >= covered and gpu:
        bottleneck = gpu["nom"]
    else:
        bottleneck = "aucun notable"
    lines.append(f"Goulot d'étranglement : {bottleneck}")

    return "\n".join(lines), resultats


def _run_fps_estimation(chosen, jeux, qualite="ultra"):
    """
    Cœur partagé par /api/estimate-fps ET /suggest-config (quand l'utilisateur
    cite un jeu dans sa demande à l'assistant) : calcule l'estimation par
    formule (voir _estimate_fps_formula, plus haut) et met en cache. Ancienne
    version basée sur un appel IA (Gemini) — remplacée : trop lente en usage
    interactif, dépendante d'un fournisseur externe, et capable d'halluciner
    des chiffres plausibles mais faux. Le résultat est maintenant instantané
    et déterministe, mis en cache par config+jeux surtout pour éviter de
    refaire le calcul à chaque appel identique (déjà quasi gratuit en soi).

    Retourne None si `chosen` ne couvre pas REQUIRED_BUILD_CATEGORIES ou si
    `jeux` est vide après nettoyage — appelant depuis /suggest-config, où
    l'estimation FPS est un bonus optionnel plutôt qu'une action explicite
    de l'utilisateur, donc jamais bloquant façon HTTPException ici.
    """
    present_categories = {c["categorie"] for c in chosen}
    if any(cat not in present_categories for cat in REQUIRED_BUILD_CATEGORIES):
        return None

    jeux = [j.strip() for j in (jeux or []) if j and j.strip()]
    jeux = list(dict.fromkeys(jeux))[:MAX_FPS_GAMES_PER_REQUEST]  # dédoublonne, garde l'ordre
    if not jeux:
        return None

    if qualite not in fps_data.QUALITY_PRESETS:
        qualite = "ultra"
    cache_key = (_fps_cache_key(chosen, jeux), qualite)
    cached = FPS_ESTIMATE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    try:
        estimation, resultats = _estimate_fps_formula(chosen, jeux, qualite)
        result = _build_fps_response(estimation, chosen)
        result["resultats"] = resultats
        result["qualite"] = {"id": qualite, "label": fps_data.QUALITY_PRESETS[qualite]["label"]}
        FPS_ESTIMATE_CACHE[cache_key] = result
        return result
    except Exception as error:
        print(f"Estimation FPS échouée : {error}")
        return None


# --- Comparateur de performance (remplace l'ancien comparateur de prix) ---
#
# Réutilise GPU_PERFORMANCE_INDEX / CPU_PERFORMANCE_INDEX (voir plus haut,
# recalibrés sur de vrais benchmarks Tom's Hardware) : même source de
# vérité que l'estimation FPS, pas une deuxième échelle à maintenir en
# double. Pour la RAM, ni indice ni benchmark : capacité et fréquence sont
# extraites directement du NOM du produit (jamais dans specs_json — pas un
# champ de compatibilité requis, voir schema.REQUIRED_FIELDS), qui les
# mentionne de façon assez régulière ("32 Go DDR4 3200 MHz") pour un regex
# simple. Toute autre catégorie retombe sur une simple comparaison de specs
# côte à côte, sans revendiquer de score de performance inventé.
RAM_CAPACITY_PATTERN = re.compile(r"(\d+)\s*go\b", re.IGNORECASE)
RAM_SPEED_PATTERN = re.compile(r"(\d{3,5})\s*(?:mhz|mt/s)\b", re.IGNORECASE)
# Beaucoup de titres écrivent la fréquence sans unité : "DDR4 3200", "DDR5-6000".
RAM_SPEED_AFTER_DDR = re.compile(r"ddr[345]\s*-?\s*(\d{4})\b", re.IGNORECASE)


def _parse_ram_specs(nom):
    capacity_match = RAM_CAPACITY_PATTERN.search(nom)
    speed_match = RAM_SPEED_PATTERN.search(nom) or RAM_SPEED_AFTER_DDR.search(nom)
    return {
        "capacite_go": int(capacity_match.group(1)) if capacity_match else None,
        "frequence_mhz": int(speed_match.group(1)) if speed_match else None,
    }


@app.get("/api/compare-performance")
def compare_performance(id_a: int, id_b: int):
    """
    Comparaison tête-à-tête de deux composants — CPU/GPU : pourcentage de
    performance relative via l'indice recalibré (voir plus haut) ; RAM :
    capacité + fréquence extraites du nom ; toute autre catégorie (ou
    catégories différentes entre A et B) : specs brutes côte à côte, sans
    score de performance.
    """
    if id_a == id_b:
        raise HTTPException(status_code=400, detail="Choisis deux composants différents à comparer.")
    components = get_catalog()
    components_by_id = {c["id"]: c for c in components}
    a = components_by_id.get(id_a)
    b = components_by_id.get(id_b)
    if not a or not b:
        raise HTTPException(status_code=404, detail="Composant introuvable.")

    # Champs Amazon purement administratifs — jamais une "stat" comparable
    # (identifiants, texte marketing libre, poids/dimensions du COLIS...) —
    # à exclure du tableau pour qu'il ne reste que des caractéristiques
    # utiles à une comparaison de performance/capacités.
    # Mots-clés (pas des phrases exactes : les libellés Amazon varient trop
    # d'un vendeur à l'autre — "Fabricant" vs "Fabriquant", "Numéro de
    # modèle" vs "Numéro du modèle") : un seul mot-clé significatif suffit à
    # attraper toutes ces variantes sans avoir à toutes les lister.
    STAT_LABEL_BLOCKLIST_KEYWORDS = (
        "asin", "numero de model", "numero du model", "numero de piece", "code article",
        "unite de comptage", "marque", "contenu de la boite", "composants inclus", "garantie",
        "fabri", "origine", "classement", "commentaires client", "nom du modele", "nom de modele",
        " ean", "upc", "poids de l", "dimensions de l", "emballage", "recommande",
        "description de la carte graphique", "point fort", "appareils compatibles",
        "nombre d'articles", "nombre d articles", "coordonnees",
    )

    def _is_real_stat(label):
        label_lower = " " + _strip_accents(label).lower().replace("’", "'").replace("'", " ") + " "
        return not any(keyword.replace("'", " ") in label_lower for keyword in STAT_LABEL_BLOCKLIST_KEYWORDS)

    # Un même fabricant AMAZON décrit souvent la MÊME caractéristique avec un
    # libellé différent selon le vendeur ("Coprocesseurgraphique" vs
    # "Coprocesseur Graphique", "Mémoire vive de la carte graphique" vs
    # "Taille de la RAM graphique") — sans les fusionner sous un même nom,
    # la comparaison A/B affichait deux lignes à moitié remplies au lieu
    # d'une seule ligne complète des deux côtés (retour utilisateur). Mot-clé
    # → libellé canonique, PAR CATÉGORIE (une même formulation peut désigner
    # une chose différente sur un CPU vs un GPU, ex: "fréquence du
    # processeur" est l'horloge du GPU lui-même sur une fiche carte
    # graphique) — premier mot-clé qui matche gagne.
    GPU_LABEL_SYNONYMS = [
        ("coprocesseur", "Puce graphique"),
        ("memoire vive de la carte graphique", "Mémoire vidéo (VRAM)"),
        ("taille de la ram graphique", "Mémoire vidéo (VRAM)"),
        ("horloge du processeur", "Fréquence GPU"),
        ("horloge du gpu", "Fréquence GPU"),
        ("horloge de la memoire", "Fréquence mémoire"),
        ("type de memoire vive", "Type de mémoire vidéo"),
        ("type de ram graphique", "Type de mémoire vidéo"),
        ("interface de sortie video", "Sorties vidéo"),
        ("interface de la carte graphique", "Interface (bus)"),
        ("nombre de ventilateur", "Nombre de ventilateurs"),
        ("serie gpu", "Série GPU"),
        ("resolution maximale", "Résolution maximale"),
    ]
    CPU_LABEL_SYNONYMS = [
        ("nombre de coeurs", "Nombre de cœurs"),
        ("nombre de c urs", "Nombre de cœurs"),
        ("nombre de threads", "Nombre de threads"),
        ("horloge du processeur", "Fréquence"),
        ("frequence du processeur", "Fréquence"),
        ("frequence de base", "Fréquence de base"),
        ("frequence turbo", "Fréquence turbo"),
        ("memoire cache", "Cache"),
        ("socket du processeur", "Socket"),
    ]

    def _canonicalize_label(label, synonyms):
        normalized = _strip_accents(label).lower().replace("’", "'").replace("'", " ")
        for keyword, canonical in synonyms:
            if keyword in normalized:
                return canonical
        return label

    def _combined_stats(component):
        # Fusionne les specs de compatibilité (déjà propres, ex: "tdp",
        # "socket") ET le tableau brut "Détails du produit" Amazon (ex:
        # "Mémoire vive de la carte graphique", "Fréquence d'horloge...") en
        # un seul dict de statistiques — beaucoup plus riche que les seules
        # specs de compatibilité, qui ne couvrent que ce qui sert à vérifier
        # qu'un composant rentre avec un autre, pas la performance brute
        # (fréquence, cache, nombre de ports...). specs_json prime en cas de
        # clé identique (déjà normalisée, voir plus haut dans ce fichier) ;
        # les entrées Amazon ne s'alignent entre A et B que si le LIBELLÉ
        # est rigoureusement identique des deux côtés (pas de tentative de
        # réconciliation de libellés différents pour la même info — mieux
        # vaut deux lignes non alignées qu'un mauvais appariement) — sauf
        # pour les libellés couverts par GPU_LABEL_SYNONYMS/CPU_LABEL_SYNONYMS
        # ci-dessus, canonicalisés avant d'être utilisés comme clé.
        synonyms = GPU_LABEL_SYNONYMS if component["categorie"] == "GPU" else (
            CPU_LABEL_SYNONYMS if component["categorie"] == "CPU" else []
        )
        stats = {}
        for entry in component.get("caracteristiques_amazon") or []:
            if entry.get("type") and entry.get("value") and _is_real_stat(entry["type"]):
                key = _canonicalize_label(entry["type"], synonyms) if synonyms else entry["type"]
                # Si deux libellés bruts différents se canonicalisent sur la
                # même clé (ex: "Coprocesseurgraphique" ET "Coprocesseur
                # Graphique" dans la même fiche), on garde la première valeur
                # rencontrée plutôt que d'écraser par la suivante.
                stats.setdefault(key, entry["value"])
        stats.update(component.get("specs") or {})
        return stats

    # Specs toujours incluses, quel que soit le mode : même en mode
    # "performance" (score CPU/GPU), le détail des caractéristiques brutes
    # (VRAM, TDP, socket...) s'affiche en complément sous le score, pour
    # ceux qui veulent voir plus que le seul chiffre agrégé.
    base = {
        "a": {"id": a["id"], "nom": a["nom"], "categorie": a["categorie"], "prix_indicatif": a.get("prix_indicatif"), "image_url": a.get("image_url"), "image_processed": a.get("image_processed"), "asin": a.get("asin"), "specs": _combined_stats(a)},
        "b": {"id": b["id"], "nom": b["nom"], "categorie": b["categorie"], "prix_indicatif": b.get("prix_indicatif"), "image_url": b.get("image_url"), "image_processed": b.get("image_processed"), "asin": b.get("asin"), "specs": _combined_stats(b)},
    }

    if a["categorie"] != b["categorie"]:
        base["mode"] = "specs"
        base["avertissement"] = "Catégories différentes : comparaison des caractéristiques uniquement, pas de score de performance."
        return base

    categorie = a["categorie"]
    if categorie in ("CPU", "GPU"):
        index_table = GPU_PERFORMANCE_INDEX if categorie == "GPU" else CPU_PERFORMANCE_INDEX
        index_a = _match_performance_index(a["nom"], index_table)
        index_b = _match_performance_index(b["nom"], index_table)
        if index_a is None or index_b is None:
            base["mode"] = "specs"
            base["avertissement"] = "Modèle non reconnu dans notre indice de performance — comparaison des caractéristiques uniquement."
            return base
        base["mode"] = "performance"
        base["a"]["indice"] = index_a
        base["b"]["indice"] = index_b
        # Score sur 100, ABSOLU sur toute la gamme (100 = la meilleure puce
        # du tableau, ex: RTX 5090 pour les GPU) — pas relatif à la seule
        # paire comparée. Bug signalé en pratique avec l'ancienne version :
        # une RTX 3060 qui bat une carte plus faible affichait "100/100",
        # donnant l'impression fausse d'égaler une RTX 5090 elle aussi à
        # 100/100 sur une autre comparaison. Avec un plafond absolu, une
        # RTX 3060 reste basse (~30/100) même quand elle gagne sa comparaison.
        ceiling = GPU_PERFORMANCE_CEILING if categorie == "GPU" else CPU_PERFORMANCE_CEILING
        base["a"]["score"] = round(index_a / ceiling * 100)
        base["b"]["score"] = round(index_b / ceiling * 100)
        return base

    if categorie == "RAM":
        ram_a = _parse_ram_specs(a["nom"])
        ram_b = _parse_ram_specs(b["nom"])
        base["mode"] = "ram"
        base["a"].update(ram_a)
        base["b"].update(ram_b)
        return base

    base["mode"] = "specs"
    base["a"]["specs"] = a.get("specs") or {}
    base["b"]["specs"] = b.get("specs") or {}
    return base


@app.post("/api/estimate-fps")
def estimate_fps(request: EstimateFpsRequest):
    """
    Estimation FPS explicitement demandée (page /estimer-fps) — validations
    strictes, voir _run_fps_estimation pour le cœur du calcul. Plus de
    enforce_ai_rate_limit : ce calcul ne passe plus par une IA externe
    depuis le passage à une estimation par formule (voir fps_data.py),
    donc plus aucune raison de le limiter comme un appel IA coûteux.
    """
    components = get_catalog()
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

    result = _run_fps_estimation(chosen, jeux, request.qualite)
    if result is None:
        return {
            "status": "error",
            "message": "Impossible de faire une estimation pour le moment. Réessaie dans quelques minutes.",
        }
    return result


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
LINK_CHECK_LOCK = ProcessLock("verification-liens")


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


# ---------------------------------------------------------------------------
# Contrôle qualité du catalogue (controle_catalogue.py) : prix suspects,
# annonces isolées qui ressemblent à un produit existant, fiches incomplètes.
# Recalculé au plus une fois par version du catalogue en mémoire ; un
# contrôle quotidien envoie par e-mail les NOUVEAUX prix suspects (une même
# annonce au même prix n'est signalée qu'une fois).
# ---------------------------------------------------------------------------
_CONTROLE = {"at": None, "rapport": None}
CONTROLE_INTERVAL_SECONDS = 24 * 60 * 60


def _controle_courant():
    catalog = get_catalog()
    if _CONTROLE["rapport"] is None or _CONTROLE["at"] != _CATALOG["at"]:
        rapport = controle_catalogue.rapport(catalog)
        # Signalements marqués « normal » depuis l'admin : un prix ignoré revient
        # s'il change, une paire d'annonces ignorée ne revient pas.
        ignores = set(_state_get("controle_ignores", []))
        rapport["prix_suspects"] = [x for x in rapport["prix_suspects"] if f"prix:{x['id']}:{x['prix']}" not in ignores]
        rapport["annonces_isolees"] = [
            x for x in rapport["annonces_isolees"]
            if f"isolee:{min(x['id'], x['proche_id'])}:{max(x['id'], x['proche_id'])}" not in ignores
        ]
        _CONTROLE.update(at=_CATALOG["at"], rapport=rapport)
    return _CONTROLE["rapport"]


@app.get("/api/admin/controle-catalogue")
def admin_controle_catalogue(_admin=Depends(require_admin)):
    return _controle_courant()


class IgnorerRequest(BaseModel):
    cle: str


@app.post("/api/admin/controle/ignorer")
def admin_controle_ignorer(request: IgnorerRequest, _admin=Depends(require_admin)):
    if not re.fullmatch(r"(prix:\d+:[\d.]+|isolee:\d+:\d+)", request.cle):
        raise HTTPException(status_code=400, detail="Clé invalide.")
    ignores = _state_get("controle_ignores", [])
    if request.cle not in ignores:
        ignores.append(request.cle)
        _state_set("controle_ignores", ignores[-500:])
    _CONTROLE["rapport"] = None
    return {"status": "ok"}


class VarianteRequest(BaseModel):
    id: int
    cible: int | None = None


@app.post("/api/admin/variantes/rattacher")
def admin_variantes_rattacher(request: VarianteRequest, _admin=Depends(require_admin)):
    """« C'est le même produit » : l'annonce devient une variante du produit de `cible`."""
    ids = {c["id"] for c in get_catalog()}
    if request.id not in ids or request.cible not in ids or request.id == request.cible:
        raise HTTPException(status_code=400, detail="Composants invalides.")
    rattacher = _state_get("variantes_rattacher", {})
    rattacher[str(request.id)] = request.cible
    _state_set("variantes_rattacher", rattacher)
    _state_set("variantes_separer", [i for i in _state_get("variantes_separer", []) if i != request.id])
    invalidate_catalog()
    _CONTROLE["rapport"] = None
    return {"status": "ok"}


@app.post("/api/admin/variantes/separer")
def admin_variantes_separer(request: VarianteRequest, _admin=Depends(require_admin)):
    """« Ce n'est pas le même produit » : l'annonce redevient un produit à part."""
    separer = _state_get("variantes_separer", [])
    if request.id not in separer:
        separer.append(request.id)
    _state_set("variantes_separer", separer)
    rattacher = _state_get("variantes_rattacher", {})
    rattacher.pop(str(request.id), None)
    _state_set("variantes_rattacher", rattacher)
    invalidate_catalog()
    _CONTROLE["rapport"] = None
    return {"status": "ok"}


def _run_controle_catalogue():
    suspects = _controle_courant()["prix_suspects"]
    cles = [f"{s['id']}:{s['prix']}" for s in suspects]
    client = get_client()
    try:
        rows = client.execute("SELECT valeur FROM app_state WHERE cle = 'controle_prix_deja_signales'").rows
        deja = set(json.loads(rows[0][0])) if rows and rows[0][0] else set()
        client.execute(
            "INSERT INTO app_state (cle, valeur) VALUES ('controle_prix_deja_signales', ?) "
            "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur",
            [json.dumps(cles)],
        )
    finally:
        client.close()
    nouveaux = [s for s, cle in zip(suspects, cles) if cle not in deja]
    if nouveaux and SMTP_FROM:
        lignes = "\n".join(
            f"- {s['nom']} ({s['categorie']}) : {s['prix']:.2f} € au lieu d'environ {s['reference']:.2f} € "
            f"({s['motif']}). {SITE_URL}{s['page'] or ''}"
            for s in nouveaux
        )
        send_email(
            SMTP_FROM, f"[PC Radar] {len(nouveaux)} prix suspect(s) dans le catalogue",
            f"Le contrôle quotidien du catalogue a repéré :\n\n{lignes}\n\n"
            f"Détail et actions dans la page admin : {SITE_URL}/admin",
        )
    return nouveaux


async def controle_catalogue_loop():
    await asyncio.sleep(10 * 60)
    while True:
        try:
            if await asyncio.to_thread(_task_is_due, "dernier_controle_catalogue", CONTROLE_INTERVAL_SECONDS):
                nouveaux = await asyncio.to_thread(_run_controle_catalogue)
                await asyncio.to_thread(_mark_task_done, "dernier_controle_catalogue")
                print(f"Contrôle du catalogue : {len(nouveaux)} nouveau(x) prix suspect(s).")
        except Exception as error:
            print(f"Contrôle du catalogue échoué : {error}")
        await asyncio.sleep(SCHEDULER_CHECK_SECONDS)


@app.on_event("startup")
async def start_controle_catalogue_loop():
    if is_background_leader():
        asyncio.create_task(controle_catalogue_loop())


def _produits_proches(titre, categorie="", catalog=None, limite=3):
    """
    Produits déjà catalogués qui ressemblent à un titre Amazon (autre annonce du
    même modèle, autre couleur, autre capacité) : tous les mots du nom catalogué,
    numéros de modèle compris, doivent se retrouver dans le titre.
    """
    titre_mots = set(variantes._mots(titre, sans_marque=False))
    titre_bas = titre.lower()
    produits, mots_produit = {}, {}
    for c in catalog if catalog is not None else get_catalog():
        if categorie and categorie != "Accessoire" and c["categorie"] != categorie:
            continue
        if (c.get("marque") or "").lower() not in titre_bas:
            continue
        # « RGB » compte ici : un kit RGB et un kit sans RGB sont deux gammes.
        mots = controle_catalogue._mots_cle(c) - (controle_catalogue.MOTS_SANS_IMPORTANCE - {"rgb", "argb"})
        if len(mots) < 2 or not mots <= titre_mots:
            continue
        g = c.get("groupe_id", c["id"])
        mots_produit[g] = mots_produit.get(g, set()) | mots
        meilleur = produits.get(g)
        if meilleur is None or (c.get("en_stock") and float(c.get("prix_indicatif") or 0) < float(meilleur.get("prix_indicatif") or 0)):
            produits[g] = c
    # « Vengeance » et « Vengeance RGB » trouvés pour un kit RGB : on ne garde que
    # le produit le plus précis (dont les mots contiennent ceux de l'autre).
    precis = [g for g in produits if not any(mots_produit[g] < mots_produit[o] for o in produits if o != g)]
    proches = sorted((produits[g] for g in precis), key=lambda c: -len(mots_produit[c.get("groupe_id", c["id"])]))[:limite]
    return [
        {"id": c["id"], "nom": c["nom"], "categorie": c["categorie"], "prix_indicatif": c.get("prix_indicatif"),
         "nb_variantes": c.get("nb_variantes") or 1, "page": c.get("page")}
        for c in proches
    ]


@app.get("/api/admin/produits-proches")
def admin_produits_proches(titre: str, categorie: str = "", _admin=Depends(require_admin)):
    """Pour l'extension, sur une fiche produit Amazon pas encore cataloguée."""
    return {"proches": _produits_proches(titre, categorie)}


class ArticlePage(BaseModel):
    asin: str
    titre: str = ""
    categorie: str = ""


class AnalysePageRequest(BaseModel):
    items: list[ArticlePage]


@app.post("/api/admin/analyse-page")
def admin_analyse_page(request: AnalysePageRequest, _admin=Depends(require_admin)):
    """
    Pour l'extension, sur une page de résultats Amazon : en une seule requête,
    pour chaque produit affiché, sa fiche au catalogue (prix, variante, prix
    suspect) ou, s'il n'y est pas, le produit catalogué le plus proche.
    """
    catalog = get_catalog()
    par_asin = {(c.get("asin") or "").upper(): c for c in catalog if c.get("asin")}
    suspects = {s["id"]: s for s in _controle_courant()["prix_suspects"]}
    resultats = {}
    for item in request.items[:80]:
        asin = item.asin.strip().upper()
        c = par_asin.get(asin)
        if c:
            resultats[asin] = {"catalogue": {
                "id": c["id"], "nom": c["nom"], "categorie": c["categorie"], "prix_indicatif": c.get("prix_indicatif"),
                "en_stock": c.get("en_stock"), "variante": c.get("variante"), "nb_variantes": c.get("nb_variantes") or 1,
                "page": c.get("page"), "prix_suspect": suspects.get(c["id"]),
            }, "proche": None}
        else:
            proches = _produits_proches(item.titre, item.categorie, catalog, limite=1) if item.titre else []
            resultats[asin] = {"catalogue": None, "proche": proches[0] if proches else None}
    return {"resultats": resultats}


class PrixAmazonRequest(BaseModel):
    prix: float


@app.post("/api/admin/components/{component_id}/prix-amazon")
def admin_prix_amazon(component_id: int, request: PrixAmazonRequest, _admin=Depends(require_admin)):
    """
    Met à jour le prix Amazon d'un composant avec le prix lu sur la page produit
    (depuis l'extension) : prix affiché, ligne Amazon des prix relevés,
    historique du jour et alertes de prix, comme le rafraîchissement automatique.
    """
    if not 0 < request.prix < 20000:
        raise HTTPException(status_code=400, detail="Prix invalide.")
    client = get_client()
    try:
        rows = client.execute(
            "SELECT nom, prix_marche_json, asin FROM components WHERE id = ?", [component_id]
        ).rows
        if not rows:
            raise HTTPException(status_code=404, detail="Composant introuvable.")
        nom, prix_marche_json, asin = rows[0]
        try:
            prix_marche = json.loads(prix_marche_json) if prix_marche_json else []
        except (TypeError, json.JSONDecodeError):
            prix_marche = []
        lien = next((m.get("lien") for m in prix_marche if m.get("vendeur") == "Amazon" and m.get("lien")), None) \
            or (f"https://www.amazon.fr/dp/{asin}" if asin else None)
        prix_marche = [m for m in prix_marche if m.get("vendeur") != "Amazon"]
        prix_marche.append({"vendeur": "Amazon", "prix": request.prix, "lien": lien,
                            "date_releve": datetime.utcnow().date().isoformat()})
        client.execute(
            "UPDATE components SET prix_indicatif = ?, prix_marche_json = ?, en_stock = 1 WHERE id = ?",
            [request.prix, json.dumps(prix_marche, ensure_ascii=False), component_id],
        )
        record_price_and_notify(client, component_id, nom, float(request.prix), lien)
    finally:
        client.close()
    invalidate_catalog()
    return {"status": "ok", "prix": request.prix}


async def link_checker_loop():
    """Boucle de fond : vérifie tous les liens une fois par jour (échéance mémorisée en base)."""
    await asyncio.sleep(10 * 60)
    while True:
        if await asyncio.to_thread(_task_is_due, "derniere_verification_liens", LINK_CHECK_INTERVAL_SECONDS):
            try:
                await asyncio.to_thread(check_all_links)
                await asyncio.to_thread(_mark_task_done, "derniere_verification_liens")
            except Exception as error:
                print(f"Vérification automatique des liens échouée : {error}")
        await asyncio.sleep(SCHEDULER_CHECK_SECONDS)


@app.on_event("startup")
async def start_link_checker():
    if is_background_leader():
        asyncio.create_task(link_checker_loop())


# Constaté en conditions réelles : après quelques minutes sans requête, la
# PROCHAINE requête vers Turso peut prendre 15 à 25+ secondes, peu importe la
# requête ou les colonnes sélectionnées — un cold-start côté Turso (instance
# de base de données qui se "rendort" quand elle est inactive), pas un
# problème de code ou de volume de données. Une requête minimale régulière
# empêche ce cold-start de jamais se produire pendant qu'un vrai visiteur
# charge le site.
DB_KEEPALIVE_INTERVAL_SECONDS = 60


async def db_keepalive_loop():
    """Boucle de fond : garde la connexion Turso "chaude" (voir commentaire ci-dessus)."""
    while True:
        try:
            client = await asyncio.to_thread(get_client)
            try:
                await asyncio.to_thread(client.execute, "SELECT 1")
            finally:
                await asyncio.to_thread(client.close)
        except Exception as error:
            print(f"Keep-alive Turso échoué (non bloquant) : {error}")
        await asyncio.sleep(DB_KEEPALIVE_INTERVAL_SECONDS)


@app.on_event("startup")
async def start_db_keepalive():
    if is_background_leader():
        asyncio.create_task(db_keepalive_loop())


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