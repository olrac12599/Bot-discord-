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
STOCKFISH_EXECUTABLE = os.path.join(STOCKFISH_DIR, "stockfish", "stockfish")
STOCKFISH_URL = "https://stockfishchess.org/files/stockfish-ubuntu-x86-64-modern.tar.zst"
ARCHIVE_NAME = "stockfish.tar.zst"

def setup_stockfish():
    """
    Télécharge et installe une version pré-compilée de Stockfish
    avec des vérifications robustes pour garantir l'intégrité du fichier.
    """
    if os.path.exists(STOCKFISH_EXECUTABLE):
        print("👍 Stockfish est déjà installé.")
        return True

    print("🔧 Stockfish non trouvé. Lancement de l'installation...")
    try:
        os.makedirs(STOCKFISH_DIR, exist_ok=True)
        archive_path = os.path.join(STOCKFISH_DIR, ARCHIVE_NAME)

        # 1. Téléchargement "blindé"
        print("📥 Téléchargement de la version pré-compilée...")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        with requests.get(STOCKFISH_URL, stream=True, headers=headers) as r:
            print(f"   - Statut de la réponse du serveur : {r.status_code}")
            r.raise_for_status() # Stoppe si le statut n'est pas 200 (OK)

            content_type = r.headers.get('content-type', '').lower()
            print(f"   - Type de contenu reçu : {content_type}")
            if 'text/html' in content_type:
                print("❌ ERREUR: Le serveur a renvoyé une page HTML au lieu du fichier binaire.")
                return False

            with open(archive_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        print("✅ Téléchargement terminé.")
        
        file_size_mb = os.path.getsize(archive_path) / (1024 * 1024)
        print(f"   - Taille du fichier téléchargé : {file_size_mb:.2f} MB")
        if file_size_mb < 5: # Le binaire de Stockfish pèse plus de 5 Mo
            print("❌ ERREUR: Le fichier téléchargé est trop petit, il est donc corrompu ou incomplet.")
            return False
        print("   - La taille du fichier semble correcte.")

        # 2. Décompresser
        print("🗜️  Décompression de l'archive...")
        dctx = zstandard.ZstdDecompressor()
        with open(archive_path, 'rb') as ifh:
            decompressed_data = dctx.decompress(ifh.read())
            with tarfile.open(fileobj=io.BytesIO(decompressed_data), mode='r:') as tar:
                tar.extractall(path=STOCKFISH_DIR)
        print("✅ Décompression terminée.")

        # 3. Appliquer les permissions
        print(f"🔑 Application des permissions d'exécution...")
        st = os.stat(STOCKFISH_EXECUTABLE)
        os.chmod(STOCKFISH_EXECUTABLE, st.st_mode | stat.S_IEXEC)
        print("✅ Permissions appliquées.")
        
        # 4. Nettoyage
        os.remove(archive_path)
        return True

    except Exception as e:
        print(f"❌ ERREUR lors de l'installation : {e}")
        return False

async def run_check():
    """Lance le moteur et vérifie qu'il fonctionne."""
    print("\n--- Démarrage de la vérification ---")
    try:
        engine = await chess.engine.SimpleEngine.popen_uci(STOCKFISH_EXECUTABLE)
        print("✅ Moteur Stockfish démarré avec succès !")
        
        board = chess.Board()
        info = await engine.analyse(board, chess.engine.Limit(time=0.5))
        best_move = info.get("pv")[0]
        
        print(f"♟️  Analyse rapide : OK (meilleur coup trouvé : {board.san(best_move)})")
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
