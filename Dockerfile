FROM python:3.12-slim

# Install dependencies
RUN apt update && apt install -y \
    ffmpeg \
    wget \
    git \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libxss1 \
    libasound2 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    x11-utils \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Install python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install playwright and browsers
RUN pip install playwright && playwright install

# Copy app code
COPY . .

CMD ["xvfb-run", "python", "main.py"]