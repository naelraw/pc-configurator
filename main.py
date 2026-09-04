import json
import os
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from groq import Groq
import libsql_client
from pydantic import BaseModel, Field
from compatibility import (
    check_alimentation,
    check_carte_mere_boitier,
    check_carte_mere_ram,
    check_cpu_carte_mere,
    check_gpu_boitier,
    check_refroidissement,
    check_stockage,
    verifier_compatibilite,
)

try:
    import google.generativeai as genai
except ImportError:
    genai = None

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")  # Fallback optionnel
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
if genai and GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


class SuggestConfigRequest(BaseModel):
    user_input: str


class BuildIn(BaseModel):
    nom: str
    composants: dict


class CompatCheckIn(BaseModel):
    cpu: dict | None = None
    motherboard: dict | None = None
    ram: dict | None = None
    case: dict | None = None
    psu: dict | None = None
    gpu: dict | None = None
    cooler: dict | None = None
    storages: list = Field(default_factory=list)


app = FastAPI()

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
            "SELECT id, categorie, nom, specs_json, prix_indicatif "
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
            }
            try:
                component["specs"] = json.loads(row[3])
            except (TypeError, json.JSONDecodeError):
                component["specs"] = {}
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
    components = get_all_components()
    component_ids = [
        suggestion.get(component_type)
        for component_type in (
            "cpu_id",
            "motherboard_id",
            "ram_id",
            "gpu_id",
            "psu_id",
            "storage_id",
            "case_id",
        )
    ]
    config_list = [component for component in components if component["id"] in component_ids]
    return check_compatibility(config_list)


@app.get("/")
def root():
    return FileResponse("static/index.html")


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


@app.post("/check-compatibility")
def check_compat(data: CompatCheckIn):
    manquants = [
        key
        for key in ["cpu", "motherboard", "ram", "case", "psu", "cooler"]
        if getattr(data, key) is None
    ]
    if manquants:
        return {"status": "incomplete", "manquants": manquants}

    erreurs = verifier_compatibilite(
        data.cpu,
        data.motherboard,
        data.ram,
        data.case,
        data.psu,
        data.gpu,
        data.storages,
        data.cooler,
    )
    return {"status": "ok" if not erreurs else "incompatible", "erreurs": erreurs}


@app.post("/builds")
def create_build(build: BuildIn):
    cpu = build.composants.get("cpu")
    carte_mere = build.composants.get("motherboard")
    ram = build.composants.get("ram")
    boitier = build.composants.get("case")
    alimentation = build.composants.get("psu")
    gpu = build.composants.get("gpu")
    cooler = build.composants.get("cooler")
    stockages = build.composants.get("storages", [])

    if not all([cpu, carte_mere, ram, boitier, alimentation, cooler]):
        raise HTTPException(status_code=400, detail="Composants obligatoires manquants.")

    erreurs = verifier_compatibilite(
        cpu, carte_mere, ram, boitier, alimentation, gpu, stockages, cooler
    )
    if erreurs:
        raise HTTPException(status_code=400, detail={"erreurs": erreurs})

    client = get_client()
    try:
        client.execute(
            "INSERT INTO builds (nom, composants_json, date) VALUES (?, ?, ?)",
            [build.nom, json.dumps(build.composants), datetime.utcnow().isoformat()],
        )
    finally:
        client.close()

    return {"status": "ok", "message": "Build sauvegardée."}


@app.get("/builds")
def list_builds():
    client = get_client()
    try:
        result = client.execute(
            "SELECT id, nom, composants_json, date FROM builds ORDER BY id DESC"
        )
        builds = [
            {
                "id": row[0],
                "nom": row[1],
                "composants": json.loads(row[2]),
                "date": row[3],
            }
            for row in result.rows
        ]
        return {"status": "ok", "builds": builds}
    finally:
        client.close()


@app.post("/suggest-config")
def suggest_config(request: SuggestConfigRequest):
    """Route IA : suggère une config basée sur la description utilisateur"""
    try:
        # Récupère tous les composants
        components = get_all_components()
        if not components:
            return {"status": "error", "message": "Aucun composant disponible"}

        # Crée le prompt
        components_list = "\n".join([
            f"- {c['categorie']}: {c['nom']} (socket/format: {c['specs_json']}, {c['prix_indicatif']}€)"
            for c in components
        ])

        prompt = f"""Tu es un expert en configuration PC. L'utilisateur décrit son besoin en langage naturel.
Suggère une configuration complète en JSON strict (pas de markdown, juste du JSON valide).

Composants disponibles:
{components_list}

Besoin utilisateur: {request.user_input}

Réponds UNIQUEMENT avec un JSON valide comme ceci:
{{"cpu_id": 1, "motherboard_id": 2, "ram_id": 3, "gpu_id": 4, "psu_id": 5, "storage_id": 6, "case_id": 7}}

Utilise les IDs des composants de la liste ci-dessus."""

        # Appel Groq
        try:
            if groq_client is None:
                raise RuntimeError("GROQ_API_KEY absente")
            message = groq_client.chat.completions.create(
                model="llama-3.1-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500,
            )
            suggestion_text = message.choices[0].message.content
        except Exception as e_groq:
            print(f"Groq échoué, fallback Gemini: {e_groq}")
            if genai is None or not GEMINI_API_KEY:
                raise RuntimeError("Groq et Gemini ne sont pas configurés") from e_groq
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            suggestion_text = response.text

        # Parse le JSON
        try:
            suggestion_json = json.loads(suggestion_text)
        except json.JSONDecodeError:
            import re
            match = re.search(r"\{.*\}", suggestion_text, re.DOTALL)
            if match:
                suggestion_json = json.loads(match.group())
            else:
                return {"status": "error", "message": f"IA a renvoyé du JSON invalide: {suggestion_text}"}

        # Vérifie la compatibilité
        compatibility_result = verify_compatibility(suggestion_json)
        if not compatibility_result["compatible"]:
            return {
                "status": "error",
                "message": f"Configuration incompatible: {compatibility_result['errors']}",
                "suggestion": suggestion_json,
            }

        return {
            "status": "ok",
            "suggestion": suggestion_json,
            "compatible": True,
        }

    except Exception as error:
        return {"status": "error", "message": str(error)}
    component_ids = [
        suggested.get(component_type, {}).get("id")
        for component_type in (
            "cpu",
            "motherboard",
            "ram",
            "gpu",
            "psu",
            "case",
            "storage",
        )
    ]
    config_list = [
        component
        for component in components["components"]
        if component["id"] in component_ids
    ]

    compat = check_compatibility(config_list)

    if not compat["compatible"]:
        return {"status": "error", "message": f"Config incompatible : {compat['errors']}"}

    return {"status": "success", "config": suggested, "compatibility": compat}


@app.get("/test-db")
def test_db():
    """Route de test : écrit une ligne puis relit toutes les lignes de components."""
    client = get_client()
    try:
        # Écriture test
        client.execute(
            "INSERT INTO components (categorie, nom, specs_json, prix_indicatif) VALUES (?, ?, ?, ?)",
            ["TEST", "Ping DB", '{"test": true}', 0.0]
        )

        # Lecture
        result = client.execute("SELECT id, categorie, nom, specs_json, prix_indicatif FROM components")
        rows = [
            {
                "id": row[0],
                "categorie": row[1],
                "nom": row[2],
                "specs_json": row[3],
                "prix_indicatif": row[4],
            }
            for row in result.rows
        ]

        return {"status": "ok", "count": len(rows), "components": rows}
    finally:
        client.close()