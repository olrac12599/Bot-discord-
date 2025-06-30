# Dockerfile finalisé pour un bot Python avec Playwright, Xvfb, FFmpeg et Flask (streaming)

# Étape 1 : Utiliser une image Docker officielle de Playwright.
# Ces images incluent déjà Python, Node.js, Playwright et TOUS les navigateurs (Chromium, Firefox, WebKit)
# avec leurs dépendances système nécessaires. Cela simplifie énormément l'installation.
# Nous utilisons une version spécifique (v1.44.0) avec Python 3.10 sur Debian Bookworm (Debian 12).
# Vérifiez https://hub.docker.com/r/mcr.microsoft.com/playwright/python/tags pour les versions plus récentes si nécessaire.
FROM mcr.microsoft.com/playwright/python:v1.44.0-python3.10-bookworm

# Étape 2 : Définir le répertoire de travail dans le conteneur.
# Tous les fichiers de votre projet seront copiés ici.
WORKDIR /app

# Étape 3 : Copier le fichier requirements.txt et installer les dépendances Python.
# Nous installons d'abord les dépendances Python pour tirer parti de la mise en cache de Docker.
# Si requirements.txt ne change pas, cette étape ne sera pas reconstruite.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Étape 4 : Installer les dépendances système supplémentaires.
# L'image Playwright inclut déjà les navigateurs et leurs dépendances.
# Nous devons nous assurer que Xvfb (pour l'affichage virtuel) et FFmpeg (pour la capture vidéo)
# sont bien installés, car ils ne sont pas toujours inclus par défaut dans toutes les images Playwright.
# --no-install-recommends réduit la taille finale de l'image.
# rm -rf /var/lib/apt/lists/* nettoie le cache APT pour une image plus petite.
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    ffmpeg \
    # Ajout d'une dépendance parfois manquante pour le rendu graphique de Xvfb avec certains logiciels
    libgl1-mesa-dri \
    && rm -rf /var/lib/apt/lists/*

# Étape 5 : Copier le reste de votre code source dans le conteneur.
# Cela inclut main.py et tout autre fichier de votre projet.
COPY . .

# Étape 6 : Définir la variable d'environnement DISPLAY.
# Xvfb va tourner sur cette "pseudo-adresse d'affichage" et Playwright sera configuré pour l'utiliser.
ENV DISPLAY=:99

# Étape 7 : Exposer le port sur lequel votre application Flask va écouter.
# C'est le port que Railway ou tout autre hébergeur doit ouvrir pour rendre votre stream accessible.
EXPOSE 5000

# Étape 8 : Définir la commande qui sera exécutée lorsque le conteneur démarre.
# Cela lance votre script Python principal.
CMD ["python", "main.py"]
