"""
Regroupement des annonces d'un même produit en variantes.

Le catalogue contient souvent plusieurs annonces pour un même produit : même
modèle vendu par plusieurs vendeurs, en noir et en blanc, en 16 ou 32 Go, en
650 ou 850 W... Chaque annonce reste une ligne à part en base (son ASIN, son
prix relevé chaque jour, les configurations qui y font référence), mais
elles partagent une même clé de produit, calculée ici à partir du nom et des
caractéristiques : le site affiche alors une seule fiche avec ses variantes
et leurs prix, plutôt que le même article plusieurs fois.

Ce qui distingue deux produits (jamais regroupés) : le modèle de processeur,
la puce graphique et la gamme de la carte, la carte mère exacte (Wi-Fi,
DDR4/DDR5), la gamme de RAM/SSD/alimentation/refroidissement/boîtier.
Ce qui n'est qu'une variante : couleur, capacité, fréquence, latence,
puissance, quantité de VRAM, version OC, révision (V2, ATX 3.1), annonce en
double.

Le calcul est automatique (les nouveaux imports sont regroupés d'office) ;
FUSIONS et SEPARES corrigent les rares cas que les règles ne voient pas.
"""
import re
import unicodedata

# Marques en plusieurs mots, ou dont le premier mot du nom ne suffit pas.
MARQUES_COMPOSEES = ["be quiet!", "Cooler Master", "Mars Gaming", "Lian Li", "Fractal Design", "Silicon Power"]
# Écriture officielle des marques dont les annonces varient (« CORSAIR », « Gigabyte »...).
MARQUES_CANONIQUES = {
    "corsair": "Corsair", "gigabyte": "GIGABYTE", "nvidia": "NVIDIA", "powercolor": "PowerColor",
    "zotac": "ZOTAC", "maxsun": "MAXSUN", "arctic": "ARCTIC", "asus": "ASUS", "msi": "MSI",
    "asrock": "ASRock", "xfx": "XFX", "sapphire": "Sapphire", "pny": "PNY", "inno3d": "INNO3D",
    "kingston": "Kingston", "crucial": "Crucial", "samsung": "Samsung", "patriot": "Patriot",
    "lexar": "Lexar", "noctua": "Noctua", "thermalright": "Thermalright", "nzxt": "NZXT",
}

# Couleurs lues dans le nom (le champ « couleur » des annonces est trop hétérogène).
COULEURS = {
    "noir": "Noir", "noire": "Noir", "black": "Noir",
    "blanc": "Blanc", "blanche": "Blanc", "white": "Blanc", "ice": "Blanc", "snow": "Blanc",
    "wood": "Bois", "noyer": "Bois",
    "rose": "Rose", "pink": "Rose", "gris": "Gris", "grey": "Gris", "gray": "Gris",
    "argent": "Argent", "silver": "Argent", "rouge": "Rouge", "red": "Rouge",
}

# Mots sans rapport avec l'identité du produit (catégorie, unités, remplissage d'annonce).
MOTS_VIDES = set("""
processeur alimentation carte graphique graphics boitier pc de et avec the for pour kit series serie
memoire ram desktop dimm udimm tour median moyen mid tower verre trempe tempered glass
ssd interne internal nvme m.2 m 2 pcie gen gen3 gen4 gen5 x4 disque dur
go gb g to tb mo mb mhz mt s w edition
cpu cooler ventirad watercooling refroidisseur liquide aio ventilateur ventilateurs fan fans
alimentation psu garantie ans an full modulaire semi certifie certified
amd intel xmp expo compatible gddr5 gddr6 gddr6x gddr7 memory air
""".split()) | set(COULEURS) | {"spectral"}

