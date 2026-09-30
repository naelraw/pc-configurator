"""
Corrections automatiques du catalogue, appliquées par main.py au moment du
contrôle (_controle_courant) et chaque jour :

- completer_fiches : remplit les champs manquants d'une fiche à partir de
  sources sûres, dans cet ordre : une autre annonce du même produit (même
  groupe_id), le même modèle ailleurs dans le catalogue (même processeur,
  même puce graphique), puis des règles tirées du nom (chipset B650 → AM5 et
  DDR5, « 850W » → 850 W...). Ce qui ne peut pas être deviné sûrement est
  renvoyé comme SUGGESTION, à valider par l'admin.
- rattachements_surs : paires d'annonces dont on est certain qu'elles sont le
  même produit (noms qui ne diffèrent que par des mots sans importance ET
  caractéristiques clés identiques) → rattachées automatiquement.
- prix_a_ignorer : prix « un peu trop cher » d'une offre qui n'est pas la
  moins chère de son produit (le site affiche déjà le prix le plus bas) →
  classés sans action.
"""
import json
import re
from collections import Counter

import variantes
from schema import REQUIRED_FIELDS


def _txt(nom):
    return variantes._ascii(nom or "")


# ---------------------------------------------------------------------------
# Lecture du nom
# ---------------------------------------------------------------------------

def modele_cpu(nom):
    return variantes._cle_cpu({"nom": nom})


PUCE_RE = re.compile(r"\b(rtx|gtx)\s*-?\s*(\d{4})\s*(ti\s*super|ti|super)?\b|\b(rx)\s*-?\s*(\d{4})\s*(xtx|xt|gre)?\b|\barc\s*([ab]\d{3})\b")


def puce_gpu(nom):
    n = _txt(nom)
    m = PUCE_RE.search(n)
    if not m:
        return None
    if m.group(1):
        suffixe = {"ti": " Ti", "super": " SUPER", "ti super": " Ti SUPER"}.get(re.sub(r"\s+", " ", m.group(3) or ""), "")
        return f"{m.group(1).upper()} {m.group(2)}{suffixe}"
    if m.group(4):
        return f"RX {m.group(5)}" + (f" {m.group(6).upper()}" if m.group(6) else "")
    return f"Arc {m.group(7).upper()}"


AMD_CHIPSETS = {"A320", "B350", "X370", "B450", "X470", "A520", "B550", "X570",
                "A620", "B650", "X670", "B840", "B850", "X870"}


def chipset(nom):
    m = re.search(r"\b([abxhz]\d{3})(e)?(m|i)?\b", _txt(nom))
    return (m.group(1).upper() + ("E" if m.group(2) else "")) if m else None


def socket_chipset(cs):
    base = cs.rstrip("E")
    if base in AMD_CHIPSETS:
        return "AM4" if base[1] in "345" else "AM5"
    n = int(base[1:])
    if 400 <= n < 600:
        return "LGA1200"
    if 600 <= n < 800:
        return "LGA1700"
    if 800 <= n < 900:
        return "LGA1851"
    return None


def socket_cpu(nom):
    n = _txt(nom)
    m = re.search(r"ryzen\s*(?:\d|threadripper)\s*(?:pro\s*)?(\d)\d{3}", n)
    if m:
        return "AM4" if m.group(1) in "12345" else "AM5"
    if re.search(r"core\s*ultra|ultra\s*[3579]\s*2\d\d", n):
        return "LGA1851"
    m = re.search(r"\bi[3579][- ]?(\d{2})\d{3}", n)
    if m:
        gen = int(m.group(1))
        return "LGA1700" if 12 <= gen <= 14 else "LGA1200" if gen in (10, 11) else None
    return None


def format_carte_mere(nom):
    n = _txt(nom)
    if re.search(r"\b(e-atx|eatx)\b", n):
        return "E-ATX"
    if re.search(r"\b(mini[- ]?itx|itx)\b|\b[abxhz]\d{3}e?-?i\b", n):
        return "Mini-ITX"
    if re.search(r"\b(micro[- ]?atx|matx|m-atx)\b|\b[abxhz]\d{3}e?m\b", n):
        return "Micro-ATX"
    return "ATX"


# ---------------------------------------------------------------------------
# Complétion des fiches
# ---------------------------------------------------------------------------

def _manquants(c):
    specs = c.get("specs") or {}
    requis = list(REQUIRED_FIELDS.get(c["categorie"], {}))
    type_ref = specs.get("type_refroidissement")
    if c["categorie"] == "Refroidissement" and type_ref in ("Watercooling AIO", "Ventilateur de boîtier"):
        requis = [r for r in requis if r != "hauteur_mm"]
        if type_ref == "Ventilateur de boîtier":
            requis = [r for r in requis if r != "sockets_supportes"]
    return [r for r in requis if specs.get(r) in (None, "", [])]


