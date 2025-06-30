FROM python:3.11-slim

# Installer les dépendances système nécessaires
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    gnupg \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libdrm2 \
    libxss1 \
    libasound2 \
    ffmpeg \
    xvfb \
    libgl1-mesa-dri \
    && rm -rf /var/lib/apt/lists/*

# Installer Node.js (requis par Playwright)
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g npm@latest

# Installer Playwright Python et navigateurs
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install

WORKDIR /app
COPY . .

ENV DISPLAY=:99

CMD ["python", "main.py"]