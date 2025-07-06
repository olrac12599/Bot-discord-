FROM python:3.12-slim

# Installer les dépendances système (ajout de python3-distutils ici 👇)
RUN apt update && apt install -y \
    ffmpeg \
    xvfb \
    chromium \
    chromium-driver \
    python3-distutils \
    && rm -rf /var/lib/apt/lists/*

ENV DISPLAY=:99

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . /app
WORKDIR /app

CMD ["xvfb-run", "python", "main.py"]