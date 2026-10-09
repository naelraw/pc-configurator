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
import os

import requests

SERVICES = ("scraperapi", "scrapingant", "scrapedo")
NOMS = {"scraperapi": "ScraperAPI", "scrapingant": "ScrapingAnt", "scrapedo": "Scrape.do"}
VARIABLES = {"scraperapi": "SCRAPERAPI_KEY", "scrapingant": "SCRAPINGANT_KEY", "scrapedo": "SCRAPEDO_KEY"}
# Crédits estimés par fiche Amazon avant la première mesure.
COUT_INITIAL = {"scraperapi": 5, "scrapingant": 10, "scrapedo": 1}
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


def credits_restants(nom):
    """Crédits restants sur le compte (None si le service ne l'indique pas)."""
    k = cle(nom)
    if not k:
        return None
    if nom == "scraperapi":
        r = _get(nom, "https://api.scraperapi.com/account", params={"api_key": k}, timeout=20)
    elif nom == "scrapingant":
        r = _get(nom, "https://api.scrapingant.com/v2/usage", headers={"x-api-key": k}, timeout=20)
    else:
        r = _get(nom, "https://api.scrape.do/info", params={"token": k}, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} : {_sans_cle(nom, r.text)[:200]}")
    d = r.json()
    if nom == "scraperapi":
        limite, utilises = _cherche(d, "requestLimit"), _cherche(d, "requestCount")
        return int(limite) - int(utilises) if limite is not None and utilises is not None else None
    if nom == "scrapingant":
        reste = _cherche(d, "remained_credits", "remaining_credits", "credits_left")
    else:
        reste = _cherche(d, "RemainingMonthlyRequest", "remaining_monthly_request", "RemainingRequest")
    return int(reste) if reste is not None else None


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
