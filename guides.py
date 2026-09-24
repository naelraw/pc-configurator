"""
Guides d'achat « meilleur PC gamer pour ... » : une page par profil des
configs du moment (featured_builds.py), rendue côté serveur pour que Google
lise le contenu sans exécuter de JavaScript. Tout vient des données du jour :
pièces, prix, compatibilité, FPS estimés — rien n'est écrit à la main, la page
suit le catalogue.
"""
import json
from datetime import datetime
from html import escape

# slug d'URL -> id de profil dans featured_builds.PROFILES
GUIDES = {
    "pc-gamer-1080p": "1080p",
    "pc-gamer-1440p": "1440p",
    "pc-gamer-haut-de-gamme": "1440p-plus",
    "pc-gamer-4k": "4k",
}
SLUG_BY_PROFILE = {v: k for k, v in GUIDES.items()}

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]
RES_LABEL = {"1080p": "1080p", "1440p": "1440p", "4k": "4K"}

_SHELL_HEAD = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="theme-color" content="#0e0f11">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:type" content="article">
<meta property="og:url" content="{canonical}">
<meta property="og:site_name" content="PC Radar">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@phosphor-icons/web@2.1.1/src/regular/style.css">
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" type="image/png" sizes="96x96" href="/static/favicon-96.png">
<link rel="icon" type="image/png" sizes="512x512" href="/static/favicon.png">
<link rel="apple-touch-icon" href="/static/apple-touch-icon.png">
<link rel="stylesheet" href="/static/style.css">
</head>
<body>

<header>
  <div class="nav-wrap">
    <a href="/" class="logo"><img src="/static/favicon.svg" alt="" width="22" height="22">PC Radar</a>
    <button class="nav-toggle" id="nav-toggle" aria-label="Ouvrir le menu" aria-expanded="false"><span></span><span></span><span></span></button>
    <nav>
      <ul>
        <li><a href="/">Accueil</a></li>
        <li><a href="/configurateur">Configurateur</a></li>
        <li><a href="/assistant">Assistant IA</a></li>
        <li><a href="/comparateur">Comparateur</a></li>
        <li><a href="/estimer-fps">Estimer FPS</a></li>
        <li><a href="/compte">Mon compte</a></li>
      </ul>
    </nav>
  </div>
</header>
"""

_SHELL_FOOT = """
<footer>
  <div class="footer-inner">
    <div class="footer-brand">
      <strong>PC Radar</strong>
      <span>Projet personnel et indépendant. Compatibilité vérifiée côté serveur, suggestions IA validées avant affichage.</span>
    </div>
    <div class="footer-legal-links">
      <a href="/guides">Guides d'achat</a>
      <a href="/composants">Composants</a>
      <a href="/comparer">Comparatifs</a>
      <a href="/mentions-legales">Mentions légales</a>
      <a href="/confidentialite">Confidentialité</a>
      <a href="/cgu">CGU</a>
      <a href="/cookies">Cookies</a>
    </div>
  </div>
</footer>

<script src="/static/nav-menu.js"></script>
<script src="/static/effects.js"></script>
<script src="/static/price-history.js"></script>
<script src="/static/pages/guide.js"></script>
</body>
</html>
"""


def _euros(value, decimals=True):
    text = f"{value:,.2f}" if decimals else f"{round(value):,}"
    return text.replace(",", " ").replace(".", ",") + " €"


def _today():
    d = datetime.utcnow()
    return f"{d.day} {MOIS[d.month - 1]} {d.year}", f"{MOIS[d.month - 1]} {d.year}"


def _page(title, description, canonical, body):
    return (
        _SHELL_HEAD.format(title=escape(title), description=escape(description), canonical=escape(canonical))
        + body + _SHELL_FOOT
    )


def _component_url(part):
    from component_pages import page_url  # import local : component_pages importe ce module
    return page_url(part)


def _part(config, categorie):
    return next((p for p in config["composants"] if p["categorie"] == categorie), None)


def _reasons(config, catalog_by_id):
    """Explications générées à partir des vraies caractéristiques des pièces."""
    parts = {p["categorie"]: catalog_by_id.get(p["id"], {}) for p in config["composants"]}
    specs = {cat: (c.get("specs") or {}) for cat, c in parts.items()}
    cpu, gpu = _part(config, "CPU"), _part(config, "GPU")
    reasons = []
    if cpu and gpu:
        reasons.append(
            f"<strong>{escape(cpu['nom'])} + {escape(gpu['nom'])}</strong> : parmi toutes les combinaisons "
            f"en stock, c'est celle qui donne le plus d'images par seconde pour un budget de "
            f"{_euros(config['budget'], False)}, sur un panel de jeux lourds et de jeux compétitifs."
        )
    mb = specs.get("Carte mère", {})
    if mb.get("socket"):
        reasons.append(
            f"<strong>Carte mère {escape(str(mb.get('format', '')))}</strong> au socket "
            f"{escape(str(mb['socket']))}, compatible avec le processeur et la mémoire "
            f"{escape(str(mb.get('ram_type', '')))}."
        )
    tdp = (specs.get("CPU", {}).get("tdp") or 0) + (specs.get("GPU", {}).get("tdp") or 0)
    watts = specs.get("Alimentation", {}).get("wattage")
    if tdp and watts:
        reasons.append(
            f"<strong>Alimentation {watts} W</strong> : le processeur et la carte graphique consomment "
            f"environ {tdp} W au maximum, ce qui laisse une marge confortable pour le reste du PC."
        )
    ram = _part(config, "RAM")
    if ram:
        reasons.append(f"<strong>Mémoire</strong> : {escape(ram['nom'])}, suffisante pour les jeux récents.")
    reasons.append(
        "<strong>Compatibilité vérifiée</strong> : sockets, type de mémoire, format de carte mère, "
        "puissance d'alimentation et dimensions sont contrôlés automatiquement."
    )
    return reasons


def render_guide(config, all_configs, catalog_by_id):
    date_long, mois = _today()
    res = RES_LABEL.get(config["resolution"], config["resolution"])
    cpu, gpu = _part(config, "CPU"), _part(config, "GPU")
    total = _euros(config["total"], False)
    title = f"Meilleur PC gamer {res} à {total} ({mois}) — PC Radar"
    if config["id"] == "1440p-plus":
        title = f"Meilleur PC gamer haut de gamme à {total} ({mois}) — PC Radar"
    description = (
        f"{config['titre']} : {cpu['nom'] if cpu else ''} + {gpu['nom'] if gpu else ''}, "
        f"{total}, compatibilité vérifiée. FPS estimés en {res} et prix mis à jour chaque jour."
    )
    canonical = f"https://pcradar.tech/guides/{SLUG_BY_PROFILE[config['id']]}"

    rows = "".join(
        f"<tr><th scope=\"row\">{escape(p['categorie'])}</th>"
        f"<td><a href=\"{escape(_component_url(p))}\">{escape(p['nom'])}</a></td><td class=\"guide-price\">{_euros(p['prix'] or 0)}</td></tr>"
        for p in config["composants"]
    )
    fps = "".join(
        f"<li><span>{escape(f['jeu'])}</span><b>{escape(str(f['fps']))} FPS</b></li>" for f in config.get("fps", [])
    )
    others = "".join(
        f"<a class=\"guide-other\" href=\"/guides/{SLUG_BY_PROFILE[c['id']]}\">"
        f"<span>{escape(c['onglet'])} · {escape(c['titre'])}</span><b>{_euros(c['total'], False)}</b></a>"
        for c in all_configs if c["id"] != config["id"]
    )
    reasons = "".join(f"<li>{r}</li>" for r in _reasons(config, catalog_by_id))
    build_json = escape(json.dumps(config["composants_json"]))

    body = f"""
