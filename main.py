import os
import io
import re
import aiohttp
import discord
from discord.ext import commands
import chess
import chess.pgn
import matplotlib.pyplot as plt
from pathlib import Path

# --- CONFIGURATION ---
# Assurez-vous d'avoir défini votre token dans vos variables d'environnement
# ou remplacez la valeur ci-dessous.
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or "VOTRE_TOKEN_DISCORD"
COMMAND_PREFIX = "!"
# Ce lien est un dépôt Git, pas une API. Il n'est pas utilisé dans le script.
# OPENING_BOOK_URL = "https://github.com/lichess-org/chess-openings.git"
WORK_DIR = Path(".") # Définit le répertoire de travail pour enregistrer les images

# --- VALEURS DES PIÈCES (pour la détection de sacrifice) ---
PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000
}

# --- MISE EN PLACE DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

# --- UTILITAIRES LICHESS EVAL ---
async def get_lichess_eval(fen: str) -> dict:
    # Ce lien est le bon lien pour l'API Cloud Eval de Lichess
    url = f"https://lichess.org/api/cloud-eval?fen={fen}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                # Gère le cas où Lichess retourne une erreur dans le JSON
                if "error" in data:
                    return {"pvs": [{"moves": "", "cp": 0}]}
                return data
            else:
                # Si l'API est indisponible, on retourne une éval neutre pour ne pas crasher
                return {"pvs": [{"moves": "", "cp": 0}]}

def get_move_quality(cp_before: int, cp_after: int, turn: bool, is_best: bool) -> str:
    # L'évaluation est toujours du point de vue des blancs.
    # Il faut inverser la perte si c'est au tour des noirs de jouer.
    loss = (cp_before - cp_after) if turn == chess.WHITE else (cp_after - cp_before)
    
    if is_best:
        return "⭐ Meilleur coup"
    if loss < 10:
        return "👍 Excellent"
    if loss < 40:
        return "✅ Bon"
    if loss < 100:
        return "🟡 Imprécision"
    if loss < 250:
        return "🟠 Erreur"
    return "🔴 Gaffe"

def generate_eval_graph(evals: list[int], path):
    plt.figure(figsize=(10, 4))
    
    # Limiter les évaluations extrêmes pour un graphique plus lisible
    capped_evals = [min(max(e, -1000), 1000) for e in evals]
    y_limit = max(abs(e) for e in capped_evals) * 1.1 if capped_evals else 1000

    plt.plot(range(len(capped_evals)), capped_evals, color='black', linewidth=1.5)
    plt.axhline(0, color='grey', linestyle='--')
    plt.fill_between(range(len(capped_evals)), capped_evals, 0, where=[e > 0 for e in capped_evals], interpolate=True, color='#f0f0f0')
    plt.fill_between(range(len(capped_evals)), capped_evals, 0, where=[e <= 0 for e in capped_evals], interpolate=True, color='#303030')
    
    plt.title("Évaluation de la partie (Lichess Cloud Eval)")
    plt.xlabel("Numéro de coup")
    plt.ylabel("Avantage (en centipawns)")
    plt.grid(axis='y', linestyle=':', color='gray')
    plt.ylim(-y_limit, y_limit)
    plt.savefig(path, bbox_inches="tight", dpi=150, transparent=True)
    plt.close()

