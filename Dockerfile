# Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:0

# Dépendances système pour Playwright et Xvfb SEULEMENT
RUN apt-get update && apt-get install -y \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxcomposite1 libxrandr2 libgbm1 libasound2 \
    libxdamage1 libxext6 libxfixes3 libx11-xcb1 fonts-liberation libappindicator3-1 \
    libpango-1.0-0 libpangocairo-1.0-0 libdrm2 ca-certificates \
    xvfb && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps

COPY start.sh /start.sh
RUN chmod +x /start.sh

# Plus besoin d'exposer de port
CMD ["/start.sh"]
