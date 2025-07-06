FROM python:3.12-slim

RUN apt update && apt install -y \
    ffmpeg \
    xvfb \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

ENV DISPLAY=:99

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . /app
WORKDIR /app

CMD ["xvfb-run", "python", "main.py"]