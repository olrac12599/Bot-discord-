FROM python:3.12-slim

# Installer les dépendances système nécessaires pour Chromium et autres outils
RUN apt-get update && apt-get install -y \
    chromium ffmpeg xvfb \
    wget unzip curl gnupg \
    --no-install-recommends && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Télécharger et installer ChromeDriver
# MISE À JOUR ICI pour correspondre à la version 138 du navigateur
RUN curl -sSLo chromedriver.zip https://storage.googleapis.com/chrome-for-testing-public/138.0.7204.49/linux64/chromedriver-linux64.zip && \
    unzip chromedriver.zip && \
    mv chromedriver-linux64/chromedriver /usr/local/bin/chromedriver && \
    chmod +x /usr/local/bin/chromedriver && \
    rm -rf chromedriver.zip chromedriver-linux64

# Variables d’environnement
ENV CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/local/bin/chromedriver \
    DISPLAY=:99 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Installer les dépendances Python à partir de requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source de l'application
COPY . .

# Lancer le bot
CMD ["python", "main.py"]
