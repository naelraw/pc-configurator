import emails


def test_chaque_email_a_sa_banniere_et_son_texte():
    mails = [
        emails.bienvenue("nael@example.com"),
        emails.alerte_composant_activee("AMD Ryzen 5 7600X", 164.46, 150, "/composant/1-ryzen"),
        emails.alerte_config_activee("Ma config <gaming>", 812.5, 780, 12),
        emails.baisse_prix_composant("RTX 5060", 329.62, 350, "https://www.amazon.fr/dp/X", "/composant/2-rtx"),
        emails.baisse_prix_config("Config", 796.4, 800, [("CPU", "Ryzen 5 7600X", 164.46)], 12),
        emails.compte_supprime(),
        emails.controle_admin([{"nom": "X", "categorie": "GPU", "prix": 900, "reference": 400, "motif": "x", "page": "/"}], "https://pcradar.tech/admin"),
    ]
    for sujet, texte, html_body, png in mails:
        assert sujet and texte and png[:8] == b"\x89PNG\r\n\x1a\n"
        assert 'src="cid:banniere"' in html_body and 'bgcolor="#0e0f11"' in html_body and '<a href="https://pcradar.tech" style="display:block;text-decoration:none;"><img src="cid:banniere"' in html_body
    # Le nom saisi par l'utilisateur est échappé dans le HTML.
    assert "&lt;gaming&gt;" in mails[2][2] and "<gaming>" not in mails[2][2]
