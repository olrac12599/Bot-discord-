# Étape 1: Choisir une image de base avec Python
FROM python:3.12-slim

# Étape 2: Installer les programmes système nécessaires (dont Stockfish)
# On met à jour les listes de paquets et on installe stockfish
RUN apt-get update && apt-get install -y stockfish && rm -rf /var/lib/apt/lists/*

# Étape 3: Préparer l'environnement pour le code de l'application
WORKDIR /app
COPY requirements.txt .

# Étape 4: Installer les bibliothèques Python
RUN pip install --no-cache-dir -r requirements.txt

# Étape 5: Copier le reste du code de l'application
COPY . .

# Étape 6: Définir la commande pour lancer le bot
CMD ["python", "main.py"]
