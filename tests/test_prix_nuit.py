"""Mise à jour des prix : 4 passages par jour (2 h, 8 h, 14 h, 20 h, heure de Paris)."""
from datetime import datetime


def _paris(main, *args):
    return datetime(*args, tzinfo=main.PRIX_FUSEAU)


def _dernier_passage(main, valeur):
    """Écrit la date comme _mark_task_done en production : texte brut, pas du JSON."""
    client = main.get_client()
    try:
        client.execute("INSERT INTO app_state (cle, valeur) VALUES ('derniere_mise_a_jour_prix', ?) "
                       "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur", [valeur])
    finally:
        client.close()


def test_creneaux(app_main):
    main = app_main
    assert main._creneau_prix(_paris(main, 2026, 10, 9, 9, 30)) == _paris(main, 2026, 10, 9, 8, 0)
    assert main._creneau_prix(_paris(main, 2026, 10, 9, 20, 0)) == _paris(main, 2026, 10, 9, 20, 0)
    # Avant 2 h : on est encore dans le créneau de 20 h de la veille.
    assert main._creneau_prix(_paris(main, 2026, 10, 9, 1, 0)) == _paris(main, 2026, 10, 8, 20, 0)


def test_un_passage_par_creneau(client, app_main):
    main = app_main
    # Passage fait à 8 h 05 (Paris) = 6 h 05 UTC.
    _dernier_passage(main, "2026-10-09T06:05:00")
    assert not main._mise_a_jour_prix_due(_paris(main, 2026, 10, 9, 9, 0))
    assert not main._mise_a_jour_prix_due(_paris(main, 2026, 10, 9, 13, 59))
    assert main._mise_a_jour_prix_due(_paris(main, 2026, 10, 9, 14, 0))
    # Passage de 20 h fait à 20 h 10 (18 h 10 UTC) : rien jusqu'à 2 h, puis le suivant.
    _dernier_passage(main, "2026-10-09T18:10:00")
    assert not main._mise_a_jour_prix_due(_paris(main, 2026, 10, 10, 1, 59))
    assert main._mise_a_jour_prix_due(_paris(main, 2026, 10, 10, 2, 0))


def test_date_ecrite_par_mark_task_done(client, app_main):
    """Bug d'octobre 2026 : la date brute était lue comme du JSON, donc jamais
    trouvée, et la mise à jour recommençait en boucle."""
    main = app_main
    main._mark_task_done("derniere_mise_a_jour_prix")
    assert not main._mise_a_jour_prix_due()


def test_alertes_en_tete_et_fiches_bloquees_reprises(client, app_main, monkeypatch):
    """Les produits suivis passent en premier ; une fiche qu'Apify n'a pas pu lire
    est reprise par Bright Data dans le même passage."""
    main = app_main
    # Journal des relevés vide : toutes les fiches sont en retard (échéancier commun).
    c = main.get_client()
    main._preparer_releves(c)
    c.execute("DELETE FROM verifications_prix")
    c.execute("DELETE FROM journal_releves")
    c.close()
    main._state_set("releve_prets", {})
    lignes = main.get_client().execute(
        "SELECT id, asin FROM components WHERE asin IS NOT NULL AND asin != '' ORDER BY id").rows
    ids = [r[0] for r in lignes]
    asin = {r[0]: r[1] for r in lignes}
    suivi, bloque = ids[-1], ids[0]
    vus_apify, vus_bright, appliques = [], [], []

    def apify(asins):
        vus_apify.extend(asins)
        return {a: {"prix": 100.0} for a in asins if a != asin[bloque]}

    def bright(items, timeout):
        vus_bright.extend(i["url"].rsplit("/", 1)[-1] for i in items)
        return [{"asin": i["url"].rsplit("/", 1)[-1]} for i in items]

    monkeypatch.setattr(main, "DAILY_ROTATION_START", datetime(2000, 1, 1))
    monkeypatch.setattr(main, "PRIX_PASSAGES_HEURES", (2,))
    monkeypatch.setattr(main, "APIFY_API_TOKEN", "t")
    monkeypatch.setattr(main, "BRIGHTDATA_API_TOKEN", "t")
    monkeypatch.setattr(main, "ZENROWS_API_KEY", "")
    monkeypatch.setattr(main, "refresh_allowance", lambda f, per_day=True: {"apify": 3, "brightdata": 2}.get(f, 0))
    monkeypatch.setattr(main, "_composants_prioritaires", lambda: set())
    monkeypatch.setattr(main, "_composants_sous_alerte", lambda: {suivi})
    monkeypatch.setattr(main, "_capacite_prix", lambda: {"total_par_jour": 1000, "services": []})
    monkeypatch.setattr(main, "_apify_credit", lambda: None)
    monkeypatch.setattr(main, "fetch_amazon_products_apify", apify)
    monkeypatch.setattr(main, "_brightdata_scrape_sync", bright)
    monkeypatch.setattr(main, "_indexer_resultats_brightdata", lambda res: ({r["asin"].upper(): r for r in res}, {}))
    monkeypatch.setattr(main, "_normalize_brightdata_item", lambda item, a: {"prix": 90.0})
    monkeypatch.setattr(main, "_marquer_vitrine", lambda *a: None)
    monkeypatch.setattr(main, "_apply_amazon_price_info", lambda client, cid, *a, **k: appliques.append((cid, k["source_label"])) or
                        {"error": None, "remis_en_stock": False, "passe_epuise": False})
    stats = main._run_daily_price_refresh_rotation()
    assert vus_apify[0] == asin[suivi]                      # le produit suivi passe en premier
    assert asin[bloque] in vus_apify
    assert vus_bright[0] == asin[bloque]                   # repris tout de suite par Bright Data
    assert (bloque, "Bright Data") in appliques
    assert stats["repris"] == 1 and stats["bloques"] == 1 and stats["alertes"] == 1
    assert len({cid for cid, _ in appliques}) == len(appliques)   # chaque fiche lue une seule fois


def test_relecture_a_la_consultation(client, app_main, monkeypatch):
    main = app_main
    lances = []
    composant = {"id": 4242, "asin": "B0VUE00001", "en_stock": 1,
                 "prix_marche": [{"vendeur": "Amazon", "prix": 99.0, "date_releve": "2026-01-01"}]}
    monkeypatch.setattr(main, "get_catalog", lambda: [composant])
    monkeypatch.setattr(main, "_relire_un_composant", lambda cid: lances.append(cid))
    main._state_set("relectures_vue", {})
    navigateur = "Mozilla/5.0 (Windows NT 10.0) Chrome/130"
    assert not main._relire_si_ancien(4242, "Googlebot/2.1")          # jamais pour un robot
    assert main._relire_si_ancien(4242, navigateur)
    main._relectures_vue_en_cours.clear()
    assert not main._relire_si_ancien(4242, navigateur)               # une fois par jour et par fiche
    composant["prix_marche"][0]["date_releve"] = datetime.utcnow().date().isoformat()
    main._state_set("relectures_vue", {})
    assert not main._relire_si_ancien(4242, navigateur)               # relevé récent : inutile
    composant["prix_marche"][0]["date_releve"] = "2026-01-01"
    monkeypatch.setattr(main, "PRIX_RELECTURES_VUE_PAR_JOUR", 0)
    assert not main._relire_si_ancien(4242, navigateur)               # plafond du jour atteint
    import time
    time.sleep(0.2)
    assert lances == [4242]
