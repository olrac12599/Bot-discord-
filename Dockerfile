FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    ffmpeg \
    xvfb \
    wget \
    unzip \
    curl \
    gnupg \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    discord.py selenium

COPY . /app
WORKDIR /app

CMD ["python", "main.py"]
