import os, urllib.request, tarfile, shutil
from stockfish import Stockfish

STOCKFISH_PATH = "/tmp/stockfish"

def download_stockfish():
    print("📦 Téléchargement de Stockfish…")
    url = "https://github.com/official-stockfish/Stockfish/releases/latest/download/stockfish-ubuntu-x86-64-avx2.tar"
    tmp_tar = "/tmp/stockfish.tar"
    urllib.request.urlretrieve(url, tmp_tar)

    with tarfile.open(tmp_tar, "r:") as tar:
        tar.extractall("/tmp/extracted", filter="data")

    for root, _, files in os.walk("/tmp/extracted"):
        if "stockfish" in files:
            src = os.path.join(root, "stockfish")
            shutil.copy(src, STOCKFISH_PATH)
            os.chmod(STOCKFISH_PATH, 0o755)
            return True
    return False

if not os.path.exists(STOCKFISH_PATH):
    success = download_stockfish()
    if not success:
        print("❌ Échec du téléchargement ou de l’extraction.")
        exit(1)

print("✅ Stockfish prêt.")
stockfish = Stockfish(STOCKFISH_PATH)
stockfish.set_position(["e2e4", "e7e5"])
print("Coup conseillé :", stockfish.get_best_move())