def test_en_tetes_de_securite(client):
    r = client.get("/")
    assert r.headers["x-frame-options"] == "DENY"
    assert "max-age" in r.headers["strict-transport-security"]
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]


def test_aucun_script_inline_dans_les_pages(client):
    for page in ("/", "/configurateur", "/comparateur", "/compte", "/estimer-fps", "/assistant", "/guides", "/composants"):
        html = client.get(page).text
        assert "<script>" not in html and " onclick=" not in html, page


def test_cors_limite_au_site(client):
    r = client.options("/api/components", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in r.headers
    r = client.get("/api/auth/me", headers={"Origin": "https://pcradar.tech"})
    assert r.headers.get("access-control-allow-origin") == "https://pcradar.tech"


def test_admin_protege(new_client):
    c = new_client("203.0.113.50")
    assert c.get("/api/admin/stats").status_code == 401
    assert c.get("/api/admin/verify", headers={"X-Admin-Secret": "admin-de-test"}).status_code == 200


def test_connexion_bloquee_apres_10_echecs(new_client):
    c = new_client("203.0.113.51")
    codes = [c.post("/api/auth/login", json={"email": "x@y.fr", "password": "faux"}).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429
    # une autre adresse n'est pas touchée
    assert new_client("203.0.113.52").post("/api/auth/login", json={"email": "x@y.fr", "password": "faux"}).status_code == 401
