import os
import requests
import tarfile
import stat
import asyncio
import chess.engine

# --- Configuration (inchangée) ---
STOCKFISH_DIR = "stockfish_engine"
STOCKFISH_EXECUTABLE = os.path.join(STOCKFISH_DIR, "stockfish", "stockfish") # On garde ce chemin pour l'instant
STOCKFISH_URL = "https://github.com/official-stockfish/Stockfish/releases/download/sf_17.1/stockfish-ubuntu-x86-64-avx2.tar"
ARCHIVE_NAME = "stockfish.tar"

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
    if os.path.exists(STOCKFISH_EXECUTABLE):
        print("👍 Stockfish est déjà installé.")
        return True

    print("🔧 Stockfish non trouvé. Lancement de l'installation...")
    try:
        os.makedirs(STOCKFISH_DIR, exist_ok=True)
        archive_path = os.path.join(STOCKFISH_DIR, ARCHIVE_NAME)

        print(f"📥 Téléchargement...")
        with requests.get(STOCKFISH_URL, stream=True) as r:
            r.raise_for_status()
            with open(archive_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        print("✅ Téléchargement terminé.")

        print("🗜️  Décompression de l'archive .tar...")
        with tarfile.open(archive_path) as tar:
            tar.extractall(path=STOCKFISH_DIR)
        print("✅ Décompression terminée.")
        
        # --- BLOC DE DÉBOGAGE ---
        # Affiche la structure des fichiers pour trouver le bon chemin
        list_files(STOCKFISH_DIR)
        # --- FIN DU BLOC DE DÉBOGAGE ---

        print("🔑 Application des permissions d'exécution...")
        st = os.stat(STOCKFISH_EXECUTABLE)
        os.chmod(STOCKFISH_EXECUTABLE, st.st_mode | stat.S_IEXEC)
        print("✅ Permissions appliquées.")
        
        os.remove(archive_path)
        print("🧹 Fichier d'archive supprimé.")
        return True

    except Exception as e:
        print(f"❌ ERREUR lors de l'installation de Stockfish : {e}")
        return False

async def run_check():
    # Cette partie ne sera pas atteinte si l'installation échoue, ce qui est normal pour ce test.
    print("\n--- Démarrage de la vérification ---")
    engine = await chess.engine.SimpleEngine.popen_uci(STOCKFISH_EXECUTABLE)
    await engine.quit()
    print("✅ Moteur démarré et arrêté avec succès.")

if __name__ == "__main__":
    if setup_stockfish():
        asyncio.run(run_check())
    else:
        print("Impossible de lancer la vérification car l'installation a échoué.")
