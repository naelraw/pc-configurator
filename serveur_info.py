"""
État du serveur pour l'admin (page « Serveur ») : processeur, mémoire, disque,
services, tâches planifiées, sauvegardes et certificat HTTPS.

Tout est lu sur le système (/proc, systemctl, statvfs) sans dépendance ni droits
root. Sur une machine qui n'a pas /proc ou systemctl (tests sous Windows), les
valeurs manquantes valent None et la page les affiche comme indisponibles.
"""
import datetime
import glob
import os
import shutil
import socket
import ssl
import subprocess
import time

RACINE = os.path.dirname(os.path.abspath(__file__))
SERVICES = (
    ("pc-configurator.service", "Site PC Radar"),
    ("nginx.service", "Serveur web (nginx)"),
    ("gymsquad.service", "GymSquad"),
)
# Arrêtés le 7 octobre 2026 car inutilisés (relançables à tout moment) :
# - PostgreSQL : GymSquad stocke ses données en SQLite ; sudo systemctl enable --now postgresql
# - rembg (détourage des images) : aucun bouton de l'admin ne l'appelait, aucune image du
#   catalogue n'était détourée ; sudo systemctl enable --now rembg-service
TACHES = (
    ("pcradar-backup.timer", "Sauvegarde de la base"),
    ("pcradar-healthcheck.timer", "Surveillance du site"),
    ("pcradar-offsite.timer", "Sauvegarde envoyée par e-mail"),
)
DOSSIERS = (
    ("Base de données", os.path.join(RACINE, "data")),
    ("Sauvegardes avant déploiement", os.path.join(RACINE, "backups")),
    ("Sauvegardes quotidiennes", "/home/ubuntu/backups"),
)
DOMAINE = "pcradar.tech"


