"""Bulle d'aide du site : discussion avec l'IA et tickets visibles dans l'admin."""
import main

ADMIN = {"X-Admin-Secret": "admin-de-test"}


def test_aide_propose_un_ticket_sans_l_envoyer(client, monkeypatch):
    monkeypatch.setattr(main, "call_ai_model", lambda *a, **k: (
        '{"message": "Je peux transmettre ça à l\'équipe.", "ticket": {"categorie": "prix", '
        '"titre": "Prix faux sur une RTX 4060", "description": "Le prix affiché ne correspond pas à Amazon."}}'))
    main._aide_par_ip.clear()
    r = client.post("/api/aide/chat", json={"messages": [{"role": "user", "content": "le prix de la 4060 est faux"}], "page": "/configurateur"})
    assert r.status_code == 200
    data = r.json()
    assert data["ticket"]["categorie"] == "prix" and data["ticket"]["titre"].startswith("Prix faux")
    # Proposer un ticket ne le crée pas : c'est le visiteur qui confirme.
    assert client.get("/api/admin/tickets", headers=ADMIN).json()["tickets"] == []


def test_aide_reponse_en_texte_simple(client, monkeypatch):
    monkeypatch.setattr(main, "call_ai_model", lambda *a, **k: "Va dans Mon compte (/compte).")
    main._aide_par_ip.clear()
    r = client.post("/api/aide/chat", json={"messages": [{"role": "user", "content": "où sont mes configs ?"}]})
    assert r.json() == {"status": "ok", "message": "Va dans Mon compte (/compte).", "ticket": None}


def test_ticket_cree_puis_gere_dans_l_admin(client):
    main._tickets_par_ip.clear()
    assert client.post("/api/aide/ticket", json={"categorie": "bug", "titre": "Bouton", "description": "Le bouton ne marche pas",
                                                 "email": "pas-un-email"}).status_code == 422
    r = client.post("/api/aide/ticket", json={
        "categorie": "bug", "titre": "Le bouton Ajouter ne marche pas", "description": "Rien ne se passe au clic sur mobile.",
        "page": "/configurateur", "email": "visiteur@test.fr",
        "discussion": [{"role": "user", "content": "le bouton ne marche pas"}],
    })
    assert r.status_code == 200
    numero = r.json()["id"]
    assert client.get("/api/admin/tickets").status_code == 401
    t = next(t for t in client.get("/api/admin/tickets", headers=ADMIN).json()["tickets"] if t["id"] == numero)
    assert t["statut"] == "ouvert" and t["email"] == "visiteur@test.fr" and t["discussion"][0]["content"] == "le bouton ne marche pas"
    assert client.post(f"/api/admin/tickets/{numero}", json={"statut": "nimporte"}, headers=ADMIN).status_code == 400
    assert client.post(f"/api/admin/tickets/{numero}", json={"statut": "resolu", "note_admin": "corrigé"}, headers=ADMIN).status_code == 200
    t = next(t for t in client.get("/api/admin/tickets", headers=ADMIN).json()["tickets"] if t["id"] == numero)
    assert t["statut"] == "resolu" and t["note_admin"] == "corrigé"
    assert client.delete(f"/api/admin/tickets/{numero}", headers=ADMIN).status_code == 200
    assert all(t["id"] != numero for t in client.get("/api/admin/tickets", headers=ADMIN).json()["tickets"])


def test_tickets_limites_par_heure(client):
    main._tickets_par_ip.clear()
    corps = {"categorie": "autre", "titre": "Test spam", "description": "Un message de test."}
    codes = [client.post("/api/aide/ticket", json=corps).status_code for _ in range(main.TICKETS_MAX_PER_HOUR + 1)]
    assert codes[:-1] == [200] * main.TICKETS_MAX_PER_HOUR and codes[-1] == 429
    for t in client.get("/api/admin/tickets", headers=ADMIN).json()["tickets"]:
        client.delete(f"/api/admin/tickets/{t['id']}", headers=ADMIN)


def test_avec_un_compte_la_bulle_propose_des_composants(new_client, catalog, monkeypatch):
    from conftest import component, inscrire
    gpu = component(catalog, "RTX 4060")
    vus = []

    def ia(prompt, **k):
        vus.append(prompt)
        return ('{"type": "advice", "message": "La RTX 4060 est un bon choix pour le 1080p.", "jeux": [], '
                f'"composants": [{gpu["id"]}], "ticket": null}}')
    monkeypatch.setattr(main, "call_ai_model", ia)
    main._chat_requests_by_ip.clear()
    membre = new_client("203.0.113.88")
    assert inscrire(membre, "bulle@test.fr").status_code == 200
    r = membre.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "quelle carte pour le 1080p ?"}],
                                                 "aide": True, "page": "/configurateur"})
    data = r.json()
    assert r.status_code == 200 and data["composants"] == [gpu["id"]] and data["ticket"] is None
    # La bulle reçoit de quoi afficher et ajouter le composant sans charger tout le catalogue.
    assert data["fiches"][str(gpu["id"])]["categorie"] == "GPU" and data["fiches"][str(gpu["id"])]["nom"] == gpu["nom"]
    assert "# Dans la bulle d'aide" in vus[-1] and "/configurateur" in vus[-1]


