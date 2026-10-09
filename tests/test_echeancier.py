"""Échéancier commun des relevés de prix : PC d'abord, services sur ce qui reste."""
from datetime import datetime, timedelta

import main

ADMIN = {"X-Admin-Secret": "admin-de-test"}


def _fiches(client):
    return [r[0] for r in main.get_client().execute(
        "SELECT id FROM components WHERE asin IS NOT NULL AND asin != '' AND en_stock = 1 ORDER BY id").rows]


def _base(monkeypatch, alertes=(), prioritaires=(), capacite=1000, volatilite=None):
    monkeypatch.setattr(main, "_composants_sous_alerte", lambda: set(alertes))
    monkeypatch.setattr(main, "_prioritaires_en_cache", lambda: set(prioritaires))
    monkeypatch.setattr(main, "_capacite_prix", lambda: {"total_par_jour": capacite, "services": []})
    monkeypatch.setattr(main, "_volatilite_prix", lambda: volatilite or {})


def _vider(client):
    c = main.get_client()
    main._preparer_releves(c)
    c.execute("DELETE FROM verifications_prix")
    c.execute("DELETE FROM journal_releves")
    c.close()
    main._state_set("releve_prets", {})


def test_categories_capacite_et_volatilite(client, monkeypatch):
    _vider(client)
    ids = _fiches(client)
    _base(monkeypatch, alertes=[ids[0]], prioritaires=[ids[1]], capacite=100000, volatilite={ids[2]: 0.6})
    fiches, infos = main._echeancier_base()
    assert fiches[ids[0]]["categorie"] == "alerte" and fiches[ids[0]]["intervalle_h"] == 6     # alertes : toujours 6 h
    assert fiches[ids[1]]["categorie"] == "prioritaire"
    # Capacité très supérieure à la demande : intervalles raccourcis au plus de moitié.
    assert infos["facteur"] == main.RELEVE_FACTEUR_MIN
    assert fiches[ids[1]]["intervalle_h"] == 12 * main.RELEVE_FACTEUR_MIN
    assert fiches[ids[2]]["intervalle_h"] == 36 * main.RELEVE_FACTEUR_MIN * 0.6                # prix qui bouge : plus souvent
    # Capacité quasi nulle : intervalles allongés au plus x4, sauf les alertes.
    main._ECHEANCIER_BASE.update(at=0.0, data=None)
    _base(monkeypatch, alertes=[ids[0]], capacite=0)
    fiches, infos = main._echeancier_base()
    assert infos["facteur"] == main.RELEVE_FACTEUR_MAX and fiches[ids[0]]["intervalle_h"] == 6


def test_peu_de_capacite_les_prioritaires_passent_avant(client, monkeypatch):
    _vider(client)
    ids = _fiches(client)
    # Capacité limitée : les prioritaires ralentissent moins que les autres annonces.
    _base(monkeypatch, prioritaires=ids[:3], capacite=12)
    fiches, infos = main._echeancier_base()
    assert infos["facteur_prioritaires"] < infos["facteur"]
    assert fiches[ids[0]]["intervalle_h"] < fiches[ids[5]]["intervalle_h"] * 12 / 36


def test_pc_d_abord_puis_services_sur_le_reste(client, monkeypatch):
    _vider(client)
    ids = _fiches(client)
    _base(monkeypatch, alertes=[ids[-1]])
    # Le PC reçoit d'abord le produit suivi par une alerte, puis les plus en retard.
    donnees = client.get("/api/admin/prix-a-relire?n=2&origine=pc", headers=ADMIN).json()["fiches"]
    assert donnees[0]["id"] == ids[-1]
    confiees = {f["id"] for f in donnees}
    # Une fiche lue à l'instant par le PC n'est plus en retard ; les fiches confiées ne vont pas aux services.
    main._noter_releve(ids[1], "PC", "lu")
    etat = {f["id"]: f for f in main._etat_releves()}
    assert etat[ids[1]]["retard"] < main.RELEVE_SEUIL_SERVICES
    prets = main._prets_actifs()
    assert confiees <= {int(k) for k in prets} and all(v["origine"] == "PC" for v in prets.values())
    candidats_services = [f["id"] for f in main._etat_releves()
                          if str(f["id"]) not in prets and (f["retard"] >= main.RELEVE_SEUIL_SERVICES or f["pc_echoue"])]
    assert ids[1] not in candidats_services and not confiees & set(candidats_services)


def test_fiche_illisible_par_le_pc_laissee_aux_services(client, monkeypatch):
    _vider(client)
    ids = _fiches(client)
    _base(monkeypatch)
    for _ in range(main.RELEVE_ECHECS_PC_MAX):
        main._noter_releve(ids[0], "PC", "sans_prix")
    etat = {f["id"]: f for f in main._etat_releves()}
    assert etat[ids[0]]["pc_echoue"]
    assert ids[0] not in [f["id"] for f in main._fiches_pour_extension(50, "PC")]
    # Une lecture réussie par le PC efface les échecs.
    main._noter_releve(ids[0], "PC", "lu")
    assert not {f["id"]: f for f in main._etat_releves()}[ids[0]]["pc_echoue"]


def test_resume_pour_l_admin_et_l_extension(client, monkeypatch):
    _vider(client)
    ids = _fiches(client)
    _base(monkeypatch, alertes=[ids[0]])
    client.get("/api/admin/prix-a-relire?n=1&origine=pc", headers=ADMIN)
    main._noter_releve(ids[0], "PC", "lu")
    main._noter_releve(ids[1], "Apify", "lu")
    main._noter_releve(ids[2], "PC", "sans_prix")
    r = client.get("/api/admin/releve-prix", headers=ADMIN).json()
    assert {c["cle"] for c in r["categories"]} >= {"alerte", "normal"}
    alerte = next(c for c in r["categories"] if c["cle"] == "alerte")
    assert alerte["a_jour"] == 1 and alerte["intervalle_h"] == 6
    assert r["lus_24h"] == 2 and r["part_gratuite"] == 50
    pc = next(p for p in r["postes"] if p["origine"] == "PC")
    assert pc["actif"] and pc["lus_24h"] == 1 and pc["sans_prix_24h"] == 1
    assert client.get("/api/admin/releve-prix").status_code == 401
