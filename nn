FROM python:3.11-slim

RUN apt update && apt install -y \
    curl wget ffmpeg stockfish libglib2.0-0 \
    libnss3 libatk-bridge2.0-0 libgtk-3-0 libdrm-dev \
    libxss1 libasound2

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright browsers
RUN pip install playwright && playwright install

# Add project files
COPY . /app
WORKDIR /app

CMD ["python", "main.py"]