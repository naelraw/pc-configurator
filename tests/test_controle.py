"""Contrôle qualité du catalogue, avertissement de câble et routes admin associées."""
import controle_catalogue
import variantes
from compatibility import check_cable_alimentation
from conftest import component

ADMIN = {"X-Admin-Secret": "admin-de-test"}


def _c(id_, categorie, nom, prix, en_stock=True, **specs):
    return {"id": id_, "categorie": categorie, "nom": nom, "prix_indicatif": prix,
            "en_stock": en_stock, "specs": specs, "image_url": "x"}


def test_prix_suspect_parmi_les_annonces_du_meme_produit():
    cat = variantes.annoter([
        _c(1, "RAM", "Lexar THOR Z Series OC 8 Go DDR5 6000", 449.99, type="DDR5", capacite_go=8),
        _c(2, "RAM", "Lexar THOR Z Series OC 8 Go DDR5 6000 MHz", 174.99, type="DDR5", capacite_go=8),
        # Même gamme mais autre capacité : prix plus élevé normal, jamais signalé.
        _c(3, "RAM", "Lexar THOR Z Series OC 32 Go DDR5 6000", 520, type="DDR5", capacite_go=32),
    ])
    suspects = controle_catalogue.prix_suspects(cat)
    assert [s["id"] for s in suspects] == [1]
    assert suspects[0]["reference"] == 174.99


def test_annonce_isolee_et_fiche_incomplete():
    cat = variantes.annoter([
        _c(10, "Refroidissement", "Noctua NH-D15 G2 chromax", 150, sockets_supportes=["AM5"], hauteur_mm=168),
        _c(11, "Refroidissement", "Noctua NH-D15 G2 chromax Ventirad CPU", 149, sockets_supportes=["AM5"]),
        _c(12, "Refroidissement", "Noctua NH-U12A chromax", 130, sockets_supportes=["AM5"], hauteur_mm=158),
    ])
    for c in cat:           # simule deux annonces que variantes.py n'a pas regroupées
        c["groupe_id"], c["nb_variantes"] = c["id"], 1
    paires = controle_catalogue.annonces_isolees(cat)
    assert [(p["id"], p["proche_id"]) for p in paires] in ([(10, 11)], [(11, 10)])
    incompletes = controle_catalogue.fiches_incompletes(cat)
    assert [(f["id"], f["manques"]) for f in incompletes] == [(11, ["hauteur_mm"])]


def test_avertissement_cable_16_broches():
    gpu = {"connecteur_alim": "1 x 16 broches (12V-2x6)"}
    assert check_cable_alimentation(gpu, {"connecteur_12v_2x6": "Non"})
    assert check_cable_alimentation(gpu, {"connecteur_12v_2x6": "Oui"}) == []
    assert check_cable_alimentation({"connecteur_alim": "2 x 8 broches"}, {"connecteur_12v_2x6": "Non"}) == []


def test_compatibilite_renvoie_les_avertissements(client):
    r = client.post("/api/check-compatibility", json={"components": [
        {"categorie": "GPU", "specs": {"connecteur_alim": "1 x 16 broches (12V-2x6)", "tdp": 200}},
        {"categorie": "Alimentation", "specs": {"connecteur_12v_2x6": "Non", "wattage": 850}},
    ]})
    data = r.json()
    assert data["compatible"] is True and len(data["avertissements"]) == 1


def test_routes_admin_du_controle(client, catalog):
    assert client.get("/api/admin/controle-catalogue").status_code == 401
    r = client.get("/api/admin/controle-catalogue", headers=ADMIN)
    assert r.status_code == 200 and set(r.json()) == {"prix_suspects", "annonces_isolees", "fiches_incompletes"}
    assert client.post("/api/admin/controle/ignorer", json={"cle": "n'importe quoi"}, headers=ADMIN).status_code == 400
    # Rattacher puis séparer : la fiche change de produit, puis redevient seule.
    a, b = component(catalog, "RTX 4060"), component(catalog, "RX 7600")
    assert client.post("/api/admin/variantes/rattacher", json={"id": a["id"], "cible": b["id"]}, headers=ADMIN).status_code == 200
    groupes = {c["id"]: c["groupe_id"] for c in client.get("/components").json()["components"]}
    assert groupes[a["id"]] == groupes[b["id"]]
    assert client.post("/api/admin/variantes/separer", json={"id": a["id"]}, headers=ADMIN).status_code == 200
    groupes = {c["id"]: c["groupe_id"] for c in client.get("/components").json()["components"]}
    assert groupes[a["id"]] != groupes[b["id"]]


def test_prix_amazon_depuis_l_extension(client, catalog):
    ssd = component(catalog, "Crucial P3")
    r = client.post(f"/api/admin/components/{ssd['id']}/prix-amazon", json={"prix": 64.9}, headers=ADMIN)
    assert r.status_code == 200
    maj = next(c for c in client.get("/components").json()["components"] if c["id"] == ssd["id"])
    assert maj["prix_indicatif"] == 64.9
    assert client.post(f"/api/admin/components/{ssd['id']}/prix-amazon", json={"prix": -1}, headers=ADMIN).status_code == 400
