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

# --- CONFIG ---
# Chargez votre token depuis une variable d'environnement pour plus de sécurité
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or "VOTRE_TOKEN_DISCORD_ICI"
COMMAND_PREFIX = "!"
# Utilise un dossier plus persistant que /tmp
WORK_DIR = Path.home() / ".stockfish_bot"
ENGINE_BIN = WORK_DIR / "stockfish_bin"

# --- DISCORD SETUP ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

# --- STOCKFISH INSTALL (AMÉLIORÉ) ---
def get_stockfish_url():
    """Détermine la bonne URL de Stockfish en fonction de l'OS."""
    if sys.platform.startswith("linux"):
        # AVX2 est commun sur les CPU modernes, mais on pourrait ajouter une option pour les plus anciens
        return "https://github.com/official-stockfish/Stockfish/releases/latest/download/stockfish-ubuntu-x86-64-avx2.tar"
    elif sys.platform == "win32":
        return "https://github.com/official-stockfish/Stockfish/releases/latest/download/stockfish-windows-x86-64-avx2.zip"
    elif sys.platform == "darwin": # macOS
        return "https://github.com/official-stockfish/Stockfish/releases/latest/download/stockfish-macos-x86-64-modern.tar"
    else:
        raise RuntimeError(f"Système d'exploitation non supporté : {sys.platform}")

