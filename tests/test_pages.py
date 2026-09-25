import time

from conftest import component


def test_pages_principales(client):
    for page in ("/", "/configurateur", "/comparateur", "/compte", "/estimer-fps", "/assistant",
                 "/mentions-legales", "/confidentialite", "/cgu", "/cookies"):
        assert client.get(page).status_code == 200, page


def _configs(client):
    for _ in range(40):  # calculées en arrière-plan au démarrage
        configs = client.get("/api/configs-vedette").json()["configs"]
        if configs:
            return configs
        time.sleep(0.25)
    return []


def test_config_du_moment_et_guide(client):
    configs = _configs(client)
    assert configs, "aucune config du moment calculée"
    c = configs[0]
    assert c["compatible"] and len(c["composants"]) == 8 and c["total"] <= 850
    html = client.get(c["guide"]).text
    assert "Pourquoi ces choix" in html and 'href="/composant/' in html
    assert client.get("/guides").status_code == 200
    assert client.get("/guides/inconnu").status_code == 404


def test_fiches_composants(client, catalog):
    gpu = component(catalog, "RTX 4060")
    html = client.get(gpu["page"]).text
    assert "FPS estimés" in html and "Alimentation recommandée" in html and "Où l'acheter" in html
    r = client.get(f"/composant/{gpu['id']}", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == gpu["page"]
    assert client.get("/composant/999999-inconnu").status_code == 404
    assert client.get("/composants").status_code == 200
    assert client.get("/composants/cartes-graphiques").text.count('href="/composant/') == 2


def test_comparatifs(client):
    assert client.get("/comparer").status_code == 200
    html = client.get("/comparer/rtx-4060-vs-rx-7600").text
    assert "rapport performance/prix" in html
    assert client.get("/comparer/rtx-9999-vs-rx-1").status_code == 404


def test_plan_du_site(client, catalog):
    sm = client.get("/sitemap.xml").text
    assert sm.count("/composant/") == len(catalog)
    assert "/guides" in sm and "/comparer/rtx-4060-vs-rx-7600" in sm


def test_favicon_ico(client):
    r = client.get("/favicon.ico")
    assert r.status_code == 200 and r.headers["content-type"] == "image/x-icon"


def test_application_installable(client):
    r = client.get("/sw.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    html = client.get("/").text
    assert 'rel="manifest"' in html and "/static/pwa.js" in html


def test_icones_a_la_racine(client):
    for chemin, type_attendu in (("/favicon.ico", "image/x-icon"), ("/apple-touch-icon.png", "image/png")):
        r = client.get(chemin)
        assert r.status_code == 200 and r.headers["content-type"] == type_attendu