def _lire(chemin):
    try:
        with open(chemin, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _cpu():
    def instant():
        ligne = (_lire("/proc/stat") or "").split("\n", 1)[0].split()
        if not ligne or ligne[0] != "cpu":
            return None
        valeurs = [int(v) for v in ligne[1:]]
        return sum(valeurs), valeurs[3] + (valeurs[4] if len(valeurs) > 4 else 0)   # total, inactif (idle + iowait)
    a = instant()
    time.sleep(0.25)
    b = instant()
    utilisation = None
    if a and b and b[0] > a[0]:
        utilisation = round(100 * (1 - (b[1] - a[1]) / (b[0] - a[0])), 1)
    try:
        charge = [round(x, 2) for x in os.getloadavg()]
    except (OSError, AttributeError):
        charge = None
    modele = None
    for ligne in (_lire("/proc/cpuinfo") or "").splitlines():
        if ligne.lower().startswith(("model name", "cpu model")):
            modele = ligne.split(":", 1)[1].strip()
            break
    return {"coeurs": os.cpu_count(), "utilisation": utilisation, "charge": charge, "modele": modele}


def _memoire():
    infos = {}
    for ligne in (_lire("/proc/meminfo") or "").splitlines():
        cle, _, reste = ligne.partition(":")
        if reste.strip():
            infos[cle] = int(reste.split()[0]) * 1024
    if "MemTotal" not in infos:
        return None
    total, dispo = infos["MemTotal"], infos.get("MemAvailable", infos.get("MemFree", 0))
    swap_total, swap_libre = infos.get("SwapTotal", 0), infos.get("SwapFree", 0)
    return {"total": total, "utilise": total - dispo, "disponible": dispo, "cache": infos.get("Cached", 0) + infos.get("Buffers", 0),
            "swap_total": swap_total, "swap_utilise": swap_total - swap_libre}


def _taille_dossier(chemin):
    total = 0
    for dossier, _, fichiers in os.walk(chemin):
        for f in fichiers:
            try:
                total += os.path.getsize(os.path.join(dossier, f))
            except OSError:
                pass
    return total if os.path.isdir(chemin) else None


def _disque():
    try:
        d = shutil.disk_usage("/")
    except OSError:
        return None
    return {"total": d.total, "utilise": d.used, "libre": d.free,
            "dossiers": [{"nom": nom, "taille": _taille_dossier(chemin)} for nom, chemin in DOSSIERS]}


def _systemctl(unites, proprietes):
    """systemctl show (lecture seule, sans droits root) : {unité: {propriété: valeur}}."""
    try:
        sortie = subprocess.run(["systemctl", "show", *unites, *[f"-p{p}" for p in proprietes], "--no-pager"],
                                capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    resultat = {}
    for bloc in sortie.strip().split("\n\n"):
        valeurs = dict(l.split("=", 1) for l in bloc.splitlines() if "=" in l)
        if valeurs.get("Id"):
            resultat[valeurs["Id"]] = valeurs
    return resultat


def _services():
    infos = _systemctl([u for u, _ in SERVICES], ("Id", "ActiveState", "MemoryCurrent", "ActiveEnterTimestamp"))
    liste = []
    for unite, nom in SERVICES:
        v = infos.get(unite, {})
        memoire = v.get("MemoryCurrent", "")
        liste.append({"nom": nom, "etat": v.get("ActiveState") or "inconnu",
                      "memoire": int(memoire) if memoire.isdigit() else None,
                      "depuis": v.get("ActiveEnterTimestamp") or None})
    return liste


def _taches():
    infos = _systemctl([u for u, _ in TACHES], ("Id", "LastTriggerUSec", "NextElapseUSecRealtime"))
    return [{"nom": nom, "dernier": infos.get(u, {}).get("LastTriggerUSec") or None,
             "prochain": infos.get(u, {}).get("NextElapseUSecRealtime") or None} for u, nom in TACHES]


def _derniere_sauvegarde():
    fichiers = sorted(glob.glob("/home/ubuntu/backups/db/*.db.gz"))
    if not fichiers:
        return None
    dernier = fichiers[-1]
    return {"fichier": os.path.basename(dernier), "taille": os.path.getsize(dernier),
            "date": datetime.datetime.utcfromtimestamp(os.path.getmtime(dernier)).isoformat(timespec="minutes"),
            "nombre": len(fichiers)}


def _certificat():
    try:
        contexte = ssl.create_default_context()
        with socket.create_connection((DOMAINE, 443), timeout=5) as brut:
            with contexte.wrap_socket(brut, server_hostname=DOMAINE) as s:
                fin = s.getpeercert()["notAfter"]
        expire = datetime.datetime.strptime(fin, "%b %d %H:%M:%S %Y %Z")
        return {"expire": expire.isoformat(timespec="minutes"), "jours": (expire - datetime.datetime.utcnow()).days}
    except Exception:
        return None


def mesures_rapides():
    """Ce qui change d'une seconde à l'autre (processeur, mémoire, durée de
    fonctionnement), pour la page Serveur en direct. Le reste (services,
    disque, certificat...) est relu moins souvent par etat_du_serveur()."""
    uptime = _lire("/proc/uptime")
    return {
        "complet": False,
        "demarre_depuis_s": int(float(uptime.split()[0])) if uptime else None,
        "cpu": _cpu(),
        "memoire": _memoire(),
        "mesure_le": datetime.datetime.utcnow().isoformat(timespec="seconds"),
    }


def etat_du_serveur():
    uptime = _lire("/proc/uptime")
    return {
        "complet": True,
        "nom": socket.gethostname(),
        "systeme": " ".join((_lire("/etc/os-release") or "").split('PRETTY_NAME="', 1)[-1].split('"', 1)[:1]) or None,
        "demarre_depuis_s": int(float(uptime.split()[0])) if uptime else None,
        "cpu": _cpu(),
        "memoire": _memoire(),
        "disque": _disque(),
        "services": _services(),
        "taches": _taches(),
        "sauvegarde": _derniere_sauvegarde(),
        "certificat": _certificat(),
        "mesure_le": datetime.datetime.utcnow().isoformat(timespec="seconds"),
    }
