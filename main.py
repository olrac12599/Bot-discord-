import os
import io
import stat
import tarfile
import shutil
import requests
import re
import sys
from pathlib import Path
import discord
from discord.ext import commands
import chess
import chess.engine
import chess.pgn
import chess.svg
import matplotlib.pyplot as plt
import cairosvg

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or "VOTRE_TOKEN_DISCORD_ICI"
COMMAND_PREFIX = "!"
WORK_DIR = Path("/tmp/stockfish_bot")
ENGINE_BIN = WORK_DIR / "stockfish_bin"

# --- DISCORD SETUP ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

# --- STOCKFISH: INSTALLATION AUTO ---
def get_stockfish_url():
    if sys.platform.startswith("linux"):
        return "https://github.com/official-stockfish/Stockfish/releases/latest/download/stockfish-ubuntu-x86-64-avx2.tar"
    elif sys.platform == "win32":
        return "https://github.com/official-stockfish/Stockfish/releases/latest/download/stockfish-windows-x86-64-avx2.zip"
    elif sys.platform == "darwin":
        return "https://github.com/official-stockfish/Stockfish/releases/latest/download/stockfish-macos-x86-64-modern.tar"
    else:
        raise RuntimeError(f"Système non supporté : {sys.platform}")

def download_and_extract_stockfish():
    stockfish_url = get_stockfish_url()
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = WORK_DIR / Path(stockfish_url).name

    print(f"📥 Téléchargement de Stockfish depuis {stockfish_url}...")
    r = requests.get(stockfish_url, stream=True, timeout=60)
    r.raise_for_status()
    with open(archive_path, "wb") as f:
        shutil.copyfileobj(r.raw, f)

    print("📂 Extraction du binaire...")
    shutil.unpack_archive(archive_path, WORK_DIR)

    for f in WORK_DIR.rglob("*stockfish*"):
        if f.is_file() and ("stockfish" in f.name):
            f.chmod(f.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            shutil.copyfile(f, ENGINE_BIN)
            ENGINE_BIN.chmod(ENGINE_BIN.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            print(f"✅ Stockfish installé : {ENGINE_BIN}")
            archive_path.unlink(missing_ok=True)
            return True

    raise RuntimeError("❌ Binaire Stockfish introuvable après extraction.")

def ensure_stockfish():
    if not ENGINE_BIN.exists():
        download_and_extract_stockfish()

# --- ANALYSE ---
def get_move_quality(cp_loss: int):
    if cp_loss <= 15:
        return "Excellent", "🟢"
    elif cp_loss <= 30:
        return "Bon", "🔵"
    elif cp_loss <= 70:
        return "Imprécision", "🟡"
    elif cp_loss <= 150:
        return "Erreur", "🟠"
    else:
        return "Gaffe", "🔴"

def calculate_accuracy(cp_losses: list) -> float:
    if not cp_losses:
        return 100.0
    scores = [100 * (1 - min(1, cp / 300)) for cp in cp_losses]
    return sum(scores) / len(scores)

def generate_eval_graph(evals: list, path: Path):
    import matplotlib.pyplot as plt
    plt.figure(figsize=(10, 4))
    plt.plot(evals, color='black', linewidth=2)
    plt.title("Évaluation de la Partie")
    plt.xlabel("Coup")
    plt.ylabel("Centipawns")
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.axhline(0, color='grey', linewidth=1)
    plt.ylim(-1000, 1000)
    plt.savefig(path, format='png', bbox_inches='tight')
    plt.close()

# --- COMMANDE !analyser ---
@bot.command(name="analyser", help="Analyse une partie d'échecs depuis un PGN ou une URL (Lichess/Chess.com)")
async def analyser(ctx, *, game_input: str):
    pgn_str = game_input.strip()
    if pgn_str.startswith("http"):
        await ctx.send("🔄 Récupération de la partie...")
        try:
            if "lichess.org" in pgn_str:
                game_id = re.search(r"lichess\.org/(\w{8})", pgn_str).group(1)
                url = f"https://lichess.org/game/export/{game_id}"
                response = requests.get(url, headers={"Accept": "application/x-chess-pgn"})
            elif "chess.com" in pgn_str:
                response = requests.get(pgn_str + ".pgn")
                if not response.ok:
                    await ctx.send("❌ Chess.com ne permet pas l'accès direct. Utilise le PGN complet.")
                    return
            else:
                await ctx.send("❌ URL non reconnue.")
                return
            response.raise_for_status()
            pgn_str = response.text
        except Exception as e:
            await ctx.send(f"❌ Erreur de récupération : {e}")
            return

    try:
        game = chess.pgn.read_game(io.StringIO(pgn_str))
        if not game:
            await ctx.send("❌ PGN invalide.")
            return

        await ctx.send("🔍 Analyse en cours...")

        board = game.board()
        white_cp, black_cp, evals, lines = [], [], [], []

        async with chess.engine.SimpleEngine.popen_uci(str(ENGINE_BIN)) as engine:
            info_before = await engine.analyse(board, chess.engine.Limit(time=0.3))
            for i, move in enumerate(game.mainline_moves()):
                info_after = await engine.analyse(board, chess.engine.Limit(time=0.3), root_moves=[move])

                score_before = info_before['score'].pov(board.turn)
                score_after = info_after[0]['score'].pov(board.turn)

                if score_before.is_mate() or score_after.is_mate():
                    cp_loss = 350
                else:
                    cp_loss = score_before.score() - score_after.score()

                quality, emoji = get_move_quality(cp_loss)
                move_san = board.san(move)
                best = board.san(info_before["pv"][0]) if "pv" in info_before else "?"

                line = f"{'⚪️' if board.turn else '⚫️'} `{i+1}. {move_san}` — {emoji} {quality}"
                if quality in ["Imprécision", "Erreur", "Gaffe"] and move_san != best:
                    line += f" (Meilleur: {best})"
                lines.append(line)

                (white_cp if board.turn else black_cp).append(cp_loss)
                board.push(move)
                info_before = info_after[0]
                evals.append(info_before["score"].white().score(mate_score=10000) or 0)

        # Accuracies
        white_acc = calculate_accuracy(white_cp)
        black_acc = calculate_accuracy(black_cp)

        # Graph
        graph_path = WORK_DIR / f"eval_graph_{ctx.message.id}.png"
        generate_eval_graph(evals, graph_path)

        # Embed
        embed = discord.Embed(
            title=f"{game.headers.get('White', 'Blancs')} vs {game.headers.get('Black', 'Noirs')}",
            description="Analyse de la partie",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="🎯 Précision",
            value=f"⚪️ Blancs : {white_acc:.1f}%\n⚫️ Noirs : {black_acc:.1f}%",
            inline=False
        )
        embed.set_image(url="attachment://graph.png")
        embed.set_footer(text="Propulsé par Stockfish")

        # Fichier texte avec les lignes d'analyse
        report_text = "\n".join(lines)
        report_file = discord.File(fp=io.StringIO(report_text), filename="analyse.txt")
        graph_file = discord.File(graph_path, filename="graph.png")

        await ctx.send(embed=embed, files=[graph_file, report_file])

    except Exception as e:
        await ctx.send(f"❌ Erreur durant l’analyse : {e}")
        import traceback
        traceback.print_exc()

# --- BOT READY ---
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

# --- MAIN ---
if __name__ == "__main__":
    try:
        ensure_stockfish()
        bot.run(DISCORD_TOKEN)
    except RuntimeError as e:
        print(e)
    except discord.errors.LoginFailure:
        print("❌ Token Discord invalide.")