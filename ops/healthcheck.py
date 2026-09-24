"""
Surveillance de PC Radar, lancée par cron toutes les 5 minutes.

- Vérifie l'application (en direct, sans passer par nginx) et le site public.
- Application qui ne répond plus 3 fois de suite : redémarrage automatique.
- Envoie un e-mail à l'adresse du site quand ça tombe, puis quand ça revient
  (une seule alerte par panne, pas un e-mail toutes les 5 minutes).
- Alerte aussi si le disque dépasse 90 % ou si la dernière sauvegarde de la
  base a plus de 30 heures.

N'utilise que la bibliothèque standard ; lit les réglages SMTP dans .env.
"""
import glob
import json
import os
import shutil
import smtplib
import subprocess
import time
import urllib.request
from email.message import EmailMessage

APP_DIR = "/home/ubuntu/pc-configurator"
STATE_FILE = "/home/ubuntu/backups/healthcheck-state.json"
BACKUP_GLOB = "/home/ubuntu/backups/db/pcradar-*.db.gz"
CHECKS = {
    "application": "http://127.0.0.1:8000/api/auth/me",
    "site public": "https://pcradar.tech/",
}
RESTART_AFTER_FAILURES = 3
ALERT_AFTER_FAILURES = 2  # évite une alerte pour un simple redémarrage
DISK_ALERT_PERCENT = 90
BACKUP_MAX_AGE_HOURS = 30


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


def send_alert(env, subject, body):
    sender = env.get("SMTP_FROM") or env.get("SMTP_USER")
    if not (env.get("SMTP_HOST") and sender):
        log("alerte non envoyée : SMTP non configuré")
        return
    msg = EmailMessage()
    msg["Subject"] = f"[PC Radar] {subject}"
    msg["From"] = sender
    msg["To"] = sender
    msg.set_content(body)
    try:
        with smtplib.SMTP(env["SMTP_HOST"], int(env.get("SMTP_PORT", "587")), timeout=20) as smtp:
            smtp.starttls()
            if env.get("SMTP_USER"):
                smtp.login(env["SMTP_USER"], env.get("SMTP_PASSWORD", ""))
            smtp.send_message(msg)
        log(f"alerte envoyée : {subject}")
    except Exception as err:
        log(f"alerte non envoyée ({subject}) : {err}")


def is_up(url):
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return 200 <= resp.status < 400
    except Exception:
        return False


def main():
    env = load_env()
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = {}

    for name, url in CHECKS.items():
        entry = state.setdefault(name, {"failures": 0, "down_since": None})
        if is_up(url):
            if entry["down_since"]:
                minutes = round((time.time() - entry["down_since"]) / 60)
                send_alert(env, f"{name} de nouveau en ligne",
                           f"{name} ({url}) répond de nouveau, après environ {minutes} min de panne.")
            entry.update(failures=0, down_since=None)
            continue

        entry["failures"] += 1
        log(f"{name} ne répond pas ({entry['failures']} fois de suite)")
        if name == "application" and entry["failures"] % RESTART_AFTER_FAILURES == 0:
            subprocess.run(["sudo", "systemctl", "restart", "pc-configurator"], check=False)
            log("application redémarrée automatiquement")
        if entry["failures"] == ALERT_AFTER_FAILURES:
            entry["down_since"] = time.time() - 5 * 60 * (ALERT_AFTER_FAILURES - 1)
            send_alert(env, f"{name} en panne",
                       f"{name} ({url}) ne répond plus depuis environ {5 * (ALERT_AFTER_FAILURES - 1)} min.\n"
                       f"L'application est redémarrée automatiquement toutes les "
                       f"{5 * RESTART_AFTER_FAILURES} min tant qu'elle ne répond pas.")

    # Disque et sauvegarde : au plus une alerte par jour pour chacun.
    today = time.strftime("%Y-%m-%d")
    usage = shutil.disk_usage("/")
    percent = round(usage.used / usage.total * 100)
    if percent >= DISK_ALERT_PERCENT and state.get("disk_alert_day") != today:
        send_alert(env, f"disque plein à {percent} %", f"Le disque du serveur est rempli à {percent} %.")
        state["disk_alert_day"] = today
    backups = glob.glob(BACKUP_GLOB)
    newest = max((os.path.getmtime(p) for p in backups), default=0)
    age_hours = (time.time() - newest) / 3600
    if age_hours > BACKUP_MAX_AGE_HOURS and state.get("backup_alert_day") != today:
        send_alert(env, "sauvegarde de la base en retard",
                   "Aucune sauvegarde de la base depuis plus de "
                   f"{BACKUP_MAX_AGE_HOURS} h. Voir /home/ubuntu/backups/db/backup.log.")
        state["backup_alert_day"] = today

    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


if __name__ == "__main__":
    main()
