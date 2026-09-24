"""
Schéma de validation des specs par catégorie de composant.

Ces champs sont ceux EXACTEMENT lus par compatibility.py. Un champ manquant
est toléré (enregistrement autorisé, à compléter plus tard) — compatibility.py
ignore alors silencieusement la vérification correspondante plutôt que de
planter. Un champ PRÉSENT mais du mauvais type reste en revanche refusé à
l'écriture : ce qui est enregistré est toujours du bon type, même incomplet.

type attendu :
    "str"       -> chaîne de caractères
    "number"    -> int ou float
    "list[str]" -> liste de chaînes de caractères
"""

REQUIRED_FIELDS = {
    "CPU": {
        "socket": "str",
        "tdp": "number",
    },
    "Carte mère": {
        "socket": "str",
        "ram_type": "str",
        "format": "str",
        "m2_slots": "number",
        "sata_ports": "number",
    },
    "RAM": {
        "type": "str",
    },
    "Boîtier": {
        "formats_supportes": "list[str]",
        "gpu_max_length_mm": "number",
        "cpu_cooler_max_height_mm": "number",
    },
    "Alimentation": {
        "wattage": "number",
    },
    "GPU": {
        "tdp": "number",
        "longueur_mm": "number",
    },
    "Stockage": {
        "type": "str",  # doit être "NVMe" ou "SATA"
    },
    "Refroidissement": {
        "sockets_supportes": "list[str]",
        "hauteur_mm": "number",
    },
    # Catégorie "périphériques/accessoires" unique : n'entre dans aucune
    # vérification de compatibility.py (pas de champ requis), sert juste à
    # cataloguer et comparer les prix de tout ce qui s'achète autour d'un PC
    # sans être une pièce interne (écran, clavier, souris, casque...) —
    # une seule catégorie plutôt qu'une par type d'accessoire, pour rester
    # simple tant que le site ne vend pas des dizaines de références de
    # chaque type.
    "Accessoire": {},
}

VALID_STOCKAGE_TYPES = {"NVMe", "SATA"}


def validate_component(component, index):
    """
    Valide un composant du fichier seed. Retourne une liste de messages
    d'erreur (vide = composant valide). `index` sert juste à identifier le
    composant fautif dans le message d'erreur (position dans le fichier).
    """
    errors = []
    label = f"[composant #{index}]"

    nom = component.get("nom")
    categorie = component.get("categorie")
    prix = component.get("prix_indicatif")
    specs = component.get("specs")

    if not nom or not isinstance(nom, str):
        errors.append(f"{label} 'nom' manquant ou invalide.")
        label = f"[composant #{index} - {categorie or '?'}]"
    else:
        label = f"[{categorie or '?'}: {nom}]"

    if not categorie or categorie not in REQUIRED_FIELDS:
        valid_cats = ", ".join(REQUIRED_FIELDS.keys())
        errors.append(f"{label} 'categorie' manquante ou inconnue. Valeurs valides : {valid_cats}")
        return errors  # inutile de continuer sans catégorie valide

    if prix is None or not isinstance(prix, (int, float)):
        errors.append(f"{label} 'prix_indicatif' manquant ou non numérique.")

    if not isinstance(specs, dict):
        errors.append(f"{label} 'specs' manquant ou n'est pas un objet.")
        return errors

    # Un champ requis manquant N'EST PLUS une erreur bloquante : on autorise
    # l'enregistrement de composants incomplets (à finir de remplir plus
    # tard), plutôt que de forcer à tout avoir dès le départ. En
    # contrepartie, compatibility.py ignore silencieusement (sans planter)
    # toute vérification qui dépendrait d'un champ absent — jamais de faux
    # "compatible" affirmé, juste "pas assez d'infos pour vérifier".
    # Un champ PRÉSENT reste en revanche validé normalement : pas question
    # de laisser une valeur du mauvais type se glisser en base.
    required = REQUIRED_FIELDS[categorie]
    for field, expected_type in required.items():
        if field not in specs or specs[field] in (None, ""):
            continue

        value = specs[field]
        if expected_type == "str" and not isinstance(value, str):
            errors.append(f"{label} 'specs.{field}' doit être une chaîne de caractères.")
        elif expected_type == "number" and not isinstance(value, (int, float)):
            errors.append(f"{label} 'specs.{field}' doit être un nombre.")
        elif expected_type == "list[str]":
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                errors.append(f"{label} 'specs.{field}' doit être une liste de chaînes.")

    if categorie == "Stockage" and "type" in specs:
        if specs["type"] not in VALID_STOCKAGE_TYPES:
            errors.append(f"{label} 'specs.type' doit être 'NVMe' ou 'SATA' (reçu: {specs['type']!r}).")

    prix_marche = component.get("prix_marche")
    if prix_marche is not None:
        errors.extend(validate_prix_marche(prix_marche, label))

    image_url = component.get("image_url")
    if image_url is not None:
        # http(s):// pour une image classique, ou data:image/... pour une
        # image détourée automatiquement (encodée directement en base, pas
        # de stockage de fichiers permanent sur le serveur).
        if not isinstance(image_url, str) or not image_url.startswith(("http://", "https://", "data:image/")):
            errors.append(f"{label} 'image_url' doit être une URL valide (http(s)://...) ou une image détourée (data:image/...).")

    return errors


def validate_prix_marche(prix_marche, label):
    """
    Valide le champ optionnel 'prix_marche' : une liste de relevés de prix
    chez différents revendeurs, saisis manuellement (jamais scrapés en
    continu). Chaque relevé doit avoir : vendeur (str), prix (number),
    lien (str, URL), date_releve (str, ex: "2026-09-12").
    """
    errors = []

    if not isinstance(prix_marche, list):
        errors.append(f"{label} 'prix_marche' doit être une liste.")
        return errors

    required_relevé_fields = {"vendeur": "str", "prix": "number", "lien": "str", "date_releve": "str"}

    for i, releve in enumerate(prix_marche, start=1):
        releve_label = f"{label} prix_marche[{i}]"
        if not isinstance(releve, dict):
            errors.append(f"{releve_label} doit être un objet.")
            continue

        for field, expected_type in required_relevé_fields.items():
            if field not in releve:
                errors.append(f"{releve_label} champ '{field}' manquant.")
                continue
            value = releve[field]
            if expected_type == "str" and not isinstance(value, str):
                errors.append(f"{releve_label} '{field}' doit être une chaîne de caractères.")
            elif expected_type == "number" and not isinstance(value, (int, float)):
                errors.append(f"{releve_label} '{field}' doit être un nombre.")

        if "prix" in releve and isinstance(releve["prix"], (int, float)) and releve["prix"] <= 0:
            errors.append(f"{releve_label} 'prix' doit être positif.")

        if "lien" in releve and isinstance(releve["lien"], str) and not releve["lien"].startswith(("http://", "https://")):
            errors.append(f"{releve_label} 'lien' doit être une URL valide (http(s)://...).")

    return errors
