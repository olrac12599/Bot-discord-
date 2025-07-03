#!/bin/bash

# 'set -e' arrête le script si une commande échoue.
# 'set -x' affiche chaque commande avant de l'exécuter.
set -ex

echo "================================================="
echo "==      DÉBUT DU SCRIPT DE DÉBOGAGE            =="
echo "================================================="
echo ""

echo "--- Contenu actuel de start.sh : ---"
cat /start.sh
echo ""

echo "--- Emplacement de xvfb-run : ---"
which xvfb-run
echo ""

echo "--- Lancement de l'application... ---"
# On lance l'application avec des options explicites pour xvfb-run
xvfb-run --auto-servernum --server-args="-screen 0 1280x720x24" python3 main.py
