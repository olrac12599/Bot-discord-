import discord
from discord.ext import commands
import chess
import chess.pgn
from stockfish import Stockfish
import io
import cairosvg
import os

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
# Pas besoin de chemin pour Stockfish, la bibl

# Initialisation de Stockfish
# La bibliothèque va télécharger une version compatible automatiquement.
stockfish = Stockfish(path="/usr/bin/stockfish")

def classify_move(eval_before, eval_after):
    delta = eval_after - eval_before
    if delta < -300:
        return "Gaffe ??", f"Une gaffe qui coûte cher ! L'évaluation a chuté de {-delta/100:.2f} pions."
    elif delta < -150:
        return "Erreur ?", f"Une erreur qui donne un avantage significatif à l'adversaire."
    elif delta < -70:
        return "Imprécision ?!", f"Un coup imprécis. Il y avait une meilleure option."
    else:
        return "Bon coup ✓", "Un coup solide."

def get_eval(board):
    stockfish.set_fen_position(board.fen())
    evaluation = stockfish.get_evaluation()
    pov_score = evaluation['value'] if board.turn == chess.WHITE else -evaluation['value']
    return pov_score, evaluation['value']

def analyse_game_moves(pgn_str: str):
    try:
        pgn = io.StringIO(pgn_str)
        game = chess.pgn.read_game(pgn)
        if game is None: return None, "PGN invalide ou vide."
    except Exception: return None, "Erreur de lecture du PGN."

    analysis_results = []
    board = game.board()

    _, current_eval = get_eval(board)
    analysis_results.append({
        "move": None, "comment_class": "Position de départ", "comment_text": "C'est le début de la partie.",
        "fen": board.fen(), "eval_after": current_eval
    })

    for move in game.mainline_moves():
        eval_before, _ = get_eval(board)
        board.push(move)
        _, eval_after = get_eval(board)

        comment_class, comment_text = classify_move(eval_before, eval_after)

        analysis_results.append({
            "move": move, "comment_class": comment_class, "comment_text": comment_text,
            "fen": board.fen(), "eval_after": eval_after
        })

    return analysis_results, None

# Le reste du code (la vue Discord) est identique à la version précédente
# ... (Copiez-collez la classe GameView et le reste du code du bot ici)
# Pour la clarté, je le remets ici :
class GameView(discord.ui.View):
    def __init__(self, analysis_results):
        super().__init__(timeout=300)
        self.analysis = analysis_results
        self.current_move = 0
        self.update_buttons()

    def create_embed_and_file(self):
        current_data = self.analysis[self.current_move]
        board = chess.Board(current_data["fen"])

        svg_image = chess.svg.board(board=board, lastmove=current_data.get("move"), size=400)
        png_bytes = cairosvg.svg2png(bytestring=svg_image.encode('utf-8'))
        png_file = discord.File(io.BytesIO(png_bytes), filename="board.png")

        move_number = (self.current_move + 1) // 2 if board.turn == chess.BLACK else self.current_move // 2 + 1
        turn_indicator = "..." if board.turn == chess.BLACK else "."
        move_str = f"Coup {move_number}{turn_indicator} {current_data['move']}" if current_data.get("move") else "Position de départ"

        embed = discord.Embed(title="Analyse de la partie", color=discord.Color.blue())
        embed.set_image(url="attachment://board.png")
        embed.add_field(name=f"Move: {move_str}", value="", inline=False)
        embed.add_field(name=f"👩‍🏫 Bilan: {current_data['comment_class']}", value=current_data['comment_text'], inline=False)

        eval_str = f"{current_data['eval_after'] / 100.0:.2f}"
        embed.set_footer(text=f"Évaluation: {eval_str}")

        return embed, png_file

    def update_buttons(self):
        self.children[0].disabled = self.current_move == 0
        self.children[1].disabled = self.current_move >= len(self.analysis) - 1

    @discord.ui.button(label="Précédent", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_move > 0:
            self.current_move -= 1
        self.update_buttons()
        embed, file = self.create_embed_and_file()
        await interaction.response.edit_message(embed=embed, attachments=[file], view=self)

    @discord.ui.button(label="Suivant", style=discord.ButtonStyle.primary, emoji="➡️")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_move < len(self.analysis) - 1:
            self.current_move += 1
        self.update_buttons()
        embed, file = self.create_embed_and_file()
        await interaction.response.edit_message(embed=embed, attachments=[file], view=self)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'Connecté en tant que {bot.user.name}')

@bot.command(name="pgn")
async def analyse_pgn_command(ctx: commands.Context, *, pgn_string: str):
    thinking_message = await ctx.send("🧠 Analyse en cours... Ceci peut prendre une minute.")
    if pgn_string.startswith("```") and pgn_string.endswith("```"):
        pgn_string = pgn_string[3:-3].strip()
    analysis, error = analyse_game_moves(pgn_string)
    if error:
        await thinking_message.edit(content=f"❌ Erreur: {error}")
        return
    view = GameView(analysis)
    embed, file = view.create_embed_and_file()
    await thinking_message.edit(content="Analyse terminée !", embed=embed, attachments=[file], view=view)

bot.run(DISCORD_TOKEN)
