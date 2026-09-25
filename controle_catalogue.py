"""
Contrôle qualité du catalogue, recalculé à chaque appel à partir du
catalogue en mémoire (get_catalog) : rien à stocker, toujours à jour.

- prix_suspects : une annonce bien plus chère (ou bien moins chère) que les
  autres annonces du MÊME produit dans la MÊME version (même capacité,
  fréquence, couleur...), ou une carte graphique hors de proportion avec
  les autres cartes de la même puce. C'est ainsi qu'on repère une annonce
  de vendeur tiers à prix délirant, ou une annonce qui ne vend pas ce
  qu'elle dit (barrette seule au prix d'un kit, lot...).
- annonces_isolees : produit sans variante qui ressemble fort à un autre
  produit de la même marque (doublon que les règles de variantes.py n'ont
  pas vu) — à rattacher dans variantes.RATTACHER si c'est bien le même.
- fiches_incompletes : champs utilisés par le contrôle de compatibilité
  manquants, prix nul alors que le produit est en stock, image absente.
"""
import re
import statistics

import variantes
from schema import REQUIRED_FIELDS

# Écart à partir duquel un prix est signalé, par rapport à la médiane des
# autres annonces comparables (et au moins ECART_MIN_EUROS d'écart absolu,
# pour ne pas signaler 12 € contre 7 € sur un ventilateur).
RATIO_TROP_CHER = 1.6
RATIO_TROP_BAS = 0.5
ECART_MIN_EUROS = 25
# Cartes graphiques : comparées à toutes les cartes de la même puce et même
# mémoire, toutes marques confondues (les modèles haut de gamme coûtent
# normalement 30-50 % de plus que l'entrée de gamme, d'où un seuil plus large).
RATIO_GPU_PUCE = 2.0


def _prix(c):
    try:
        return float(c.get("prix_indicatif") or 0)
    except (TypeError, ValueError):
        return 0.0


def _vendable(c):
    return c.get("en_stock") is not False and _prix(c) > 0


def _version(c):
    """Même produit, même version : le libellé de variante sans le « Offre n »."""
    return re.sub(r"(\s*·\s*)?Offre \d+$", "", c.get("variante") or "").strip()


def _signal(c, reference, n, motif):
    prix = _prix(c)
    return {
        "id": c["id"], "nom": c["nom"], "categorie": c["categorie"], "prix": prix,
        "reference": round(reference, 2), "ratio": round(prix / reference, 2) if reference else None,
        "comparees": n, "motif": motif, "page": c.get("page"),
    }


def prix_suspects(catalog):
    signales = {}
    # 1. Même produit, même version.
    groupes = {}
    for c in catalog:
        if _vendable(c) and (c.get("nb_variantes") or 1) > 1:
            groupes.setdefault((c.get("groupe_id"), _version(c)), []).append(c)
    for membres in groupes.values():
        if len(membres) < 2:
            continue
        for c in membres:
            autres = [_prix(x) for x in membres if x["id"] != c["id"]]
            ref = statistics.median(autres)
            prix = _prix(c)
            if prix > ref * RATIO_TROP_CHER and prix - ref >= ECART_MIN_EUROS:
                signales[c["id"]] = _signal(c, ref, len(autres), "bien plus cher que les autres annonces du même produit")
            # « Trop bas » seulement face à au moins 2 autres annonces : face à une
            # seule, c'est l'autre (la plus chère) qui est déjà signalée.
            elif len(autres) >= 2 and prix < ref * RATIO_TROP_BAS and ref - prix >= ECART_MIN_EUROS:
                signales[c["id"]] = _signal(c, ref, len(autres), "bien moins cher que les autres annonces du même produit (autre article ?)")
    # 2. Cartes graphiques : même puce, même mémoire, toutes marques.
    puces = {}
    for c in catalog:
        specs = c.get("specs") or {}
        if c["categorie"] == "GPU" and _vendable(c) and specs.get("puce"):
            puces.setdefault((specs["puce"], specs.get("vram_go")), []).append(c)
    for membres in puces.values():
        if len(membres) < 4:
            continue
        for c in membres:
            if c["id"] in signales:
                continue
            autres = [_prix(x) for x in membres if x["id"] != c["id"]]
            ref = statistics.median(autres)
            if _prix(c) > ref * RATIO_GPU_PUCE and _prix(c) - ref >= ECART_MIN_EUROS:
                signales[c["id"]] = _signal(c, ref, len(autres), "bien plus cher que les autres cartes de la même puce")
    return sorted(signales.values(), key=lambda s: -(s["ratio"] or 0))


