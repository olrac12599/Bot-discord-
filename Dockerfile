FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    xvfb libnss3 libatk-bridge2.0-0 libxcomposite1 libxdamage1 \
    libxrandr2 libgbm1 libgtk-3-0 libasound2 libxss1 libxtst6 \
    x11-utils ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY . .

CMD ["xvfb-run", "--server-args=-screen 0 1280x720x24", "python", "main.py"]