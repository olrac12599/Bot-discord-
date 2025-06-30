# --- IMPORTS ---
import discord
from discord.ext import commands, tasks
from twitchio.ext import commands as twitch_commands
import requests
import os
import asyncio
import chess
import chess.pgn
import io
from enum import Enum, auto
import re  # ajouté pour le parsing HTML

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_TOKEN = os.getenv("TWITCH_TOKEN")
TTV_BOT_NICKNAME = os.getenv("TTV_BOT_NICKNAME")
TTV_BOT_TOKEN = os.getenv("TTV_BOT_TOKEN")

if not all([DISCORD_TOKEN, TWITCH_CLIENT_ID, TWITCH_TOKEN, TTV_BOT_NICKNAME, TTV_BOT_TOKEN]):
    raise ValueError("ERREUR CRITIQUE: Variables d'environnement manquantes.")

# --- INIT BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- STOCKAGE ---
tracked_games = {}  # pour analyse échecs (par salon)
streamer_id_cache = {}

# --- FONCTIONS UTILES ---

def get_live_game_moves(game_id):
    url = f"https://api.chess.com/pub/game/live/{game_id}"
    r = requests.get(url, timeout=5)
    r.raise_for_status()
    data = r.json()
    print(f"DEBUG data received: {data}")  # <-- Ajoute cette ligne
    if data.get("status") != "started":
        raise RuntimeError("La partie est terminée ou indisponible.")
    moves_str = data.get("moves", "")
    if not moves_str:
        raise RuntimeError("Impossible de trouver les coups dans la page.")
    moves = moves_str.split()
    return moves

def get_lichess_evaluation(fen):
    url = f"https://lichess.org/api/cloud-eval?fen={fen}"
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        data = r.json()
        if 'pvs' in data and data['pvs']:
            pvs0 = data['pvs'][0]
            if 'cp' in pvs0:
                return pvs0['cp']
            elif 'mate' in pvs0:
                return 10000 if pvs0['mate'] > 0 else -10000
        return None
    except Exception:
        return None

def classify_move(eval_before, eval_after, turn):
    if turn == chess.BLACK:
        eval_before = -eval_before
        eval_after = -eval_after
    loss = eval_before - eval_after
    if loss >= 300: return "🤯 Gaffe monumentale"
    if loss >= 150: return "⁉️ Gaffe"
    if loss >= 70: return "❓ Erreur"
    if loss >= 30: return "🤔 Imprécision"
    return None

# --- CLASSE BOT TWITCH ---

class WatcherMode(Enum):
    IDLE = auto()
    KEYWORD = auto()
    MIRROR = auto()

class WatcherBot(twitch_commands.Bot):
    def __init__(self, discord_bot_instance):
        super().__init__(token=TTV_BOT_TOKEN, prefix='!', initial_channels=[])
        self.discord_bot = discord_bot_instance
        self.mode = WatcherMode.IDLE
        self.current_channel_name = None
        self.target_discord_channel = None
        self.keyword_to_watch = None

    async def event_ready(self):
        print(f"Bot Twitch '{TTV_BOT_NICKNAME}' prêt.")

    async def stop_task(self):
        if self.current_channel_name:
            await self.part_channels([self.current_channel_name])
        self.mode = WatcherMode.IDLE
        self.current_channel_name = None
        self.target_discord_channel = None
        self.keyword_to_watch = None

    async def start_keyword_watch(self, twitch_channel, keyword, discord_channel):
        await self.stop_task()
        self.mode = WatcherMode.KEYWORD
        self.keyword_to_watch = keyword
        self.target_discord_channel = discord_channel
        self.current_channel_name = twitch_channel.lower()
        await self.join_channels([self.current_channel_name])

    async def start_mirror(self, twitch_channel, discord_channel):
        await self.stop_task()
        self.mode = WatcherMode.MIRROR
        self.target_discord_channel = discord_channel
        self.current_channel_name = twitch_channel.lower()
        await self.join_channels([self.current_channel_name])

    async def event_message(self, message):
        if message.echo or self.mode == WatcherMode.IDLE:
            return

        if self.mode == WatcherMode.KEYWORD:
            if self.keyword_to_watch.lower() in message.content.lower():
                embed = discord.Embed(
                    title="🚨 Mot-Clé Twitch détecté !",
                    description=message.content,
                    color=discord.Color.orange()
                )
                embed.set_footer(text=f"Chaîne : {message.channel.name} | Auteur : {message.author.name}")
                await self.target_discord_channel.send(embed=embed)

        elif self.mode == WatcherMode.MIRROR:
            msg = f"**{message.author.name}**: {message.content}"
            await self.target_discord_channel.send(msg[:2000])

