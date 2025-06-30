# Utiliser une image Python officielle (basée sur Debian)
FROM python:3.11-slim

# Installer les dépendances système nécessaires pour Playwright, Chromium et Selenium
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
    libx11-xcb1 \
    libxss1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    libxshmfence1 \
    libxcb1 \
    libx11-6 \
    unzip \
    fonts-ipafont-gothic \
    fonts-wqy-zenhei \
    fonts-thai-tlwg \
    fonts-kacst \
    fonts-symbola \
    chromium-driver \
    chromium \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Mettre à jour ChromeDriver vers la version compatible avec Chromium installé (optionnel mais conseillé)
RUN chromedriver --version

# Installer les packages Python nécessaires
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Installer les navigateurs Playwright
RUN playwright install --with-deps

# Copier le code dans le container
WORKDIR /app
COPY . /app

# Variables d'environnement (à adapter en prod, mieux via docker-compose ou variables d'env Docker)
ENV PYTHONUNBUFFERED=1
ENV DISCORD_TOKEN=""
ENV TWITCH_CLIENT_ID=""
ENV TWITCH_TOKEN=""
ENV TTV_BOT_NICKNAME=""
ENV TTV_BOT_TOKEN=""
ENV CHESS_USERNAME=""
ENV CHESS_PASSWORD=""

# Expose le port si nécessaire (pas utile pour un bot Discord mais bon)
EXPOSE 8080

# Commande pour lancer le bot
CMD ["python", "bot.py"]