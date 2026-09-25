"""
Une page par composant (/composant/{id}-{nom}), rendue côté serveur pour que
les moteurs de recherche lisent tout sans JavaScript : prix, où l'acheter,
caractéristiques, historique de prix, FPS estimés (cartes graphiques et
processeurs), pièces compatibles et alternatives. Tout vient du catalogue.

Plus des pages de catégorie (/composants, /composants/{categorie}) qui listent
tout le catalogue, pour que chaque fiche soit atteignable par des liens.
"""
import json
import re
import unicodedata
from html import escape
from urllib.parse import quote, urlparse, parse_qsl, urlencode, urlunparse

from guides import _euros, _page, _today

CATEGORY_SLUGS = {
    "CPU": "processeurs", "GPU": "cartes-graphiques", "Carte mère": "cartes-meres",
    "RAM": "memoire-ram", "Stockage": "stockage-ssd", "Alimentation": "alimentations",
    "Boîtier": "boitiers", "Refroidissement": "refroidissement",
}
CATEGORY_BY_SLUG = {v: k for k, v in CATEGORY_SLUGS.items()}
CATEGORY_NAMES = {
    "CPU": "Processeurs", "GPU": "Cartes graphiques", "Carte mère": "Cartes mères",
    "RAM": "Mémoire RAM", "Stockage": "Stockage (SSD)", "Alimentation": "Alimentations",
    "Boîtier": "Boîtiers", "Refroidissement": "Refroidissement",
}
CATEGORY_SINGULAR = {
    "CPU": "processeur", "GPU": "carte graphique", "Carte mère": "carte mère", "RAM": "mémoire RAM",
    "Stockage": "SSD", "Alimentation": "alimentation", "Boîtier": "boîtier", "Refroidissement": "refroidissement",
}
SPEC_LABELS = {
    "socket": "Socket", "tdp": "Consommation (TDP)", "wattage": "Puissance", "format": "Format",
    "ram_type": "Type de mémoire", "type": "Type", "m2_slots": "Emplacements M.2", "sata_ports": "Ports SATA",
    "formats_supportes": "Formats de carte mère", "gpu_max_length_mm": "Longueur max. de carte graphique",
    "cpu_cooler_max_height_mm": "Hauteur max. de ventirad", "longueur_mm": "Longueur",
    "hauteur_mm": "Hauteur", "sockets_supportes": "Sockets supportés", "couleur": "Couleur",
    "coeurs": "Cœurs", "threads": "Threads", "frequence_base_ghz": "Fréquence de base",
    "frequence_boost_ghz": "Fréquence boost", "cache_l3_mo": "Cache L3", "memoire": "Mémoire supportée",
    "igpu": "Graphique intégré",
}
SPEC_UNITS = {"tdp": " W", "wattage": " W", "gpu_max_length_mm": " mm", "cpu_cooler_max_height_mm": " mm",
              "longueur_mm": " mm", "hauteur_mm": " mm", "frequence_base_ghz": " GHz",
              "frequence_boost_ghz": " GHz", "cache_l3_mo": " Mo"}
FPS_GAMES = ["Cyberpunk 2077", "Fortnite", "Counter-Strike 2", "Black Myth Wukong", "Baldur's Gate 3"]


def slugify(text):
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:80].rstrip("-") or "composant"


def page_url(component):
    return f"/composant/{component['id']}-{slugify(component['nom'])}"


def category_url(categorie):
    return f"/composants/{CATEGORY_SLUGS[categorie]}" if categorie in CATEGORY_SLUGS else "/composants"