# Corrections manuelles, pour les cas que les règles ne voient pas :
# RATTACHER {id: id d'une annonce du produit visé} ; SEPARES : ids toujours seuls.
RATTACHER = {
    2268: 2206,   # « Corsair CX Series CX750 » = gamme CX
    2615: 1903, 1898: 1903,           # PUSKILL DDR4 3200 (annonces sans nom de gamme)
    1927: 1920,                       # Lexar Thor Z DDR5 6000 (« Series OC » dans une seule annonce)
    2546: 2573,                       # GIGABYTE RX 6500 XT Eagle (référence GV-R65XTEAGLE collée au nom)
    2412: 2336,                       # PNY RTX 5060 OC : toujours à deux ventilateurs
    2462: 2368,                       # PNY RTX 5070 Ti OC : toujours à trois ventilateurs
    2501: 2497, 2490: 2488,           # XFX Swift RX 9070 (XT) : toujours à trois ventilateurs
    2697: 2713,                       # Thermalright Assassin X120 SE ARGB (écrit sans espace)
    2711: 2694, 2703: 2694,           # Peerless Assassin 120 SE (« Dual Fan », V2)
    2714: 2699,                       # be quiet! Pure Rock Pro 3 (LX = version ARGB)
    2736: 2748,                       # Thermalright TL-C12C-S ARGB (« PWM » dans une seule annonce)
}
SEPARES = set()


def _ascii(texte):
    return unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode().lower()


def marque(nom):
    """Marque d'un composant, déduite du début de son nom, dans son écriture officielle."""
    nom = (nom or "").strip()
    bas = nom.lower()
    for m in MARQUES_COMPOSEES:
        if bas.startswith(m.lower() + " ") or bas == m.lower():
            return m
    premier = nom.split(" ")[0] if nom else ""
    return MARQUES_CANONIQUES.get(premier.lower(), premier)


def _mots(nom, sans_marque=True):
    n = _ascii(nom)
    if sans_marque:
        m = _ascii(marque(nom))
        if n.startswith(m):
            n = n[len(m):]
    n = re.sub(r"\(.*?\)", " ", n)                      # « (2x16Go) »
    n = n.replace("wi-fi", "wifi")
    n = re.sub(r"\b\d+\s*x\s*\d+\s*(go|gb|g)?\b", " ", n)  # « 2x16 », « 2 x 16 Go »
    return [t for t in re.split(r"[^a-z0-9.!]+", n) if t and t != "."]


def _reference(t):
    """Référence fabricant collée au nom (GV-R65XTEAGLE, RX-76PSWFTFA, 912-V502-039)."""
    return len(t) >= 8 and any(ch.isdigit() for ch in t)


def _sans_unites(mots):
    """Retire capacités, fréquences, puissances, latences et nombres seuls."""
    garde = []
    for t in mots:
        if re.fullmatch(r"\d+([.,]\d+)?(go|gb|g|to|tb|mo|mb|w|mhz|mt|s|mm)?", t):
            continue
        if re.fullmatch(r"c?l?\d{2}|cl\d+|c\d{2}", t):     # CL30, C36
            continue
        garde.append(t)
    return garde


def _cle_cpu(c):
    n = _ascii(c["nom"])
    m = (re.search(r"\b(i[3579])[- ]?(\d{4,5}[a-z]*)", n)
         or re.search(r"ultra\s*([3579])\s*(\d{3}[a-z]*)", n)
         or re.search(r"ryzen\s*(?:ai\s*)?([3579]|threadripper)\s*(?:pro\s*)?(\d{4}[a-z0-9]*)", n))
    return f"{m.group(1)}-{m.group(2)}" if m else None


def _cle_gpu(c):
    puce = _ascii((c.get("specs") or {}).get("puce") or "")
    mots = [t for t in _mots(c["nom"]) if t not in MOTS_VIDES]
    puce_mots = set(puce.split()) | {"".join(puce.split()[i:]) for i in range(len(puce.split()))}
    puce_mots |= {"geforce", "radeon", "nvidia", "rtx", "rx", "gtx", "oc", "overclocked", "arc"}
    ligne = [t for t in _sans_unites(mots) if t not in puce_mots and not _reference(t)
             and not re.fullmatch(r"v\d+|rev\d(\.\d)?|d6|d7", t)]
    # « Gaming » ne désigne une gamme que seul (GIGABYTE Gaming OC) ; ailleurs
    # c'est un mot d'annonce (MSI Gaming Ventus, Sapphire Pulse Gaming OC).
    if len(set(ligne)) > 1:
        ligne = [t for t in ligne if t != "gaming"]
    if not puce:
        return None
    return f"{puce}|{' '.join(sorted(set(ligne)))}"


def _cle_carte_mere(c):
    mots = [t for t in _mots(c["nom"]) if t not in MOTS_VIDES]
    mots = [t for t in mots if not re.fullmatch(r"v\d|rev\d(\.\d)?|r\d|ddr[45]", t)]
    ram = (c.get("specs") or {}).get("ram_type") or ""
    return f"{ram}|{' '.join(sorted(set(mots)))}"


