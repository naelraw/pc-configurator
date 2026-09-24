#!/usr/bin/env bash
# Sauvegarde quotidienne de la base PC Radar (lancée par cron chaque nuit).
# ".backup" de sqlite3 produit une copie cohérente même pendant que le site
# écrit (mode WAL) — un simple "cp" pourrait rater les dernières écritures.
set -euo pipefail
umask 077  # les sauvegardes contiennent des données personnelles

DB=/home/ubuntu/pc-configurator/data/pcradar.db
DEST=/home/ubuntu/backups/db
KEEP_DAYS=14

mkdir -p "$DEST"
STAMP=$(date +%Y%m%d-%H%M)
TMP="$DEST/pcradar-$STAMP.db"

sqlite3 "$DB" ".backup '$TMP'"
CHECK=$(sqlite3 "$TMP" "PRAGMA integrity_check;")
if [ "$CHECK" != "ok" ]; then
    echo "$(date -Is) ÉCHEC intégrité : $CHECK"
    rm -f "$TMP"
    exit 1
fi
gzip -9 "$TMP"
find "$DEST" -name 'pcradar-*.db.gz' -mtime +"$KEEP_DAYS" -delete
echo "$(date -Is) ok $(du -h "$TMP.gz" | cut -f1) — $(ls "$DEST"/pcradar-*.db.gz | wc -l) sauvegarde(s) gardée(s)"
