# Base Python officielle allégée (Debian Bookworm Slim + Python 3.11)
FROM python:3.11-slim-bookworm

# Définir dossier de travail
WORKDIR /app

# 1. Installer dépendances système requises pour Playwright + FFmpeg + GUI headless
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
    build-essential \
    stockfish \
    && rm -rf /var/lib/apt/lists/*

# 2. Installer Node.js (nécessaire pour Playwright)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g npm@latest && \
    rm -f /etc/apt/sources.list.d/nodesource.list

# 3. Copier et installer les dépendances Python en 2 étapes pour meilleure gestion des erreurs
COPY requirements.txt .

# Installer d'abord playwright seul
RUN pip install --upgrade pip
RUN pip install --no-cache-dir playwright==1.45.0

# Puis stealth séparément (si intégré dans le bloc requirements ça peut fail)
RUN pip install --no-cache-dir playwright-stealth==0.2.3

# Installer les autres paquets
RUN pip install --no-cache-dir \
    discord.py==2.3.1 \
    twitchio==3.4.2 \
    python-chess==1.999

# 4. Installer les navigateurs nécessaires à Playwright
RUN playwright install chromium

# 5. Copier tout le code source dans le conteneur
COPY . .

# 6. Exporter la variable DISPLAY pour Xvfb
ENV DISPLAY=:99

# 7. (Facultatif) Expose un port si besoin pour une API ou dashboard futur
EXPOSE 5000

# 8. Lancer le bot à l'exécution du conteneur
CMD ["python", "main.py"]