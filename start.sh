#!/bin/bash

# 1. Lancer l'affichage virtuel pour le navigateur
Xvfb :0 -screen 0 1280x720x24 &

# 2. Lancer le bot Discord
python3 main.py
