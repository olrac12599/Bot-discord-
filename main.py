import os
import requests
import tarfile
import zstandard
import stat
import asyncio
import chess.engine
import io

# --- Configuration Finale ---
STOCKFISH_DIR = "stockfish_engine"
# Le chemin vers l'exécutable dans les archives officielles
STOCKFISH_EXECUTABLE = os.path.join(STOCKFISH_DIR, "stockfish", "stockfish")
# L'URL d'une version pré-compilée officielle pour Linux
STOCKFISH_URL = "https://stockfishchess.org/files/stockfish-ubuntu-x86-64-modern.tar.zst"
ARCHIVE_NAME = "stockfish.tar.zst"

def setup_stockfish():
    """
    Télécharge et installe une version pré-compilée de Stockfish.
    """
    if os.path.exists(STOCKFISH_EXECUTABLE):
        print("👍 Stockfish est déjà installé.")
        return True

    print("🔧 Stockfish non trouvé. Lancement de l'installation...")
    try:
        os.makedirs(STOCKFISH_DIR, exist_ok=True)
        archive_path = os.path.join(STOCKFISH_DIR, ARCHIVE_NAME)

        # 1. Télécharger
        print(f"📥 Téléchargement de la version pré-compilée de Stockfish...")
        with requests.get(STOCKFISH_URL, stream=True) as r:
            r.raise_for_status()
            with open(archive_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        print("✅ Téléchargement terminé.")

        # 2. Décompresser l'archive .tar.zst
        print("🗜️  Décompression de l'archive...")
        dctx = zstandard.ZstdDecompressor()
        with open(archive_path, 'rb') as ifh:
            decompressed_data = dctx.decompress(ifh.read())
            with tarfile.open(fileobj=io.BytesIO(decompressed_data), mode='r:') as tar:
                tar.extractall(path=STOCKFISH_DIR)
        print("✅ Décompression terminée.")

        # 3. Rendre l'exécutable
        print(f"🔑 Application des permissions d'exécution au fichier : {STOCKFISH_EXECUTABLE}")
        st = os.stat(STOCKFISH_EXECUTABLE)
        os.chmod(STOCKFISH_EXECUTABLE, st.st_mode | stat.S_IEXEC)
        print("✅ Permissions appliquées.")
        
        # 4. Nettoyage
        os.remove(archive_path)
        print("🧹 Fichier d'archive supprimé.")
        return True

    except Exception as e:
        print(f"❌ ERREUR lors de l'installation de Stockfish : {e}")
        # Affiche le contenu du dossier en cas d'erreur pour aider au diagnostic
        if os.path.exists(STOCKFISH_DIR):
            print(f"--- Contenu actuel de {STOCKFISH_DIR} ---")
            for item in os.listdir(STOCKFISH_DIR):
                print(f"- {item}")
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
        info = await engine.analyse(board, chess.engine.Limit(time=0.5))
        best_move = info.get("pv")[0]
        
        print(f"♟️  Analyse rapide de la position initiale : OK (meilleur coup trouvé : {board.san(best_move)})")
        
        await engine.quit()
        print("\n🎉 Mission accomplie ! Stockfish est installé et fonctionnel.")
        
    except Exception as e:
        print(f"❌ ERREUR lors du test de Stockfish : {e}")

# --- Script Principal ---
if __name__ == "__main__":
    if setup_stockfish():
        asyncio.run(run_check())
    else:
        print("Impossible de lancer la vérification car l'installation a échoué.")
