import os
import urllib.request
import tarfile
import shutil
from stockfish import Stockfish
import zstandard
import requests
import stat
import chess.engine
import asyncio

STOCKFISH_DIR = "/tmp/stockfish_dir"
STOCKFISH_EXEC = os.path.join(STOCKFISH_DIR, "stockfish")

STOCKFISH_URL = (
    "https://github.com/official-stockfish/Stockfish/"
    "releases/download/sf_17.1/stockfish-ubuntu-x86-64-avx2.tar"
)

def download_and_extract():
    os.makedirs(STOCKFISH_DIR, exist_ok=True)
    tar_path = os.path.join(STOCKFISH_DIR, "stockfish.tar")

    print("📦 Téléchargement de Stockfish…")
    urllib.request.urlretrieve(STOCKFISH_URL, tar_path)

    with tarfile.open(tar_path, "r:") as tar:
        tar.extractall(STOCKFISH_DIR, filter="data")
    os.remove(tar_path)

    for root, _, files in os.walk(STOCKFISH_DIR):
        if "stockfish" in files:
            src = os.path.join(root, "stockfish")
            shutil.copy(src, STOCKFISH_EXEC)
            os.chmod(STOCKFISH_EXEC, stat.S_IEXEC)
            return True
    return False

async def test_engine():
    engine = await chess.engine.SimpleEngine.popen_uci(STOCKFISH_EXEC)
    info = await engine.analyse(chess.Board(), chess.engine.Limit(time=0.1))
    move = info["pv"][0]
    print("♟️ Best move:", chess.Board().san(move))
    await engine.quit()

def setup_and_run():
    if not os.path.exists(STOCKFISH_EXEC):
        if not download_and_extract():
            print("❌ Échec download ou extraction")
            return
    print("✅ Stockfish prêt.")
    asyncio.run(test_engine())

if __name__ == "__main__":
    setup_and_run()