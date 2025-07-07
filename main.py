import os
import io
import re
import aiohttp
import discord
from discord.ext import commands
import chess
import chess.pgn
import matplotlib.pyplot as plt

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or "VOTRE_TOKEN_DISCORD"
COMMAND_PREFIX = "!"
OPENING_BOOK_URL = "https://github.com/lichess-org/chess-openings.git"

# --- MISE EN PLACE DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

# --- UTILITAIRES LICHESS EVAL ---
async def get_lichess_eval(fen: str) -> dict:
    url = f"https://lichess.org/api/cloud-eval?fen={fen}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                raise RuntimeError(f"Erreur Lichess Eval: HTTP {resp.status}")

def get_move_quality(cp_before: int, cp_after: int, is_best: bool, is_sacrifice: bool) -> str:
    loss = cp_before - cp_after
    if is_best:
        if is_sacrifice and loss < -50:
            return "✨ Brillant (!!)"
        return "⭐ Meilleur coup"
    if loss < 10:
        return "👍 Excellent"
    if loss < 40:
        return "✅ Bon"
    if loss < 100:
        return "🟡 Imprécision"
    if loss < 250:
        return "🟠 Erreur"
    return "🔴 Gaffe"

def generate_eval_graph(evals: list[int], path):
    plt.figure(figsize=(10,4))
    plt.plot(evals, color='black', linewidth=1.5)
    plt.axhline(0, color='grey', linestyle='--')
    plt.fill_between(range(len(evals)), evals, 0, where=[e>0 for e in evals], color='white', edgecolor='black')
    plt.fill_between(range(len(evals)), evals, 0, where=[e<=0 for e in evals], color='black', edgecolor='black')
    plt.title("Évaluation (Cloud Eval)")
    plt.xlabel("Coup")
    plt.ylabel("Centipawns")
    plt.grid(axis='y', linestyle=':')
    plt.ylim(min(evals)-100, max(evals)+100)
    plt.savefig(path, bbox_inches="tight", dpi=150)
    plt.close()

# --- COMMANDE !analyser ---
@bot.command(name="analyser")
async def analyser(ctx, *, pgn: str):
    msg = await ctx.send("⏳ Analyse en cours…")
    try:
        game = chess.pgn.read_game(io.StringIO(re.sub(r"{\[.*?\]}", "", pgn)))
        if not game:
            return await msg.edit(content="❌ PGN invalide")

        report = []
        evals = [0]
        board = game.board()

        for move in game.mainline_moves():
            fen_before = board.fen()
            lich = await get_lichess_eval(fen_before)
            pv0 = lich.get("pvs", [{}])[0]
            best_move = pv0.get("moves")
            cp_before = pv0.get("cp", 0)

            san = board.san(move)
            uci_move = move.uci()
            is_best = (uci_move == best_move)
            is_sac = board.is_capture(move) and (
                chess.PIECE_VALUES.get(board.piece_at(move.to_square).piece_type, 0) 
                < chess.PIECE_VALUES.get(board.piece_at(move.from_square).piece_type, 0)
            )

            board.push(move)
            lich2 = await get_lichess_eval(board.fen())
            cp_after = lich2.get("pvs", [{}])[0].get("cp", cp_before)

            quality = get_move_quality(cp_before, cp_after, is_best, is_sac)
            report.append(f"🔹 {san:<8} — **{quality}**")
            evals.append(cp_after)

        graph = WORK_DIR / f"eval_{ctx.message.id}.png"
        generate_eval_graph(evals, graph)

        embed = discord.Embed(title="📊 Analyse Chess.com–style", color=0x1F8B4C)
        embed.set_image(url=f"attachment://{graph.name}")
        embed.set_footer(text=f"Demandé par {ctx.author.display_name}")
        embed.description = "\n".join(report)[:4096]

        files = [discord.File(fp=open(graph, "rb"), filename=graph.name)]
        await msg.edit(content=None, embed=embed, attachments=files)

    except Exception as e:
        await msg.edit(content=f"❌ Erreur: `{e}`")

# --- COMMANDE DE PROBLÈMES ---
@bot.command(name="puzzle", help="Envoie un puzzle tactique Lichess aléatoire.")
async def puzzle(ctx):
    await ctx.send("🎲 Chargement d'un puzzle…")
    async with aiohttp.ClientSession() as s:
        async with s.get("https://lichess.org/api/puzzle/random") as resp:
            data = await resp.json()

    fen = data["puzzle"]["fen"]
    moves = data["puzzle"]["moves"].split()
    board = chess.Board(fen)
    san_moves = [board.san(chess.Move.from_uci(m)) for m in moves]
    solution = san_moves[0]
    board.push(chess.Move.from_uci(moves[0]))

    embed = discord.Embed(title="🧠 Puzzle tactique", color=0xDD9933)
    embed.add_field(name="Position (FEN)", value=f"```\n{fen}\n```", inline=False)
    embed.add_field(name="Premier coup (format UCI)", value=moves[0], inline=True)
    embed.add_field(name="Solution (SAN)", value=solution, inline=True)
    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    print(f"✅ Connecté comme {bot.user}")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)