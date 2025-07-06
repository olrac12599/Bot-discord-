import os
import urllib.request
import tarfile
import shutil
from stockfish import Stockfish

STOCKFISH_PATH = "/tmp/stockfish"

def is_within_directory(directory, target):
    abs_directory = os.path.abspath(directory)
    abs_target = os.path.abspath(target)
    return os.path.commonpath([abs_directory]) == os.path.commonpath([abs_directory, abs_target])

def safe_extract(tar: tarfile.TarFile, path: str):
    for member in tar.getmembers():
        member_path = os.path.join(path, member.name)
        if not is_within_directory(path, member_path):
            raise Exception("Tente d’extraire en dehors du dossier autorisé !")
    tar.extractall(path)

def download_stockfish():
    print("📦 Téléchargement de Stockfish...")
    url = "https://github.com/official-stockfish/Stockfish/releases/download/sf_17.1/stockfish-ubuntu-x86-64-avx2.tar"
    local = "/tmp/stockfish.tar"
    urllib.request.urlretrieve(url, local)

    with tarfile.open(local, "r:") as tar_ref:
        safe_extract(tar_ref, "/tmp/stockfish_extracted")

    for root, dirs, files in os.walk("/tmp/stockfish_extracted"):
        if "stockfish" in files:
            src = os.path.join(root, "stockfish")
            shutil.copy(src, STOCKFISH_PATH)
            os.chmod(STOCKFISH_PATH, 0o755)
            return True
    return False

if not os.path.exists(STOCKFISH_PATH):
    if not download_stockfish():
        print("❌ Échec du téléchargement ou de l’extraction.")
        exit(1)

print("✅ Stockfish prêt.")
stockfish = Stockfish(STOCKFISH_PATH)
stockfish.set_position(["e2e4", "e7e5"])
print("Coup conseillé :", stockfish.get_best_move())