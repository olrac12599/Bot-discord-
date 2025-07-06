# Utilise une image Python 3.12 slim
FROM python:3.12-slim

# Met à jour et installe les dépendances système requises
RUN apt-get update && apt-get install -y \
    ffmpeg \
    xvfb \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Définit l'affichage virtuel sur lequel le navigateur s'exécutera
# Bien que l'entrypoint s'en occupe, le définir ici reste une bonne pratique
ENV DISPLAY=:99

# Copie et installe les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie le reste de l'application
COPY . /app
WORKDIR /app

# Rendre le script d'entrée exécutable
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Définir le script d'entrée comme point de lancement du conteneur
ENTRYPOINT ["./entrypoint.sh"]
