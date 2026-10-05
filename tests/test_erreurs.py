"""Pages d'erreur au thème du site pour les navigateurs, JSON pour les appels d'API."""
import os

import erreurs

NAVIGATEUR = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}


def test_page_introuvable_au_theme_du_site(client):
    r = client.get("/cette-page-nexiste-pas", headers=NAVIGATEUR)
    assert r.status_code == 404 and r.headers["content-type"].startswith("text/html")
    assert "Cette page n’existe pas" in r.text and 'class="erreur-page"' in r.text and "/static/style.css" in r.text


def test_composant_introuvable_message_adapte(client):
    r = client.get("/composant/999999-inconnu", headers=NAVIGATEUR)
    assert r.status_code == 404 and "plus au catalogue" in r.text


def test_api_et_fetch_gardent_le_json(client):
    assert client.get("/api/nexiste-pas", headers=NAVIGATEUR).headers["content-type"].startswith("application/json")
    r = client.get("/composant/999999-inconnu")          # fetch : Accept */*
    assert r.status_code == 404 and r.json()["detail"] == "Composant introuvable."


def test_fichiers_statiques_pour_nginx_a_jour():
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for nom, code in erreurs.FICHIERS_STATIQUES.items():
        with open(os.path.join(racine, "static", "erreurs", nom), encoding="utf-8") as f:
            assert f.read() == erreurs.page(code, scripts=(code == 404)), f"lancer : python erreurs.py ({nom})"
