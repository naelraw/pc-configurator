import os
import tempfile
from datetime import datetime, timedelta

import site_stats


def test_un_appareil_qui_revient_ne_compte_qu_une_fois():
    iphone, pc = "Mozilla/5.0 (iPhone) Safari", "Mozilla/5.0 (Windows NT 10.0) Chrome"
    now = datetime.utcnow()
    jour = lambda d=0: (now - timedelta(days=d)).strftime("%d/%b/%Y")
    ligne = lambda ip, d, chemin, ua, statut=200, ref="-": f'{ip} - - [{jour(d)}:10:00:00 +0000] "GET {chemin} HTTP/1.1" {statut} 1 "{ref}" "{ua}"'
    lignes = []
    for d in range(3):  # un vrai iPhone : page + feuille de style, 3 jours de suite
        lignes += [ligne("1.1.1.1", d, "/", iphone), ligne("1.1.1.1", d, "/api/components", iphone, 304)]
    lignes += [ligne("2.2.2.2", 0, "/application", pc, ref="https://www.tiktok.com/"), ligne("2.2.2.2", 0, "/api/config", pc)]
    lignes.append(ligne("3.3.3.3", 0, "/", "Googlebot/2.1"))
    # Robot déguisé en iPhone : ne charge que le HTML → ignoré
    lignes.append(ligne("4.4.4.4", 0, "/", "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15"))
    # Scanner qui charge page et API mais cherche aussi des secrets → ignoré
    lignes += [ligne("6.6.6.6", 0, "/", pc), ligne("6.6.6.6", 0, "/api/config", pc), ligne("6.6.6.6", 0, "/api/.env", pc, 404)]
    # Page + style seulement, sans appel à l'API (robot) → ignoré
    lignes += [ligne("7.7.7.7", 0, "/", pc), ligne("7.7.7.7", 0, "/static/style.css", pc)]
    # Le propriétaire (admin connecté) → ignoré
    lignes += [ligne("5.5.5.5", 0, "/", pc), ligne("5.5.5.5", 0, "/static/style.css", pc), ligne("5.5.5.5", 0, "/api/admin/stats", pc)]
    chemin = os.path.join(tempfile.mkdtemp(), "access.log")
    open(chemin, "w").write("\n".join(lignes) + "\n")
    r = site_stats.compute(log_glob=chemin)
    assert r["jours"][-1]["visiteurs"] == 2          # iPhone + PC aujourd'hui, le robot est ignoré
    assert r["semaine"]["visiteurs"] == 2            # l'iPhone venu 3 jours ne compte qu'une fois
    assert r["semaine"]["visites"] == 4
    assert r["quinzaine"]["visiteurs"] == 2
    assert r["appareils"] == {"Mobile": 1, "Ordinateur": 1}
    assert {"page": "/application", "vues": 1} in r["pages"]
    assert {"source": "tiktok.com", "visites": 1} in r["provenance"]


def test_totaux_depuis_le_debut():
    import main
    from datetime import datetime
    hier = {"visiteurs": 3, "pages_vues": 10, "pages": {"/": 8, "/configurateur": 2}, "sources": {"Google": 2}, "appareils": {"Mobile": 2, "Ordinateur": 1}}
    avant = {"visiteurs": 5, "pages_vues": 7, "pages": {"/": 7}, "sources": {"Bing": 1}, "appareils": {"Ordinateur": 5}}
    auj = datetime.utcnow().date().isoformat()
    data = {"detail": {auj: {"visiteurs": 1, "pages_vues": 2, "pages": {"/application": 2}, "sources": {}, "appareils": {"Mobile": 1}}}}
    t = main._totaux_stats({"2026-09-01": avant, "2026-09-02": hier}, data)
    assert t["depuis"] == "2026-09-01" and t["jours"] == 3
    assert t["visites"] == 9 and t["pages_vues"] == 19
    assert t["meilleur_jour"] == {"date": "2026-09-01", "visiteurs": 5}
    assert t["appareils"] == {"Mobile": 3, "Ordinateur": 6}
    assert t["pages"][0] == {"page": "/", "vues": 15}


def test_liens_de_partage(client):
    import os, tempfile
    from datetime import datetime
    r = client.get("/tiktok", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/?utm_source=tiktok"
    assert client.get("/insta", follow_redirects=False).headers["location"] == "/?utm_source=instagram"
    jour = datetime.utcnow().strftime("%d/%b/%Y")
    ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15"
    lignes = [f'8.8.8.8 - - [{jour}:10:00:00 +0000] "GET /?utm_source=tiktok HTTP/1.1" 200 1 "-" "{ua}"',
              f'8.8.8.8 - - [{jour}:10:00:01 +0000] "GET /api/components HTTP/1.1" 200 1 "https://pcradar.tech/" "{ua}"']
    chemin = os.path.join(tempfile.mkdtemp(), "access.log")
    open(chemin, "w").write("\n".join(lignes) + "\n")
    r = site_stats.compute(log_glob=chemin)
    assert {"source": "TikTok", "visites": 1} in r["provenance"]
