"""Liens que l'assistant fait afficher : fabriqués par le serveur, code partenaire compris."""
import main


def _pieces():
    return {
        1: {"id": 1, "categorie": "CPU", "nom": "AMD Ryzen 5 7600", "asin": "B0BMQJWBDM", "page": "/composant/1-ryzen", "prix_marche": []},
        2: {"id": 2, "categorie": "GPU", "nom": "RTX 5060", "asin": "B0F1234567", "page": "/composant/2-rtx",
            "prix_marche": [{"vendeur": "Amazon", "lien": "https://www.amazon.fr/dp/B0F1234567"}]},
        3: {"id": 3, "categorie": "Boîtier", "nom": "Sans ASIN", "asin": None, "page": None, "prix_marche": []},
    }


def test_panier_de_la_config_meme_si_l_ia_l_oublie(monkeypatch):
    monkeypatch.setattr(main, "AMAZON_ASSOCIATE_TAG", "tag-21")
    liens = main._resoudre_liens([], "donne moi le lien amazon de cette config", [1, 2, 3, None], [], _pieces())
    assert len(liens) == 1 and liens[0]["externe"]
    url = liens[0]["url"]
    assert "cart/add.html" in url and "AssociateTag=tag-21" in url and "ASIN.1=B0BMQJWBDM" in url and "ASIN.2=B0F1234567" in url
    assert "ASIN.3" not in url and "(2 articles)" in liens[0]["libelle"]


def test_liens_demandes_par_l_ia(monkeypatch):
    monkeypatch.setattr(main, "AMAZON_ASSOCIATE_TAG", "tag-21")
    liens = main._resoudre_liens(["amazon:2", "fiche:1", "partage", "configurateur", "n'importe quoi", "amazon:999"],
                                 "et pour la carte graphique ?", [1, 2], [], _pieces())
    urls = [l["url"] for l in liens]
    assert urls[0] == "https://www.amazon.fr/dp/B0F1234567?tag=tag-21"
    assert "/composant/1-ryzen" in urls and "/configurateur" in urls
    assert any(u.endswith("/partage?c=1-2") for u in urls) and len(liens) == 4
