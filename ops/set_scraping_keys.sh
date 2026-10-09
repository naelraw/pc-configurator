#!/bin/bash
# Enregistre les clés des services de lecture de pages de secours (ScraperAPI,
# ScrapingAnt, Scrape.do) dans .env sans les afficher, puis vérifie auprès de
# chaque service que la clé est acceptée (crédits restants, aucune page lue).
# Usage (depuis le PC) :
#   ssh -t -i <clé ssh> ubuntu@88.96.49.31 "bash pc-configurator/ops/set_scraping_keys.sh"
# Entrée vide = clé inchangée.
cd /home/ubuntu/pc-configurator || exit 1
cp .env ".env.avant-cles-scraping-$(date +%H%M%S)"

demander() {
  local nom="$1" var="$2" k
  read -r -s -p "Colle la cle $nom (clic droit > Coller, UNE seule fois) puis Entree (vide = inchangee) : " k
  echo
  k=$(printf '%s' "$k" | tr -d '\r\n\t ')
  [ -z "$k" ] && { echo "  $nom : inchangee."; return; }
  # Rien ne s'affiche pendant le collage : une clé collée deux fois de suite est ramenée à une copie.
  local moitie=$(( ${#k} / 2 ))
  if [ $(( ${#k} % 2 )) -eq 0 ] && [ "${k:0:$moitie}" = "${k:$moitie}" ]; then k="${k:0:$moitie}"; fi
  if ! printf '%s' "$k" | grep -Eq '^[A-Za-z0-9_-]{20,80}$'; then
    echo "  ERREUR : la cle $nom recue fait ${#k} caracteres et contient des caracteres inattendus. Non enregistree."
    return
  fi
  sed -i "/^$var=/d" .env
  printf '%s=%s\n' "$var" "$k" >> .env
  echo "  $nom : enregistree (${#k} caracteres)."
}

demander "ScraperAPI" SCRAPERAPI_KEY
demander "ScrapingAnt" SCRAPINGANT_KEY
demander "Scrape.do" SCRAPEDO_KEY

venv/bin/python - <<'PY'
from dotenv import dotenv_values
import os
os.environ.update({k: v for k, v in dotenv_values(".env").items() if v})
import scrapers_secours as s
for nom in s.TOUS:
    if not s.cle(nom):
        print(f"{s.NOMS[nom]} : pas de cle.")
        continue
    try:
        reste = s.credits_restants(nom)
        print(f"OK : {s.NOMS[nom]} accepte la cle ({reste} credits restants)." if reste is not None
              else f"? : {s.NOMS[nom]} n'a pas indique ses credits restants.")
    except Exception as err:
        print(f"ECHEC : {s.NOMS[nom]} refuse la cle ou ne repond pas : {err}")
PY
sudo systemctl restart pc-configurator && echo "Site redemarre."
