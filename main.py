import os, io, stat, tarfile, shutil, requests, re
from pathlib import Path
import discord
from discord.ext import commands
import chess
import chess.engine
import chess.pgn
import matplotlib.pyplot as plt

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or "TON_TOKEN_ICI"
COMMAND_PREFIX = "!"
STOCKFISH_URL = "https://github.com/official-stockfish/Stockfish/releases/download/sf_17.1/stockfish-ubuntu-x86-64-avx2.tar"
WORK_DIR = Path("/tmp/stockfish")
ENGINE_BIN = WORK_DIR / "stockfish_bin"

# --- DISCORD BOT ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

# --- INSTALLATION DE STOCKFISH ---
def download_stockfish():
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    archive = WORK_DIR / "sf.tar"
    print("📥 Téléchargement de Stockfish 17.1...")
    r = requests.get(STOCKFISH_URL, stream=True, timeout=60)
    with open(archive, "wb") as f:
        shutil.copyfileobj(r.raw, f)
    return archive

def extract_stockfish(archive: Path):
    print("📂 Extraction de Stockfish...")
    with tarfile.open(archive, "r:") as tar:
        tar.extractall(WORK_DIR)
    for f in WORK_DIR.rglob("*stockfish*"):
        if f.is_file() and os.access(f, os.X_OK):
            shutil.copyfile(f, ENGINE_BIN)
            ENGINE_BIN.chmod(f.stat().st_mode | stat.S_IEXEC)
            print(f"✅ Stockfish prêt : {ENGINE_BIN}")
            return True
    return False

def ensure_stockfish():
    if ENGINE_BIN.exists():
        return
    archive = download_stockfish()
    if not extract_stockfish(archive):
        raise RuntimeError("❌ Stockfish introuvable.")
    archive.unlink()

# --- QUALITÉ DES COUPS ---
def classify_move(score_before, score_after, turn):
    pov_before = score_before.white() if turn == chess.WHITE else score_before.black()
    pov_after = score_after.white() if turn == chess.WHITE else score_after.black()
    if pov_before.is_mate() or pov_after.is_mate():
        return "✨ Brillant"
    if pov_before.score() is None or pov_after.score() is None:
        return "Inconnu"
    loss = pov_before.score() - pov_after.score()
    if loss > 300:
        return "🔴 Gaffe"
    elif loss > 150:
        return "🟠 Erreur"
    elif loss > 50:
        return "🟡 Imprécision"
    elif loss < 10:
        return "📚 Théorique"
    else:
        return "👍 Bon"

def format_score(score):
    if score.is_mate():
        return f"M{score.mate()}"
    return f"{score.score()/100:.2f}"

def calculate_accuracy(cp_losses):
    if not cp_losses:
        return 100.0
    accuracy = [100 * (1 - min(1, loss / 300)) for loss in cp_losses]
    return round(sum(accuracy) / len(accuracy), 1)

def generate_graph(evals, filename):
    plt.figure(figsize=(8, 3))
    plt.plot(evals, label="Évaluation", color="black")
    plt.axhline(0, linestyle="--", color="gray")
    plt.title("Évolution de l'évaluation")
    plt.xlabel("Coup")
    plt.ylabel("Centipawns")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(filename)
    plt.close()

# --- COMMANDE !analyser ---
@bot.command()
async def analyser(ctx, *, pgn_input: str):
    await ctx.send("🔍 Analyse en cours...")
    try:
        # Nettoyage
        pgn_clean = re.sub(r"{\[.*?\]}", "", pgn_input)
        pgn_io = io.StringIO(pgn_clean)
        game = chess.pgn.read_game(pgn_io)

        if not game:
            await ctx.send("❌ PGN invalide.")
            return

        board = game.board()
        engine = chess.engine.SimpleEngine.popen_uci(str(ENGINE_BIN))
        messages = []
        white_cp, black_cp, evals = [], [], []

        for i, move in enumerate(game.mainline_moves(), 1):
            info_before = engine.analyse(board, chess.engine.Limit(time=0.1))
            best_score = info_before["score"]
            best_move = info_before["pv"][0] if "pv" in info_before else None

            if move not in board.legal_moves:
                await ctx.send(f"❌ Coup illégal détecté : {move}")
                break

            board.push(move)
            info_after = engine.analyse(board, chess.engine.Limit(time=0.1))
            actual_score = info_after["score"]

            # Analyse
            cp_loss = 0
            if not best_score.is_mate() and not actual_score.is_mate():
                cp_loss = (best_score.score() or 0) - (actual_score.score() or 0)

            if board.turn == chess.WHITE:
                black_cp.append(abs(cp_loss))
            else:
                white_cp.append(abs(cp_loss))

            quality = classify_move(best_score, actual_score, not board.turn)
            emoji = "⚪️" if not board.turn else "⚫️"
            san = board.san(move)
            msg = f"{emoji} {san} — {quality} ({format_score(actual_score)})"
            if best_move and best_move != move:
                try:
                    best_move_san = board.san(best_move)
                    msg += f" | Meilleur coup : {best_move_san}"
                except:
                    pass
            messages.append(msg)
            evals.append(actual_score.white().score(mate_score=10000) or 0)

        engine.quit()

        # Résumé
        accuracy_white = calculate_accuracy(white_cp)
        accuracy_black = calculate_accuracy(black_cp)
        summary = (
            f"🎯 **Précision** :\n"
            f"⚪️ Blancs : {accuracy_white}%\n"
            f"⚫️ Noirs : {accuracy_black}%\n"
        )

        # Graphique
        graph_path = WORK_DIR / f"eval_{ctx.message.id}.png"
        generate_graph(evals, graph_path)

        embed = discord.Embed(
            title=f"Analyse de Partie : {game.headers.get('White', '?')} vs {game.headers.get('Black', '?')}",
            description=summary,
            color=discord.Color.green()
        )
        file = discord.File(graph_path, filename="eval.png")
        embed.set_image(url="attachment://eval.png")

        if len(messages) > 50:
            buffer = io.StringIO("\n".join(messages))
            await ctx.send(embed=embed, files=[file, discord.File(buffer, filename="analyse.txt")])
        else:
            await ctx.send(embed=embed, file=file)
            await ctx.send("\n".join(messages))

    except Exception as e:
        await ctx.send(f"❌ Erreur pendant l’analyse : {e}")

# --- READY ---
@bot.event
async def on_ready():
    print(f"🤖 Connecté en tant que {bot.user}")

# --- MAIN ---
if __name__ == "__main__":
    ensure_stockfish()
    bot.run(DISCORD_TOKEN)