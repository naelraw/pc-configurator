"""
Relevé des prix PC Radar depuis ce PC, en arrière-plan, sans navigateur.

Même travail que le « Relevé automatique des prix » de l'extension : toutes les
~30 s, le site donne la fiche la plus urgente, ce programme lit sa page
amazon.fr (connexion de la maison, qu'Amazon ne bloque pas, sans cookies donc
sans lien avec un compte Amazon) et renvoie au site seulement la zone du prix
et de la disponibilité. Le site applique le prix avec ses garde-fous habituels.

- Vérification « robot » d'Amazon : pause d'une heure, jamais de contournement.
- Au plus MAX_PAR_JOUR fiches par jour.
- Pages demandées compressées (environ 300 Ko au lieu de 2,5 Mo).
- Un seul exemplaire à la fois ; journal dans %LOCALAPPDATA%\\PCRadar\\releve.log.

Utilisation :
  python releve_prix_pc.py --configurer   enregistre le mot de passe admin (saisie masquée)
  python releve_prix_pc.py --essai ASIN   lit une page Amazon sans rien envoyer au site
  pythonw releve_prix_pc.py               relevé en continu, sans fenêtre (lancé au démarrage)
Installation au démarrage de Windows : installer_releve_prix.bat (même dossier).
Uniquement la bibliothèque standard de Python.
"""
import datetime
import getpass
import gzip
import json
import os
import random
import socket
import sys
import time
import urllib.error
import urllib.request

SITE = "https://pcradar.tech"
INTERVALLE_SECONDES = 30
MAX_PAR_JOUR = 800
PAUSE_BLOCAGE_SECONDES = 3600
DOSSIER = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "PCRadar")
CONFIG = os.path.join(DOSSIER, "releve.json")
JOURNAL = os.path.join(DOSSIER, "releve.log")
PORT_VERROU = 47831   # un seul exemplaire du programme à la fois
ENTETES_AMAZON = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept-Encoding": "gzip",
}


def journal(message):
    os.makedirs(DOSSIER, exist_ok=True)
    try:
        if os.path.exists(JOURNAL) and os.path.getsize(JOURNAL) > 1_000_000:
            os.replace(JOURNAL, JOURNAL + ".ancien")
        with open(JOURNAL, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {message}\n")
    except OSError:
        pass


def http(url, donnees=None, entetes=None, delai=45):
    """(statut, texte) ; texte décompressé si la réponse est en gzip."""
    requete = urllib.request.Request(url, data=donnees, headers=entetes or {}, method="POST" if donnees else "GET")
    try:
        with urllib.request.urlopen(requete, timeout=delai) as r:
            brut, statut, codage = r.read(), r.status, r.headers.get("Content-Encoding", "")
    except urllib.error.HTTPError as err:
        brut, statut, codage = err.read(), err.code, err.headers.get("Content-Encoding", "")
    if "gzip" in codage:
        brut = gzip.decompress(brut)
    return statut, brut.decode("utf-8", errors="replace")


def extrait_amazon(html):
    """Seulement ce dont le site a besoin : titre, zone du prix, disponibilité."""
    morceaux = []
    for repere, longueur in (('id="productTitle"', 600), ('id="corePriceDisplay_desktop_feature_div"', 8000),
                             ('id="availability"', 2000)):
        i = html.find(repere)
        if i >= 0:
            morceaux.append(html[i:i + longueur])
    if "validateCaptcha" in html:
        morceaux.append("validateCaptcha")
    return "\n".join(morceaux)


def page_amazon(asin):
    return http(f"https://www.amazon.fr/dp/{asin}?th=1&psc=1", entetes=ENTETES_AMAZON)


def lire_config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def configurer():
    print("Relevé des prix PC Radar : enregistrement du mot de passe admin (il ne s'affiche pas).")
    secret = getpass.getpass("Mot de passe admin du site puis Entrée : ").strip()
    statut, _ = http(SITE + "/api/admin/prix-extension/stats", entetes={"X-Admin-Secret": secret})
    if statut != 200:
        print(f"Le site refuse ce mot de passe (réponse {statut}). Rien n'a été enregistré.")
        return False
    os.makedirs(DOSSIER, exist_ok=True)
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump({"secret": secret}, f)
    print("Mot de passe accepté et enregistré sur ce PC.")
    return True


def un_releve(secret):
    entete = {"X-Admin-Secret": secret}
    statut, texte = http(SITE + "/api/admin/prix-a-relire?n=1&origine=pc", entetes=entete)
    if statut == 401:
        journal("Le site refuse le mot de passe admin : relancer « installer_releve_prix.bat ».")
        return "refuse"
    if statut != 200:
        journal(f"Site indisponible (réponse {statut}).")
        return "erreur"
    fiches = json.loads(texte).get("fiches") or []
    if not fiches:
        return "rien"
    fiche = fiches[0]
    statut, html = page_amazon(fiche["asin"])
    corps = json.dumps({"id": fiche["id"], "asin": fiche["asin"], "extrait": extrait_amazon(html), "origine": "pc"}).encode()
    statut, texte = http(SITE + "/api/admin/prix-extension", donnees=corps,
                         entetes=dict(entete, **{"Content-Type": "application/json"}))
    try:
        r = json.loads(texte)
    except ValueError:
        r = {}
    resultat = r.get("resultat") or f"erreur {statut}"
    detail = f"{r['prix']} €" if r.get("prix") is not None else ""
    journal(f"{fiche['nom'][:60]} : {resultat} {detail}".rstrip())
    return resultat


def en_continu():
    verrou = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        verrou.bind(("127.0.0.1", PORT_VERROU))
    except OSError:
        return   # déjà en cours
    secret = lire_config().get("secret")
    if not secret:
        journal("Pas de mot de passe enregistré : lancer « installer_releve_prix.bat ».")
        return
    journal("Démarrage du relevé des prix.")
    jour, compte = None, 0
    while True:
        if datetime.date.today() != jour:
            jour, compte = datetime.date.today(), 0
        if compte >= MAX_PAR_JOUR:
            time.sleep(600)
            continue
        try:
            resultat = un_releve(secret)
        except Exception as err:   # réseau coupé, PC en veille... : on réessaie plus tard
            journal(f"Erreur : {type(err).__name__} : {str(err)[:150]}")
            resultat = "erreur"
        if resultat in ("lu", "ignore", "sans_prix"):
            compte += 1
        if resultat == "bloque":
            journal("Amazon demande une vérification : pause d'une heure.")
            time.sleep(PAUSE_BLOCAGE_SECONDES)
        elif resultat == "refuse":
            time.sleep(3600)
            secret = lire_config().get("secret") or secret
        elif resultat in ("rien", "erreur"):
            time.sleep(300)
        else:
            time.sleep(INTERVALLE_SECONDES + random.uniform(-5, 10))


if __name__ == "__main__":
    if "--configurer" in sys.argv:
        sys.exit(0 if configurer() else 1)
    if "--essai" in sys.argv:
        asin = sys.argv[sys.argv.index("--essai") + 1]
        statut, html = page_amazon(asin)
        ex = extrait_amazon(html)
        print(f"Amazon : réponse {statut}, page {len(html)} caractères, extrait {len(ex)} caractères, "
              f"{'vérification robot' if 'validateCaptcha' in ex else 'pas de vérification'}, "
              f"zone de prix {'trouvée' if 'corePriceDisplay' in ex else 'absente'}.")
        sys.exit(0)
    en_continu()
