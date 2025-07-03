# Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:0

# Assurez-vous que 'supervisor' est bien dans la liste
RUN apt-get update && apt-get install -y \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxcomposite1 libxrandr2 libgbm1 libasound2 \
    libxdamage1 libxext6 libxfixes3 libx11-xcb1 fonts-liberation libappindicator3-1 libpangocairo-1.0-0 \
    libpango-1.0-0 libdrm2 ca-certificates wget unzip git \
    xvfb x11vnc curl net-tools supervisor && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps

RUN git clone https://github.com/novnc/noVNC.git

# Copier la configuration de supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# La commande finale est maintenant de lancer supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
