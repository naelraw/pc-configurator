"""
Comparatifs « X vs Y » par modèle de puce (RTX 5070 vs RX 9070, Ryzen 7 9800X3D
vs Core i7-14700K...), rendus côté serveur. Les paires sont choisies
automatiquement parmi les modèles en stock : chaque modèle face à son
concurrent le plus proche en performance chez l'autre marque. Performances,
FPS et prix viennent des mêmes données que le reste du site.
"""
import re
from html import escape

import fps_data
from component_pages import FPS_GAMES, page_url, slugify
from guides import _euros, _page, _today

MAX_RATIO = 1.25  # écart de performance max pour qu'une paire soit un vrai duel


def _price(c):
    return float(c.get("prix_indicatif") or 0)


GPU_WORDS = {"arc": "Arc", "super": "Super", "ti": "Ti"}


def _gpu_label(card, vram, multi_vram):
    """"rtx 5070 ti" -> "RTX 5070 Ti", "arc b580" -> "Arc B580" ; mémoire ajoutée si plusieurs variantes."""
    label = " ".join(GPU_WORDS.get(w, w.upper()) for w in card.split())
    return f"{label} {vram} Go" if multi_vram else label


def _cpu_model(nom):
    """Nom commercial -> (modèle, indice) via les mêmes motifs que l'estimation FPS."""
    n = fps_data.normalize_cpu_name(nom)
    for pattern, value, _origin in fps_data.CPU_RELATIVE:
        m = re.search(pattern, n)
        if m:
            return m.group(0), value
    return None, None


def _cpu_label(model, names):
    text = " ".join(names).lower()
    if model.startswith(("i3", "i5", "i7", "i9")):
        return "Core " + model.upper().replace("I", "i", 1)
    if model.startswith("ultra"):
        parts = model.split()
        return "Core Ultra " + " ".join(p.upper() for p in parts[1:]) if len(parts) > 1 else "Core " + model.title()
    if model.startswith("ryzen"):
        return model.title()
    tier = re.search(r"ryzen\s*(\d)", text)
    return f"Ryzen {tier.group(1)} {model.upper()}" if tier else f"Ryzen {model.upper()}"


def _brand(kind, key):
    if kind == "GPU":
        return "nvidia" if key.startswith(("rtx", "gtx")) else "amd" if key.startswith("rx") else "intel"
    return "intel" if key.startswith(("i3", "i5", "i7", "i9", "ultra")) else "amd"


def models(catalog):
    """Modèles en stock : {clé: {kind, label, perf (1080p,1440p,4K), listings, best}}."""
    out = {}
    gpus = {}
    for c in catalog:
        if not (c.get("en_stock") and _price(c) > 0):
            continue
        if c["categorie"] == "GPU":
            card, rel, vram = fps_data.match_gpu_full(c["nom"])
            if card and rel:
                gpus.setdefault(card, set()).add(vram)
                out.setdefault(f"{card}|{vram}", {"kind": "GPU", "card": card, "vram": vram, "perf": rel, "listings": []})["listings"].append(c)
        elif c["categorie"] == "CPU":
            model, index = _cpu_model(c["nom"])
            if model:
                out.setdefault(model, {"kind": "CPU", "perf": (index, index, index), "listings": []})["listings"].append(c)
    for key, m in out.items():
        m["listings"].sort(key=_price)
        m["best"] = m["listings"][0]
        if m["kind"] == "GPU":
            m["label"] = _gpu_label(m["card"], m["vram"], len(gpus[m["card"]]) > 1)
        else:
            m["label"] = _cpu_label(key, [x["nom"] for x in m["listings"]])
        m["key"] = key
        m["slug"] = slugify(m["label"])
    return out


