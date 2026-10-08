import main


def test_prix_texte_formats_amazon():
    cas = {"299,99 €": 299.99, "1.063,05 €": 1063.05, "1 063,05 €": 1063.05, "1 246,00 €": 1246.0,
           "$1,299.99": 1299.99, "1,246": 1246.0, "1.246": 1246.0, "6.299": 6299.0, "1.234.567": 1234567.0,
           "49.9": 49.9, "49,90": 49.9, "1063.05": 1063.05, "12": 12.0, "1.335,90 €": 1335.9}
    for brut, attendu in cas.items():
        assert main.parse_amazon_price(brut) == attendu, brut
    assert main.parse_amazon_price({"displayString": "1.335,90 €"}) == 1335.9
    assert main.parse_amazon_price(1335.9) == 1335.9


def test_zenrows_prix_a_quatre_chiffres():
    for entier in ("1&nbsp;063", "1 063", "1.063", "1 063", "1&#8239;063", "1063"):
        html = ('<div id="corePriceDisplay_desktop_feature_div"><span class="a-price-whole">' + entier +
                '<span class="a-price-decimal">,</span></span><span class="a-price-fraction">05</span>'
                '<div id="availability"><span>En stock</span></div>')
        assert main._parse_zenrows_amazon_html(html, "B0TEST")["prix"] == 1063.05, entier
    html = ('<div id="corePriceDisplay_desktop_feature_div"><span class="a-price-whole">89<span class="a-price-decimal">,'
            '</span></span><span class="a-price-fraction">99</span><div id="availability">En stock</div>')
    assert main._parse_zenrows_amazon_html(html, "B0TEST")["prix"] == 89.99