def test_suivi_des_tickets_et_demande_explicite(client, monkeypatch):
    main._tickets_par_ip.clear()
    main._aide_par_ip.clear()
    r = client.post("/api/aide/ticket", json={"categorie": "bug", "titre": "Bouton cassé sur le comparateur",
                                              "description": "Le bouton Comparer ne répond pas."})
    numero, jeton = r.json()["id"], r.json()["jeton"]
    assert jeton and len(jeton) >= 16
    vus = []

    def ia(prompt, **k):
        vus.append(prompt)
        return '{"message": "D\'accord.", "ticket": null}'
    monkeypatch.setattr(main, "call_ai_model", ia)
    # Avec le bon code : l'IA connaît le ticket et son statut.
    client.post("/api/aide/chat", json={"messages": [{"role": "user", "content": f"où en est mon ticket {numero} ?"}],
                                        "tickets": [{"id": numero, "jeton": jeton}]})
    assert "Bouton cassé sur le comparateur" in vus[-1] and "pas encore traité" in vus[-1]
    # Mauvais code : rien (jamais les tickets des autres).
    main._aide_par_ip.clear()
    client.post("/api/aide/chat", json={"messages": [{"role": "user", "content": "et mon ticket ?"}],
                                        "tickets": [{"id": numero, "jeton": "faux"}]})
    assert "Bouton cassé" not in vus[-1] and "aucun ticket" in vus[-1]
    # Demande explicite : le formulaire s'affiche même si l'IA n'a pas proposé de ticket.
    main._aide_par_ip.clear()
    data = client.post("/api/aide/chat", json={"messages": [{"role": "user", "content": "tu peux me créer un ticket"}]}).json()
    assert data["ticket"] and data["ticket"]["titre"] == "Demande d'aide"
    client.delete(f"/api/admin/tickets/{numero}", headers=ADMIN)


def test_refus_hors_sujet_construit_par_le_serveur(client, monkeypatch):
    r = main._refus_hors_sujet("te dire qui est Amixem", [])
    assert "te dire qui est Amixem" in r or "Te dire qui est Amixem" in r
    assert r.rstrip().endswith("?")
    # Relances déjà utilisées : jamais redites tant qu'il en reste d'autres.
    deja = list(main.RELANCES_HORS_SUJET[:-1])
    for _ in range(10):
        assert main._refus_hors_sujet("faire ce calcul", [], refus_precedents=deja).endswith(main.RELANCES_HORS_SUJET[-1])
    # L'IA signale le hors sujet : le serveur répond, sans reprendre la question précédente.
    monkeypatch.setattr(main, "call_ai_model", lambda *a, **k: '{"message": "x", "ticket": null, "hors_sujet": true, "demande": "te dire qui est Amixem"}')
    main._aide_par_ip.clear()
    data = client.post("/api/aide/chat", json={"messages": [
        {"role": "user", "content": "un synonyme de maison"},
        {"role": "assistant", "content": "Je ne vais pas pouvoir te donner un synonyme de maison."},
        {"role": "user", "content": "qui est amixem"}]}).json()
    assert data["hors_sujet"] is True and "Amixem" in data["message"] and "maison" not in data["message"]


def test_composant_cite_fidele_a_la_demande():
    q = "c'est quoi la différence entre la rtx 5060 ti 8 go et 16 go ?"
    assert main._fidelite_a_la_demande("ASUS Dual GeForce RTX 5060 Ti 16GB", q) > main._fidelite_a_la_demande("PNY GeForce RTX 5060 8Go", q)
    assert main._fidelite_a_la_demande("PNY GeForce RTX 5060 8Go", "la 5060 elle vaut quoi") > main._fidelite_a_la_demande("ASUS RTX 5060 Ti 8GB", "la 5060 elle vaut quoi")
    # Aucun caractère de contrôle glissé dans le code (vu : \x08 à la place de \b dans une regex).
    import re, pathlib
    assert not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", pathlib.Path(main.__file__).read_text(encoding="utf-8"))


def test_reponse_ia_avec_echappement_casse_reste_lisible():
    casse = '{"type": "advice", "message": "son cache qui am' + chr(92) + 'u00eilore les perfs", "composants": []}'
    data = main.parse_ai_json(casse)
    assert data and data["type"] == "advice" and "les perfs" in data["message"]


def test_tickets_exportes_puis_anonymises_a_la_suppression_du_compte(new_client):
    from conftest import inscrire
    main._tickets_par_ip.clear()
    membre = new_client("203.0.113.91")
    assert inscrire(membre, "rgpd-ticket@test.fr").status_code == 200
    r = membre.post("/api/aide/ticket", json={"categorie": "bug", "titre": "Prix faux sur une carte",
                                              "description": "Le prix affiché ne correspond pas.",
                                              "discussion": [{"role": "user", "content": "le prix est faux"}]})
    numero = r.json()["id"]
    export = membre.get("/api/auth/export").json()
    assert [t["id"] for t in export["demandes_d_aide"]] == [numero]
    assert membre.delete("/api/auth/account").status_code == 200
    t = next(t for t in membre.get("/api/admin/tickets", headers=ADMIN).json()["tickets"] if t["id"] == numero)
    assert t["email"] is None and not t["discussion"] and t["titre"] == "Prix faux sur une carte"
    membre.delete(f"/api/admin/tickets/{numero}", headers=ADMIN)
