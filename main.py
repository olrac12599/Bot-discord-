import os
import urllib.request
import zipfile
import shutil
from stockfish import Stockfish

STOCKFISH_PATH = "/tmp/stockfish"

def download_stockfish():
    print("📦 Téléchargement de Stockfish...")
    url = "https://stockfishchess.org/files/stockfish-ubuntu-x86-64-avx2.zip"
    zip_path = "/tmp/stockfish.zip"

    urllib.request.urlretrieve(url, zip_path)

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall("/tmp/stockfish_extracted")

    # Trouve le fichier binaire dans le dossier extrait
    for root, dirs, files in os.walk("/tmp/stockfish_extracted"):
        for file in files:
            if file == "stockfish":
                stockfish_bin = os.path.join(root, file)
                shutil.copy(stockfish_bin, STOCKFISH_PATH)
                os.chmod(STOCKFISH_PATH, 0o755)
                return True
    return False

# Téléchargement si nécessaire
if not os.path.exists(STOCKFISH_PATH):
    success = download_stockfish()
    if not success:
        print("❌ Échec du téléchargement de Stockfish")
        exit(1)

print("✅ Stockfish est prêt.")

# Utilisation
stockfish = Stockfish(STOCKFISH_PATH)
stockfish.set_position(["e2e4", "e7e5"])
print("Coup conseillé :", stockfish.get_best_move())
