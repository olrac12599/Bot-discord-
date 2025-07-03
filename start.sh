#!/bin/bash

# 1. Lancer l'affichage virtuel
Xvfb :0 -screen 0 1280x720x24 &
sleep 2

# 2. Lancer le serveur VNC
x11vnc -display :0 -forever -nopw -shared -bg
sleep 2

# 3. Lancer websockify directement
#    --listen "$PORT" : Écoute sur le port fourni par Railway
#    --web /app/noVNC : Indique où se trouvent les fichiers vnc_lite.html etc.
#    --vnc localhost:5900 : Indique où se trouve le serveur VNC à relayer
websockify --listen "$PORT" --web /app/noVNC --vnc localhost:5900 &
sleep 2

# 4. Lancer le bot Discord (processus principal)
echo "Lancement du bot Discord..."
python3 main.py
