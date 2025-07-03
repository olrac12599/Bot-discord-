#!/bin/bash

# Lance le serveur Xvfb et exécute le bot à l'intérieur.
# Ceci garantit que l'affichage est prêt avant que le bot ne démarre.
xvfb-run python3 main.py
