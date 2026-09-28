"""
Statistiques de visite à partir des journaux nginx (déjà tenus pour la
sécurité, 14 jours) : aucun script, aucun cookie, rien de plus collecté.
Les adresses IP ne servent qu'à compter les appareils différents (empreinte
adresse + navigateur, calculée en mémoire le temps du calcul) et
n'apparaissent jamais dans le résultat.

Un « appareil » = une même adresse IP avec le même navigateur. C'est une
estimation : un téléphone qui passe du Wi-Fi à la 4G compte deux fois, deux
personnes derrière la même box avec le même navigateur comptent une fois.
"""
import glob
import gzip
import hashlib
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from urllib.parse import urlparse

LOG_GLOB = os.getenv("PCRADAR_ACCESS_LOG_GLOB", "/var/log/nginx/access.log*")
LINE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<day>\d{2}/\w{3}/\d{4}):[^\]]+\] "(?P<method>[A-Z]+) (?P<path>\S+) [^"]*" '
    r'(?P<status>\d{3}) \S+ "(?P<ref>[^"]*)" "(?P<ua>[^"]*)"'
)
BOTS = re.compile(
    r"bot|crawl|spider|slurp|curl|wget|python|httpx|go-http|java/|apachebench|monitor|uptime|headless|"
    r"lighthouse|preview|facebookexternalhit|scan|feed|http-client|okhttp|axios|node-fetch|"
    r"iPhone OS 13_2_3",  # faux iPhone de 2019, signature de nombreux robots scanneurs
    re.IGNORECASE,
)
# Adresses que seuls les robots demandent (fichiers secrets, WordPress...) :
# l'adresse IP qui en demande une est traitée comme un robot ce jour-là.
PROBES = re.compile(r"\.(env|git|php|ya?ml|sql|bak|ini)\b|wp-|xmlrpc|phpmyadmin|secrets?\b|/\.|config\.js", re.IGNORECASE)
MOBILE = re.compile(r"mobile|android|iphone|ipad", re.IGNORECASE)
NOT_PAGES = re.compile(r"^/(api|static|admin)|\.(xml|txt|ico|png|svg|jpg|webp|js|css|json|map|php|env)$", re.IGNORECASE)
# Seules les vraies pages du site comptent : les adresses inventées par les
# robots qui sondent le serveur (/wp-login, /.git...) sont ignorées.
SITE_PAGES = re.compile(
    r"^/(|configurateur|comparateur|assistant|estimer-fps|compte|application|mentions-legales|confidentialite|cgu|cookies"
    r"|guides(/[a-z0-9-]+)?|composants(/[a-z0-9-]+)?|composant/\d+-[a-z0-9-]+|comparer(/[a-z0-9-]+)?|build/\d+)$"
)
SEARCH_ENGINES = {"google": "Google", "bing": "Bing", "duckduckgo": "DuckDuckGo", "qwant": "Qwant",
                  "yahoo": "Yahoo", "ecosia": "Ecosia", "yandex": "Yandex", "brave": "Brave Search"}


def _source(ref, host):
    if not ref or ref == "-":
        return "Accès direct"
    try:
        domain = (urlparse(ref).hostname or "").lower()
    except ValueError:
        return "Autre"
    if not domain or domain.endswith(host):
        return None  # navigation interne
    if re.fullmatch(r"[\d.]+|[0-9a-f:]+", domain):
        return "Accès direct"  # site ouvert par son adresse IP : jamais d'IP dans le résultat
    for key, name in SEARCH_ENGINES.items():
        if key in domain:
            return name
    return domain.removeprefix("www.")


def _open(path):
    return gzip.open(path, "rt", encoding="utf-8", errors="replace") if path.endswith(".gz") else open(path, encoding="utf-8", errors="replace")


def _lines(log_glob):
    for path in sorted(glob.glob(log_glob)):
        try:
            with _open(path) as f:
                for line in f:
                    m = LINE.match(line)
                    if m:
                        yield m
        except OSError:
            continue


