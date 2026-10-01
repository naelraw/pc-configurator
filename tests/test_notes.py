import notes


def _c(categorie, nom, **specs):
    return {"categorie": categorie, "nom": nom, "specs": specs}


def test_gpu_variante_memoire_video():
    """Une RTX 5060 Ti 8 Go ne doit pas avoir la note de la 16 Go."""
    huit = notes.noter(_c("GPU", "RTX 5060 Ti 8GB", vram_go=8))["note"]
    seize = notes.noter(_c("GPU", "RTX 5060 Ti 16GB", vram_go=16))["note"]
    assert huit < seize


def test_gpu_meilleure_carte_a_100():
    assert notes.noter(_c("GPU", "GeForce RTX 5090 32 Go", vram_go=32))["note"] == 100


def test_cpu_ryzen_9600_reconnu():
    assert notes.noter(_c("CPU", "AMD Ryzen 5 9600"))["note"] > 0


def test_ram_ddr5_rapide_devant_ddr4():
    ddr5 = notes.noter(_c("RAM", "x", capacite_go=32, frequence_mt_s=6000, latence_cl=30, type="DDR5"))["note"]
    ddr4 = notes.noter(_c("RAM", "x", capacite_go=32, frequence_mt_s=3200, latence_cl=16, type="DDR4"))["note"]
    assert ddr5 > ddr4


def test_ssd_pcie4_devant_sata():
    nvme = notes.noter(_c("Stockage", "x", lecture_mo_s=7000, capacite_go=1000, type="NVMe"))["note"]
    sata = notes.noter(_c("Stockage", "x", lecture_mo_s=560, capacite_go=1000, type="SATA"))["note"]
    assert nvme > sata


def test_alimentation_gold_modulaire_devant_bronze():
    gold = notes.noter(_c("Alimentation", "x", certification="80 PLUS Gold", modularite="Entièrement modulaire"))["note"]
    bronze = notes.noter(_c("Alimentation", "x", certification="80 PLUS Bronze", modularite="Non modulaire"))["note"]
    assert gold > bronze


def test_alimentation_sans_certification_notee():
    assert notes.noter(_c("Alimentation", "Tacens Anima 750W", wattage=750))["note"] <= 30


def test_ventirad_double_tour_devant_simple():
    double = notes.noter(_c("Refroidissement", "Peerless Assassin 120 SE", type_refroidissement="Ventirad", hauteur_mm=155))
    simple = notes.noter(_c("Refroidissement", "Assassin X 120 SE", type_refroidissement="Ventirad", hauteur_mm=148))
    assert double["note"] > simple["note"]


def test_ventilateurs_au_format_texte():
    n = notes.noter(_c("Refroidissement", "x", type_refroidissement="Ventirad", hauteur_mm=154, ventilateurs="2 x 120 mm"))
    assert n is not None


def test_ventilateur_de_boitier_sans_note():
    assert notes.noter(_c("Refroidissement", "ARCTIC P12", type_refroidissement="Ventilateur de boîtier")) is None


def test_watercooling_360_devant_240():
    n360 = notes.noter(_c("Refroidissement", "x", type_refroidissement="Watercooling AIO", radiateur_mm=360))["note"]
    n240 = notes.noter(_c("Refroidissement", "x", type_refroidissement="Watercooling AIO", radiateur_mm=240))["note"]
    assert n360 > n240


def test_carte_mere_x870e_devant_a620():
    haut = notes.noter(_c("Carte mère", "x", chipset="AMD X870E", m2_slots=4, wifi="Wi-Fi 7", ram_type="DDR5", slots_ram=4))["note"]
    bas = notes.noter(_c("Carte mère", "x", chipset="AMD A620", m2_slots=1, wifi="Non", ram_type="DDR5", slots_ram=2))["note"]
    assert haut > bas


def test_critere_manquant_note_partielle():
    n = notes.noter(_c("Boîtier", "x", gpu_max_length_mm=400, cpu_cooler_max_height_mm=170))
    assert n["partielle"] is True and 0 <= n["note"] <= 100
