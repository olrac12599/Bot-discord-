# Base Python officielle
FROM python:3.11-slim

# Installer dépendances système nécessaires (navigateur + ffmpeg + GUI headless)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    curl \
    unzip \
    chromium \
    chromium-driver \
    libglib2.0-0 \
    libnss3 \
    libgconf-2-4 \
    libxss1 \
    libasound2 \
    libxtst6 \
    libgtk-3-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Définir les variables d’environnement pour Selenium
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV VIDEO_PATH=recording.mp4

# Définir le dossier de travail
WORKDIR /app

# Copier tous les fichiers
COPY . .

# Installer les dépendances Python
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Commande de lancement du bot
CMD ["python", "main.py"]