# --- COMMANDES DISCORD ---

@bot.command(name="chess")
async def start_chess_analysis(ctx, game_id: str):
    if ctx.channel.id in tracked_games:
        await ctx.send("⏳ Une analyse est déjà en cours dans ce salon. Utilisez `!stopchess` pour l'arrêter.")
        return

    try:
        moves = get_live_game_moves(game_id)  # test validité
    except Exception as e:
        await ctx.send(f"❌ Erreur récupération partie : {e}")
        return

    tracked_games[ctx.channel.id] = {"game_id": game_id, "last_ply": 0}
    game_analysis_loop.start(ctx)
    await ctx.send(f"✅ Analyse démarrée pour la partie live `{game_id}`. Mise à jour toutes les 15 secondes.")

@bot.command(name="stopchess")
async def stop_chess_analysis(ctx):
    if ctx.channel.id in tracked_games:
        game_analysis_loop.cancel()
        del tracked_games[ctx.channel.id]
        await ctx.send("⏹️ Analyse arrêtée.")
    else:
        await ctx.send("Aucune analyse active dans ce salon.")

@bot.command(name="motcle")
@commands.has_permissions(administrator=True)
async def watch_keyword(ctx, streamer: str, *, keyword: str):
    if hasattr(bot, 'twitch_bot'):
        await bot.twitch_bot.start_keyword_watch(streamer, keyword, ctx.channel)
        await ctx.send(f"🔍 Mot-clé **{keyword}** sur **{streamer}** surveillé.")

@bot.command(name="tchat")
@commands.has_permissions(administrator=True)
async def mirror_chat(ctx, streamer: str):
    if hasattr(bot, 'twitch_bot'):
        await bot.twitch_bot.start_mirror(streamer, ctx.channel)
        await ctx.send(f"🪞 Miroir du chat de **{streamer}** activé.")

@bot.command(name="stop")
@commands.has_permissions(administrator=True)
async def stop_twitch_watch(ctx):
    if hasattr(bot, 'twitch_bot'):
        await bot.twitch_bot.stop_task()
        await ctx.send("🛑 Surveillance Twitch arrêtée.")

@bot.command(name="ping")
async def ping(ctx):
    await ctx.send("Pong!")

# --- TÂCHE D'ANALYSE ÉCHECS ---

@tasks.loop(seconds=15)
async def game_analysis_loop(ctx):
    cid = ctx.channel.id
    if cid not in tracked_games:
        game_analysis_loop.cancel()
        return
    game_id = tracked_games[cid]["game_id"]

    try:
        moves = get_live_game_moves(game_id)
        board = chess.Board()
        last_ply = tracked_games[cid]["last_ply"]
        current_ply = len(moves)

        # Analyser uniquement les coups nouveaux
        for i in range(last_ply, current_ply):
            move_san = moves[i]
            try:
                move = board.parse_san(move_san)
            except Exception:
                break
            fen_before = board.fen()
            turn = board.turn
            board.push(move)
            eval_before = get_lichess_evaluation(fen_before)
            eval_after = get_lichess_evaluation(board.fen())

            if eval_before is not None and eval_after is not None:
                quality = classify_move(eval_before, eval_after, turn)
                if quality:
                    ply_num = i+1
                    await ctx.send(f"**{(ply_num+1)//2}. {move_san}** – {quality} (Eval: {eval_before/100:.2f} ➜ {eval_after/100:.2f})")

        tracked_games[cid]["last_ply"] = current_ply

    except RuntimeError as e:
        await ctx.send(f"⚠️ {e} Analyse arrêtée.")
        tracked_games.pop(cid, None)
        game_analysis_loop.cancel()
    except Exception as e:
        await ctx.send(f"⚠️ Erreur durant l'analyse : {e}")
        tracked_games.pop(cid, None)
        game_analysis_loop.cancel()

# --- ÉVÉNEMENTS ---

@bot.event
async def on_ready():
    print(f"Bot Discord connecté en tant que {bot.user} !")

# --- LANCEMENT ---

async def main():
    twitch_bot_instance = WatcherBot(bot)
    bot.twitch_bot = twitch_bot_instance
    await asyncio.gather(
        bot.start(DISCORD_TOKEN),
        twitch_bot_instance.start()
    )

if __name__ == "__main__":
    asyncio.run(main())