def _valeur_majoritaire(valeurs):
    valeurs = [v for v in valeurs if v not in (None, "", [])]
    if not valeurs:
        return None
    (v, n), = Counter(json.dumps(x, sort_keys=True) for x in valeurs).most_common(1)
    # Seulement si les sources sont d'accord (au moins 2/3).
    return json.loads(v) if n >= max(1, round(len(valeurs) * 2 / 3)) else None


VARIABLES_PAR_VERSION = {"wattage", "longueur_mm", "sockets_supportes", "formats_supportes"}


def deviner(c, catalog):
    """
    Pour une fiche, renvoie ({champ: (valeur, source)} sûrs, {champ: (valeur, source)} suggérés).
    """
    manques = _manquants(c)
    if not manques:
        return {}, {}
    cat, nom, specs = c["categorie"], c["nom"], c.get("specs") or {}
    sur, suggere = {}, {}
    memes_cat = [x for x in catalog if x["categorie"] == cat and x["id"] != c["id"]]

    def depuis(groupe, source, cible=sur, champs=None):
        for champ in (manques if champs is None else champs):
            if champ in sur:
                continue
            v = _valeur_majoritaire([(x.get("specs") or {}).get(champ) for x in groupe])
            if v is not None:
                cible[champ] = (v, source)

    # 1. Même produit (autres annonces du groupe), seulement pour les champs
    # identiques d'une version à l'autre : la puissance d'une alim (850/1000 W),
    # la longueur d'une carte graphique, les sockets d'un ventirad ou les formats
    # d'un boîtier changent entre versions d'un même produit (mesuré : 60 à 80 %
    # de justesse seulement) → proposés en suggestion, jamais appliqués seuls.
    gid = c.get("groupe_id")
    if gid is not None:
        stables = [m for m in manques if m not in VARIABLES_PAR_VERSION]
        groupe = [x for x in memes_cat if x.get("groupe_id") == gid]
        if stables:
            depuis(groupe, "autre annonce du même produit", champs=stables)
        variables = [m for m in manques if m in VARIABLES_PAR_VERSION]
        if variables:
            depuis(groupe, "autre version du même produit (à vérifier)", cible=suggere, champs=variables)

    # 2. Même modèle ailleurs dans le catalogue.
    if cat == "CPU":
        mod = modele_cpu(nom)
        if mod:
            depuis([x for x in memes_cat if modele_cpu(x["nom"]) == mod], f"même processeur ({mod})")
    elif cat == "GPU":
        puce = specs.get("puce") or puce_gpu(nom)
        if puce:
            # Même puce ET même mémoire : une RTX 3050 6 Go consomme 70 W, la 8 Go 130 W.
            vram = specs.get("vram_go")
            memes = [x for x in memes_cat if ((x.get("specs") or {}).get("puce") or "").lower() == puce.lower()
                     and (vram is None or (x.get("specs") or {}).get("vram_go") in (None, vram))]
            # La consommation dépend de la puce ; la longueur, du modèle de carte (pas devinable).
            depuis(memes, f"même puce ({puce})", champs=[m for m in manques if m != "longueur_mm"])

    # 3. Règles tirées du nom.
    if cat == "CPU" and "socket" in manques and "socket" not in sur:
        s = socket_cpu(nom)
        if s:
            sur["socket"] = (s, "série du processeur")
    elif cat == "Carte mère":
        cs = chipset(nom)
        if cs:
            s = socket_chipset(cs)
            if s and "socket" in manques and "socket" not in sur:
                sur["socket"] = (s, f"chipset {cs}")
            if "ram_type" in manques and "ram_type" not in sur:
                n = _txt(nom)
                if re.search(r"\bddr4\b|\bd4\b", n):
                    sur["ram_type"] = ("DDR4", "nom (DDR4)")
                elif re.search(r"\bddr5\b|\bd5\b", n) or s in ("AM5", "LGA1851"):
                    sur["ram_type"] = ("DDR5", f"chipset {cs}" if s in ("AM5", "LGA1851") else "nom (DDR5)")
                elif s in ("AM4", "LGA1200"):
                    sur["ram_type"] = ("DDR4", f"chipset {cs}")
        if "format" in manques and "format" not in sur:
            sur["format"] = (format_carte_mere(nom), "nom de la carte")
    elif cat == "RAM" and "type" in manques and "type" not in sur:
        m = re.search(r"\bddr([45])\b", _txt(nom))
        if m:
            sur["type"] = (f"DDR{m.group(1)}", "nom")
    elif cat == "Stockage" and "type" in manques and "type" not in sur:
        n = _txt(nom)
        if re.search(r"nvme|m\.2|pcie|gen\s*[345]", n):
            sur["type"] = ("NVMe", "nom")
        elif re.search(r"\bsata\b|2[,.]5", n):
            sur["type"] = ("SATA", "nom")
    elif cat == "Alimentation" and "wattage" in manques and "wattage" not in sur:
        m = re.search(r"\b(\d{3,4})\s*w\b", _txt(nom))
        if m and 200 <= int(m.group(1)) <= 2000:
            sur["wattage"] = (int(m.group(1)), "nom")
    elif cat == "GPU" and "tdp" not in sur and "tdp" in manques:
        pass  # sans autre carte de la même puce au catalogue : à compléter à la main

    # 4. Suggestions (à valider) : produit le plus proche par le nom, même marque.
    reste = [m for m in manques if m not in sur]
    if reste:
        mots = set(variantes._mots(nom)) - variantes.MOTS_VIDES
        marque = variantes.marque(nom)
        meilleur, score = None, 0
        for x in memes_cat:
            if variantes.marque(x["nom"]) != marque:
                continue
            autres = set(variantes._mots(x["nom"])) - variantes.MOTS_VIDES
            s = len(mots & autres) / max(1, len(mots | autres))
            if s > score:
                meilleur, score = x, s
        if meilleur and score >= 0.5:
            for champ in reste:
                v = (meilleur.get("specs") or {}).get(champ)
                if v not in (None, "", []) and champ not in suggere:
                    suggere[champ] = (v, f"produit proche : {meilleur['nom']}")
    return sur, {k: v for k, v in suggere.items() if k not in sur}