def _cle_ram(c):
    mots = [t for t in _sans_unites(_mots(c["nom"])) if t not in MOTS_VIDES and not re.fullmatch(r"ddr[45]", t)]
    type_ = (c.get("specs") or {}).get("type") or ""
    return f"{type_}|{' '.join(sorted(set(mots)))}"


def _cle_stockage(c):
    n = re.sub(r"\b\d+([.,]\d+)?\s*(go|gb|to|tb)\b", " ", _ascii(c["nom"]))
    mots = [t for t in _mots(n.replace(_ascii(marque(c["nom"])), "", 1), sans_marque=False)
            if t not in MOTS_VIDES and not re.fullmatch(r"\d\.\d|dissipateur|heatsink|pcie\d|22[348]0", t)]
    return " ".join(sorted(set(mots)))


def _cle_alim(c):
    mots = []
    for t in _mots(c["nom"]):
        if t in MOTS_VIDES or t in {"atx", "gold", "bronze", "silver", "platinum", "titanium", "80", "plus", "80+", "pcie5", "pcie5.1"}:
            continue
        # Puissance (650, 850w) et révision (V2, ATX 3.1) ; pas le numéro de gamme (Pure Power 12).
        if re.fullmatch(r"\d+w|[2-9]\d\d|1\d{3}|v\d|3\.\d", t):
            continue
        mots.append(re.sub(r"\d{3,4}", "#", t))
    cert = (c.get("specs") or {}).get("certification") or ""
    return f"{cert}|{' '.join(sorted(set(mots)))}"


def _cle_generique(c):
    n = re.sub(r"\b(lot|pack|kit)\s+de\s+\d+\b|\b\d\s*(pack|pcs)\b", " ", _ascii(c["nom"]))
    n = re.sub(r"\b\d+\s*(caloducs?|heat\s*pipes?)\b", " ", n)   # « 4 caloducs », « 6 Heat Pipes »
    n = re.sub(r"\b(\d+)\s+mm\b", r"\1mm", n)                      # « 120 mm » = « 120mm »
    mots = [t for t in _mots(marque(c["nom"]) + n[len(_ascii(marque(c["nom"]))):]) if t not in MOTS_VIDES]
    mots = [t for t in mots if t not in {"argb", "rgb", "gaming", "airflow", "panoramique", "atx", "e-atx", "matx"}
            and not re.fullmatch(r"v\d", t)]
    # Watercooling : 240, 360, 420 mm ne sont que des tailles du même modèle.
    if (c.get("specs") or {}).get("type_refroidissement") == "Watercooling AIO":
        mots = [t for t in mots if t not in {"120", "140", "240", "280", "360", "420"}]
    return " ".join(sorted(set(mots)))


CLES = {
    "CPU": _cle_cpu, "GPU": _cle_gpu, "Carte mère": _cle_carte_mere, "RAM": _cle_ram,
    "Stockage": _cle_stockage, "Alimentation": _cle_alim,
}


def cle_produit(c):
    """Clé commune à toutes les annonces d'un même produit (None = produit à part)."""
    if c["id"] in SEPARES:
        return None
    try:
        cle = CLES.get(c["categorie"], _cle_generique)(c)
    except Exception:
        cle = None
    if not cle or cle.endswith("|"):
        return None
    return f"{c['categorie']}|{marque(c['nom']).lower()}|{cle}"


def couleur(nom):
    for t in _mots(nom):
        if t in COULEURS:
            return COULEURS[t]
    return None


def _fmt(v):
    return f"{v:g}".replace(".", ",") if isinstance(v, float) else str(v)


CONDITIONNEMENTS = {"tray": "Tray (sans boîte)", "plateau": "Tray (sans boîte)", "oem": "Tray (sans boîte)",
                    "box": "En boîte", "mpk": "Multipack", "argb": "ARGB", "rgb": "RGB", "lx": "LX (ARGB)"}

def _capacite(go):
    return f"{_fmt(go / 1000)} To" if go >= 1000 else f"{_fmt(go)} Go"


def _kit(s):
    if s.get("capacite_go") is None:
        return None
    m = re.match(r"(\d+)\s*x\s*(\d+)", str(s.get("barrettes") or ""))
    return _capacite(s["capacite_go"]) + (f" ({m.group(1)} × {m.group(2)} Go)" if m else "")


