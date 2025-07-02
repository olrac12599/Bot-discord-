# Étape 1: Définir l'image de base
FROM python:3.10-slim

# Définir le répertoire de travail dans le conteneur
WORKDIR /app

# Étape 2: Installer les dépendances système nécessaires
# - ffmpeg: Pour le traitement vidéo (compression par moviepy)
# - xvfb: Pour créer un écran virtuel (indispensable pour la capture d'écran en headless)
# - libgl1-mesa-glx: Dépendance pour opencv
# - wget & gnupg: Pour télécharger et installer Google Chrome
RUN apt-get update && apt-get install -y \
    ffmpeg \
    xvfb \
    libgl1-mesa-glx \
    wget \
    gnupg \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Étape 3: Installer Google Chrome
# Nécessaire pour que Selenium puisse piloter un navigateur
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Étape 4: Installer les dépendances Python
# On copie d'abord uniquement requirements.txt pour profiter du cache de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Étape 5: Copier le code de l'application
# Copie tout le reste (votre script .py)
COPY . .

# Étape 6: Définir la commande de lancement
# - xvfb-run: Lance la commande suivante dans l'environnement d'écran virtuel
# - python bot.py: Exécute votre script de bot
CMD ["xvfb-run", "python", "bot.py"]
