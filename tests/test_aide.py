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
    from conftest import component
    gpu = component(catalog, "RTX 4060")
    vus = []

    def ia(prompt, **k):
        vus.append(prompt)
        return ('{"type": "advice", "message": "La RTX 4060 est un bon choix pour le 1080p.", "jeux": [], '
                f'"composants": [{gpu["id"]}], "ticket": null}}')
    monkeypatch.setattr(main, "call_ai_model", ia)
    main._chat_requests_by_ip.clear()
    membre = new_client("203.0.113.88")
    assert membre.post("/api/auth/register", json={"email": "bulle@test.fr", "password": "motdepasse123"}).status_code == 200
    r = membre.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "quelle carte pour le 1080p ?"}],
                                                 "aide": True, "page": "/configurateur"})
    data = r.json()
    assert r.status_code == 200 and data["composants"] == [gpu["id"]] and data["ticket"] is None
    # La bulle reçoit de quoi afficher et ajouter le composant sans charger tout le catalogue.
    assert data["fiches"][str(gpu["id"])]["categorie"] == "GPU" and data["fiches"][str(gpu["id"])]["nom"] == gpu["nom"]
    assert "bulle d'aide du site" in vus[-1] and "/configurateur" in vus[-1]
