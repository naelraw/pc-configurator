import auto_catalogue as a


def _c(i, cat, nom, specs=None, gid=None, prix=100.0):
    return {"id": i, "categorie": cat, "nom": nom, "specs": specs or {}, "groupe_id": gid or i,
            "prix_indicatif": prix, "en_stock": True}


def test_lecture_du_nom():
    assert a.socket_chipset(a.chipset("ASUS Prime B650M-A WiFi")) == "AM5"
    assert a.format_carte_mere("ASUS ROG Strix B850-I Gaming WiFi") == "Mini-ITX"
    assert a.format_carte_mere("GIGABYTE B760M DS3H DDR4") == "Micro-ATX"
    assert a.socket_cpu("Intel Core Ultra 7 265KF") == "LGA1851"
    assert a.socket_cpu("AMD Ryzen 5 5500") == "AM4"
    assert a.puce_gpu("ASUS Dual RTX4060Ti OC") == "RTX 4060 Ti"


def test_completion_sure_et_suggestions():
    cat = [
        _c(1, "Carte mère", "MSI PRO B650M-P", {}),
        _c(2, "Alimentation", "Corsair RM850e 850W", {}),
        _c(3, "GPU", "MSI RTX 5060 Ti Ventus", {"puce": "RTX 5060 Ti", "vram_go": 8}),
        _c(4, "GPU", "ASUS Dual RTX 5060 Ti", {"puce": "RTX 5060 Ti", "vram_go": 8, "tdp": 180, "longueur_mm": 229}),
        _c(5, "GPU", "PNY RTX 5060 Ti", {"puce": "RTX 5060 Ti", "vram_go": 8, "tdp": 180, "longueur_mm": 299}),
    ]
    sur, _ = a.deviner(cat[0], cat)
    assert sur["socket"][0] == "AM5" and sur["ram_type"][0] == "DDR5" and sur["format"][0] == "Micro-ATX"
    sur, _ = a.deviner(cat[1], cat)
    assert sur["wattage"][0] == 850
    sur, _ = a.deviner(cat[2], cat)
    assert sur["tdp"][0] == 180 and "longueur_mm" not in sur   # la longueur ne se devine pas


def test_rattachement_seulement_si_caracteristiques_identiques():
    x = _c(1, "GPU", "MSI RTX 4060 Ventus 2X Black", {"puce": "RTX 4060", "vram_go": 8})
    y = _c(2, "GPU", "MSI RTX 4060 Ventus 2X White", {"puce": "RTX 4060", "vram_go": 8})
    z = _c(3, "GPU", "MSI RTX 4060 Ventus 2X", {"puce": "RTX 4060", "vram_go": 16})
    paire = {"id": 1, "proche_id": 2, "score": 0.8}
    assert a.rattachements_surs([paire], [x, y, z]) == [paire]
    assert a.rattachements_surs([{"id": 1, "proche_id": 3, "score": 0.8}], [x, y, z]) == []


def test_prix_un_peu_cher_ignore_seulement_si_offre_moins_chere():
    cat = [_c(1, "RAM", "Kit A", prix=150, gid=9), _c(2, "RAM", "Kit A bis", prix=100, gid=9)]
    s = {"id": 1, "prix": 150, "ratio": 1.7, "motif": "bien plus cher que les autres annonces du même produit"}
    assert a.prix_a_ignorer([s], cat) == [s]
    assert a.prix_a_ignorer([{**s, "ratio": 2.5}], cat) == []