# Mots qui ne changent pas le produit : si deux noms ne diffèrent QUE par
# ceux-là, c'est très probablement le même article sous deux annonces.
MOTS_SANS_IMPORTANCE = set(variantes.COULEURS) | {
    "oc", "gaming", "edition", "ventirad", "cpu", "air", "cooler", "pwm", "argb", "rgb",
    "v2", "v3", "boite", "noire", "processeur", "carte", "graphique", "memoire", "ram",
}


def _mots_cle(c):
    mots = [t for t in variantes._mots(c["nom"]) if t not in variantes.MOTS_VIDES]
    # Les unités (« 16go », « 850w ») partent, mais pas les numéros de modèle (5060, B850).
    return {t for t in mots if not re.fullmatch(r"\d{1,3}([.,]\d+)?(go|gb|g|to|tb|mo)|\d+(mhz|mt|w)", t)}


def annonces_isolees(catalog, seuil=0.5):
    """Paires (produit seul, produit proche) de même catégorie et même marque."""
    produits = {}
    for c in catalog:
        produits.setdefault(c.get("groupe_id", c["id"]), c)
    reps = list(produits.values())
    par_cle = {}
    for c in reps:
        par_cle.setdefault((c["categorie"], c.get("marque") or variantes.marque(c["nom"])), []).append(c)
    paires = []
    for membres in par_cle.values():
        mots = {c["id"]: _mots_cle(c) for c in membres}
        for c in membres:
            if (c.get("nb_variantes") or 1) > 1:
                continue
            a = mots[c["id"]]
            if len(a) < 2:
                continue
            meilleur, score = None, 0
            for o in membres:
                if o["id"] == c["id"]:
                    continue
                b = mots[o["id"]]
                # Seuls des mots sans importance diffèrent (couleur, « OC », « Gaming »...) :
                # un numéro de modèle, « WiFi », « Ti » ou « Slim » en plus = autre produit.
                if not (a ^ b) <= MOTS_SANS_IMPORTANCE:
                    continue
                s = len(a & b) / len(a | b)
                if s > score:
                    meilleur, score = o, s
            if meilleur and score >= seuil:
                paires.append({
                    "id": c["id"], "nom": c["nom"], "categorie": c["categorie"], "prix": _prix(c),
                    "proche_id": meilleur["id"], "proche_nom": meilleur["nom"],
                    "proche_variantes": meilleur.get("nb_variantes") or 1, "score": round(score, 2),
                })
    # Chaque paire une seule fois (A~B et B~A).
    vues, uniques = set(), []
    for p in sorted(paires, key=lambda p: -p["score"]):
        cle = frozenset((p["id"], p["proche_id"]))
        if cle not in vues:
            vues.add(cle)
            uniques.append(p)
    return uniques


def fiches_incompletes(catalog):
    fiches = []
    for c in catalog:
        manques = []
        requis = REQUIRED_FIELDS.get(c["categorie"], {})
        specs = c.get("specs") or {}
        for champ in requis:
            # Un watercooling n'a pas de hauteur de ventirad, un ventilateur de boîtier pas de socket.
            if c["categorie"] == "Refroidissement" and champ in ("hauteur_mm", "sockets_supportes") \
                    and specs.get("type_refroidissement") in ("Watercooling AIO", "Ventilateur de boîtier"):
                if not (champ == "sockets_supportes" and specs.get("type_refroidissement") == "Watercooling AIO"):
                    continue
            if specs.get(champ) in (None, "", []):
                manques.append(champ)
        if c.get("en_stock") is not False and _prix(c) <= 0:
            manques.append("prix")
        if not c.get("image_url"):
            manques.append("image")
        if manques:
            fiches.append({"id": c["id"], "nom": c["nom"], "categorie": c["categorie"], "manques": manques})
    return sorted(fiches, key=lambda f: (f["categorie"], f["nom"]))


def rapport(catalog):
    return {
        "prix_suspects": prix_suspects(catalog),
        "annonces_isolees": annonces_isolees(catalog),
        "fiches_incompletes": fiches_incompletes(catalog),
    }
