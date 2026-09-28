import os
import tempfile
from datetime import datetime, timedelta

import site_stats


def test_un_appareil_qui_revient_ne_compte_qu_une_fois():
    iphone, pc = "Mozilla/5.0 (iPhone) Safari", "Mozilla/5.0 (Windows NT 10.0) Chrome"
    now = datetime.utcnow()
    lignes = [f'1.1.1.1 - - [{(now - timedelta(days=d)).strftime("%d/%b/%Y")}:10:00:00 +0000] "GET / HTTP/1.1" 200 1 "-" "{iphone}"'
              for d in range(3)]
    lignes.append(f'2.2.2.2 - - [{now.strftime("%d/%b/%Y")}:10:00:00 +0000] "GET /application HTTP/1.1" 200 1 "https://www.tiktok.com/" "{pc}"')
    lignes.append(f'3.3.3.3 - - [{now.strftime("%d/%b/%Y")}:10:00:00 +0000] "GET / HTTP/1.1" 200 1 "-" "Googlebot/2.1"')
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
