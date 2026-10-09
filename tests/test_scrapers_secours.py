"""Services de secours (ScraperAPI, ScrapingAnt, Scrape.do) : lecture de prix seulement, clés jamais affichées."""
from datetime import datetime
from types import SimpleNamespace

import pytest
import requests

import main
import scrapers_secours as s


class Reponse(SimpleNamespace):
    def json(self):
        return self.donnees


def test_cle_jamais_dans_une_erreur(monkeypatch):
    monkeypatch.setenv("SCRAPEDO_KEY", "clesecrete1234567890abcdef")

    def panne(url, **k):
        raise requests.ConnectionError(f"Max retries exceeded with url: /info?token=clesecrete1234567890abcdef")
    monkeypatch.setattr(s.requests, "get", panne)
    with pytest.raises(RuntimeError) as err:
        s.credits_restants("scrapedo")
    assert "clesecrete" not in str(err.value) and "***" in str(err.value)


def test_scraperapi_prix_structure(monkeypatch):
    monkeypatch.setenv("SCRAPERAPI_KEY", "k" * 32)
    monkeypatch.setattr(s.requests, "get", lambda url, **k: Reponse(status_code=200, text="", donnees={
        "name": "AMD Ryzen 7 9800X3D", "pricing": "1.063,05 €", "images": ["https://m.media-amazon.com/x.jpg"]}))
    info = s.lire("scraperapi", "B0TEST0001", main._parse_zenrows_amazon_html, main.parse_amazon_price)
    assert info["prix"] == 1063.05 and info["image_url"].endswith("x.jpg")


def test_page_html_lue_ou_refusee(monkeypatch):
    monkeypatch.setenv("SCRAPEDO_KEY", "k" * 32)
    page = ('<span id="productTitle">Carte</span><div id="corePriceDisplay_desktop_feature_div">'
            '<span class="a-price-whole">1&nbsp;246<span class="a-price-decimal">,</span></span>'
            '<span class="a-price-fraction">00</span><div id="availability">En stock</div>')
    monkeypatch.setattr(s.requests, "get", lambda url, **k: Reponse(status_code=200, text=page))
    assert s.lire("scrapedo", "B0TEST0001", main._parse_zenrows_amazon_html, main.parse_amazon_price)["prix"] == 1246.0
    # Captcha Amazon : erreur, rien n'est modifié.
    monkeypatch.setattr(s.requests, "get", lambda url, **k: Reponse(status_code=200, text="<form action='/errors/validateCaptcha'>"))
    with pytest.raises(RuntimeError, match="bloquée"):
        s.lire("scrapedo", "B0TEST0001", main._parse_zenrows_amazon_html, main.parse_amazon_price)
    # Page sans prix : jamais « épuisé » sur la foi d'un service de secours.
    monkeypatch.setattr(s.requests, "get", lambda url, **k: Reponse(status_code=200, text='<span id="productTitle">Carte</span>'))
    with pytest.raises(RuntimeError, match="prix non lisible"):
        s.lire("scrapedo", "B0TEST0001", main._parse_zenrows_amazon_html, main.parse_amazon_price)


def test_passage_reprend_les_fiches_restantes(client, monkeypatch):
    lignes = main.get_client().execute(
        "SELECT id, asin FROM components WHERE asin IS NOT NULL AND asin != '' ORDER BY id").rows
    appliques = []
    monkeypatch.setattr(main, "DAILY_ROTATION_START", datetime(2000, 1, 1))
    monkeypatch.setattr(main, "PRIX_PASSAGES_HEURES", (2,))
    for var in ("APIFY_API_TOKEN", "BRIGHTDATA_API_TOKEN", "ZENROWS_API_KEY"):
        monkeypatch.setattr(main, var, "")
    monkeypatch.setattr(main, "_composants_prioritaires", lambda: set())
    monkeypatch.setattr(main, "_composants_sous_alerte", lambda: set())
    monkeypatch.setattr(main, "_capacite_prix", lambda: {"total_par_jour": 1000, "services": []})
    c = main.get_client()
    main._preparer_releves(c)
    c.execute("DELETE FROM verifications_prix")
    c.close()
    main._state_set("releve_prets", {})
    monkeypatch.setattr(main, "_part_secours", lambda nom, passages: (2, 100) if nom == "scrapingant" else (0, None))
    monkeypatch.setattr(main.scrapers_secours, "lire", lambda nom, asin, *a: {"prix": 50.0, "lien": None})
    monkeypatch.setattr(main.scrapers_secours, "credits_restants", lambda nom: 80)
    monkeypatch.setattr(main, "_apply_amazon_price_info", lambda client, cid, *a, **k: appliques.append((cid, k["source_label"])) or
                        {"error": None, "remis_en_stock": False, "passe_epuise": False})
    main._state_set("secours_cout", {})
    stats = main._run_daily_price_refresh_rotation()
    assert [src for _, src in appliques] == ["ScrapingAnt", "ScrapingAnt"]
    assert stats["secours"]["scrapingant"] == 2
    assert main._state_get("secours_cout", {})["scrapingant"] == 10   # (100 - 80) / 2 fiches
    assert len(lignes) > 2


def test_jours_jusqu_au_renouvellement(monkeypatch):
    from datetime import datetime, timedelta, timezone
    maintenant = datetime.now(timezone.utc)
    iso = lambda d: d.isoformat().replace("+00:00", "Z")
    monkeypatch.setenv("SCRAPERAPI_KEY", "k" * 32)
    monkeypatch.setenv("SCRAPINGANT_KEY", "k" * 32)
    # Essai ScraperAPI commencé il y a 2 jours : crédits à dépenser dans les 5 jours, pas en un mois.
    monkeypatch.setattr(s.requests, "get", lambda url, **k: Reponse(status_code=200, text="", donnees={
        "requestLimit": 5000, "requestCount": 5, "creditsLeft": 4995,
        "subscriptionDate": iso(maintenant - timedelta(days=2)), "nextBillingDate": iso(maintenant + timedelta(days=28))}))
    assert s.etat("scraperapi") == {"reste": 4995, "jours": 5}
    # Offre gratuite ordinaire (1 000 crédits) : jusqu'à la prochaine facturation.
    monkeypatch.setattr(s.requests, "get", lambda url, **k: Reponse(status_code=200, text="", donnees={
        "requestLimit": 1000, "requestCount": 0, "creditsLeft": 1000,
        "subscriptionDate": iso(maintenant - timedelta(days=40)), "nextBillingDate": iso(maintenant + timedelta(days=20))}))
    assert s.etat("scraperapi")["jours"] == 20
    monkeypatch.setattr(s.requests, "get", lambda url, **k: Reponse(status_code=200, text="", donnees={
        "plan_total_credits": 10000, "remained_credits": 9974, "end_date": (maintenant + timedelta(days=30)).isoformat()}))
    assert s.etat("scrapingant") == {"reste": 9974, "jours": 30}
