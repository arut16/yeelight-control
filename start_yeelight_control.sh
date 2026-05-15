#!/bin/bash

# Fichier de log unique pour tout le processus
LOG_FILE="/home/arut16/start_yeelight_control_debug.log"
PYTHON_BIN="/home/arut16/YeelightDomEnv/bin/python3"
APP_DIR="/home/arut16"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Sur le Raspberry Pi de production, tous les scripts sont directement dans
# /home/arut16. Si ce chemin n'est pas disponible (tests/dev), on retombe sur
# le dossier qui contient ce lanceur.
if [ ! -f "$APP_DIR/yeelight_control.py" ] || [ ! -f "$APP_DIR/cpu_temp_bubble.py" ]; then
    APP_DIR="$SCRIPT_DIR"
fi

if [ ! -f "$APP_DIR/yeelight_control.py" ] || [ ! -f "$APP_DIR/cpu_temp_bubble.py" ]; then
    echo "Erreur: scripts Yeelight introuvables dans $APP_DIR" > "$LOG_FILE"
    exit 1
fi

if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="$(command -v python3)"
fi

# Initialiser le log (écrase le fichier existant)
echo "Script started - $(date)" > "$LOG_FILE"
echo "APP_DIR=$APP_DIR" >> "$LOG_FILE"
echo "PYTHON_BIN=$PYTHON_BIN" >> "$LOG_FILE"

# Configuration de l'environnement graphique
export DISPLAY=:0
echo "DISPLAY set to :0" >> "$LOG_FILE"

# Attendre que le bureau LXDE soit complètement chargé
echo "Waiting for LXDE to start..." >> "$LOG_FILE"
while ! pgrep -f "lxsession" > /dev/null; do
    sleep 1
    echo "LXDE not yet started, waiting..." >> "$LOG_FILE"
done
echo "LXDE détecté comme démarré" >> "$LOG_FILE"
sleep 2  # Délai supplémentaire pour stabiliser

# Lancer l'interface Yeelight
echo "Starting Yeelight Control: $APP_DIR/yeelight_control.py" >> "$LOG_FILE"
if ! pgrep -f "$APP_DIR/yeelight_control.py" > /dev/null; then
    "$PYTHON_BIN" "$APP_DIR/yeelight_control.py" >> "$LOG_FILE" 2>&1 &
    sleep 2  # Délai de 2 secondes
    if pgrep -f "$APP_DIR/yeelight_control.py" > /dev/null; then
        echo "Yeelight Control lancé avec succès" >> "$LOG_FILE"
    else
        echo "Erreur lors du lancement de Yeelight Control (voir traceback ci-dessus)" >> "$LOG_FILE"
    fi
else
    echo "Yeelight Control est déjà en cours d'exécution" >> "$LOG_FILE"
fi

# Lancer le moniteur de température CPU
echo "Starting CPU Temperature Bubble: $APP_DIR/cpu_temp_bubble.py" >> "$LOG_FILE"
if ! pgrep -f "$APP_DIR/cpu_temp_bubble.py" > /dev/null; then
    "$PYTHON_BIN" "$APP_DIR/cpu_temp_bubble.py" >> "$LOG_FILE" 2>&1 &
    sleep 1
    if pgrep -f "$APP_DIR/cpu_temp_bubble.py" > /dev/null; then
        echo "CPU Temperature Bubble lancé avec succès" >> "$LOG_FILE"
    else
        echo "Erreur lors du lancement de CPU Temperature Bubble (voir traceback ci-dessus)" >> "$LOG_FILE"
    fi
else
    echo "CPU Temperature Bubble est déjà en cours d'exécution" >> "$LOG_FILE"
fi

echo "Tous les scripts sont lancés" >> "$LOG_FILE"
