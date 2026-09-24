# Sauvegardes de PC Radar

## Ce qui tourne automatiquement (serveur Oracle)

| Minuterie systemd | Quand | Ce qu'elle fait |
|---|---|---|
| `pcradar-backup.timer` | chaque nuit, 3 h 30 UTC | `ops/backup_db.sh` : copie cohérente de la base dans `/home/ubuntu/backups/db/`, 14 jours gardés |
| `pcradar-offsite.timer` | chaque dimanche, 4 h 30 UTC | `ops/offsite_backup.py` : dernière copie **chiffrée** envoyée par e-mail à l'adresse du site |
| `pcradar-healthcheck.timer` | toutes les 5 minutes | `ops/healthcheck.py` : alerte e-mail si le site tombe, sauvegarde en retard ou disque plein |

## La clé de chiffrement

Elle est sur le serveur dans `/home/ubuntu/backups/.passphrase`. **Garde-en une copie ailleurs**
(gestionnaire de mots de passe) : sans elle, les copies envoyées par e-mail sont illisibles.

## Restaurer depuis l'e-mail (serveur perdu)

1. Télécharger la pièce jointe `pcradar-AAAAMMJJ-HHMM.db.gz.enc` du dernier e-mail « Sauvegarde chiffrée ».
2. Enregistrer la clé dans un fichier `cle.txt`.
3. Déchiffrer puis décompresser :

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -in pcradar-AAAAMMJJ-HHMM.db.gz.enc -out pcradar.db.gz -pass file:cle.txt
gunzip pcradar.db.gz
```

4. Copier `pcradar.db` dans `data/` sur le nouveau serveur (service arrêté), puis redémarrer le service.

## Restaurer une sauvegarde quotidienne (serveur intact)

```bash
sudo systemctl stop pc-configurator
gunzip -c /home/ubuntu/backups/db/pcradar-AAAAMMJJ-HHMM.db.gz > /home/ubuntu/pc-configurator/data/pcradar.db
rm -f /home/ubuntu/pc-configurator/data/pcradar.db-wal /home/ubuntu/pc-configurator/data/pcradar.db-shm
sudo systemctl start pc-configurator
```
