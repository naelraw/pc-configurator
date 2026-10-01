"""
Note sur 100 de chaque composant, utilisée par le comparateur (et pour
classer « meilleur d'abord »). Une note n'a de sens qu'entre composants de la
même catégorie : on ne compare pas un ventirad à une alimentation.

  - Processeur et carte graphique : performances MESURÉES en jeu
    (tests TechPowerUp, voir fps_data.py). 100 = le meilleur modèle du
    tableau (Ryzen 7 9850X3D, RTX 5090). Pour une carte graphique, la
    variante de mémoire vidéo compte (une RTX 3050 6 Go n'est pas une 8 Go).
  - Autres catégories : pas de test de performance publié comparable pour
    tout le catalogue, donc une note calculée à partir des caractéristiques
    qui font vraiment la différence (vitesse et latence de la RAM, débit des
    SSD, rendement des alimentations, taille du radiateur...), avec le
    détail de chaque critère pour que la note soit vérifiable.

Chaque note renvoie : {"note", "titre", "base", "criteres": [{"nom",
"valeur", "note", "poids"}], "partielle"} ; None si le composant ne peut pas
être noté (ventilateur de boîtier, accessoire, modèle inconnu).
"""
import math
import re

import fps_data

FORMATS = ["Mini-ITX", "Micro-ATX", "ATX", "E-ATX"]


