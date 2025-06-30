# Utilise une image Python officielle Debian Bookworm slim
FROM python:3.11-slim-bookworm

# Définir dossier de travail
WORKDIR /app

# Installer les dépendances système nécessaires (pour Playwright + Stockfish + ffmpeg + Xvfb)
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
    stockfish \
    && rm -rf /var/lib/apt/lists/*

# Installer Node.js (nécessaire pour Playwright)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g npm@latest && \
    rm -f /etc/apt/sources.list.d/nodesource.list

# Copier requirements.txt et installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Installer les navigateurs Playwright (Chromium)
RUN playwright install chromium

# Copier tout le code source
COPY . .

# Variable d'environnement DISPLAY (pour Xvfb)
ENV DISPLAY=:99

# Exposer le port pour Flask si tu l'utilises (ou ignore si pas besoin)
EXPOSE 5000

# Commande au démarrage du conteneur
CMD ["python", "main.py"]