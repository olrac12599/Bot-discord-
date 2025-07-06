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

# --- DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

# --- INSTALLATION STOCKFISH ---
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

# --- CLASSIFICATION DES COUPS ---
def classify_move(score_before, score_after, turn, best_move, played_move):
    # Mat imminent
    if score_after.is_mate():
        mate = score_after.mate()
        return "♟️ Mat en " + str(abs(mate)) if mate else "♟️ Mat"
    
    eval_before = score_before.white().score() if turn else score_before.black().score()
    eval_after = score_after.white().score() if turn else score_after.black().score()
    cp_loss = eval_before - eval_after

    if cp_loss < 15:
        if best_move == played_move:
            return "✨ Brillant"
        return "👍 Excellent"
    elif cp_loss < 50:
        return "📘 Théorique"
    elif cp_loss < 100:
        return "🟡 Imprécision"
    elif cp_loss < 200:
        return "🟠 Erreur"
    else:
        return "🔴 Gaffe"

def calculate_accuracy(cp_losses):
    return 100 - min(100, sum(min(x, 300) for x in cp_losses) / len(cp_losses)) if cp_losses else 100

def generate_eval_graph(evals, path):
    plt.figure(figsize=(10, 4))
    plt.plot(evals, color='black', linewidth=2)
    plt.title("Évaluation de la Partie")
    plt.xlabel("Coup")
    plt.ylabel("Évaluation (centipawns)")
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.axhline(0, color='grey')
    plt.ylim(-1000, 1000)
    plt.tight_layout()
    plt.savefig(path)
    plt.close()

# --- COMMANDE !analyser ---
@bot.command()
async def analyser(ctx, *, pgn: str):
    await ctx.send("⏳ Analyse de la partie...")

    try:
        pgn_clean = re.sub(r"{\[.*?\]}", "", pgn)
        pgn_io = io.StringIO(pgn_clean)
        game = chess.pgn.read_game(pgn_io)

        if not game:
            await ctx.send("❌ Format PGN invalide.")
            return

        board = game.board()
        engine = chess.engine.SimpleEngine.popen_uci(str(ENGINE_BIN))
        evals = []
        white_losses, black_losses = [], []
        report = ""

        for i, move in enumerate(game.mainline_moves()):
            info_before = engine.analyse(board, chess.engine.Limit(time=0.1))
            best = info_before.get("pv", [None])[0]
            score_before = info_before["score"]

            board.push(move)

            info_after = engine.analyse(board, chess.engine.Limit(time=0.1))
            score_after = info_after["score"]

            classification = classify_move(score_before, score_after, not board.turn, best, move)
            player = "⚪️" if not board.turn else "⚫️"
            san = board.san(move)

            cp_loss = 0
            if score_before.is_cp() and score_after.is_cp():
                cp_loss = score_before.pov(not board.turn).score() - score_after.pov(not board.turn).score()

            if not board.turn:
                white_losses.append(cp_loss)
            else:
                black_losses.append(cp_loss)

            score_str = f"{score_after.white().score() / 100:.2f}" if score_after.is_cp() else f"M{score_after.mate()}"
            report += f"{player} {san} — {classification} ({score_str})\n"
            evals.append(score_after.white().score(mate_score=1000) if score_after else 0)

        engine.quit()

        # Précision et Graph
        white_accuracy = calculate_accuracy(white_losses)
        black_accuracy = calculate_accuracy(black_losses)

        graph_path = WORK_DIR / f"graph_{ctx.message.id}.png"
        generate_eval_graph(evals, graph_path)

        embed = discord.Embed(
            title=f"Analyse de {game.headers.get('White')} vs {game.headers.get('Black')}",
            color=discord.Color.green()
        )
        embed.add_field(name="🎯 Précision", value=f"⚪️ Blancs : {white_accuracy:.1f}%\n⚫️ Noirs : {black_accuracy:.1f}%", inline=False)
        embed.set_image(url="attachment://graph.png")

        # Envoie
        if len(report) > 1900:
            txt = io.StringIO(report)
            await ctx.send(embed=embed, files=[discord.File(graph_path, "graph.png"), discord.File(txt, "analyse.txt")])
        else:
            await ctx.send(embed=embed, file=discord.File(graph_path, "graph.png"))
            await ctx.send(f"📝\n{report}")

    except Exception as e:
        await ctx.send(f"❌ Erreur pendant l’analyse : {e}")

# --- READY ---
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

# --- MAIN ---
if __name__ == "__main__":
    ensure_stockfish()
    bot.run(DISCORD_TOKEN)