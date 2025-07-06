FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    curl \
    unzip \
    xvfb \
    libglib2.0-0 \
    libnss3 \
    libgconf-2-4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libxss1 \
    libasound2 \
    fonts-liberation \
    libappindicator3-1 \
    libdbus-glib-1-2 \
    && apt-get clean

# Install Python dependencies
RUN pip install --no-cache-dir playwright python-dotenv discord.py

# Install browsers for Playwright
RUN playwright install chromium

# Create app directory
WORKDIR /app

# Copy all files to the container
COPY . .

# Run the bot
CMD ["python", "main.py"]