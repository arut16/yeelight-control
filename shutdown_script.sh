#!/bin/bash
# Tuer les processus Tkinter et Pygame proprement
pkill -f cpu_temp_bubble.py
pkill -f yeelight_control.py
# Attendre un instant pour garantir l’arrêt
sleep 2
# Éteindre le système
sudo /sbin/shutdown -h now
