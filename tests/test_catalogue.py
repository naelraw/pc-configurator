import pytest

from compatibility import verifier_compatibilite
from conftest import component


def test_catalogue_compresse_et_cache(client, catalog):
    r = client.get("/api/components", headers={"Accept-Encoding": "gzip"})
    assert r.headers["content-encoding"] == "gzip"
    assert client.get("/api/components", headers={"If-None-Match": r.headers["etag"]}).status_code == 304
    assert len(catalog) == 16
    assert all(c["page"].startswith(f"/composant/{c['id']}-") for c in catalog)


def test_compatibilite():
    cpu = {"socket": "AM4", "tdp": 65}
    mb = {"socket": "AM4", "ram_type": "DDR4", "format": "ATX", "m2_slots": 2, "sata_ports": 4}
    ram = {"type": "DDR4"}
    case = {"formats_supportes": ["ATX"], "gpu_max_length_mm": 300}
    psu = {"wattage": 650}
    gpu = {"tdp": 200, "longueur_mm": 250}
    cooler = {"sockets_supportes": ["AM4"], "hauteur_mm": 150}
    assert verifier_compatibilite(cpu, mb, ram, case, psu, gpu, [{"type": "NVMe"}], cooler) == []
    assert verifier_compatibilite({**cpu, "socket": "AM5"}, mb, ram, case, psu, gpu, [], cooler)
    assert verifier_compatibilite(cpu, mb, {"type": "DDR5"}, case, psu, gpu, [], cooler)
    assert verifier_compatibilite(cpu, mb, ram, case, {"wattage": 300}, gpu, [], cooler)
    assert verifier_compatibilite(cpu, mb, ram, case, psu, {**gpu, "longueur_mm": 350}, [], cooler)
    # Watercooling (pas de hauteur) : le socket est quand même vérifié.
    aio = {"sockets_supportes": ["AM5"]}
    assert verifier_compatibilite(cpu, mb, ram, case, psu, gpu, [], aio)
    # Carte mère sans slots M.2 connus : les ports SATA sont quand même vérifiés.
    mb_sata = {k: v for k, v in mb.items() if k != "m2_slots"}
    assert verifier_compatibilite(cpu, mb_sata, ram, case, psu, gpu, [{"type": "SATA"}] * 5, cooler)
    assert verifier_compatibilite(cpu, mb_sata, ram, case, psu, gpu, [{"type": "NVMe"}] * 5, cooler) == []


@pytest.mark.parametrize("titre, attendu", [
    ("【DDR4 RAM】 GIGASTONE Game Pro 32Go Kit(4x8Go) DDR4 3200MHz Intel XMP 2.0 AMD Ryzen", "RAM"),
    ("ASRock X870E Challenger WiFi", "Carte mère"),
    ("Intel Arc A770 16 Go carte graphique", "GPU"),
    ("AMD Ryzen 7 7700X processeur Radeon Graphics", "CPU"),
    ("ARCTIC Liquid Freezer III Pro 360", "Refroidissement"),
    ("Thermalright A70 ARGB Boîtier PC Verre Trempé", "Boîtier"),
    ("ASUS TUF Gaming - 1200W Gold, Alimentation modulaire", "Alimentation"),
])
def test_categorie_devinee_a_l_import(app_main, titre, attendu):
    assert app_main.guess_categorie_from_amazon(titre, []) == attendu


@pytest.mark.parametrize("nom, go, mhz", [
    ("Corsair Vengeance LPX 16 Go DDR4 3200 MHz", 16, 3200),
    ("Kingston FURY Beast 32 Go 6000 MT/s DDR5", 32, 6000),
    ("Corsair Vengeance RGB 32 Go DDR5 6000", 32, 6000),
])
def test_frequence_ram_reconnue(app_main, nom, go, mhz):
    assert app_main._parse_ram_specs(nom) == {"capacite_go": go, "frequence_mhz": mhz}


def test_comparateur_refuse_le_meme_composant(client, catalog):
    gpu = component(catalog, "RTX 4060")
    assert client.get(f"/api/compare-performance?id_a={gpu['id']}&id_b={gpu['id']}").status_code == 400
    autre = component(catalog, "RX 7600")
    assert client.get(f"/api/compare-performance?id_a={gpu['id']}&id_b={autre['id']}").status_code == 200


def test_estimation_fps(client, catalog):
    ids = {"CPU": component(catalog, "Ryzen 5 5600")["id"], "GPU": component(catalog, "RTX 4060")["id"]}
    r = client.post("/api/estimate-fps", json={"composants_json": ids, "jeux": ["Fortnite", "Cyberpunk 2077"]})
    assert r.status_code == 200
    assert all(res["couvert"] for res in r.json()["resultats"])


def test_tendances_de_prix(app_main, catalog):
    import sqlite3
    from datetime import datetime, timedelta, timezone
    from conftest import DB
    today = datetime.now(timezone.utc).date()     # la base date en UTC, comme le serveur
    ssd = component(catalog, "Crucial P3")          # prix du jour 70 €
    psu = component(catalog, "Corsair RM750e")      # prix du jour 95 €
    db = sqlite3.connect(DB)
    for d in range(1, 9):                            # 8 relevés, dont un plus bas à 65 €
        db.execute("insert or replace into price_history values (?, ?, ?)",
                   (ssd["id"], (today - timedelta(days=d)).isoformat(), 65 if d == 5 else 80))
    db.execute("insert or replace into price_history values (?, ?, ?)",
               (psu["id"], (today - timedelta(days=1)).isoformat(), 110))  # hier 110 € -> baisse
    db.commit()
    app_main.invalidate_catalog()
    by_id = {c["id"]: c for c in app_main.get_catalog()}
    t_ssd, t_psu = by_id[ssd["id"]]["tendance_prix"], by_id[psu["id"]]["tendance_prix"]
    assert t_ssd["releves_30j"] == 8 and t_ssd["min_30j"] == 65 and t_ssd["precedent"] == 80
    assert t_psu["precedent"] == 110
    assert by_id[component(catalog, "Ryzen 5 5600")["id"]]["tendance_prix"] is None
