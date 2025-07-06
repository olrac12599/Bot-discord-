import os
import io
import stat
import tarfile
import shutil
import requests
import re
from pathlib import Path
import discord
from discord.ext import commands
import chess
import chess.engine
import chess.pgn
import chess.polyglot # Important pour les ouvertures
import matplotlib.pyplot as plt

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or "VOTRE_TOKEN_DISCORD_ICI"
COMMAND_PREFIX = "!"
STOCKFISH_URL = "https://github.com/official-stockfish/Stockfish/releases/download/sf_17.1/stockfish-ubuntu-x86-64-avx2.tar"
# URL d'un livre d'ouvertures populaire (format Polyglot .bin)
OPENING_BOOK_URL = "https://github.com/lichess-org/chess-openings.git"

WORK_DIR = Path("/tmp/stockfish")
ENGINE_BIN = WORK_DIR / "stockfish"
BOOK_PATH = WORK_DIR / "opening_book.bin" # Chemin vers le livre d'ouvertures

# --- MISE EN PLACE DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

# --- INSTALLATION DES DÉPENDANCES (STOCKFISH & LIVRE D'OUVERTURES) ---
def download_file(url: str, dest: Path):
    """Fonction générique pour télécharger un fichier."""
    print(f"📥 Téléchargement de {dest.name}...")
    try:
        r = requests.get(url, stream=True, timeout=120)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    except requests.RequestException as e:
        raise RuntimeError(f"❌ Échec du téléchargement de {dest.name} : {e}")

def ensure_stockfish():
    """Vérifie si Stockfish est présent, sinon l'installe."""
    if ENGINE_BIN.is_file() and os.access(ENGINE_BIN, os.X_OK):
        print("👍 Stockfish est déjà installé.")
        return
    print("Stockfish non trouvé, lancement de l'installation...")
    archive_path = WORK_DIR / "sf.tar.gz"
    download_file(STOCKFISH_URL, archive_path)
    
    print("📂 Extraction de Stockfish...")
    with tarfile.open(archive_path, "r:") as tar:
        for member in tar.getmembers():
            # Cible le binaire dans la structure de l'archive (ex: 'stockfish-ubuntu-x86-64-avx2/stockfish')
            if member.isfile() and 'stockfish' in member.name and member.name.count('/') == 1:
                member.name = Path(member.name).name # Enlève le dossier parent
                tar.extract(member, path=WORK_DIR)
                extracted_file = WORK_DIR / member.name
                shutil.move(extracted_file, ENGINE_BIN)
                break
        else:
            raise RuntimeError("❌ Binaire de Stockfish introuvable dans l'archive.")

    ENGINE_BIN.chmod(ENGINE_BIN.stat().st_mode | stat.S_IEXEC)
    print(f"✅ Stockfish installé dans {ENGINE_BIN}")
    archive_path.unlink(missing_ok=True)

def ensure_opening_book():
    """Vérifie si le livre d'ouvertures est présent, sinon le télécharge."""
    if BOOK_PATH.is_file():
        print("👍 Le livre d'ouvertures est déjà présent.")
        return
    print("Livre d'ouvertures non trouvé, lancement du téléchargement...")
    download_file(OPENING_BOOK_URL, BOOK_PATH)
    print(f"✅ Livre d'ouvertures téléchargé dans {BOOK_PATH}")

# --- LOGIQUE D'ANALYSE D'ÉCHECS (style Chess.com) ---
def get_move_quality(player_move, info_before, info_after, is_sacrifice) -> str:
    """Détermine la qualité d'un coup en se basant sur la logique de Chess.com."""
    pov_score_before = info_before['score'].pov(info_before['board'].turn)
    pov_score_after = info_after['score'].pov(info_after['board'].turn)
    best_move = info_before['pv'][0]

    # La perte en centipawns
    loss = (pov_score_before.score(mate_score=10000) or 0) - (pov_score_after.score(mate_score=10000) or 0)

    # Catégorisation
    if player_move == best_move:
        if is_sacrifice and loss < -50: # Le coup est le meilleur ET c'est un sacrifice qui améliore la situation
            return "✨ Brillant (!!)"
        else:
            return "⭐ Meilleur coup"

    if loss < 10:
        return "👍 Excellent"
    if loss < 40:
        return "✅ Bon"
    if loss < 100:
        return "🟡 Imprécision (?!)"
    if loss < 250:
        return "🟠 Erreur (?)"
    
    return "🔴 Gaffe (??)"
    # La catégorie "Occasion manquée" est plus complexe car elle dépend de l'évaluation absolue
    # et de l'état de la partie (par ex, passer d'une position gagnante à une position égale).
    # Pour la simplicité, elle est omise ici mais peut être ajoutée.

