import os, io, stat, tarfile, shutil, requests, re
from pathlib import Path
import discord
from discord.ext import commands
import chess
import chess.engine
import chess.pgn
import asyncio

# --- CONFIG ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or "VOTRE_TOKEN_DISCORD_ICI"
COMMAND_PREFIX = "!"
STOCKFISH_URL = "https://github.com/official-stockfish/Stockfish/releases/download/sf_17.1/stockfish-ubuntu-x86-64-avx2.tar"
WORK_DIR = Path("/tmp/stockfish")
ENGINE_BIN = WORK_DIR / "stockfish_bin"

# --- DISCORD SETUP ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

# --- STOCKFISH INSTALL ---
def download_stockfish():
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    archive = WORK_DIR / "sf.tar"
    print("📥 Téléchargement de Stockfish 17.1...")
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
        if f.is_file() and os.access(f, os.X_OK) and "stockfish" in f.name.lower():
            shutil.copyfile(f, ENGINE_BIN)
            ENGINE_BIN.chmod(ENGINE_BIN.stat().st_mode | stat.S_IEXEC)
            print(f"✅ Stockfish installé depuis {f}")
            return True
    return False

def ensure_stockfish():
    if ENGINE_BIN.exists():
        return
    archive = download_stockfish()
    if not extract_stockfish(archive):
        raise RuntimeError("❌ Stockfish introuvable après extraction.")
    archive.unlink(missing_ok=True)

# --- ANALYSE LOGIQUE ---
def get_move_quality(score_before, score_after, turn):
    pov_before = score_before.white() if turn == chess.WHITE else score_before.black()
    pov_after = score_after.white() if turn == chess.WHITE else score_after.black()
    if pov_before.is_mate() or pov_after.is_mate():
        return "⚡️ Coup décisif"
    loss = pov_before.score() - pov_after.score()
    if loss > 200:
        return "🔴 ⁉️ Gaffe"
    elif loss > 100:
        return "🟠 ❓ Erreur"
    elif loss > 50:
        return "🟡 ❔ Imprécision"
    else:
        return "📚 Théorique"

# --- COMMANDE !analyser ---
@bot.command()
async def analyser(ctx, *, pgn: str):
    await ctx.send("⏳ Analyse en cours...")

    try:
        pgn_clean = re.sub(r"{\[.*?\]}", "", pgn)
        pgn_io = io.StringIO(pgn_clean)
        game = chess.pgn.read_game(pgn_io)

        if not game:
            await ctx.send("❌ Format PGN invalide.")
            return

        board = game.board()
        analyses = []

        async with chess.engine.SimpleEngine.popen_uci(str(ENGINE_BIN)) as engine:
            info_before = await engine.analyse(board, chess.engine.Limit(time=0.2))
            for move in game.mainline_moves():
                if move not in board.legal_moves:
                    await ctx.send(f"⚠️ Coup illégal détecté : `{move.uci()}`")
                    return

                info_after = await engine.analyse(board, chess.engine.Limit(time=0.2))
                analyses.append((move, info_before["score"], info_after["score"]))
                board.push(move)
                info_before = info_after

        # Génération du message
        msg = ""
        board = game.board()
        for i, (move, score_before, score_after) in enumerate(analyses):
            player = "⚪️" if board.turn == chess.WHITE else "⚫️"
            san = board.san(move)
            board.push(move)
            quality = get_move_quality(score_before, score_after, not board.turn)
            msg += f"{player} {san} — {quality}\n"

        if len(msg) > 1900:
            buffer = io.StringIO(msg)
            await ctx.send("📝 Analyse complète :", file=discord.File(fp=buffer, filename="analyse.txt"))
        else:
            await ctx.send(msg)

    except Exception as e:
        await ctx.send(f"❌ Erreur pendant l'analyse : {e}")

# --- READY ---
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

# --- MAIN ---
if __name__ == "__main__":
    ensure_stockfish()
    bot.run(DISCORD_TOKEN)