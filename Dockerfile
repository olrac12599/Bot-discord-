FROM python:3.11-slim

# Installer les dépendances système requises
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    libffi-dev \
    libssl-dev \
    ffmpeg \
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
    && rm -rf /var/lib/apt/lists/*

# Copier le fichier requirements
COPY requirements.txt /app/requirements.txt

# Mettre à jour pip et installer les dépendances Python
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r /app/requirements.txt

# Installer les navigateurs Playwright
RUN playwright install --with-deps

WORKDIR /app
COPY . /app

ENV PYTHONUNBUFFERED=1

CMD ["python", "bot.py"]