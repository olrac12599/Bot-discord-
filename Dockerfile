# Dockerfile optimisé pour un bot Python avec Playwright, Xvfb, FFmpeg et Flask (streaming)

# Utilise une image Python de base plus spécifique (Debian Bookworm) pour la stabilité
FROM python:3.11-slim-bookworm

# Définit le répertoire de travail pour toutes les opérations
WORKDIR /app

# Étape 1 : Installer les dépendances système nécessaires
# J'ai regroupé et optimisé l'installation des paquets.
# --no-install-recommends: Réduit la taille de l'image en n'installant pas les paquets "recommandés".
# xvfb: Serveur d'affichage virtuel.
# ffmpeg: Pour la capture et le traitement vidéo.
# Toutes les autres libs sont des dépendances courantes pour Chromium headless.
# ca-certificates: Important pour les requêtes HTTPS.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    gnupg \
    ca-certificates \
    xvfb \
    ffmpeg \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libdrm2 \
    libxss1 \
    libasound2 \
    libgl1-mesa-dri \
    libgl1-mesa-glx \
    libgbm-dev \
    libfontconfig1 \
    libgdk-pixbuf2.0-0 \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libwebp-dev \
    # Nettoie le cache APT pour réduire la taille de l'image Docker finale
    && rm -rf /var/lib/apt/lists/*

# Étape 2 : Installer Node.js (requis par Playwright pour certains outils et l'installation des navigateurs)
# Utilise la méthode recommandée par NodeSource pour les images Debian, plus robuste en conteneur.
# Nous utiliserons Node.js 20.x, qui est une version LTS (support à long terme).
RUN mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.d/nodesource.gpg | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y nodejs && \
    npm install -g npm@latest && \
    rm -rf /etc/apt/sources.list.d/nodesource.list # Nettoyage après l'installation

# Étape 3 : Installer Playwright Python et les navigateurs (Chromium).
# Copie requirements.txt AVANT d'installer Playwright et les dépendances pour la mise en cache de Docker.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# La commande `playwright install` sans "--with-deps" suffit ici
# car nous avons installé toutes les dépendances système dans l'Étape 1.
RUN playwright install chromium

# Étape 4 : Copier le reste de votre code source dans le conteneur.
# Ceci doit être fait APRÈS l'installation de toutes les dépendances pour optimiser le cache de Docker.
COPY . .

# Étape 5 : Définir la variable d'environnement DISPLAY pour Xvfb.
ENV DISPLAY=:99

# Étape 6 : Exposer le port pour l'application Flask.
EXPOSE 5000

# Étape 7 : Définir la commande qui sera exécutée lorsque le conteneur démarre.
CMD ["python", "main.py"]
