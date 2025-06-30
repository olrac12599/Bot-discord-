# Utilise une image Python de base
FROM python:3.10-slim-buster

# Définit la variable d'environnement DISPLAY pour Xvfb
ENV DISPLAY=:99

# Définit le répertoire de travail dans le conteneur
WORKDIR /app

# Met à jour la liste des paquets et installe les dépendances système nécessaires
# xvfb: pour l'affichage virtuel
# ffmpeg: pour la capture et l'encodage vidéo
# libgl1-mesa-glx: dépendance pour Playwright/Chromium pour le rendu graphique
# ca-certificates: souvent nécessaire pour les requêtes SSL
RUN apt-get update && apt-get install -y \
    xvfb \
    ffmpeg \
    libgl1-mesa-glx \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Installe Playwright et Chromium
RUN pip install playwright
RUN playwright install chromium --with-deps

# Copie tous les fichiers de votre projet dans le conteneur
COPY . .

# Installe les dépendances Python de votre requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Définit le port sur lequel votre application Flask va écouter
# Railway injecte la variable PORT, mais Flask a besoin de savoir où écouter.
# La variable PORT dans votre Python est déjà configurée pour utiliser os.getenv("PORT", 5000)
# Ce EXPOSE est plus pour la documentation du Dockerfile.
EXPOSE 5000

# Commande à exécuter lorsque le conteneur démarre
# Lance votre script main.py
CMD ["python", "main.py"]
