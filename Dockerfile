# Utilise une image Python 3.12 slim
FROM python:3.12-slim

# Met à jour et installe les dépendances système requises
# ffmpeg pour l'enregistrement, xvfb pour l'affichage virtuel, et chromium
RUN apt-get update && apt-get install -y \
    ffmpeg \
    xvfb \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Définit l'affichage virtuel sur lequel le navigateur s'exécutera
ENV DISPLAY=:99

# Copie et installe les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie le reste de l'application
COPY . /app
WORKDIR /app

# Commande de lancement : exécute le script Python à l'intérieur de l'environnement virtuel xvfb
CMD ["xvfb-run", "python", "main.py"]

