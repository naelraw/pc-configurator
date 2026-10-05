#!/bin/bash
# Change le mot de passe admin (ADMIN_SECRET dans .env) sans qu'il passe par
# une conversation ou un fichier du dépôt.
# Usage (depuis le PC) :
#   ssh -t -i <clé ssh> ubuntu@88.96.49.31 "bash pc-configurator/ops/set_admin_secret.sh"
# Entrée vide : un mot de passe solide est généré et affiché UNE fois, dans ce
# terminal seulement (à copier dans un gestionnaire de mots de passe).
cd /home/ubuntu/pc-configurator || exit 1
echo "Nouveau mot de passe admin :"
echo "  - appuie sur Entree pour en generer un solide automatiquement (recommande)"
echo "  - ou tape le tien (16 caracteres minimum, rien ne s'affiche pendant la saisie)"
read -r -s -p "> " S
echo
S=$(printf '%s' "$S" | tr -d '\r\n')
if [ -z "$S" ]; then
  S=$(venv/bin/python -c "import secrets, string; a = string.ascii_letters + string.digits; print(''.join(secrets.choice(a) for _ in range(32)))")
  GENERE=1
fi
if [ ${#S} -lt 16 ]; then
  echo "ERREUR : ${#S} caracteres, il en faut au moins 16. Rien n'a ete modifie."
  exit 1
fi
cp .env ".env.avant-admin-$(date +%H%M%S)"
chmod 600 .env.avant-admin-*
sed -i '/^ADMIN_SECRET=/d' .env
printf 'ADMIN_SECRET=%s\n' "$S" >> .env
sudo systemctl restart pc-configurator && echo "Site redemarre avec le nouveau mot de passe admin."
if [ -n "$GENERE" ]; then
  echo
  echo "Ton nouveau mot de passe admin (copie-le maintenant dans ton gestionnaire de mots de passe) :"
  echo
  echo "    $S"
  echo
  echo "Il ne sera plus jamais affiche. Pense a le remettre aussi dans l'extension PC Radar."
fi
