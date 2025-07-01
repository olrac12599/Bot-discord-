FROM python:3.12-slim

# Dépendances système
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    curl \
    gnupg \
    libglib2.0-0 \
    libnss3 \
    libgconf-2-4 \
    libfontconfig1 \
    libx11-xcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxrandr2 \
    libasound2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libgtk-3-0 \
    xdg-utils \
    --no-install-recommends && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Installer Chrome 117 (version archivée)
RUN wget https://dl.google.com/linux/chrome/deb/pool/main/g/google-chrome-stable/google-chrome-stable_117.0.5938.149-1_amd64.deb && \
    apt install -y ./google-chrome-stable_117.0.5938.149-1_amd64.deb && \
    rm google-chrome-stable_117.0.5938.149-1_amd64.deb

# Installer ChromeDriver 117
RUN wget -O /tmp/chromedriver.zip https://chromedriver.storage.googleapis.com/117.0.5938.149/chromedriver_linux64.zip && \
    unzip /tmp/chromedriver.zip -d /usr/local/bin && \
    rm /tmp/chromedriver.zip

# Variables d'environnement pour Selenium
ENV CHROME_BIN=/usr/bin/google-chrome-stable \
    CHROMEDRIVER_PATH=/usr/local/bin/chromedriver \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Répertoire de travail
WORKDIR /app

# Dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code de l'app
COPY . .

# Commande de démarrage
CMD ["python", "main.py"]