def pairs(catalog):
    """Chaque modèle face à son concurrent le plus proche (autre marque), sans doublon."""
    ms = models(catalog)
    result, seen, uses = [], set(), {}
    for kind, main_res in (("GPU", 1), ("CPU", 0)):
        pool = [m for m in ms.values() if m["kind"] == kind]
        for m in sorted(pool, key=lambda x: -x["perf"][main_res]):
            rivals = [o for o in pool if _brand(kind, o["key"]) != _brand(kind, m["key"])]
            if not rivals:
                continue
            rival = min(rivals, key=lambda o: abs(o["perf"][main_res] / m["perf"][main_res] - 1))
            ratio = max(rival["perf"][main_res], m["perf"][main_res]) / min(rival["perf"][main_res], m["perf"][main_res])
            ident = frozenset((m["key"], rival["key"]))
            # Un modèle apparaît dans 2 duels au plus : au-delà, les pages se
            # ressemblent trop (mauvais pour le référencement, peu utile).
            if ratio > MAX_RATIO or ident in seen or uses.get(m["key"], 0) >= 2 or uses.get(rival["key"], 0) >= 2:
                continue
            seen.add(ident)
            uses[m["key"]] = uses.get(m["key"], 0) + 1
            uses[rival["key"]] = uses.get(rival["key"], 0) + 1
            # Ordre habituel des recherches : NVIDIA/Intel d'abord.
            a, b = (m, rival) if _brand(kind, m["key"]) in ("nvidia", "intel") else (rival, m)
            result.append({"kind": kind, "a": a, "b": b, "slug": f"{a['slug']}-vs-{b['slug']}", "main_res": main_res})
    return result


def _pct(x, y):
    return round((x / y - 1) * 100)


