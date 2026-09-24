import sqlite3

from conftest import DB, component


def _inscrit(new_client, email, ip):
    c = new_client(ip)
    assert c.post("/api/auth/register", json={"email": email, "password": "motdepasse123"}).status_code == 200
    return c


def test_inscription_connexion_deconnexion(new_client):
    c = _inscrit(new_client, "compte@test.fr", "203.0.113.10")
    assert c.get("/api/auth/me").json()["logged_in"] is True
    c.post("/api/auth/logout")
    assert c.get("/api/auth/me").json()["logged_in"] is False
    assert c.post("/api/auth/login", json={"email": "compte@test.fr", "password": "motdepasse123"}).status_code == 200
    assert c.get("/api/auth/me").json()["user"]["email"] == "compte@test.fr"


def test_export_et_suppression_du_compte(new_client, catalog):
    a = _inscrit(new_client, "a-supprimer@test.fr", "203.0.113.11")
    b = _inscrit(new_client, "a-garder@test.fr", "203.0.113.12")
    cpu = component(catalog, "Ryzen 5 5600")
    for c in (a, b):
        bid = c.post("/api/builds", json={"nom": "Ma config", "composants_json": {"CPU": cpu["id"]}}).json()["id"]
        c.post("/api/favorites", json={"component_id": cpu["id"]})
        c.put(f"/api/builds/{bid}/alerte", json={"prix_cible": 100})
    uid = sqlite3.connect(DB).execute("select id from users where email='a-supprimer@test.fr'").fetchone()[0]
    db = sqlite3.connect(DB)
    db.execute("insert into link_corrections (component_id, vendeur, nouveau_lien, user_id, user_email, date) "
               "values (?, 'Amazon', 'https://x', ?, 'a-supprimer@test.fr', '2026-09-24')", (cpu["id"], uid))
    db.commit()

    export = a.get("/api/auth/export")
    assert "attachment" in export.headers["content-disposition"]
    data = export.json()
    assert data["compte"]["email"] == "a-supprimer@test.fr" and len(data["configurations"]) == 1
    assert "password" not in export.text

    assert new_client("203.0.113.13").delete("/api/auth/account").status_code == 401
    assert a.delete("/api/auth/account").status_code == 200
    q = lambda sql: sqlite3.connect(DB).execute(sql, (uid,)).fetchone()[0]
    assert q("select count(*) from users where id=?") == 0
    assert q("select count(*) from favorites where user_id=?") == 0
    assert q("select count(*) from build_alerts where user_id=?") == 0
    # signalement gardé mais anonymisé (colonnes NOT NULL en production)
    assert q("select count(*) from link_corrections where user_id=?") == 0
    assert sqlite3.connect(DB).execute("select count(*) from link_corrections where user_email='compte supprimé'").fetchone()[0] == 1
    assert len(b.get("/api/auth/export").json()["configurations"]) == 1
