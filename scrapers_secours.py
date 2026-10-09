"""
Services de secours pour lire le prix d'une fiche Amazon : ScraperAPI,
ScrapingAnt et Scrape.do, sur leurs quotas gratuits mensuels. Utilisés après
Apify, Bright Data et ZenRows dans chaque passage de la mise à jour des prix,
surtout pour reprendre les fiches bloquées ailleurs.

Ils servent uniquement à LIRE un prix : une fiche sans prix lisible lève une
erreur et ne change rien (jamais « épuisé » sur leur seule foi ; c'est Bright
Data, qui lit la fiche avec son statut de disponibilité, qui en décide).

Crédits restants demandés au service lui-même (le coût d'une page Amazon varie
selon le service et le type de proxy) ; le coût réel par fiche est mesuré à
chaque passage par l'appelant. Les clés ne sont jamais écrites dans un message
d'erreur (les erreurs de requests contiennent l'adresse appelée).
"""
import math
import os
from datetime import datetime, timedelta, timezone

import requests

# Services utilisés par la mise à jour des prix. Scrape.do n'y est pas : avec le
# proxy de centre de données de son offre gratuite (les proxys résidentiels sont
# réservés aux offres payantes), Amazon lui renvoie une page sans aucune offre
# ni prix, décomptée quand même (constaté le 9 octobre 2026). Sa clé reste
# enregistrée et vérifiée par ops/set_scraping_keys.sh.
SERVICES = ("scraperapi", "scrapingant")
TOUS = ("scraperapi", "scrapingant", "scrapedo")
NOMS = {"scraperapi": "ScraperAPI", "scrapingant": "ScrapingAnt", "scrapedo": "Scrape.do"}
VARIABLES = {"scraperapi": "SCRAPERAPI_KEY", "scrapingant": "SCRAPINGANT_KEY", "scrapedo": "SCRAPEDO_KEY"}
# Crédits estimés par fiche Amazon avant la première mesure.
COUT_INITIAL = {"scraperapi": 5, "scrapingant": 26, "scrapedo": 1}   # ScraperAPI et ScrapingAnt mesurés le 9/10/2026
# Essai ScraperAPI : 5 000 crédits sur 7 jours, puis 1 000 par mois (offre gratuite).
SCRAPERAPI_LIMITE_GRATUITE = 1000
SCRAPERAPI_DUREE_ESSAI_JOURS = 7
DELAI_SECONDES = 70


def cle(nom):
    return os.getenv(VARIABLES[nom], "").strip()


def _sans_cle(nom, texte):
    k = cle(nom)
    return str(texte).replace(k, "***") if k else str(texte)


def _get(nom, url, **kwargs):
    try:
        reponse = requests.get(url, timeout=kwargs.pop("timeout", DELAI_SECONDES), **kwargs)
    except requests.RequestException as err:
        raise RuntimeError(f"{type(err).__name__} : {_sans_cle(nom, err)[:200]}") from None
    return reponse


def _cherche(donnees, *noms):
    """Valeur d'un des champs (sans tenir compte de la casse), au premier niveau puis un niveau plus bas."""
    if not isinstance(donnees, dict):
        return None
    minuscules = {str(k).lower(): v for k, v in donnees.items()}
    for n in noms:
        if n.lower() in minuscules and minuscules[n.lower()] not in (None, ""):
            return minuscules[n.lower()]
    for v in donnees.values():
        if isinstance(v, dict):
            trouve = _cherche(v, *noms)
            if trouve is not None:
                return trouve
    return None


