import os
import requests
import tarfile
import stat
import asyncio
import chess.engine

# --- Configuration ---
STOCKFISH_DIR = "stockfish_engine"
# Lien direct vers une version pré-compilée sur GitHub (source fiable)
STOCKFISH_URL = "https://github.com/abrok/stockfish-builds/releases/download/stockfish-17/stockfish-17-ubuntu-20.04-x86-64-avx2.tar.gz"
ARCHIVE_NAME = "stockfish.tar.gz"
# On ne connaît pas encore le chemin exact, on met une valeur temporaire
STOCKFISH_EXECUTABLE_TEMP_PATH = os.path.join(STOCKFISH_DIR, "stockfish")

def list_files(startpath):
    """Fonction de débogage pour lister les fichiers."""
    print(f"\n--- CONTENU DU DOSSIER '{startpath}' ---")
    for root, dirs, files in os.walk(startpath):
        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * (level)
        print(f'{indent}{os.path.basename(root)}/')
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            print(f'{subindent}{f}')
    print("----------------------------------------\n")

def setup_stockfish():
    print("🔧 Lancement de l'installation...")
    try:
        os.makedirs(STOCKFISH_DIR, exist_ok=True)
        archive_path = os.path.join(STOCKFISH_DIR, ARCHIVE_NAME)

        # 1. Télécharger
        print(f"📥 Téléchargement depuis la nouvelle source...")
        with requests.get(STOCKFISH_URL, stream=True) as r:
            r.raise_for_status()
            with open(archive_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        print("✅ Téléchargement terminé.")

        # 2. Décompresser l'archive .tar.gz
        print("🗜️  Décompression de l'archive...")
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=STOCKFISH_DIR)
        print("✅ Décompression terminée.")
        
        # 3. BLOC DE DÉBOGAGE
        print("🔍 Le script va maintenant lister les fichiers extraits puis s'arrêter.")
        print("   Copiez-collez le log pour trouver le bon chemin de l'exécutable.")
        list_files(STOCKFISH_DIR)
        
        # 4. On s'arrête ici volontairement pour le débogage
        return False # Stoppe le script pour éviter une erreur

    except Exception as e:
        print(f"❌ ERREUR lors de l'installation : {e}")
        return False

# Le reste du script ne sera pas exécuté grâce au "return False"
async def run_check():
    pass

if __name__ == "__main__":
    if setup_stockfish():
        asyncio.run(run_check())
    else:
        print("Script de débogage terminé. Veuillez fournir les logs.")
