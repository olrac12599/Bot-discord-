import os, io, stat, tarfile, shutil, requests, re
import discord
from discord.ext import commands
import chess
import chess.engine
import chess.pgn
from pathlib import Path

# ---- CONFIGURATION ----
TOKEN = os.getenv("DISCORD_TOKEN") or "VOTRE_TOKEN_DISCORD_ICI"
COMMAND_PREFIX = "!"
STOCKFISH_URL = "https://github.com/official-stockfish/Stockfish/releases/download/sf_17.1/stockfish-ubuntu-x86-64-avx2.tar"
WORK_DIR = Path("/tmp/stockfish")
ENGINE_BIN = WORK_DIR / "stockfish_bin"

# ---- BOT INIT ----
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

# ---- INSTALLATION STOCKFISH ----
def download_stockfish():
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    archive = WORK_DIR / "sf.tar"
    print("📥 Téléchargement de Stockfish...")
    r = requests.get(STOCKFISH_URL, stream=True, timeout=60)
    r.raise_for_status()
    with open(archive, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    return archive

def extract_stockfish(archive: Path):
    print("📂 Extraction du binaire...")
    with tarfile.open(archive, "r:") as tar:
        tar.extractall(WORK_DIR, filter="data")

    for f in WORK_DIR.rglob("*"):
        if f.is_file() and os.access(f, os.X_OK) and "stockfish" in f.name:
            shutil.copyfile(f, ENGINE_BIN)
            ENGINE_BIN.chmod(ENGINE_BIN.stat().st_mode | stat.S_IEXEC)
            print(f"✅ Binaire copié depuis : {f}")
            return True

    print("❌ Aucun binaire Stockfish trouvé.")
    return False

def ensure_stockfish():
    if ENGINE_BIN.exists():
        return
    archive = download_stockfish()
    if not extract_stockfish(archive):
        raise RuntimeError("❌ Impossible d’installer Stockfish.")
    archive.unlink(missing_ok=True)

# ---- QUALITÉ DES COUPS ----
def get_move_quality(score_before, score_after, turn):
    pov_before = score_before.white() if turn == chess.WHITE else score_before.black()
    pov_after = score_after.white() if turn == chess.WHITE else score_after.black()

    if pov_before.is_mate() or pov_after.is_mate():
        return "⚡️ Coup décisif"
    loss = pov_before.score() - pov_after.score()
    if loss > 200:
        return "⁉️ Gaffe"
    elif loss > 100:
        return "❓ Erreur"
    elif loss > 50:
        return "❔ Imprécision"
    else:
        return "✅ Bon coup"

# ---- COMMANDE !analyser ----
@bot.command()
async def analyser(ctx, *, pgn: str):
    await ctx.send("🔎 Analyse en cours...")

    try:
        # Nettoyage des annotations inutiles
        pgn_clean = re.sub(r"{\[.*?\]}", "", pgn)
        pgn_io = io.StringIO(pgn_clean)
        game = chess.pgn.read_game(pgn_io)

        if not game:
            await ctx.send("❌ Format PGN invalide.")
            return

        board = game.board()
        engine = chess.engine.SimpleEngine.popen_uci(str(ENGINE_BIN))
        analyses = []

        for move in game.mainline_moves():
            if move not in board.legal_moves:
                await ctx.send(f"⚠️ Coup illégal détecté : `{move.uci()}`")
                break

            info_before = engine.analyse(board, chess.engine.Limit(time=0.1))
            board.push(move)
            info_after = engine.analyse(board, chess.engine.Limit(time=0.1))

            analyses.append((move, info_before["score"], info_after["score"]))

        engine.quit()

        if not analyses:
            await ctx.send("❌ Aucune analyse effectuée.")
            return

        # Générer le message avec tous les coups
        msg = ""
        board = game.board()
        for i, (move, score_before, score_after) in enumerate(analyses):
            board.push(move)
            quality = get_move_quality(score_before, score_after, not board.turn)
            score_cp = score_after.white().score(mate_score=10000) / 100.0
            msg += f"**{i+1}.** `{move.uci()}` → {quality} | Éval : `{score_cp}`\n"

        # Envoyer en plusieurs messages si trop long
        if len(msg) > 2000:
            for chunk in [msg[i:i+1900] for i in range(0, len(msg), 1900)]:
                await ctx.send(chunk)
        else:
            await ctx.send(msg)

    except Exception as e:
        await ctx.send(f"❌ Erreur pendant l'analyse : {e}")

# ---- DÉMARRAGE ----
@bot.event
async def on_ready():
    print(f"✅ Bot prêt : connecté en tant que {bot.user}")

if __name__ == "__main__":
    ensure_stockfish()
    bot.run(TOKEN)