def affiliate_url(url, vendeur, amazon_tag, awin_publisher, awin_merchants):
    """Même règle que static/affiliate-tag.js, côté serveur."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    if "amazon." in (parsed.hostname or ""):
        if not amazon_tag:
            return url
        query = dict(parse_qsl(parsed.query))
        query["tag"] = amazon_tag
        return urlunparse(parsed._replace(query=urlencode(query)))
    merchant = awin_merchants.get(vendeur) if vendeur else None
    if not merchant or not awin_publisher:
        return url
    return (f"https://www.awin1.com/cread.php?awinmid={quote(str(merchant))}"
            f"&awinaffid={quote(str(awin_publisher))}&ued={quote(url, safe='')}")


def _price(c):
    return float(c.get("prix_indicatif") or 0)


def _spec(c, key):
    return (c.get("specs") or {}).get(key)


def _fmt_spec(key, value):
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, float):
        value = f"{value:g}".replace(".", ",")   # 4.7 -> « 4,7 » à la française
    return f"{value}{SPEC_UNITS.get(key, '')}"


def _link_list(items, extra=None):
    if not items:
        return ""
    rows = "".join(
        f"<a class=\"guide-other\" href=\"{escape(page_url(c))}\"><span>{escape(c['nom'])}"
        f"{(' — ' + escape(extra(c))) if extra else ''}</span><b>{_euros(_price(c))}</b></a>"
        for c in items
    )
    return f"<div class=\"guide-others\">{rows}</div>"


def _compatible_sections(c, by_cat):
    """Pièces compatibles, déduites des mêmes règles que le contrôle de compatibilité."""
    cat = c["categorie"]
    in_stock = lambda items: [x for x in items if x.get("en_stock") and _price(x) > 0]
    sections = []
    if cat == "CPU" and _spec(c, "socket"):
        mbs = sorted(in_stock(x for x in by_cat.get("Carte mère", []) if _spec(x, "socket") == _spec(c, "socket")), key=_price)
        if mbs:
            sections.append((f"Cartes mères compatibles (socket {escape(str(_spec(c, 'socket')))})",
                             f"{len(mbs)} cartes mères compatibles en stock, les moins chères :", _link_list(mbs[:6])))
    elif cat == "Carte mère" and _spec(c, "socket"):
        cpus = sorted(in_stock(x for x in by_cat.get("CPU", []) if _spec(x, "socket") == _spec(c, "socket")),
                      key=lambda x: -(x.get("perf_index") or 0))
        if cpus:
            sections.append(("Processeurs compatibles", f"{len(cpus)} processeurs compatibles en stock, les plus performants :",
                             _link_list(cpus[:6])))
        if _spec(c, "ram_type"):
            rams = sorted(in_stock(x for x in by_cat.get("RAM", []) if _spec(x, "type") == _spec(c, "ram_type")), key=_price)
            if rams:
                sections.append((f"Mémoire compatible ({escape(str(_spec(c, 'ram_type')))})",
                                 "Les barrettes compatibles les moins chères :", _link_list(rams[:4])))
    elif cat == "RAM" and _spec(c, "type"):
        mbs = sorted(in_stock(x for x in by_cat.get("Carte mère", []) if _spec(x, "ram_type") == _spec(c, "type")), key=_price)
        if mbs:
            sections.append((f"Cartes mères compatibles ({escape(str(_spec(c, 'type')))})",
                             f"{len(mbs)} cartes mères {escape(str(_spec(c, 'type')))} en stock, les moins chères :", _link_list(mbs[:6])))
    elif cat == "GPU" and isinstance(_spec(c, "tdp"), (int, float)):
        need = int(_spec(c, "tdp")) + 150 + 150
        need = int(-(-need // 50) * 50)
        psus = sorted(in_stock(x for x in by_cat.get("Alimentation", [])
                               if isinstance(_spec(x, "wattage"), (int, float)) and _spec(x, "wattage") >= need), key=_price)
        text = (f"Avec un processeur classique, prévoyez une alimentation d'au moins <strong>{need} W</strong> "
                f"(carte graphique {int(_spec(c, 'tdp'))} W + processeur + marge).")
        sections.append(("Alimentation recommandée", text, _link_list(psus[:4])))
    elif cat == "Alimentation" and isinstance(_spec(c, "wattage"), (int, float)):
        budget = _spec(c, "wattage") - 300
        gpus = sorted(in_stock(x for x in by_cat.get("GPU", [])
                               if isinstance(_spec(x, "tdp"), (int, float)) and _spec(x, "tdp") <= budget),
                      key=lambda x: -(x.get("perf_index") or 0))
        if gpus:
            sections.append(("Cartes graphiques supportées",
                             f"Avec {int(_spec(c, 'wattage'))} W, les cartes graphiques les plus puissantes compatibles "
                             "(processeur classique inclus) :", _link_list(gpus[:6])))
    return sections


def _alternatives(c, by_cat):
    price = _price(c)
    if price <= 0:
        return []
    pool = [x for x in by_cat.get(c["categorie"], [])
            if x["id"] != c["id"] and x.get("en_stock") and 0.75 * price <= _price(x) <= 1.25 * price
            and x["nom"].lower() != c["nom"].lower()]
    return sorted(pool, key=lambda x: abs(_price(x) - price))[:5]


def render_component(c, catalog, fps_block, price_stats, affiliate):
    by_cat = {}
    for x in catalog:
        by_cat.setdefault(x["categorie"], []).append(x)
    date_long, mois = _today()
    cat = c["categorie"]
    nom = c["nom"]
    price = _price(c)
    title = f"{nom} : prix, caractéristiques et compatibilité ({mois}) — PC Radar"
    description = (
        f"{nom} ({CATEGORY_SINGULAR.get(cat, cat)}) à {_euros(price)} : caractéristiques, historique du prix, "
        f"{'FPS estimés, ' if fps_block else ''}pièces compatibles et alternatives. Prix mis à jour chaque jour."
    )
    canonical = f"https://pcradar.tech{page_url(c)}"

    image = (f"<div class=\"comp-image\"><img src=\"{escape(c['image_url'])}?w=480\" alt=\"{escape(nom)}\" "
             f"width=\"240\" height=\"240\" loading=\"eager\"></div>") if c.get("image_url") else ""
    stock = ("<span class=\"comp-badge\">En stock</span>" if c.get("en_stock")
             else "<span class=\"comp-badge is-out\">Actuellement indisponible</span>")

    offers = sorted([p for p in (c.get("prix_marche") or []) if p.get("prix") and p.get("lien")], key=lambda p: p["prix"])
    if not offers and c.get("asin") and price:
        offers = [{"vendeur": "Amazon", "prix": price, "lien": f"https://www.amazon.fr/dp/{c['asin']}"}]
    offers_html = "".join(
        f"<li><span>{escape(str(p.get('vendeur') or 'Marchand'))}</span><b>{_euros(float(p['prix']))}</b>"
        f"<a href=\"{escape(affiliate(p['lien'], p.get('vendeur')))}\" target=\"_blank\" rel=\"noopener noreferrer sponsored\">"
        f"Voir l'offre ↗</a></li>" for p in offers[:6]
    ) or "<li><span>Aucune offre relevée pour le moment.</span></li>"

    specs = c.get("specs") or {}
    specs_rows = "".join(
        f"<tr><th scope=\"row\">{escape(SPEC_LABELS.get(k, k))}</th><td>{escape(_fmt_spec(k, v))}</td></tr>"
        for k, v in specs.items() if v not in (None, "", [])
    ) or "<tr><td>Aucune caractéristique enregistrée.</td></tr>"

    history = ""
    if price_stats and price_stats.get("n"):
        history = (f"<p class=\"guide-note\">Plus bas prix relevé : <strong>{_euros(price_stats['min'])}</strong>"
                   f" · {price_stats['n']} relevé{'s' if price_stats['n'] > 1 else ''} depuis le {escape(price_stats['depuis'])}.</p>")
    history += f"<div data-price-history=\"{c['id']}\"></div>"

    fps_html = ""
    if fps_block:
        rows = "".join(
            f"<tr><th scope=\"row\">{escape(r['jeu'])}</th>" + "".join(
                f"<td>{escape(str(r['resolutions'][res]['fps']))}</td>" for res in ("1080p", "1440p", "4k")
            ) + "</tr>" for r in fps_block["resultats"] if r.get("couvert")
        )
        fps_html = f"""
  <h2>FPS estimés</h2>
  <p class="guide-note">{escape(fps_block['contexte'])} Qualité Ultra, d'après des tests publiés (TechPowerUp, TechSpot).</p>
  <div class="comp-table-wrap"><table class="guide-table comp-fps">
    <thead><tr><th></th><th>1080p</th><th>1440p</th><th>4K</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
  <a class="btn-link" href="/estimer-fps">Estimer d'autres jeux <i class="ph ph-arrow-right" aria-hidden="true"></i></a>"""

    compat_html = "".join(
        f"<h2>{title_}</h2><p class=\"guide-note\">{text}</p>{links}" for title_, text, links in _compatible_sections(c, by_cat)
    )
    alts = _alternatives(c, by_cat)
    alts_html = (f"<h2>Alternatives à prix proche</h2>{_link_list(alts)}" if alts else "")
    build_json = escape(json.dumps({cat: c["id"]}))

    body = f"""
<main class="legal-page guide-page comp-page">
  <a href="{escape(category_url(cat))}" class="legal-back">← {escape(CATEGORY_NAMES.get(cat, cat))}</a>
  <div class="comp-hero">
    {image}
    <div class="comp-head">
      <p class="guide-kicker">{escape(CATEGORY_SINGULAR.get(cat, cat).capitalize())} · {stock}</p>
      <h1>{escape(nom)}</h1>
      <p class="comp-price">{_euros(price) if price else 'Prix non disponible'}</p>
      <div class="legal-updated">Prix mis à jour le {date_long}</div>
      <button type="button" class="btn btn-primary guide-cta" data-build="{build_json}">Ajouter au configurateur</button>
    </div>
  </div>

  <div class="guide-grid">
    <section class="guide-card" aria-labelledby="comp-offers">
      <h2 id="comp-offers">Où l'acheter</h2>
      <ul class="guide-fps comp-offers">{offers_html}</ul>
      {history}
    </section>
    <section class="guide-card" aria-labelledby="comp-specs">
      <h2 id="comp-specs">Caractéristiques</h2>
      <table class="guide-table"><tbody>{specs_rows}</tbody></table>
    </section>
  </div>
  {fps_html}
  {compat_html}
  {alts_html}
  <p class="guide-note guide-disclaimer">
    Prix indicatifs relevés chez les marchands, susceptibles de changer. Les liens vers les marchands
    peuvent être affiliés : PC Radar touche alors une commission, sans surcoût pour vous.
  </p>
</main>
"""
    return _page(title, description, canonical, body)


