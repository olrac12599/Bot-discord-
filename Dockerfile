# Dockerfile optimisé pour un bot Python avec Playwright, Xvfb, FFmpeg et Flask (streaming)

# Utilise une image Python de base plus spécifique (Debian Bookworm) pour la stabilité
# J'ai ajouté "-bookworm" car "slim" est souvent basé sur Debian, et cela assure la compatibilité des paquets.
FROM python:3.11-slim-bookworm

# Définit le répertoire de travail pour toutes les opérations
WORKDIR /app

# Étape 1 : Installer les dépendances système nécessaires
# J'ai regroupé et optimisé l'installation des paquets.
# --no-install-recommends: Réduit la taille de l'image en n'installant pas les paquets "recommandés".
# xvfb: Serveur d'affichage virtuel.
# ffmpeg: Pour la capture et le traitement vidéo.
# Toutes les autres libs sont des dépendances courantes pour Chromium headless.
# curl, wget, gnupg: outils nécessaires pour l'installation de Node.js.
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
    # Ajouts supplémentaires pour une compatibilité Chromium plus large sur slim images
    libfontconfig1 \
    libgdk-pixbuf2.0-0 \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libwebp-dev \
    # Nettoie le cache APT pour réduire la taille de l'image Docker finale
    && rm -rf /var/lib/apt/lists/*

# Étape 2 : Installer Node.js (requis par Playwright pour certains outils et l'installation des navigateurs)
# Utilise NodeSource pour obtenir une version stable de Node.js.
# Attention, setup_18.x est pour Node 18.x. Si vous voulez Node 20.x, changez à setup_20.x
# J'ai ajouté && rm -rf /etc/apt/sources.list.d/nodesource.list pour un nettoyage après l'installation
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g npm@latest && \
    rm -rf /etc/apt/sources.list.d/nodesource.list

# Étape 3 : Installer Playwright Python et les navigateurs (Chromium).
# Copie requirements.txt AVANT d'installer Playwright et les dépendances pour la mise en cache de Docker.
# Si seulement requirements.txt change, Docker peut réutiliser la couche précédente.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# La commande `playwright install` sans "--with-deps" suffit ici
# car nous avons installé toutes les dépendances système dans l'Étape 1.
RUN playwright install chromium

# Étape 4 : Copier le reste de votre code source dans le conteneur.
# Ceci devrait être fait APRÈS l'installation de toutes les dépendances
# pour que si seul votre code change, Docker ne reconstruise pas les couches d'installation lourdes.
COPY . .

# Étape 5 : Définir la variable d'environnement DISPLAY pour Xvfb.
ENV DISPLAY=:99

# Étape 6 : Exposer le port pour l'application Flask.
EXPOSE 5000

# Étape 7 : Définir la commande qui sera exécutée lorsque le conteneur démarre.
CMD ["python", "main.py"]
