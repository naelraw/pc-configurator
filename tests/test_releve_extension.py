"""Relevé des prix par l'extension de l'admin (depuis son navigateur, sans quota)."""
import main

ADMIN = {"X-Admin-Secret": "admin-de-test"}


def _zone(prix_entier, centimes="00"):
    return ('<span id="productTitle">Produit</span>\n<div id="corePriceDisplay_desktop_feature_div">'
            f'<span class="a-price-whole">{prix_entier}<span class="a-price-decimal">,</span></span>'
            f'<span class="a-price-fraction">{centimes}</span></div>\n<div id="availability"><span>En stock</span></div>')


def test_fiches_confiees_par_urgence_sans_doublon(client, monkeypatch):
    main._state_set("extension_prets", {})
    ids = [r[0] for r in main.get_client().execute(
        "SELECT id FROM components WHERE asin IS NOT NULL AND asin != '' AND en_stock = 1 ORDER BY id").rows]
    monkeypatch.setattr(main, "_composants_sous_alerte", lambda: {ids[-1]})
    monkeypatch.setattr(main, "_prioritaires_en_cache", lambda: set())
    assert client.get("/api/admin/prix-a-relire").status_code == 401
    premiere = client.get("/api/admin/prix-a-relire?n=2", headers=ADMIN).json()["fiches"]
    assert premiere[0]["id"] == ids[-1]                       # produit suivi par une alerte en premier
    suivante = client.get("/api/admin/prix-a-relire?n=2", headers=ADMIN).json()["fiches"]
    assert not {f["id"] for f in premiere} & {f["id"] for f in suivante}   # jamais confiée deux fois
    main._state_set("extension_prets", {})


def test_prix_lu_applique_et_pages_refusees(client):
    cid, asin, prix = main.get_client().execute(
        "SELECT id, asin, prix_indicatif FROM components WHERE asin IS NOT NULL AND asin != '' AND en_stock = 1 LIMIT 1").rows[0]
    main._state_set("extension_stats", {})
    nouveau = int(prix) - 1
    r = client.post("/api/admin/prix-extension", headers=ADMIN, json={"id": cid, "asin": asin, "extrait": _zone(nouveau)}).json()
    assert r["resultat"] == "lu" and r["prix"] == float(nouveau)
    assert main.get_client().execute("SELECT prix_indicatif FROM components WHERE id = ?", [cid]).rows[0][0] == float(nouveau)
    # Vérification « robot » d'Amazon : signalée, rien de modifié.
    r = client.post("/api/admin/prix-extension", headers=ADMIN,
                    json={"id": cid, "asin": asin, "extrait": "<form action='/errors/validateCaptcha'>"}).json()
    assert r["resultat"] == "bloque"
    # Page sans prix : jamais « épuisé » sur la foi de l'extension.
    r = client.post("/api/admin/prix-extension", headers=ADMIN,
                    json={"id": cid, "asin": asin, "extrait": '<span id="productTitle">Produit</span>'}).json()
    assert r["resultat"] == "sans_prix"
    assert main.get_client().execute("SELECT en_stock FROM components WHERE id = ?", [cid]).rows[0][0] == 1
    stats = main._state_get("extension_stats", {})
    assert (stats["lus"], stats["bloques"], stats["sans_prix"]) == (1, 1, 1)
    # Mauvais ASIN pour cette fiche : refusé.
    assert client.post("/api/admin/prix-extension", headers=ADMIN,
                       json={"id": cid, "asin": "B0AUTRE000", "extrait": _zone(10)}).status_code == 404


def test_zone_prix_reelle_avant_le_bloc_de_donnees():
    """Le nom de la zone de prix apparaît aussi plus haut dans un bloc de données :
    la lecture doit viser la vraie zone (id=...)."""
    html = ('{"dtu":"corePriceDisplay_desktop_feature_div","lb":0}' + "x" * 9000 + _zone("1&nbsp;063", "05"))
    assert main._parse_zenrows_amazon_html(html, "B0TEST")["prix"] == 1063.05


def test_fiche_ouverte_par_l_admin_notee_navigation(client):
    cid, asin, prix = main.get_client().execute(
        "SELECT id, asin, prix_indicatif FROM components WHERE asin IS NOT NULL AND asin != '' AND en_stock = 1 LIMIT 1 OFFSET 3").rows[0]
    extrait = ('<span id="productTitle">Produit</span>\n<div id="corePriceDisplay_desktop_feature_div" class="celwidget">'
               '<span class="a-price-whole">' + str(int(prix)) + '<span class="a-price-decimal">,</span></span>'
               '<span class="a-price-fraction">00</span></div>\n<div id="availability"><span> En stock </span></div>')
    r = client.post("/api/admin/prix-extension", headers=ADMIN,
                    json={"id": cid, "asin": asin, "extrait": extrait, "origine": "navigation"}).json()
    assert r["resultat"] == "lu" and r["prix"] == float(int(prix))
    derniere = main.get_client().execute(
        "SELECT source, resultat FROM journal_releves WHERE component_id = ? ORDER BY id DESC LIMIT 1", [cid]).rows[0]
    assert tuple(derniere) == ("Navigation", "lu")
