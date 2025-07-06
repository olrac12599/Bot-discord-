#!/bin/sh

# Démarrer le serveur d'affichage virtuel Xvfb en arrière-plan
# sur l'écran :99 avec une résolution de 1280x720 et une profondeur de couleur de 16 bits.
Xvfb :99 -screen 0 1280x720x16 &

# Laisser un court instant au serveur Xvfb pour se lancer complètement
sleep 2

# Exécuter la commande principale de l'application (votre bot Python)
exec python main.py