def render_pair(pair, all_pairs, fps_for, ref_partner):
    date_long, mois = _today()
    a, b, kind = pair["a"], pair["b"], pair["kind"]
    res_names = ("1080p", "1440p", "4K")
    main = pair["main_res"]
    what = "carte graphique" if kind == "GPU" else "processeur"
    pronoun = "laquelle" if kind == "GPU" else "lequel"
    faster, slower = (a, b) if a["perf"][main] >= b["perf"][main] else (b, a)
    gap = _pct(faster["perf"][main], slower["perf"][main])
    pa, pb = _price(a["best"]), _price(b["best"])
    value_a, value_b = a["perf"][main] / pa, b["perf"][main] / pb
    better_value = a if value_a >= value_b else b
    value_gap = _pct(max(value_a, value_b), min(value_a, value_b))

    if gap <= 2:
        verdict = f"Performances quasi identiques en {res_names[main]} : le prix fait la différence."
    else:
        verdict = f"<strong>{escape(faster['label'])}</strong> est environ <strong>{gap} % plus rapide</strong> en {res_names[main]}."
    verdict += (f" Meilleur rapport performance/prix : <strong>{escape(better_value['label'])}</strong>"
                + (f" ({value_gap} % de performance par euro en plus)." if value_gap >= 3 else " (de peu)."))

    perf_rows = ""
    if kind == "GPU":
        perf_rows = "".join(
            f"<tr><th scope=\"row\">{name}</th><td>{a['perf'][i]}</td><td>{b['perf'][i]}</td>"
            f"<td>{'+' if _pct(a['perf'][i], b['perf'][i]) > 0 else ''}{_pct(a['perf'][i], b['perf'][i])} %</td></tr>"
            for i, name in enumerate(res_names)
        )
        perf_html = f"""
  <h2>Performances relatives</h2>
  <p class="guide-note">Indice de performance (plus = mieux), issu de tests publiés sur de nombreux jeux.</p>
  <div class="comp-table-wrap"><table class="guide-table comp-fps">
    <thead><tr><th></th><th>{escape(a['label'])}</th><th>{escape(b['label'])}</th><th>Écart</th></tr></thead>
    <tbody>{perf_rows}</tbody></table></div>"""
    else:
        perf_html = f"""
  <h2>Performances en jeu</h2>
  <p class="guide-note">Indice de performance en jeu (plus = mieux) : {escape(a['label'])} {a['perf'][0]}, {escape(b['label'])} {b['perf'][0]}.</p>"""

    fps_a, fps_b = fps_for(a["best"], ref_partner), fps_for(b["best"], ref_partner)
    res_key = ("1080p", "1440p", "4k")[main]
    fps_rows = ""
    if fps_a and fps_b:
        by_game_b = {r["jeu"]: r for r in fps_b["resultats"] if r.get("couvert")}
        for r in fps_a["resultats"]:
            if r.get("couvert") and r["jeu"] in by_game_b:
                va, vb = r["resolutions"][res_key]["fps"], by_game_b[r["jeu"]]["resolutions"][res_key]["fps"]
                cls_a = " class=\"is-win\"" if va > vb else ""
                cls_b = " class=\"is-win\"" if vb > va else ""
                fps_rows += f"<tr><th scope=\"row\">{escape(r['jeu'])}</th><td{cls_a}>{va}</td><td{cls_b}>{vb}</td></tr>"
    fps_html = ""
    if fps_rows and ref_partner:
        context = (f"avec un {escape(ref_partner['nom'])}" if kind == "GPU"
                   else f"avec une {escape(ref_partner['nom'])} (la carte graphique ne limite pas)")
        fps_html = f"""
  <h2>FPS estimés en {res_names[main]}</h2>
  <p class="guide-note">Qualité Ultra, {context}, d'après des tests publiés (TechPowerUp, TechSpot).</p>
  <div class="comp-table-wrap"><table class="guide-table comp-fps">
    <thead><tr><th></th><th>{escape(a['label'])}</th><th>{escape(b['label'])}</th></tr></thead>
    <tbody>{fps_rows}</tbody></table></div>"""

    def side(m):
        tdp = (m["best"].get("specs") or {}).get("tdp")
        return f"""
    <section class="guide-card">
      <h2>{escape(m['label'])}</h2>
      <p class="comp-price">à partir de {_euros(_price(m['best']))}</p>
      <p class="guide-note">{len(m['listings'])} modèle{'s' if len(m['listings']) > 1 else ''} en stock{f" · consommation {tdp} W" if tdp else ""}{f" · {m['vram']} Go de mémoire vidéo" if kind == "GPU" else ""}</p>
      <a class="btn btn-secondary" href="{escape(page_url(m['best']))}">Voir le moins cher <i class="ph ph-arrow-right" aria-hidden="true"></i></a>
    </section>"""

    related = [p for p in all_pairs if p["slug"] != pair["slug"]
               and ({p["a"]["key"], p["b"]["key"]} & {a["key"], b["key"]} or p["kind"] == kind)][:6]
    related_html = "".join(
        f"<a class=\"guide-other\" href=\"/comparer/{escape(p['slug'])}\"><span>{escape(p['a']['label'])} vs {escape(p['b']['label'])}</span>"
        f"<b>→</b></a>" for p in related
    )
    title = f"{a['label']} vs {b['label']} : {pronoun} choisir ? ({mois}) — PC Radar"
    description = (f"{a['label']} ou {b['label']} ? Écart de performance, FPS estimés, prix du jour et rapport "
                   f"performance/prix pour choisir votre {what}.")
    body = f"""
<main class="legal-page guide-page">
  <a href="/comparer" class="legal-back">← Tous les comparatifs</a>
  <p class="guide-kicker">Comparatif {what} · {mois}</p>
  <h1>{escape(a['label'])} vs {escape(b['label'])} : {pronoun} choisir ?</h1>
  <div class="legal-updated">Mis à jour le {date_long} · prix relevés chaque jour</div>
  <p class="guide-lede">{verdict}</p>
  <div class="guide-grid">{side(a)}{side(b)}</div>
  {perf_html}
  {fps_html}
  <p><a class="btn-link" href="/comparateur">Comparer d'autres composants <i class="ph ph-arrow-right" aria-hidden="true"></i></a></p>
  {f'<h2>Autres comparatifs</h2><div class="guide-others">{related_html}</div>' if related_html else ''}
  <p class="guide-note guide-disclaimer">Prix indicatifs du modèle le moins cher en stock, susceptibles de changer.</p>
</main>
"""
    return _page(title, description, f"https://pcradar.tech/comparer/{pair['slug']}", body)


def render_index(all_pairs):
    date_long, mois = _today()
    blocks = ""
    for kind, name in (("GPU", "Cartes graphiques"), ("CPU", "Processeurs")):
        rows = "".join(
            f"<a class=\"guide-other\" href=\"/comparer/{escape(p['slug'])}\"><span>{escape(p['a']['label'])} vs {escape(p['b']['label'])}</span><b>→</b></a>"
            for p in all_pairs if p["kind"] == kind
        )
        if rows:
            blocks += f"<h2>{name}</h2><div class=\"guide-others\">{rows}</div>"
    body = f"""
<main class="legal-page guide-page">
  <a href="/" class="legal-back">← Retour à l'accueil</a>
  <p class="guide-kicker">Comparatifs · {mois}</p>
  <h1>Comparatifs cartes graphiques et processeurs</h1>
  <div class="legal-updated">Mis à jour le {date_long} · {len(all_pairs)} duels entre modèles en stock</div>
  {blocks}
</main>
"""
    return _page(f"Comparatifs cartes graphiques et processeurs ({mois}) — PC Radar",
                 "RTX contre Radeon, Ryzen contre Core : écarts de performance, FPS et rapport performance/prix.",
                 "https://pcradar.tech/comparer", body)