<main class="legal-page guide-page">
  <a href="/guides" class="legal-back">← Tous les guides d'achat</a>
  <p class="guide-kicker">{escape(config['usage'])} · configuration de {mois}</p>
  <h1>{escape(title.split(' — ')[0].split(' (')[0])}</h1>
  <div class="legal-updated">Mis à jour le {date_long} · prix relevés chaque jour</div>

  <p class="guide-lede">
    Pour {escape(config['usage'].lower())}, cette configuration associe le <strong>{escape(cpu['nom'] if cpu else '')}</strong>
    et la <strong>{escape(gpu['nom'] if gpu else '')}</strong>, pour un total de <strong>{total}</strong>.
    Toutes les pièces sont en stock et compatibles entre elles.
  </p>

  <div class="guide-grid">
    <section class="guide-card" aria-labelledby="guide-parts">
      <h2 id="guide-parts">Les pièces</h2>
      <table class="guide-table">
        <tbody>{rows}</tbody>
        <tfoot><tr><th scope="row">Total</th><td></td><td class="guide-price">{_euros(config['total'])}</td></tr></tfoot>
      </table>
      <button type="button" class="btn btn-primary guide-cta" data-build="{build_json}">Personnaliser cette config</button>
    </section>

    <section class="guide-card" aria-labelledby="guide-fps">
      <h2 id="guide-fps">FPS estimés en {res}</h2>
      <p class="guide-note">Qualité {escape(config['qualite'])}, d'après des tests publiés (TechPowerUp, TechSpot).</p>
      <ul class="guide-fps">{fps}</ul>
      <a class="btn-link" href="/estimer-fps">Estimer d'autres jeux <i class="ph ph-arrow-right" aria-hidden="true"></i></a>
    </section>
  </div>

  <h2>Pourquoi ces choix</h2>
  <ul class="guide-reasons">{reasons}</ul>

  <h2>Les autres budgets</h2>
  <div class="guide-others">{others}</div>

  <p class="guide-note guide-disclaimer">
    Prix indicatifs relevés chez les marchands, susceptibles de changer. Les liens vers les marchands
    peuvent être affiliés : PC Radar touche alors une commission, sans surcoût pour vous.
  </p>
</main>
"""
    return _page(title, description, canonical, body)


def render_index(all_configs):
    date_long, mois = _today()
    cards = "".join(
        f"<a class=\"guide-other\" href=\"/guides/{SLUG_BY_PROFILE[c['id']]}\">"
        f"<span>{escape(c['onglet'])} · {escape(c['titre'])} — {escape(c['usage'])}</span>"
        f"<b>{_euros(c['total'], False)}</b></a>"
        for c in all_configs
    )
    body = f"""
<main class="legal-page guide-page">
  <a href="/" class="legal-back">← Retour à l'accueil</a>
  <p class="guide-kicker">Guides d'achat · {mois}</p>
  <h1>Quel PC gamer acheter selon ton budget</h1>
  <div class="legal-updated">Mis à jour le {date_long} · prix relevés chaque jour</div>
  <p class="guide-lede">
    Quatre configurations complètes, recalculées chaque jour à partir des composants en stock :
    la combinaison processeur + carte graphique qui donne le plus de FPS pour le budget, et des
    pièces compatibles autour.
  </p>
  <div class="guide-others">{cards}</div>
</main>
"""
    return _page(
        f"Guides d'achat PC gamer ({mois}) — PC Radar",
        "Quel PC gamer acheter en 1080p, 1440p ou 4K : configurations complètes, compatibles et mises à jour chaque jour.",
        "https://pcradar.tech/guides",
        body,
    )
