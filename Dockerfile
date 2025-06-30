# Image de base Python
FROM python:3.11-slim

# Installer dépendances système
RUN apt-get update && apt-get install -y \
   
    ffmpeg \
    chromium \
    chromium-driver \
    libglib2.0-0 \
    libnss3 \
    libgconf-2-4 \
    libxss1 \
    libasound2 \
    libxtst6 \
    libgtk-3-0 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
wget \
    curl \
    unzip \
    ffmpeg \
    chromium \
    chromium-driver \
    libglib2.0-0 \
    libnss3 \
    libgconf-2-4 \
    libxss1 \
    libasound2 \
    libxtst6 \
    libgtk-3-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Définir variables d’environnement pour Chromium
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV VIDEO_PATH=recording.mp4

# Définir le dossier de travail
WORKDIR /app

# Copier les fichiers
COPY . /app

# Installer les dépendances Python
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Lancer le bot
CMD ["python", "main.py"]