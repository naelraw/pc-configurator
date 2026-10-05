"""Couleur demandée respectée par l'assistant, et version du site pour les mises à jour en direct."""
import main


def test_couleur_lue_dans_le_nom_ou_les_caracteristiques():
    assert main._couleur({"nom": "Corsair 4000D Airflow White"}) == "blanc"
    assert main._couleur({"nom": "NZXT H5 Flow", "specs": {"couleur": "Blanc"}}) == "blanc"
    assert main._couleur({"nom": "be quiet! Pure Base 500DX Black"}) == "noir"
    assert main._couleur({"nom": "Fractal Design North"}) is None


def test_couleur_demandee():
    assert main._couleur_demandee("je veux un boîtier blanc") == "blanc"
    assert main._couleur_demandee("une config toute blanche avec RTX") == "blanc"
    assert main._couleur_demandee("un ventirad noir et blanc") == "blanc"
    assert main._couleur_demandee("config 1000 € pour Fortnite") is None


def test_l_ia_voit_les_composants_de_la_couleur_demandee():
    composants = [
        {"id": 1, "categorie": "Boîtier", "nom": "Corsair 4000D Airflow White", "prix_indicatif": 95, "en_stock": True, "specs": {}},
        {"id": 2, "categorie": "Boîtier", "nom": "Corsair 4000D Airflow Black", "prix_indicatif": 89, "en_stock": True, "specs": {}},
        {"id": 3, "categorie": "Refroidissement", "nom": "ARCTIC Freezer 36 A-RGB White", "prix_indicatif": 35, "en_stock": True, "specs": {}},
        {"id": 4, "categorie": "Boîtier", "nom": "NZXT H5 Flow", "prix_indicatif": 90, "en_stock": False, "specs": {"couleur": "Blanc"}},
    ]
    assert [c["id"] for c in main._composants_de_couleur("blanc", composants, "un boîtier blanc")] == [1]
    assert {c["id"] for c in main._composants_de_couleur("blanc", composants, "config blanche")} == {1, 3}
    assert "couleur=blanc" in main._ligne_composant(composants[0])
    assert "couleur=" not in main._ligne_composant({"id": 9, "categorie": "CPU", "nom": "AMD Ryzen 5 7600 White box", "prix_indicatif": 180, "specs": {}})


def test_version_du_site(client):
    r = client.get("/api/version")
    assert r.status_code == 200 and set(r.json()) == {"css", "pages"}
    assert r.headers["cache-control"] == "no-store"
