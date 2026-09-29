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
        assert 'src="cid:banniere"' in html_body and 'bgcolor="#141517"' in html_body and '<a href="https://pcradar.tech" style="display:block;text-decoration:none;"><img src="cid:banniere"' in html_body
    # Le nom saisi par l'utilisateur est échappé dans le HTML.
    assert "&lt;gaming&gt;" in mails[2][2] and "<gaming>" not in mails[2][2]


def test_secours_gmail_si_brevo_echoue(monkeypatch):
    import smtplib, main
    envois = []

    class FauxSMTP:
        def __init__(self, host, port, timeout=None):
            self.host = host
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): pass
        def login(self, u, p): pass
        def send_message(self, m):
            if self.host == "smtp-relay.brevo.com":
                raise smtplib.SMTPDataError(450, b"quota journalier atteint")
            envois.append((self.host, m["From"]))

    monkeypatch.setattr(smtplib, "SMTP", FauxSMTP)
    for k, v in {"SMTP_HOST": "smtp-relay.brevo.com", "SMTP_FROM": "contact@pcradar.tech",
                 "SMTP_SECOURS_HOST": "smtp.gmail.com", "SMTP_SECOURS_FROM": "contact.pcradar@gmail.com"}.items():
        monkeypatch.setattr(main, k, v)
    assert main.send_email("x@example.com", "Test", "texte")
    assert envois == [("smtp.gmail.com", "PC Radar <contact.pcradar@gmail.com>")]
