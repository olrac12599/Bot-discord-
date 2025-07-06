import os, io, stat, tarfile, shutil, requests, discord, chess, chess.engine, chess.pgn
from pathlib import Path
from discord.ext import commands

# ---- CONFIG ----
STOCKFISH_URL = (
    "https://github.com/official-stockfish/Stockfish/"
    "releases/download/sf_17.1/stockfish-ubuntu-x86-64-avx2.tar"
)
WORK_DIR = Path("/tmp/stockfish")
ENGINE_BIN = WORK_DIR / "stockfish"

BOT_TOKEN = os.getenv("DISCORD_TOKEN") or "VOTRE_TOKEN_DISCORD_ICI"

bot = commands.Bot(command_prefix="/", intents=discord.Intents.default())

# ---- INSTALLATION DE STOCKFISH ----
def download_stockfish():
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    archive = WORK_DIR / "sf.tar"
    print(f"📥 Téléchargement : {STOCKFISH_URL}")
    r = requests.get(STOCKFISH_URL, stream=True, timeout=60)
    r.raise_for_status()
    with open(archive, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    print(f"✅ Téléchargé : {archive.stat().st_size/1_048_576:.1f} MB")
    return archive

def extract_stockfish(archive: Path):
    print("📂 Extraction...")
    with tarfile.open(archive, "r:") as tar:
        tar.extractall(WORK_DIR, filter="data")
    for f in WORK_DIR.rglob("*"):
        if "stockfish" in f.name and os.access(f, os.X_OK):
            shutil.copy(f, ENGINE_BIN)
            ENGINE_BIN.chmod(ENGINE_BIN.stat().st_mode | stat.S_IEXEC)
            return True
    return False

def ensure_stockfish():
    if ENGINE_BIN.exists():
        print("✅ Stockfish déjà prêt.")
        return
    archive = download_stockfish()
    if extract_stockfish(archive):
        print("✅ Installation terminée.")
        archive.unlink(missing_ok=True)
    else:
        raise RuntimeError("❌ Stockfish introuvable après extraction.")

# ---- ANALYSE PGN ----
async def analyser_partie(pgn_text: str):
    pgn = io.StringIO(pgn_text)
    game = chess.pgn.read_game(pgn)
    if game is None:
        return None, "Le format PGN est invalide."

    engine = chess.engine.SimpleEngine.popen_uci(str(ENGINE_BIN))
    analyses = []
    board = game.board()

    for move in game.mainline_moves():
        info_before = engine.analyse(board, chess.engine.Limit(time=0.1))
        board.push(move)
        info_after = engine.analyse(board, chess.engine.Limit(time=0.1))
        analyses.append({
            "move": move,
            "score_before": info_before["score"],
            "score_after": info_after["score"],
            "best_move": info_before.get("pv")[0] if "pv" in info_before else None
        })

    engine.quit()
    return analyses, None

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

# ---- COMMANDE DISCORD ----
@bot.slash_command(name="chess", description="Analyse une partie d'échecs au format PGN.")
async def analyser(ctx: discord.ApplicationContext, pgn: str):
    await ctx.defer()
    analyses, error = await analyser_partie(pgn)
    if error:
        await ctx.respond(f"❌ Erreur : {error}")
        return

    index = 4 if len(analyses) > 4 else len(analyses) - 1
    analyse_coup = analyses[index]

    board = chess.pgn.read_game(io.StringIO(pgn)).board()
    for i in range(index + 1):
        board.push(analyses[i]['move'])

    turn = board.turn
    quality = get_move_quality(analyse_coup["score_before"], analyse_coup["score_after"], not turn)
    score_cp = analyse_coup["score_after"].white().score(mate_score=10000) / 100.0

    embed = discord.Embed(
        title=f"Coup {index+1} : {board.san(analyse_coup['move'])}",
        description=f"**Qualité :** {quality}\n**Évaluation :** {score_cp}",
        color=discord.Color.blue()
    )

    svg = chess.svg.board(board=board, lastmove=analyse_coup["move"]).encode("utf-8")
    file = discord.File(io.BytesIO(svg), filename="board.svg")
    await ctx.respond("Voici l’analyse du coup sélectionné :", file=file, embed=embed)

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

# ---- LANCEMENT ----
if __name__ == "__main__":
    ensure_stockfish()
    bot.run(BOT_TOKEN)