import os
import urllib.request
import tarfile
import shutil
from stockfish import Stockfish

STOCKFISH_PATH = "/tmp/stockfish"

def download_stockfish():
    print("📦 Téléchargement de Stockfish...")
    # <-- Correction du lien vers le fichier .tar
    url = "https://github.com/official-stockfish/Stockfish/releases/download/sf_17.1/stockfish-ubuntu-x86-64-avx2.tar"
    local = "/tmp/stockfish.tar"

    urllib.request.urlretrieve(url, local)

    # On extrait le .tar
    with tarfile.open(local, "r:") as tar_ref:
        tar_ref.extractall("/tmp/stockfish_extracted")

    # On cherche le binaire
    for root, _, files in os.walk("/tmp/stockfish_extracted"):
        if "stockfish" in files:
            src = os.path.join(root, "stockfish")
            shutil.copy(src, STOCKFISH_PATH)
            os.chmod(STOCKFISH_PATH, 0o755)
            return True
    return False

if not os.path.exists(STOCKFISH_PATH):
    if not download_stockfish():
        print("❌ Échec du téléchargement ou extraction.")
        exit(1)

print("✅ Stockfish prêt.")
stockfish = Stockfish(STOCKFISH_PATH)
stockfish.set_position(["e2e4", "e7e5"])
print("Coup conseillé :", stockfish.get_best_move())