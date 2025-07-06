# Utiliser une image de base Python
FROM python:3.9-slim

# Mettre à jour les paquets et installer les dépendances nécessaires
RUN apt-get update && apt-get install -y \
    stockfish \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Copier les fichiers du projet dans le conteneur
WORKDIR /app
COPY . .

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Commande pour exécuter le bot
CMD ["python", "main.py"]