def _borne(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def _interp(x, points):
    """Interpolation linéaire sur des points (x, note) triés."""
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def _resultat(titre, base, criteres):
    """Moyenne pondérée des critères connus ; les critères sans donnée sont
    écartés (note « partielle ») plutôt que comptés zéro."""
    connus = [c for c in criteres if c["note"] is not None]
    if not connus:
        return None
    poids = sum(c["poids"] for c in connus)
    note = round(sum(c["note"] * c["poids"] for c in connus) / poids)
    for c in criteres:
        if c["note"] is not None:
            c["note"] = round(c["note"])
    return {"note": int(_borne(note)), "titre": titre, "base": base, "criteres": criteres,
            "partielle": len(connus) < len(criteres)}


def _critere(nom, valeur, note, poids):
    return {"nom": nom, "valeur": valeur, "note": note, "poids": poids}


# --- Processeur et carte graphique : tests mesurés --------------------------

CPU_PLAFOND = max(v for _, v, _ in fps_data.CPU_RELATIVE)
GPU_PLAFOND = max(variants[vram][1] for _, variants, vram in fps_data.GPU_RELATIVE)


def indice_gpu(c):
    """Indice 1440p de la carte, variante de mémoire vidéo comprise (fiche
    d'abord, sinon le nom), ou None."""
    vram = (c.get("specs") or {}).get("vram_go")
    _, rel, _ = fps_data.match_gpu_full(c.get("nom", ""), vram_go=vram)
    return rel[1] if rel else None


def indice_cpu(c):
    indice, _ = fps_data.match_cpu(c.get("nom", ""))
    return indice


def _note_cpu(c):
    indice, origine = fps_data.match_cpu(c.get("nom", ""))
    if indice is None:
        return None
    s = c.get("specs") or {}
    source = "tests TechPowerUp" if origine == "m" else "estimé d'après le modèle mesuré le plus proche"
    criteres = [_critere("Performances en jeu", f"indice {indice} ({source})", indice / CPU_PLAFOND * 100, 1)]
    if s.get("coeurs"):
        criteres.append(_critere("Cœurs / threads", f"{s['coeurs']} / {s.get('threads', '?')}", None, 0))
    r = _resultat("Performances en jeu", "mesure" if origine == "m" else "estimation", criteres)
    if r:
        r["partielle"] = False
    return r


def _note_gpu(c):
    indice = indice_gpu(c)
    if indice is None:
        return None
    s = c.get("specs") or {}
    criteres = [_critere("Performances en jeu (1440p)", f"indice {indice} (tests TechPowerUp)", indice / GPU_PLAFOND * 100, 1)]
    if s.get("vram_go"):
        criteres.append(_critere("Mémoire vidéo", f"{s['vram_go']} Go {s.get('type_memoire') or ''}".strip(), None, 0))
    r = _resultat("Performances en jeu", "mesure", criteres)
    if r:
        r["partielle"] = False
    return r


# --- Mémoire vive ------------------------------------------------------------
# Capacité (au-delà de 32 Go, le gain en jeu devient marginal) et vitesse
# réelle : débit (MT/s) et latence vraie en nanosecondes = 2000 × CL / MT/s
# (DDR5-6000 CL30 = 10 ns, DDR4-3200 CL16 = 10 ns mais deux fois moins de débit).

def _note_ram(c):
    s = c.get("specs") or {}
    cap, mt, cl = s.get("capacite_go"), s.get("frequence_mt_s"), s.get("latence_cl")
    n_cap = _interp(cap, [(8, 25), (16, 65), (24, 75), (32, 90), (48, 95), (64, 100)]) if cap else None
    n_debit = _borne((mt - 2133) / (8000 - 2133) * 100) if mt else None
    latence = 2000 * cl / mt if mt and cl else None
    n_latence = _borne((16 - latence) / (16 - 8) * 100) if latence else None
    return _resultat("Note d'après les caractéristiques", "caracteristiques", [
        _critere("Capacité", f"{cap} Go" if cap else "inconnue", n_cap, 0.45),
        _critere("Débit", f"{mt} MT/s ({s.get('type') or ''})".strip() if mt else "inconnu", n_debit, 0.35),
        _critere("Latence réelle", f"{latence:.1f} ns (CL{cl})" if latence else "inconnue", n_latence, 0.20),
    ])


# --- Stockage ------------------------------------------------------------------
# Débit en lecture sur une échelle logarithmique (SATA ~560 Mo/s, PCIe 3 ~3500,
# PCIe 4 ~7000, PCIe 5 ~14 500) et capacité (250 Go → 4 To).

def _note_stockage(c):
    s = c.get("specs") or {}
    lecture, cap = s.get("lecture_mo_s"), s.get("capacite_go")
    if not lecture:
        interface = str(s.get("interface") or "")
        lecture = 14000 if "5.0" in interface else 7000 if "4.0" in interface else 3500 if "3.0" in interface else 550 if s.get("type") == "SATA" else None
        estime = True
    else:
        estime = False
    n_vitesse = _borne(math.log(lecture / 100) / math.log(14900 / 100) * 100) if lecture else None
    n_cap = _borne(math.log2(cap / 125) / math.log2(4000 / 125) * 100) if cap else None
    cap_txt = (f"{cap / 1000:g} To" if cap and cap >= 1000 else f"{cap} Go") if cap else "inconnue"
    return _resultat("Note d'après les caractéristiques", "caracteristiques", [
        _critere("Vitesse en lecture", (f"{lecture} Mo/s" + (" (selon l'interface)" if estime else "")) if lecture else "inconnue", n_vitesse, 0.6),
        _critere("Capacité", cap_txt, n_cap, 0.4),
    ])


# --- Alimentation ------------------------------------------------------------
# Qualité, pas puissance (la bonne puissance dépend de la config) : rendement
# 80 PLUS, câbles modulaires, norme ATX 3 / câble 16 broches natif.

CERTIFS = [("Titanium", 100), ("Platinum", 92), ("Gold", 80), ("Silver", 65), ("Bronze", 55), ("Standard", 35)]


def _note_alimentation(c):
    s = c.get("specs") or {}
    # Certification absente de la fiche : on la cherche dans le nom, sinon
    # l'alimentation est considérée non certifiée (les certifiées l'affichent toujours).
    certif = str(s.get("certification") or "") or next(
        (f"80 PLUS {nom}" for nom, _ in CERTIFS if re.search(rf"\b{nom}\b", c.get("nom", ""), re.I)), "")
    n_certif = next((n for nom, n in CERTIFS if nom.lower() in certif.lower()), 25)
    modul = s.get("modularite")
    n_modul = {"Non modulaire": 40, "Semi-modulaire": 75, "Entièrement modulaire": 100}.get(modul)
    norme, natif = str(s.get("norme_atx") or ""), s.get("connecteur_12v_2x6")
    if natif is None and not norme:
        n_atx = None
    else:
        n_atx = 100 if natif == "Oui" or re.search(r"3\.\d", norme) else 50
    r = _resultat("Note de qualité", "caracteristiques", [
        _critere("Rendement", certif or "non certifiée", n_certif, 0.6),
        _critere("Câbles", modul or "inconnu", n_modul, 0.2),
        _critere("Norme ATX 3 / câble 16 broches", ("oui" if n_atx == 100 else "non") if n_atx is not None else "inconnu", n_atx, 0.2),
    ])
    if r and s.get("wattage"):
        r["criteres"].append(_critere("Puissance", f"{s['wattage']} W (à choisir selon la config)", None, 0))
    return r


# --- Refroidissement -----------------------------------------------------------
# Capacité de refroidissement : taille du radiateur pour un watercooling ;
# pour un ventirad, hauteur (surface d'ailettes), nombre de ventilateurs et
# double tour. Un ventirad double tour haut de gamme vaut un watercooling 280.

DOUBLE_TOUR = re.compile(r"peerless|phantom spirit|dual tower|double tour|ak620|ak 620|nh-d15|nh-d12|dark rock pro|fuma|frost commander|royal knight|assassin x 120r|assassin iv|ps120|pa120", re.I)


DEUX_VENTILATEURS = re.compile(r"dual fan|2 ventilateurs|deux ventilateurs|2 x 120|nh-u12a|nh-u14s dx|\bx2\b", re.I)


def _note_refroidissement(c):
    s = c.get("specs") or {}
    type_ = s.get("type_refroidissement")
    nom = c.get("nom", "")
    if type_ == "Watercooling AIO":
        rad = s.get("radiateur_mm") or (int(m.group(1)) if (m := re.search(r"\b(120|140|240|280|360|420)\b", nom)) else None)
        return _resultat("Capacité de refroidissement", "caracteristiques", [
            _critere("Taille du radiateur", f"{rad} mm" if rad else "inconnue",
                     _interp(rad, [(120, 45), (140, 50), (240, 70), (280, 80), (360, 90), (420, 100)]) if rad else None, 1),
        ])
    if type_ == "Ventirad":
        h = s.get("hauteur_mm")
        double = bool(DOUBLE_TOUR.search(nom))
        # « 2 x 120 mm » dans la fiche, sinon le nom ; un double tour en a toujours deux.
        m = re.match(r"\s*(\d+)", str(s.get("ventilateurs") or ""))
        fans = int(m.group(1)) if m else (2 if double or DEUX_VENTILATEURS.search(nom) else 1)
        criteres = [
            _critere("Hauteur (surface de refroidissement)", f"{h} mm" if h else "inconnue",
                     _interp(h, [(40, 20), (70, 35), (125, 60), (155, 75), (165, 80)]) if h else None, 0.6),
            _critere("Ventilateurs", f"{fans}", 100 if fans >= 2 else 60, 0.2),
            _critere("Double tour", "oui" if double else "non", 100 if double else 50, 0.2),
        ]
        return _resultat("Capacité de refroidissement", "caracteristiques", criteres)
    return None  # ventilateur de boîtier : rien de comparable à un refroidissement processeur


# --- Carte mère ----------------------------------------------------------------
# Équipement : gamme du chipset, emplacements M.2, Wi-Fi, mémoire, slots RAM.

def _gamme_chipset(chipset):
    c = str(chipset or "").upper()
    if re.search(r"X[6-9]70E", c):
        return 92, "très haut de gamme"
    if re.search(r"\b(X\d{3}|Z\d{3})", c):
        return 80, "haut de gamme"
    if re.search(r"B[6-9]50E", c):
        return 70, "milieu de gamme +"
    if re.search(r"\b(B\d{3}|H[5-7]70)", c):
        return 60, "milieu de gamme"
    if re.search(r"\b(A\d{3}|H\d{3})", c):
        return 40, "entrée de gamme"
    return None, "inconnue"


def _note_carte_mere(c):
    s = c.get("specs") or {}
    n_chip, gamme = _gamme_chipset(s.get("chipset"))
    m2 = s.get("m2_slots")
    wifi = str(s.get("wifi") or "")
    n_wifi = 0 if wifi == "Non" else 100 if "7" in wifi else 85 if "6E" in wifi else 70 if "6" in wifi else 50 if "5" in wifi else None
    slots = s.get("slots_ram")
    return _resultat("Note d'équipement", "caracteristiques", [
        _critere("Chipset", f"{s.get('chipset') or '?'} ({gamme})", n_chip, 0.45),
        _critere("Emplacements M.2", f"{m2}" if m2 is not None else "inconnu", _interp(m2, [(0, 0), (1, 40), (2, 65), (3, 85), (4, 100)]) if m2 is not None else None, 0.2),
        _critere("Wi-Fi", wifi or "inconnu", n_wifi, 0.15),
        _critere("Mémoire", s.get("ram_type") or "inconnue", {"DDR5": 100, "DDR4": 60}.get(s.get("ram_type")), 0.1),
        _critere("Emplacements RAM", f"{slots}" if slots else "inconnu", (100 if slots >= 4 else 50) if slots else None, 0.1),
    ])


# --- Boîtier -------------------------------------------------------------------
# Flux d'air et place : ventilateurs fournis, longueur de carte graphique,
# hauteur de ventirad et radiateur acceptés, plus grand format de carte mère.

def _note_boitier(c):
    s = c.get("specs") or {}
    fans = s.get("ventilateurs_inclus")
    lg, hv, rad = s.get("gpu_max_length_mm"), s.get("cpu_cooler_max_height_mm"), s.get("radiateur_max_mm")
    formats = [f for f in (s.get("formats_supportes") or []) if f in FORMATS]
    plus_grand = max(formats, key=FORMATS.index) if formats else None
    return _resultat("Note d'équipement", "caracteristiques", [
        _critere("Ventilateurs fournis", f"{fans}" if fans is not None else "inconnu", _interp(fans, [(0, 0), (1, 35), (2, 60), (3, 80), (4, 100)]) if fans is not None else None, 0.3),
        _critere("Carte graphique max.", f"{lg} mm" if lg else "inconnue", _borne((lg - 300) / (420 - 300) * 100) if lg else None, 0.2),
        _critere("Ventirad max.", f"{hv} mm" if hv else "inconnue", _borne((hv - 130) / (180 - 130) * 100) if hv else None, 0.2),
        _critere("Radiateur max.", f"{rad} mm" if rad else "aucun", _interp(rad or 0, [(0, 0), (240, 60), (280, 75), (360, 90), (420, 100)]) if rad is not None else None, 0.2),
        _critere("Format de carte mère", plus_grand or "inconnu", {"Mini-ITX": 30, "Micro-ATX": 60, "ATX": 85, "E-ATX": 100}.get(plus_grand), 0.1),
    ])


NOTEURS = {
    "CPU": _note_cpu, "GPU": _note_gpu, "RAM": _note_ram, "Stockage": _note_stockage,
    "Alimentation": _note_alimentation, "Refroidissement": _note_refroidissement,
    "Carte mère": _note_carte_mere, "Boîtier": _note_boitier,
}


def noter(c):
    fonction = NOTEURS.get(c.get("categorie"))
    try:
        return fonction(c) if fonction else None
    except (TypeError, ValueError, ZeroDivisionError):
        return None