def _spec(cle, fmt):
    return lambda s: None if s.get(cle) in (None, "") else fmt(s[cle])


# Ce qui distingue les variantes, par catégorie, dans l'ordre d'affichage
# (fonction specs -> libellé ; n'apparaît que si la valeur change dans le groupe).
DIMENSIONS = {
    "GPU": [_spec("vram_go", lambda v: f"{_fmt(v)} Go")],
    "RAM": [_kit, _spec("frequence_mt_s", lambda v: f"{_fmt(v)} MT/s"), _spec("latence_cl", lambda v: f"CL{_fmt(v)}")],
    "Stockage": [_spec("capacite_go", _capacite)],
    "Alimentation": [_spec("wattage", lambda v: f"{_fmt(v)} W"), _spec("norme_atx", str)],
    "Refroidissement": [_spec("radiateur_mm", lambda v: f"{_fmt(v)} mm")],
}


def _etiquettes(groupe):
    """Libellé court de chaque variante : seulement ce qui change d'une variante à l'autre."""
    specs = [c.get("specs") or {} for c in groupe]
    parts = [[] for _ in groupe]
    for dim in DIMENSIONS.get(groupe[0]["categorie"], []):
        valeurs = []
        for sp in specs:
            try:
                valeurs.append(dim(sp))
            except (TypeError, ValueError):
                valeurs.append(None)
        if len(set(valeurs)) > 1:
            for i, v in enumerate(valeurs):
                if v:
                    parts[i].append(v)
    oc = ["oc" in _mots(c["nom"]) for c in groupe]
    if groupe[0]["categorie"] == "GPU" and len(set(oc)) > 1:
        for i, o in enumerate(oc):
            if o:
                parts[i].append("OC")
    # Sans couleur dans le nom, un produit est noir (la couleur de série).
    couleurs = [couleur(c["nom"]) or "Noir" for c in groupe]
    if len(set(couleurs)) > 1:
        for i, col in enumerate(couleurs):
            parts[i].append(col)
    # Mots d'annonce qui signalent une vraie différence de conditionnement.
    mots = [set(_mots(c["nom"])) for c in groupe]
    for mot, libelle in CONDITIONNEMENTS.items():
        presents = [mot in m for m in mots]
        if any(presents) and not all(presents):
            for i, present in enumerate(presents):
                if present and libelle not in parts[i]:
                    parts[i].append(libelle)
    labels = [" · ".join(p) for p in parts]
    # Annonces encore identiques (même produit, autre vendeur) : « Offre 1, 2... »
    # dans l'ordre du prix (le groupe est trié du moins cher au plus cher).
    compte, rang = {}, {}
    for l in labels:
        compte[l] = compte.get(l, 0) + 1
    for i, l in enumerate(labels):
        if compte[l] > 1:
            rang[l] = rang.get(l, 0) + 1
            labels[i] = f"{l + ' · ' if l else ''}Offre {rang[l]}"
        elif not l:
            labels[i] = "Standard"
    return labels


def annoter(composants):
    """
    Ajoute à chaque composant (dict du catalogue) :
      marque       -> marque officielle
      groupe_id    -> id commun à toutes les variantes du produit (le plus petit id)
      variante     -> libellé court de la variante (None si produit sans variante)
      nb_variantes -> nombre d'annonces du produit
    """
    cles = {}
    for c in composants:
        c["marque"] = marque(c["nom"])
        cles[c["id"]] = cle_produit(c) or f"seul:{c['id']}"
    for id_, cible in RATTACHER.items():
        if id_ in cles and cible in cles:
            cles[id_] = cles[cible]
    groupes = {}
    for c in composants:
        groupes.setdefault(cles[c["id"]], []).append(c)
    for groupe in groupes.values():
        groupe.sort(key=lambda c: (float(c.get("prix_indicatif") or 0) <= 0, float(c.get("prix_indicatif") or 0), c["id"]))
        gid = min(c["id"] for c in groupe)
        labels = _etiquettes(groupe) if len(groupe) > 1 else [None]
        for c, label in zip(groupe, labels):
            c["groupe_id"] = gid
            c["variante"] = label
            c["nb_variantes"] = len(groupe)
    return composants