def generate_eval_graph(evals: list[int], path: Path):
    """Génère et sauvegarde un graphique de l'évaluation de la partie."""
    # (Pas de changement dans cette fonction, elle reste identique)
    plt.figure(figsize=(10, 4))
    plt.plot(evals, color='black', linewidth=1.5)
    plt.axhline(0, color='grey', linestyle='--')
    plt.fill_between(range(len(evals)), evals, 0, where=[e > 0 for e in evals], color='white', edgecolor='black', interpolate=True)
    plt.fill_between(range(len(evals)), evals, 0, where=[e <= 0 for e in evals], color='black', edgecolor='black', interpolate=True)
    plt.title("Évaluation de la partie par Stockfish")
    plt.xlabel("Numéro de coup")
    plt.ylabel("Évaluation (en centipawns)")
    plt.grid(axis='y', linestyle=':', color='gray')
    plt.ylim(min(min(evals), -100)-100, max(max(evals), 100)+100)
    plt.savefig(path, bbox_inches="tight", dpi=150)
    plt.close()


# --- COMMANDE DISCORD ---
@bot.command(name="analyser", help="Analyse une partie d'échecs au format PGN (style Chess.com).")
async def analyser(ctx, *, pgn: str):
    """Commande principale pour analyser une partie."""
    processing_message = await ctx.send("⏳ Préparation de l'analyse (style Chess.com)...")

    try:
        pgn_clean = re.sub(r"{\[.*?\]}", "", pgn)
        pgn_io = io.StringIO(pgn_clean)
        game = chess.pgn.read_game(pgn_io)

        if not game:
            await processing_message.edit(content="❌ Format PGN invalide.")
            return

        await processing_message.edit(content="⏳ Analyse de la partie en cours...")
        
        report_lines = []
        evaluations = [0]
        
        engine = chess.engine.SimpleEngine.popen_uci(str(ENGINE_BIN))
        board = game.board()

        # Ouvre le livre d'ouvertures
        with chess.polyglot.open_reader(str(BOOK_PATH)) as reader:
            for i, move in enumerate(game.mainline_moves()):
                is_book_move = bool(reader.find(board, move))
                turn = board.turn
                player_emoji = "⚪️" if turn == chess.WHITE else "⚫️"
                move_number_str = f"`{board.fullmove_number}.`" if turn == chess.WHITE else "`...`"
                san = board.san(move)
                
                quality = ""
                if is_book_move:
                    quality = "📚 Théorique"
                    board.push(move)
                    info_after = engine.analyse(board, chess.engine.Limit(depth=14)) # Analyse rapide pour le graph
                    eval_cp = info_after["score"].white().score(mate_score=10000)
                    evaluations.append(eval_cp or evaluations[-1])
                else:
                    # Si ce n'est pas un coup théorique, on analyse avec le moteur
                    # L'analyse doit inclure les "pv" (principales variations) pour trouver le meilleur coup
                    info_before = engine.analyse(board, chess.engine.Limit(depth=15), multipv=1)
                    info_before['board'] = board.copy() # Ajoute l'état de l'échiquier à l'info

                    # Vérifie si le coup est un sacrifice
                    is_sacrifice = board.is_capture(move) and \
                        chess.PIECE_VALUES[board.piece_at(move.to_addr).piece_type] < chess.PIECE_VALUES[board.piece_at(move.from_addr).piece_type]

                    board.push(move)
                    info_after = engine.analyse(board, chess.engine.Limit(depth=15))

                    quality = get_move_quality(move, info_before, info_after, is_sacrifice)
                    
                    eval_cp = info_after["score"].white().score(mate_score=10000)
                    evaluations.append(eval_cp or evaluations[-1])

                report_lines.append(f"{move_number_str} {player_emoji} {san:<8} — **{quality}**")

        engine.quit()
        
        graph_path = WORK_DIR / f"eval_{ctx.message.id}.png"
        generate_eval_graph(evaluations, graph_path)

        embed = discord.Embed(
            title="📊 Rapport d'analyse (Style Chess.com)",
            color=discord.Color.dark_green()
        )
        # Note : Le calcul de précision de Chess.com est complexe et propriétaire.
        # Nous omettons ce champ pour ne pas donner d'information potentiellement trompeuse.
        embed.set_image(url=f"attachment://{graph_path.name}")
        embed.set_footer(text=f"Analyse par Stockfish 17.1 | Demandé par {ctx.author.display_name}")

        report_text = "\n".join(report_lines)
        files_to_send = [discord.File(graph_path, filename=graph_path.name)]
        
        if len(report_text) <= 4096:
            embed.description = report_text
        else:
            embed.description = "Le rapport est trop long, voir le fichier `analyse.txt` ci-joint."
            files_to_send.append(discord.File(fp=io.StringIO(report_text), filename="analyse.txt"))

        await processing_message.edit(content=None, embed=embed, attachments=files_to_send)

    except Exception as e:
        print(f"Erreur lors de la commande !analyser : {e}")
        await processing_message.edit(content=f"❌ Une erreur inattendue est survenue : `{type(e).__name__}` - `{e}`")


# --- DÉMARRAGE DU BOT ---
@bot.event
async def on_ready():
    """Événement déclenché lorsque le bot est prêt."""
    print(f"✅ Bot connecté en tant que {bot.user}")

if __name__ == "__main__":
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    try:
        ensure_stockfish()
        ensure_opening_book()
        if DISCORD_TOKEN == "VOTRE_TOKEN_DISCORD_ICI":
            raise ValueError("Veuillez remplacer 'VOTRE_TOKEN_DISCORD_ICI' par votre vrai token Discord.")
        bot.run(DISCORD_TOKEN)
    except (RuntimeError, ValueError) as e:
        print(e)