def compute(excluded_ips=(), host="pcradar.tech", days=14, log_glob=LOG_GLOB):
    """
    Seuls comptent les vrais navigateurs : un appareil n'est retenu que si,
    le même jour, il a aussi appelé l'API du site (/api/...), ce que fait le
    JavaScript des pages. Les robots qui se font passer pour un navigateur ne
    récupèrent que la page HTML : ils étaient la grande majorité des
    « visiteurs » (constaté : 111 sur 123 en une journée).
    Sont aussi exclues, pour la journée, les adresses qui sondent le serveur
    (/.env, /wp-login...) et celles utilisées pour l'admin (appel /api/admin/
    accepté, donc avec le mot de passe) : le propriétaire.
    """
    since = (datetime.utcnow() - timedelta(days=days - 1)).date()
    navigateurs, exclus = set(), set()
    for m in _lines(log_glob):
        path = m["path"]
        if path.startswith("/api/admin/") and m["status"] == "200":
            exclus.add((m["ip"], m["day"]))
        elif PROBES.search(path):
            exclus.add((m["ip"], m["day"]))
        elif path.startswith("/api/") and m["status"] in ("200", "304"):
            navigateurs.add((m["ip"], m["ua"], m["day"]))
    week_start = (datetime.utcnow() - timedelta(days=6)).date()
    per_day_views, per_day_visitors = Counter(), defaultdict(set)
    pages, sources = Counter(), Counter()
    # Appareils différents sur toute la période (sans la date dans
    # l'empreinte) : quelqu'un qui revient 3 jours ne compte qu'une fois.
    week_devices, all_devices = {}, set()
    # Détail par jour, pour l'archive des totaux (main.py) : uniquement des
    # compteurs, aucune adresse ni empreinte.
    day_pages, day_sources, day_types = defaultdict(Counter), defaultdict(Counter), defaultdict(dict)
    for m in _lines(log_glob):
        if m["method"] != "GET" or m["status"] not in ("200", "304"):
            continue
        if m["ip"] in excluded_ips or BOTS.search(m["ua"]) or not m["ua"] or m["ua"] == "-":
            continue
        if (m["ip"], m["ua"], m["day"]) not in navigateurs or (m["ip"], m["day"]) in exclus:
            continue
        page = m["path"].split("?", 1)[0]
        if NOT_PAGES.search(page) or not SITE_PAGES.match(page):
            continue
        day = datetime.strptime(m["day"], "%d/%b/%Y").date()
        if day < since:
            continue
        device = hashlib.sha256(f"{m['ip']}|{m['ua']}".encode()).hexdigest()[:16]
        per_day_views[day] += 1
        per_day_visitors[day].add(device)
        all_devices.add(device)
        day_pages[day][page] += 1
        day_types[day][device] = "Mobile" if MOBILE.search(m["ua"]) else "Ordinateur"
        day_src = _source(m["ref"], host)
        if day_src:
            day_sources[day][day_src] += 1
        if day >= week_start:
            pages[page] += 1
            week_devices[device] = "Mobile" if MOBILE.search(m["ua"]) else "Ordinateur"
            src = _source(m["ref"], host)
            if src:
                sources[src] += 1
    days_list = [since + timedelta(days=i) for i in range(days)]
    return {
        "jours": [{"date": d.isoformat(), "pages_vues": per_day_views[d], "visiteurs": len(per_day_visitors[d])}
                  for d in days_list],
        # visiteurs = appareils différents sur 7 jours ; visites = somme des
        # appareils de chaque jour (un habitué compte une visite par jour).
        "semaine": {"pages_vues": sum(pages.values()), "visiteurs": len(week_devices),
                    "visites": sum(len(per_day_visitors[d]) for d in days_list[-7:])},
        "quinzaine": {"visiteurs": len(all_devices)},
        "pages": [{"page": p, "vues": n} for p, n in pages.most_common(15)],
        "provenance": [{"source": s, "visites": n} for s, n in sources.most_common(10)],
        "appareils": dict(Counter(week_devices.values())),
        "detail": {d.isoformat(): {"visiteurs": len(per_day_visitors[d]), "pages_vues": per_day_views[d],
                                   "pages": dict(day_pages[d]), "sources": dict(day_sources[d]),
                                   "appareils": dict(Counter(day_types[d].values()))}
                   for d in days_list},
    }
