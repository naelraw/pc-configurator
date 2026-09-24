"""
Copie hors serveur de la base PC Radar (lancée chaque semaine par
pcradar-offsite.timer) : la dernière sauvegarde quotidienne est chiffrée
(AES-256, openssl) puis envoyée en pièce jointe à l'adresse du site.

Si le serveur disparaît, la base se récupère depuis la boîte mail avec la clé
gardée à part (voir ops/README-sauvegardes.md). Sans la clé, la pièce jointe
est illisible : la messagerie ne voit aucune donnée des comptes.
"""
import glob
import os
import smtplib
import subprocess
import sys
import tempfile
import time
from email.message import EmailMessage

APP_DIR = "/home/ubuntu/pc-configurator"
BACKUP_GLOB = "/home/ubuntu/backups/db/pcradar-*.db.gz"
PASSPHRASE_FILE = "/home/ubuntu/backups/.passphrase"


def load_env():
    env = {}
    with open(os.path.join(APP_DIR, ".env"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def log(message):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), message, flush=True)


def main():
    backups = sorted(glob.glob(BACKUP_GLOB), key=os.path.getmtime)
    if not backups:
        log("aucune sauvegarde à envoyer")
        return 1
    latest = backups[-1]
    if not os.path.exists(PASSPHRASE_FILE):
        log(f"clé absente ({PASSPHRASE_FILE}) : envoi annulé")
        return 1

    env = load_env()
    sender = env.get("SMTP_FROM") or env.get("SMTP_USER")
    with tempfile.TemporaryDirectory() as tmp:
        encrypted = os.path.join(tmp, os.path.basename(latest) + ".enc")
        subprocess.run(
            ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-salt",
             "-in", latest, "-out", encrypted, "-pass", f"file:{PASSPHRASE_FILE}"],
            check=True,
        )
        msg = EmailMessage()
        msg["Subject"] = f"[PC Radar] Sauvegarde chiffrée de la base — {os.path.basename(latest)}"
        msg["From"] = sender
        msg["To"] = sender
        msg.set_content(
            "Copie hebdomadaire hors serveur de la base de PC Radar, chiffrée (AES-256).\n"
            "À conserver : elle sert si le serveur est perdu.\n\n"
            "Pour la restaurer, voir ops/README-sauvegardes.md dans le dépôt GitHub du projet.\n"
        )
        with open(encrypted, "rb") as f:
            msg.add_attachment(f.read(), maintype="application", subtype="octet-stream",
                               filename=os.path.basename(encrypted))
        with smtplib.SMTP(env["SMTP_HOST"], int(env.get("SMTP_PORT", "587")), timeout=60) as smtp:
            smtp.starttls()
            if env.get("SMTP_USER"):
                smtp.login(env["SMTP_USER"], env.get("SMTP_PASSWORD", ""))
            smtp.send_message(msg)
        log(f"envoyé : {os.path.basename(encrypted)} ({os.path.getsize(encrypted) // 1024} Ko) à {sender}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
