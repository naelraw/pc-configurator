"""
Statistiques de visite à partir des journaux nginx (déjà tenus pour la
sécurité, 14 jours) : aucun script, aucun cookie, rien de plus collecté.
Les adresses IP ne servent qu'à compter les visiteurs uniques d'une journée
(empreinte calculée en mémoire) et n'apparaissent jamais dans le résultat.
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
    r"lighthouse|preview|facebookexternalhit|scan|feed|http-client|okhttp|axios|node-fetch",
    re.IGNORECASE,
)
MOBILE = re.compile(r"mobile|android|iphone|ipad", re.IGNORECASE)
NOT_PAGES = re.compile(r"^/(api|static|admin)|\.(xml|txt|ico|png|svg|jpg|webp|js|css|json|map|php|env)$", re.IGNORECASE)
# Seules les vraies pages du site comptent : les adresses inventées par les
# robots qui sondent le serveur (/wp-login, /.git...) sont ignorées.
SITE_PAGES = re.compile(
    r"^/(|configurateur|comparateur|assistant|estimer-fps|compte|mentions-legales|confidentialite|cgu|cookies"
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


def compute(excluded_ips=(), host="pcradar.tech", days=14, log_glob=LOG_GLOB):
    since = (datetime.utcnow() - timedelta(days=days - 1)).date()
    week_start = (datetime.utcnow() - timedelta(days=6)).date()
    per_day_views, per_day_visitors = Counter(), defaultdict(set)
    pages, sources, devices = Counter(), Counter(), Counter()
    week_visitors = set()
    for path in sorted(glob.glob(log_glob)):
        try:
            with _open(path) as f:
                for line in f:
                    m = LINE.match(line)
                    if not m or m["method"] != "GET" or m["status"] not in ("200", "304"):
                        continue
                    if m["ip"] in excluded_ips or BOTS.search(m["ua"]) or not m["ua"] or m["ua"] == "-":
                        continue
                    page = m["path"].split("?", 1)[0]
                    if NOT_PAGES.search(page) or not SITE_PAGES.match(page):
                        continue
                    day = datetime.strptime(m["day"], "%d/%b/%Y").date()
                    if day < since:
                        continue
                    visitor = hashlib.sha256(f"{m['ip']}|{m['ua']}|{day}".encode()).hexdigest()[:16]
                    per_day_views[day] += 1
                    per_day_visitors[day].add(visitor)
                    if day >= week_start:
                        pages[page] += 1
                        week_visitors.add(visitor)
                        src = _source(m["ref"], host)
                        if src:
                            sources[src] += 1
                        devices["Mobile" if MOBILE.search(m["ua"]) else "Ordinateur"] += 1
        except OSError:
            continue
    days_list = [since + timedelta(days=i) for i in range(days)]
    return {
        "jours": [{"date": d.isoformat(), "pages_vues": per_day_views[d], "visiteurs": len(per_day_visitors[d])}
                  for d in days_list],
        "semaine": {"pages_vues": sum(pages.values()), "visiteurs": len(week_visitors)},
        "pages": [{"page": p, "vues": n} for p, n in pages.most_common(15)],
        "provenance": [{"source": s, "visites": n} for s, n in sources.most_common(10)],
        "appareils": dict(devices),
    }