# --- COMMANDE !analyser ---
@bot.command(name="analyser")
async def analyser(ctx, *, pgn: str):
    msg = await ctx.send("⏳ Analyse en cours… (cela peut prendre un certain temps)")
    try:
        # Nettoyer le PGN des commentaires pour éviter les erreurs de parsing
        pgn_cleaned = re.sub(r"{\[.*?\]}", "", pgn)
        game = chess.pgn.read_game(io.StringIO(pgn_cleaned))
        if not game:
            return await msg.edit(content="❌ PGN invalide ou format non reconnu.")

        report = []
        evals = [0]
        board = game.board()

        for i, move in enumerate(game.mainline_moves()):
            fen_before = board.fen()
            
            # On récupère l'évaluation *avant* le coup
            lich_eval_before = await get_lichess_eval(fen_before)
            
            # S'il n'y a pas de variation principale, on prend une éval neutre
            if not lich_eval_before.get("pvs"):
                lich_eval_before['pvs'] = [{'moves': '', 'cp': evals[-1]}]
            
            pv0 = lich_eval_before["pvs"][0]
            best_move_uci = pv0.get("moves", "").split(" ")[0]
            cp_before = pv0.get("cp", evals[-1])
            
            # On vérifie si le coup joué est le meilleur coup trouvé
            is_best = (move.uci() == best_move_uci)
            
            san_move = board.san(move)
            turn = board.turn
            board.push(move)

            # On récupère l'évaluation *après* le coup
            lich_eval_after = await get_lichess_eval(board.fen())
            if not lich_eval_after.get("pvs"):
                 lich_eval_after['pvs'] = [{'moves': '', 'cp': cp_before}]
                 
            cp_after = lich_eval_after["pvs"][0].get("cp", cp_before)

            # On ajoute le numéro de coup au rapport
            move_number = i // 2 + 1
            ply_char = "..." if turn == chess.BLACK else "."
            
            quality = get_move_quality(cp_before, cp_after, turn, is_best)
            report.append(f"`{move_number}{ply_char} {san_move:<8}` — **{quality}**")
            evals.append(cp_after if turn == chess.WHITE else -cp_after)
        
        # Le nom du fichier est unique pour éviter les conflits
        graph_path = WORK_DIR / f"eval_{ctx.message.id}.png"
        generate_eval_graph(evals, graph_path)

        embed = discord.Embed(title="📊 Analyse de la partie", color=0xCCCCCC)
        embed.set_footer(text=f"Analyse via Lichess Cloud Eval pour {ctx.author.display_name}")
        
        # On divise le rapport en plusieurs champs si trop long
        report_str = "\n".join(report)
        chunks = [report_str[i:i + 1024] for i in range(0, len(report_str), 1024)]
        for i, chunk in enumerate(chunks):
             embed.add_field(name=f"Déroulement ({i+1}/{len(chunks)})", value=chunk, inline=False)
        
        file = discord.File(fp=graph_path, filename=graph_path.name)
        embed.set_image(url=f"attachment://{graph_path.name}")
        await msg.edit(content=None, embed=embed, attachments=[file])

    except Exception as e:
        await msg.edit(content=f"❌ Une erreur est survenue: `{e}`")
    finally:
        # On nettoie le fichier image après envoi
        if 'graph_path' in locals() and graph_path.exists():
            os.remove(graph_path)

# --- COMMANDE DE PUZZLE ---
@bot.command(name="puzzle", help="Envoie le puzzle du jour de Lichess.")
async def puzzle(ctx):
    msg = await ctx.send("🎲 Chargement du puzzle du jour…")
    try:
        # Le VRAI lien pour un puzzle est /api/puzzle/daily (le puzzle du jour)
        # L'endpoint /api/puzzle/random N'EXISTE PAS.
        async with aiohttp.ClientSession() as s:
            async with s.get("https://lichess.org/api/puzzle/daily") as resp:
                if resp.status != 200:
                    return await msg.edit(content="❌ Impossible de récupérer le puzzle du jour de Lichess.")
                data = await resp.json()

        puzzle_id = data["id"]
        fen = data["game"]["fen"]
        # La solution est une liste de coups au format UCI
        solution_uci = data["puzzle"]["solution"]
        board = chess.Board(fen)
        
        # On trouve le trait et le premier coup de la solution
        turn = "blancs" if board.turn == chess.WHITE else "noirs"
        first_move_uci = solution_uci[0]
        first_move_san = board.san(chess.Move.from_uci(first_move_uci))

        embed = discord.Embed(
            title="🧠 Puzzle du Jour Lichess",
            description=f"**Trait aux {turn}**. Quelle est la meilleure suite ?",
            color=0xDD9933,
            url=f"https://lichess.org/puzzles/daily/{puzzle_id}"
        )
        embed.add_field(name="Position (FEN)", value=f"```{fen}```", inline=False)
        embed.add_field(name="Solution (1er coup)", value=f"||{first_move_san}||", inline=True)
        embed.add_field(name="Lien vers le puzzle", value=f"[Voir sur Lichess](https://lichess.org/training/{puzzle_id})", inline=True)
        
        # Générer une image de l'échiquier (nécessite 'cairosvg' et 'chess' avec support svg)
        board_svg = chess.svg.board(board=board, size=350)
        svg_path = WORK_DIR / f"puzzle_{puzzle_id}.svg"
        png_path = WORK_DIR / f"puzzle_{puzzle_id}.png"
        
        with open(svg_path, "w") as f:
            f.write(board_svg)
        
        # Conversion SVG vers PNG (nécessite une bibliothèque comme 'cairosvg')
        try:
            import cairosvg
            cairosvg.svg2png(url=str(svg_path), write_to=str(png_path))
            file = discord.File(png_path, filename="board.png")
            embed.set_image(url="attachment://board.png")
            await msg.edit(content=None, embed=embed, attachments=[file])
        except ImportError:
            await msg.edit(content=None, embed=embed) # Envoie sans image si la lib manque
        finally:
            if svg_path.exists(): os.remove(svg_path)
            if png_path.exists(): os.remove(png_path)

    except Exception as e:
        await msg.edit(content=f"❌ Une erreur est survenue: `{e}`")


@bot.event
async def on_ready():
    print(f"✅ Connecté comme {bot.user}")

if __name__ == "__main__":
    if DISCORD_TOKEN == "VOTRE_TOKEN_DISCORD":
        print("ERREUR: Veuillez remplacer 'VOTRE_TOKEN_DISCORD' par votre vrai token de bot.")
    else:
        bot.run(DISCORD_TOKEN)
