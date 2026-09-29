#!/bin/bash
# Serveur d'envoi de secours (Gmail) : enregistre le mot de passe
# d'application de contact.pcradar@gmail.com sans l'afficher, puis vérifie
# que Gmail l'accepte. Utilisé si Brevo échoue (quota du jour épuisé...).
# Usage (depuis le PC) :
#   ssh -t -i <clé ssh> ubuntu@88.96.49.31 "bash pc-configurator/ops/set_gmail_secours.sh"
cd /home/ubuntu/pc-configurator || exit 1
read -r -s -p "Colle le mot de passe d'application Gmail (16 lettres, clic droit > Coller, une seule fois) puis Entree : " P
echo
P=$(printf '%s' "$P" | tr -d ' \r\n\t')
# Collé plusieurs fois (rien ne s'affiche) : n'en garder qu'une copie.
[ ${#P} -gt 16 ] && [ $(( ${#P} % 16 )) -eq 0 ] && [ "$(printf '%s' "$P" | sed "s/${P:0:16}//g")" = "" ] && P=${P:0:16}
if ! printf '%s' "$P" | grep -qE '^[a-zA-Z]{16}$'; then
  echo "ERREUR : il faut 16 lettres (recu : ${#P} caracteres). Rien n'a ete modifie."; exit 1
fi
cp .env ".env.avant-secours-$(date +%H%M%S)"
sed -i -E '/^SMTP_SECOURS_(HOST|PORT|USER|PASSWORD|FROM)=/d' .env
printf 'SMTP_SECOURS_HOST=smtp.gmail.com\nSMTP_SECOURS_PORT=587\nSMTP_SECOURS_USER=contact.pcradar@gmail.com\nSMTP_SECOURS_PASSWORD=%s\nSMTP_SECOURS_FROM=contact.pcradar@gmail.com\n' "$P" >> .env
chmod 600 .env .env.*
venv/bin/python - <<'PY'
import smtplib
from dotenv import dotenv_values
e = dotenv_values(".env")
try:
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as s:
        s.starttls(); s.login(e["SMTP_SECOURS_USER"], e["SMTP_SECOURS_PASSWORD"])
    print("OK : Gmail accepte le mot de passe. Le secours est pret.")
except Exception as err:
    print("ECHEC : Gmail refuse :", err)
PY
sudo systemctl restart pc-configurator && echo "Site redemarre."
