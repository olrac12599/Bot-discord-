#!/bin/bash

# 1. Lancer l'affichage virtuel
Xvfb :0 -screen 0 1280x720x24 &
sleep 2

# 2. Lancer le serveur VNC
x11vnc -display :0 -forever -nopw -shared -bg
sleep 2

# 3. Lancer noVNC en écoutant sur le port de Railway ($PORT)
# Le script launch.sh sert aussi les fichiers web (vnc_lite.html, etc.).
./noVNC/utils/launch.sh --vnc localhost:5900 --listen "$PORT" &
sleep 2

# 4. Lancer le bot Discord (processus principal)
echo "Lancement du bot Discord..."
python3 main.py
