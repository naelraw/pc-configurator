#!/bin/bash
# Enregistre la clé SMTP Brevo dans .env sans l'afficher, puis vérifie que
# Brevo l'accepte (connexion seulement, aucun e-mail envoyé).
# Usage (depuis le PC) :
#   ssh -t -i <clé ssh> ubuntu@88.96.49.31 "bash pc-configurator/ops/set_smtp_key.sh"
cd /home/ubuntu/pc-configurator || exit 1
read -r -s -p "Colle la cle SMTP Brevo (clic droit > Coller, UNE seule fois) puis Entree : " K
echo
K=$(printf '%s' "$K" | tr -d '\r\n\t ')
# Rien ne s'affiche pendant le collage : si la clé a été collée plusieurs
# fois de suite, on n'en garde qu'une copie.
PREMIERE=$(printf '%s' "$K" | grep -o 'xsmtpsib-[^x]*' | head -1)
[ -n "$PREMIERE" ] && [ "$(printf '%s' "$K" | sed "s/$PREMIERE//g")" = "" ] && K="$PREMIERE"
case "$K" in
  xsmtpsib-*) ;;
  *) echo "ERREUR : la cle recue fait ${#K} caracteres et ne commence pas par xsmtpsib-. Rien n'a ete modifie."; exit 1 ;;
esac
cp .env ".env.avant-cle-$(date +%H%M%S)"
sed -i '/^SMTP_PASSWORD=/d' .env
printf 'SMTP_PASSWORD=%s\n' "$K" >> .env
venv/bin/python - <<'PY'
import smtplib
from dotenv import dotenv_values
e = dotenv_values(".env")
try:
    with smtplib.SMTP(e["SMTP_HOST"], int(e.get("SMTP_PORT") or 587), timeout=20) as s:
        s.starttls(); s.login(e["SMTP_USER"], e["SMTP_PASSWORD"])
    print("OK : Brevo accepte la cle.")
except Exception as err:
    print("ECHEC : Brevo refuse la connexion :", err)
    print("Verifie dans Brevo que la cle est active et que l'adresse 88.96.49.31 est autorisee (Securite > Adresses IP autorisees).")
PY
sudo systemctl restart pc-configurator && echo "Site redemarre."
