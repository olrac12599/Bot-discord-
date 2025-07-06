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

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

# --- STOCKFISH INSTALLATION ---
def download_stockfish():
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    archive = WORK_DIR / "sf.tar"
    print("📥 Téléchargement de Stockfish 17.1...")
    r = requests.get(STOCKFISH_URL, stream=True)
    with open(archive, "wb") as f:
        shutil.copyfileobj(r.raw, f)
    return archive

def extract_stockfish(archive: Path):
    print("📂 Extraction de Stockfish...")
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
    if ENGINE_BIN.exists(): return
    archive = download_stockfish()
    if not extract_stockfish(archive):
        raise RuntimeError("❌ Échec installation Stockfish.")
    archive.unlink(missing_ok=True)

# --- QUALITÉ DE COUP ---
def get_move_quality(cp_loss):
    if cp_loss <= 15:
        return "✨ Brillant"
    elif cp_loss <= 30:
        return "👍 Excellent"
    elif cp_loss <= 70:
        return "🟡 Imprécision"
    elif cp_loss <= 150:
        return "🟠 Erreur"
    else:
        return "🔴 Gaffe"

# --- PRÉCISION ---
def calculate_accuracy(cp_losses):
    if not cp_losses:
        return 100.0
    return sum(100 * (1 - min(1, cp / 300)) for cp in cp_losses) / len(cp_losses)

# --- GRAPHIQUE ---
def generate_eval_graph(evals, path):
    plt.figure(figsize=(10, 4))
    plt.plot(evals, color='blue', linewidth=2)
    plt.axhline(0, color='black')
    plt.title("Évaluation (en centipawns)")
    plt.xlabel("Coup")
    plt.ylabel("Avantage")
    plt.grid(True)
    plt.savefig(path)
    plt.close()

# --- COMMANDE !analyser ---
@bot.command()
async def analyser(ctx, *, pgn: str):
    await ctx.send("⏳ Analyse en cours...")

    try:
        pgn_clean = re.sub(r"{\[.*?\]}", "", pgn)
        game = chess.pgn.read_game(io.StringIO(pgn_clean))
        if not game:
            await ctx.send("❌ Format PGN invalide.")
            return

        board = game.board()
        engine = chess.engine.SimpleEngine.popen_uci(str(ENGINE_BIN))
        evals, report = [], []
        white_losses, black_losses = [], []

        for move in game.mainline_moves():
            info_before = engine.analyse(board, chess.engine.Limit(time=0.1))
            score_before = info_before["score"].pov(board.turn)
            best_move = info_before.get("pv", [move])[0]

            if move not in board.legal_moves:
                await ctx.send(f"⚠️ Coup illégal détecté : `{move.uci()}`")
                return

            san = board.san(move)
            cp_before = score_before.score(mate_score=10000) or 0

            board.push(move)

            info_after = engine.analyse(board, chess.engine.Limit(time=0.1))
            score_after = info_after["score"].pov(not board.turn)
            cp_after = score_after.score(mate_score=10000) or 0

            cp_loss = cp_before - cp_after
            quality = get_move_quality(cp_loss)
            player = "⚪️" if board.turn == chess.BLACK else "⚫️"

            line = f"{player} {san} — {quality}"
            if quality in ["🟡 Imprécision", "🟠 Erreur", "🔴 Gaffe"]:
                best_san = board.san(best_move) if best_move in board.legal_moves else best_move.uci()
                line += f" (Meilleur : {best_san})"

            report.append(line)

            if board.turn == chess.WHITE:
                white_losses.append(abs(cp_loss))
            else:
                black_losses.append(abs(cp_loss))

            evals.append(cp_after)

        engine.quit()

        # Précision
        white_acc = calculate_accuracy(white_losses)
        black_acc = calculate_accuracy(black_losses)

        # Graphique
        graph_path = WORK_DIR / f"graph_{ctx.message.id}.png"
        generate_eval_graph(evals, graph_path)

        embed = discord.Embed(title="📊 Rapport d'Analyse", color=discord.Color.green())
        embed.add_field(name="Précision", value=f"⚪️ Blancs : {white_acc:.1f}%\n⚫️ Noirs : {black_acc:.1f}%")
        embed.set_image(url="attachment://graph.png")
        file = discord.File(graph_path, filename="graph.png")

        # Texte long en fichier
        if len("\n".join(report)) > 1900:
            txt = io.StringIO("\n".join(report))
            await ctx.send(embed=embed, files=[file, discord.File(txt, filename="analyse.txt")])
        else:
            await ctx.send(embed=embed, file=file)
            await ctx.send("📝\n" + "\n".join(report))

    except Exception as e:
        await ctx.send(f"❌ Erreur pendant l'analyse : {e}")

# --- BOT READY ---
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

# --- MAIN ---
if __name__ == "__main__":
    ensure_stockfish()
    bot.run(DISCORD_TOKEN)