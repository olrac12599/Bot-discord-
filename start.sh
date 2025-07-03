#!/bin/bash

# 1. Lancer l'affichage virtuel
Xvfb :0 -screen 0 1280x720x24 &
sleep 2

# 2. Lancer le serveur VNC
x11vnc -display :0 -forever -nopw -shared -bg
sleep 2

# 3. Lancer noVNC
./noVNC/utils/launch.sh --vnc localhost:5900 --listen 8080 &
sleep 2

# 4. Lancer le serveur web Flask (en fond)
python3 web_server.py &

# 5. Lancer le bot Discord
python3 main.py