def render_category(categorie, items):
    date_long, mois = _today()
    items = sorted(items, key=lambda c: (not c.get("en_stock"), c["nom"].lower()))
    rows = "".join(
        f"<a class=\"guide-other\" href=\"{escape(page_url(c))}\"><span>{escape(c['nom'])}"
        f"{'' if c.get('en_stock') else ' <em>(indisponible)</em>'}</span><b>{_euros(_price(c)) if _price(c) else '—'}</b></a>"
        for c in items
    )
    name = CATEGORY_NAMES.get(categorie, categorie)
    body = f"""
<main class="legal-page guide-page">
  <a href="/composants" class="legal-back">← Toutes les catégories</a>
  <p class="guide-kicker">Catalogue · {mois}</p>
  <h1>{escape(name)} : prix et caractéristiques</h1>
  <div class="legal-updated">{len(items)} références · prix mis à jour le {date_long}</div>
  <div class="guide-others">{rows}</div>
</main>
"""
    return _page(f"{name} : prix et comparatif ({mois}) — PC Radar",
                 f"{len(items)} {name.lower()} avec leur prix du jour, leurs caractéristiques et leur compatibilité.",
                 f"https://pcradar.tech{category_url(categorie)}", body)


def render_index(catalog):
    date_long, mois = _today()
    counts = {}
    for c in catalog:
        counts[c["categorie"]] = counts.get(c["categorie"], 0) + 1
    rows = "".join(
        f"<a class=\"guide-other\" href=\"{escape(category_url(cat))}\"><span>{escape(CATEGORY_NAMES[cat])}</span>"
        f"<b>{counts.get(cat, 0)}</b></a>" for cat in CATEGORY_SLUGS if counts.get(cat)
    )
    body = f"""
<main class="legal-page guide-page">
  <a href="/" class="legal-back">← Retour à l'accueil</a>
  <p class="guide-kicker">Catalogue · {mois}</p>
  <h1>Tous les composants PC</h1>
  <div class="legal-updated">{len(catalog)} références · prix mis à jour le {date_long}</div>
  <div class="guide-others">{rows}</div>
</main>
"""
    return _page(f"Catalogue de composants PC ({mois}) — PC Radar",
                 "Processeurs, cartes graphiques, cartes mères, RAM, SSD, alimentations, boîtiers : prix du jour et compatibilité.",
                 "https://pcradar.tech/composants", body)
