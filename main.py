import os, io, stat, tarfile, shutil, requests, re
from pathlib import Path
import discord
from discord.ext import commands
import chess
import chess.engine
import chess.pgn
import matplotlib.pyplot as plt

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
        tar.extractall(WORK_DIR)
    for f in WORK_DIR.rglob("*"):
        if f.is_file() and os.access(f, os.X_OK) and "stockfish" in f.name:
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

# --- ÉVALUATION ---
def format_score(score):
    if score.is_mate():
        return f"M{score.mate()}"
    return f"{score.score / 100:.2f}"

def get_move_quality(best_score, actual_score, turn):
    best = best_score.white() if turn == chess.WHITE else best_score.black()
    actual = actual_score.white() if turn == chess.WHITE else actual_score.black()

    if best.is_mate() or actual.is_mate():
        return "⚡️ Coup décisif", 0

    loss = (best.score or 0) - (actual.score or 0)

    if loss >= 300:
        return "🔴 ⁉️ Gaffe", loss
    elif loss >= 150:
        return "🟠 ❓ Erreur", loss
    elif loss >= 50:
        return "🟡 ❔ Imprécision", loss
    elif loss >= 15:
        return "👍 Bon", loss
    else:
        return "📚 Théorique", loss

# --- GRAPHIQUE ---
def generate_graph(evals, path):
    plt.figure(figsize=(10, 4))
    plt.plot(evals, color='blue')
    plt.axhline(0, color='black', linewidth=0.5)
    plt.title("Évolution de l'évaluation")
    plt.xlabel("Coup")
    plt.ylabel("Évaluation (centipawns)")
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.savefig(path, bbox_inches='tight')
    plt.close()

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
        engine = chess.engine.SimpleEngine.popen_uci(str(ENGINE_BIN))

        analyses = []
        evals = []

        for move in game.mainline_moves():
            if move not in board.legal_moves:
                await ctx.send(f"⚠️ Coup illégal détecté : `{move.uci()}`")
                break

            info_before = engine.analyse(board, chess.engine.Limit(time=0.2))
            best_move = info_before.get("pv", [None])[0]

            board.push(move)
            info_after = engine.analyse(board, chess.engine.Limit(time=0.2))

            best_score = info_before["score"]
            actual_score = info_after["score"]

            evals.append(actual_score.white().score(mate_score=10000) or 0)

            analyses.append((move, best_move, best_score, actual_score, board.turn))

        engine.quit()

        # Format texte
        msg = ""
        board = game.board()
        for i, (move, best_move, best_score, actual_score, turn) in enumerate(analyses):
            player = "⚪️" if board.turn == chess.WHITE else "⚫️"
            san = board.san(move)
            board.push(move)

            quality, loss = get_move_quality(best_score, actual_score, not board.turn)
            best_san = board.san(best_move) if best_move and best_move in board.legal_moves else "?"
            score = format_score(actual_score)

            line = f"{player} {san} — {quality} ({score})"
            if quality.startswith("🟡") or quality.startswith("🟠") or quality.startswith("🔴"):
                line += f" | Meilleur : {best_san}"
            msg += line + "\n"

        # Graphique
        graph_path = WORK_DIR / f"eval_graph_{ctx.message.id}.png"
        generate_graph(evals, graph_path)

        # Envoi
        if len(msg) > 1900:
            buffer = io.StringIO(msg)
            await ctx.send("📝 Analyse :", files=[
                discord.File(buffer, filename="analyse.txt"),
                discord.File(graph_path, filename="eval.png")
            ])
        else:
            await ctx.send(msg, file=discord.File(graph_path, filename="eval.png"))

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