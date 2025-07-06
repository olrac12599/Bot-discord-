import os
import requests
import tarfile
import zstandard
import stat
import asyncio
import chess.engine

# --- Configuration ---
STOCKFISH_DIR = "stockfish_engine"
STOCKFISH_EXECUTABLE = os.path.join(STOCKFISH_DIR, "stockfish", "stockfish")
STOCKFISH_URL = "https://stockfishchess.org/files/stockfish-ubuntu-x86-64-modern.tar.zst"
ARCHIVE_NAME = "stockfish.tar.zst"

def setup_stockfish():
    """
    Vérifie si Stockfish est présent, sinon le télécharge et l'installe.
    """
    if os.path.exists(STOCKFISH_EXECUTABLE):
        print("👍 Stockfish est déjà installé.")
        return True

    print("🔧 Stockfish non trouvé. Lancement de l'installation...")
    try:
        # Créer le répertoire de destination
        os.makedirs(STOCKFISH_DIR, exist_ok=True)
        archive_path = os.path.join(STOCKFISH_DIR, ARCHIVE_NAME)

        # 1. Télécharger
        print(f"📥 Téléchargement de Stockfish depuis {STOCKFISH_URL}...")
        response = requests.get(STOCKFISH_URL, stream=True)
        response.raise_for_status()
        with open(archive_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print("✅ Téléchargement terminé.")

        # 2. Décompresser l'archive .tar.zst
        print("🗜️  Décompression de l'archive...")
        with open(archive_path, 'rb') as f:
            dctx = zstandard.ZstdDecompressor()
            with dctx.stream_reader(f) as reader:
                with tarfile.open(fileobj=reader, mode='r:') as tar:
                    tar.extractall(path=STOCKFISH_DIR)
        print("✅ Décompression terminée.")

        # 3. Rendre l'exécutable
        print("🔑 Application des permissions d'exécution...")
        st = os.stat(STOCKFISH_EXECUTABLE)
        os.chmod(STOCKFISH_EXECUTABLE, st.st_mode | stat.S_IEXEC)
        print("✅ Permissions appliquées.")

        # 4. Nettoyage
        os.remove(archive_path)
        print("🧹 Fichier d'archive supprimé.")
        return True

    except Exception as e:
        print(f"❌ ERREUR lors de l'installation de Stockfish : {e}")
        return False

async def run_check():
    """
    Lance le moteur et vérifie qu'il fonctionne.
    """
    print("\n--- Démarrage de la vérification ---")
    try:
        engine = await chess.engine.SimpleEngine.popen_uci(STOCKFISH_EXECUTABLE)
        print("✅ Moteur Stockfish démarré avec succès !")

        board = chess.Board()
        info = await engine.analyse(board, chess.engine.Limit(time=1.0))
        best_move = info.get("pv")[0]

        print(f"♟️  Analyse rapide de la position initiale : OK (meilleur coup trouvé : {board.san(best_move)})")

        await engine.quit()
        print("🔌 Moteur arrêté proprement.")

    except Exception as e:
        print(f"❌ ERREUR lors du test de Stockfish : {e}")

# --- Script Principal ---
if __name__ == "__main__":
    if setup_stockfish():
        # Lancer la partie asynchrone pour la vérification
        asyncio.run(run_check())
    else:
        print("Impossible de lancer la vérification car l'installation a échoué.")