def _date(texte):
    try:
        d = datetime.fromisoformat(str(texte).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def etat(nom):
    """{"reste": crédits restants, "jours": jours avant qu'ils ne se renouvellent (ou
    n'expirent)} ; None pour ce que le service n'indique pas."""
    k = cle(nom)
    if not k:
        return {"reste": None, "jours": None}
    if nom == "scraperapi":
        r = _get(nom, "https://api.scraperapi.com/account", params={"api_key": k}, timeout=20)
    elif nom == "scrapingant":
        r = _get(nom, "https://api.scrapingant.com/v2/usage", headers={"x-api-key": k}, timeout=20)
    else:
        r = _get(nom, "https://api.scrape.do/info", params={"token": k}, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} : {_sans_cle(nom, r.text)[:200]}")
    d = r.json()
    fin = None
    if nom == "scraperapi":
        reste = _cherche(d, "creditsLeft")
        if reste is None:
            limite, utilises = _cherche(d, "requestLimit"), _cherche(d, "requestCount")
            reste = int(limite) - int(utilises) if limite is not None and utilises is not None else None
        fin = _date(_cherche(d, "nextBillingDate"))
        # Crédits d'essai (au-delà de l'offre gratuite) : valables 7 jours après l'inscription.
        debut = _date(_cherche(d, "subscriptionDate"))
        if debut and int(_cherche(d, "requestLimit") or 0) > SCRAPERAPI_LIMITE_GRATUITE:
            fin_essai = debut + timedelta(days=SCRAPERAPI_DUREE_ESSAI_JOURS)
            if fin_essai > datetime.now(timezone.utc):
                fin = min(fin, fin_essai) if fin else fin_essai
    elif nom == "scrapingant":
        reste = _cherche(d, "remained_credits", "remaining_credits", "credits_left")
        fin = _date(_cherche(d, "end_date"))
    else:
        reste = _cherche(d, "RemainingMonthlyRequest", "remaining_monthly_request", "RemainingRequest")
    jours = None
    if fin:
        jours = max(1, math.ceil((fin - datetime.now(timezone.utc)).total_seconds() / 86400))
    return {"reste": int(reste) if reste is not None else None, "jours": jours}


def credits_restants(nom):
    """Crédits restants sur le compte (None si le service ne l'indique pas)."""
    return etat(nom)["reste"]


def _page_bloquee(html):
    return ("validateCaptcha" in html or "api-services-support@amazon.com" in html
            or "Saisissez les caractères que vous voyez" in html)


def lire(nom, asin, analyser_html, lire_prix):
    """Prix d'une fiche amazon.fr (même forme que la lecture ZenRows). Lève une erreur sans prix lisible."""
    k = cle(nom)
    if not k:
        raise RuntimeError("pas de clé")
    url = f"https://www.amazon.fr/dp/{asin}"
    if nom == "scraperapi":
        # Données déjà structurées (JSON) : pas d'analyse de page à faire.
        r = _get(nom, "https://api.scraperapi.com/structured/amazon/product",
                 params={"api_key": k, "asin": asin, "country": "fr", "tld": "fr"})
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        d = r.json()
        images = _cherche(d, "images", "image")
        info = {
            "asin": asin, "nom": _cherche(d, "name", "title"), "marque": _cherche(d, "brand"),
            "prix": lire_prix(_cherche(d, "pricing", "price", "final_price")),
            "image_url": images[0] if isinstance(images, list) and images else images if isinstance(images, str) else None,
            "disponibilite": True, "lien": url, "caracteristiques_amazon": [], "description": None,
        }
    else:
        if nom == "scrapingant":
            # Proxy de centre de données d'abord (le moins cher) ; résidentiel si Amazon bloque.
            r = None
            for proxy in ("datacenter", "residential"):
                r = _get(nom, "https://api.scrapingant.com/v2/general", headers={"x-api-key": k},
                         params={"url": url, "browser": "false", "proxy_country": "FR", "proxy_type": proxy})
                if r.status_code == 200 and not _page_bloquee(r.text):
                    break
        else:
            r = _get(nom, "https://api.scrape.do/", params={"token": k, "url": url, "geoCode": "fr"})
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        if _page_bloquee(r.text):
            raise RuntimeError("page bloquée par Amazon")
        info = analyser_html(r.text, asin)
    if info.get("prix") is None:
        raise RuntimeError("prix non lisible sur la page (épuisé ou bloqué), rien de modifié")
    return info
