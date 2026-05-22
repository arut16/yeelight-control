#!/usr/bin/env python3
import os
import re
import time
import subprocess
from collections import deque

DISPLAY = ":0"
XAUTH = os.path.expanduser("~/.Xauthority")

# Détection robuste : mmc0, mmcblk0, sdhci + mots-clés d'erreur
PATTERN = re.compile(
    r"\b(mmc0|mmcblk0|sdhci)\b.*\b(crc|timeout|timed out|reset|i/o error|error)\b",
    re.IGNORECASE
)

# Exclure les erreurs ioctl provoquées par mmc-utils (extcsd)
EXCLUDE = re.compile(r"__mmc_blk_ioctl_cmd", re.IGNORECASE)

WINDOW_SEC = 600   # 10 minutes
THRESHOLD = 3

events = deque()

def popen_safe(cmd, env=None):
    try:
        return subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"POPEN FAILED: {cmd} -> {e}", flush=True)
        return None

def send_alert(alert: str) -> None:
    env = os.environ.copy()
    env["DISPLAY"] = DISPLAY
    env["XAUTHORITY"] = XAUTH

    # Popup + notif, exécutés dans la session graphique arut16
    popen_safe(
        ["sudo", "-u", "arut16", "zenity", "--warning",
         "--title=Alerte microSD (Raspberry Pi)", "--text", alert],
        env=env
    )
    popen_safe(
        ["sudo", "-u", "arut16", "notify-send", "-u", "critical",
         "Alerte microSD (Raspberry Pi)", alert],
        env=env
    )

def extract_message(kmsg_line: str) -> str:
    # Format /dev/kmsg: "<pri>,seq,timestamp,flags;message"
    # On garde "message" (après ';')
    if ";" in kmsg_line:
        return kmsg_line.split(";", 1)[1].strip()
    return kmsg_line.strip()

def main() -> None:
    print("SD Watchdog started (reading /dev/kmsg).", flush=True)
    print(f"Threshold={THRESHOLD} events / {WINDOW_SEC}s | DISPLAY={DISPLAY}", flush=True)

    # Ouvrir /dev/kmsg en lecture
    with open("/dev/kmsg", "r", errors="replace") as f:
        # Purger le backlog au démarrage (sans seek)
        # On lit tout ce qui est déjà dispo, puis on passe en mode "follow".
        fcntl = None
        try:
            import fcntl as _fcntl
            fcntl = _fcntl
        except Exception:
            pass

        # Mettre en non-bloquant pour vider rapidement le backlog
        if fcntl:
            flags = fcntl.fcntl(f, fcntl.F_GETFL)
            fcntl.fcntl(f, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        purged = 0
        while True:
            try:
                line = f.readline()
                if not line:
                    break
                purged += 1
            except Exception:
                break

        # Revenir en bloquant (mode suivi)
        if fcntl:
            flags = fcntl.fcntl(f, fcntl.F_GETFL)
            fcntl.fcntl(f, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)

        print(f"Purged {purged} existing kmsg lines. Now following live kernel messages.", flush=True)

        # Suivi live
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.2)
                continue

            msg = extract_message(line)

            if not PATTERN.search(msg):
                continue
            if EXCLUDE.search(msg):
                continue

            print("MATCH:", msg, flush=True)

            now = time.time()
            events.append(now)

            while events and now - events[0] > WINDOW_SEC:
                events.popleft()

            if len(events) >= THRESHOLD:
                alert = (
                    f"Erreurs microSD/MMC détectées : {len(events)} événements en {WINDOW_SEC//60} minutes.\n\n"
                    f"Dernier log :\n{msg}\n\n"
                    "Action recommandée : sauvegarde + planifier remplacement de la carte."
                )
                send_alert(alert)
                print("ALERT SENT", flush=True)
                events.clear()

if __name__ == "__main__":
    main()
