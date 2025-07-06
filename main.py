import os, stat, shutil, tarfile, requests, chess.engine
from pathlib import Path

# ----- CONFIG -----
STOCKFISH_URL = (
    "https://github.com/official-stockfish/Stockfish/"
    "releases/download/sf_17.1/stockfish-ubuntu-x86-64-avx2.tar"
)
WORK_DIR   = Path("/tmp/stockfish_work")
ENGINE_BIN = WORK_DIR / "stockfish"

# ----- TELECHARGEMENT & EXTRACTION -----
def download_stockfish(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"📥 Téléchargement : {url}")
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    print(f"✅ Fichier téléchargé : {dest.stat().st_size/1_048_576:.1f} MB")
    return dest

def extract_tar(tar_path: Path, out_dir: Path) -> Path:
    print("📂 Extraction du .tar…")
    out_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "r:") as tar:
        tar.extractall(out_dir, filter="data")
    for f in out_dir.rglob("*"):
        if f.is_file() and f.name.startswith("stockfish") and os.access(f, os.X_OK):
            print(f"🔎 Binaire trouvé : {f}")
            return f
    raise FileNotFoundError("Binaire Stockfish introuvable dans l’archive")

def ensure_engine_ready():
    if ENGINE_BIN.exists():
        print("👍 Stockfish déjà présent.")
        return
    tar_file = WORK_DIR / "stockfish.tar"
    download_stockfish(STOCKFISH_URL, tar_file)
    bin_in_tar = extract_tar(tar_file, WORK_DIR / "extracted")
    shutil.copy(bin_in_tar, ENGINE_BIN)
    ENGINE_BIN.chmod(ENGINE_BIN.stat().st_mode | stat.S_IEXEC)
    tar_file.unlink(missing_ok=True)
    print("✅ Installation terminée.")

# ----- TEST DU MOTEUR -----
def quick_test():
    print("🚀 Lancement du moteur pour test…")
    eng = chess.engine.SimpleEngine.popen_uci(str(ENGINE_BIN))
    board = chess.Board()
    info  = eng.analyse(board, chess.engine.Limit(depth=10))
    move  = info["pv"][0]
    print("♟️ Coup conseillé :", board.san(move))
    eng.quit()
    print("🏁 Test terminé, tout est OK.")

# ----- MAIN -----
if __name__ == "__main__":
    try:
        ensure_engine_ready()
        quick_test()
    except Exception as e:
        print("❌ Problème :", e)
        raise