def download_and_extract_stockfish():
    """Télécharge et extrait Stockfish."""
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
    
    # Cherche le binaire exécutable de stockfish
    for f in WORK_DIR.rglob("*stockfish*"):
        if f.is_file() and (os.access(f, os.X_OK) or f.name.endswith(".exe")):
            f.chmod(f.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
            shutil.copyfile(f, ENGINE_BIN)
            print(f"✅ Stockfish installé : {ENGINE_BIN}")
            archive_path.unlink() # Nettoyage de l'archive
            return True
            
    raise RuntimeError("❌ Binaire de Stockfish introuvable après extraction.")

def ensure_stockfish():
    """S'assure que Stockfish est prêt à l'emploi."""
    if not ENGINE_BIN.exists():
        download_and_extract_stockfish()

# --- LOGIQUE D'ANALYSE (AMÉLIORÉE) ---
def get_move_quality(cp_loss: int):
    """Retourne une classification et une couleur basées sur la perte de centipawns."""
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

def calculate_accuracy(centipawn_losses: list) -> float:
    """Calcule un score de précision en pourcentage."""
    if not centipawn_losses:
        return 100.0
    # Formule simple pour mapper la perte de cp à un score de précision
    accuracy_scores = [100 * (1 - min(1, cp_loss / 300)) for cp_loss in centipawn_losses]
    return sum(accuracy_scores) / len(accuracy_scores)

# --- GÉNÉRATION VISUELLE ---
def generate_eval_graph(evals: list, path: Path):
    """Génère un graphique de l'évaluation de la partie."""
    plt.figure(figsize=(10, 4))
    plt.plot(evals, color='black', linewidth=2)
    plt.title("Évaluation de la Partie")
    plt.xlabel("Numéro de Coup")
    plt.ylabel("Avantage (en centipawns)")
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.axhline(0, color='grey', linewidth=1)
    # Limite l'axe Y pour une meilleure lisibilité, sauf si les valeurs sont extrêmes
    max_val = max(abs(e) for e in evals) if evals else 1000
    display_limit = min(max_val + 100, 1000)
    plt.ylim(-display_limit, display_limit)
    plt.savefig(path, format='png', bbox_inches='tight')
    plt.close()

# --- COMMANDE !analyser (REFAITE) ---
@bot.command(name="analyser", help="Analyse une partie d'échecs depuis un PGN ou une URL (lichess.org, chess.com).")
async def analyser(ctx, *, game_input: str):
    pgn_str = game_input.strip()
    
    # Détection d'URL
    if pgn_str.startswith("http"):
        await ctx.send(f"⏳ Récupération de la partie depuis l'URL...")
        try:
            if "lichess.org" in pgn_str:
                game_id = re.search(r"lichess\.org/(\w{8})", pgn_str).group(1)
                url = f"https://lichess.org/game/export/{game_id}"
                headers = {"Accept": "application/x-chess-pgn"}
                response = requests.get(url, headers=headers)
            elif "chess.com" in pgn_str:
                # L'API de chess.com est différente, on récupère le PGN via leur API publique
                # Exemple : https://www.chess.com/game/live/114995775955 -> T7 (archive)/2024-05 (mois)
                # C'est complexe, on va se contenter d'une approche simple
                response = requests.get(pgn_str + ".pgn") # Tente d'ajouter .pgn
                if not response.ok: # Si ça ne marche pas, il faut une méthode plus complexe
                     await ctx.send("❌ L'API de Chess.com est complexe. Essayez de fournir le PGN directement.")
                     return
            else:
                 await ctx.send("❌ URL non supportée. Utilisez un lien Lichess ou Chess.com.")
                 return
                 
            response.raise_for_status()
            pgn_str = response.text
        except Exception as e:
            await ctx.send(f"❌ Erreur lors de la récupération de la partie : {e}")
            return
            
    try:
        pgn_io = io.StringIO(pgn_str)
        game = chess.pgn.read_game(pgn_io)
        if not game:
            await ctx.send("❌ Format PGN invalide ou partie non trouvée.")
            return

        await ctx.send(f"⏳ Analyse de la partie en cours... Cela peut prendre un moment.")
        
        analysis_report = []
        evals_graph = []
        white_cp_losses, black_cp_losses = [], []
        
        board = game.board()
        # Utilisation du moteur en mode asynchrone
        async with chess.engine.SimpleEngine.popen_uci(str(ENGINE_BIN)) as engine:
            info_before = await engine.analyse(board, chess.engine.Limit(time=0.5))
            
            for i, move in enumerate(game.mainline_moves()):
                info_after = await engine.analyse(board, chess.engine.Limit(time=0.5), root_moves=[move])
                
                score_before = info_before['score'].pov(board.turn)
                score_after = info_after[0]['score'].pov(board.turn)

                # Calcul de la perte en centipawns
                cp_loss = 0
                if score_before.is_mate() or score_after.is_mate():
                    cp_loss = 350 # Perte arbitraire haute pour un mat raté/subi
                else:
                    cp_loss = score_before.score() - score_after.score()

                quality, emoji = get_move_quality(cp_loss)
                best_move = board.san(info_before["pv"][0]) if "pv" in info_before else "N/A"
                
                player_icon = "⚪️" if board.turn == chess.WHITE else "⚫️"
                move_san = board.san(move)
                
                analysis_line = f"`{i+1}. {move_san.ljust(7)}` — {emoji} {quality}"
                if quality in ["Imprécision", "Erreur", "Gaffe"] and best_move != move_san:
                    analysis_line += f" (Meilleur: **{best_move}**)"
                analysis_report.append(analysis_line)

                if board.turn == chess.WHITE:
                    white_cp_losses.append(cp_loss)
                else:
                    black_cp_losses.append(cp_loss)
                    
                board.push(move)
                info_before = info_after[0]
                evals_graph.append(info_before["score"].white().score(mate_score=10000) or 0)

        # Calculs finaux
        white_accuracy = calculate_accuracy(white_cp_losses)
        black_accuracy = calculate_accuracy(black_cp_losses)

        # Génération du graphique
        graph_path = WORK_DIR / f"eval_graph_{ctx.message.id}.png"
        generate_eval_graph(evals_graph, graph_path)
        
        # Création de l'embed
        embed = discord.Embed(
            title=f"Analyse de la Partie : {game.headers.get('White', '?')} vs {game.headers.get('Black', '?')}",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="🎯 Précision",
            value=f"⚪️ **Blancs**: {white_accuracy:.1f}%\n⚫️ **Noirs**: {black_accuracy:.1f}%",
            inline=False
        )
        embed.set_footer(text="Analyse par Stockfish via Discord Bot")
        
        # Ajout du graphique à l'embed
        file = discord.File(graph_path, filename="evaluation.png")
        embed.set_image(url="attachment://evaluation.png")
        
        # Envoi de l'analyse détaillée en fichier texte
        report_text = "\n".join(analysis_report)
        buffer = io.StringIO(report_text)
        report_file = discord.File(fp=buffer, filename="analyse_detaillee.txt")
        
        await ctx.send(embed=embed, files=[file, report_file])

    except Exception as e:
        await ctx.send(f"❌ Une erreur majeure est survenue pendant l'analyse : {e}")
        import traceback
        traceback.print_exc()

# --- ÉVÉNEMENTS DU BOT ---
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")
    print("🤖 Le bot est prêt à analyser !")

# --- POINT D'ENTRÉE ---
if __name__ == "__main__":
    try:
        ensure_stockfish()
        bot.run(DISCORD_TOKEN)
    except RuntimeError as e:
        print(e)
    except discord.errors.LoginFailure:
        print("❌ Échec de la connexion : Le token Discord est invalide.")

