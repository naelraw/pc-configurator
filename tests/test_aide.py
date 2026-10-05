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