def completer_fiches(catalog):
    """[(composant, {champ: (valeur, source)} sûrs, suggestions)] pour les fiches incomplètes."""
    resultat = []
    for c in catalog:
        if not _manquants(c):
            continue
        sur, suggere = deviner(c, catalog)
        if sur or suggere:
            resultat.append((c, sur, suggere))
    return resultat


# ---------------------------------------------------------------------------
# Rattachements sûrs
# ---------------------------------------------------------------------------

# Caractéristiques qui doivent être identiques (et connues) pour affirmer
# que deux annonces sont le même produit.
CLES_IDENTITE = {
    "CPU": ("socket",),
    "GPU": ("puce", "vram_go"),
    "Carte mère": ("socket", "format"),
    "RAM": ("type", "capacite_go"),
    "Stockage": ("type", "capacite_go"),
    "Alimentation": ("wattage",),
    "Boîtier": ("gpu_max_length_mm",),
    "Refroidissement": ("type_refroidissement",),
}


def identite_compatible(a, b):
    champs = CLES_IDENTITE.get(a["categorie"])
    if not champs:
        return False
    sa, sb = a.get("specs") or {}, b.get("specs") or {}
    return all(sa.get(k) not in (None, "", []) and sa.get(k) == sb.get(k) for k in champs)


def rattachements_surs(paires, catalog):
    """Parmi les paires d'annonces_isolees, celles à rattacher sans demander."""
    by = {c["id"]: c for c in catalog}
    surs = []
    for p in paires:
        a, b = by.get(p["id"]), by.get(p["proche_id"])
        if a and b and p.get("score", 0) >= 0.6 and identite_compatible(a, b):
            surs.append(p)
    return surs


# ---------------------------------------------------------------------------
# Prix suspects sans conséquence
# ---------------------------------------------------------------------------

def prix_a_ignorer(suspects, catalog):
    """
    « Un peu trop cher » (moins de 2× la référence) sur une offre d'un produit
    qui a une offre moins chère en stock : le site affiche déjà le prix le plus
    bas, cette offre ne trompe personne.
    """
    groupes = {}
    for c in catalog:
        if c.get("en_stock") is not False and (c.get("prix_indicatif") or 0) > 0:
            groupes.setdefault(c.get("groupe_id", c["id"]), []).append(float(c["prix_indicatif"]))
    by = {c["id"]: c for c in catalog}
    ignores = []
    for s in suspects:
        c = by.get(s["id"])
        if not c or "plus cher" not in s["motif"] or (s.get("ratio") or 99) >= 2:
            continue
        prix_groupe = groupes.get(c.get("groupe_id", c["id"]), [])
        if prix_groupe and min(prix_groupe) < s["prix"]:
            ignores.append(s)
    return ignores
