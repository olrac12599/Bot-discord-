FROM python:3.12-slim

# Installer Chromium, ChromeDriver, ffmpeg, xvfb, distutils via python3-venv
RUN apt-get update && apt-get install -y \
    python3-venv \
    chromium ffmpeg xvfb \
    wget unzip curl gnupg \
    libglib2.0-0 libnss3 libgconf-2-4 libfontconfig1 \
    libx11-xcb1 libxcomposite1 libxcursor1 libxdamage1 \
    libxrandr2 libasound2 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libgtk-3-0 xdg-utils \
    --no-install-recommends && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Télécharger ChromeDriver version 138 (compatible avec Chromium 138)
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

# Installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source
COPY . .

# Lancer le bot
CMD ["python", "main.py"]