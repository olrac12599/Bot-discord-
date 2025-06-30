# --- SECTION 1 : IMPORTS ---
import discord
from discord.ext import commands, tasks
from twitchio.ext import commands as twitch_commands
import requests
import os
import asyncio
from enum import Enum, auto
import chess
import chess.pgn
import io

# --- SECTION 2 : CONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_TOKEN = os.getenv("TWITCH_TOKEN")
TTV_BOT_NICKNAME = os.getenv("TTV_BOT_NICKNAME")
TTV_BOT_TOKEN = os.getenv("TTV_BOT_TOKEN")

if not all([DISCORD_TOKEN, TWITCH_CLIENT_ID, TWITCH_TOKEN, TTV_BOT_NICKNAME, TTV_BOT_TOKEN]):
    raise ValueError("ERREUR CRITIQUE: Variables d'environnement manquantes.")

# --- SECTION 3 : INITIALISATION DES BOTS ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- SECTION 4 : STOCKAGE ET CACHES ---
blazx_subscriptions = []
streamer_id_cache = {}
tracked_games = {}

# --- SECTION 5 : FONCTIONS UTILITAIRES ---

def get_chess_com_game_pgn(game_url: str) -> str:
    """
    Récupère le PGN d'une partie en direct Chess.com.
    Renvoie une erreur si la partie est terminée (404) ou si l'URL est invalide.
    """
    try:
        if "/game/live/" not in game_url:
            raise ValueError("❌ Cette commande ne fonctionne que pour les parties *en direct* de Chess.com.")

        game_id = game_url.strip("/").split("/")[-1]
        api_url = f"https://www.chess.com/game/live/pgn/{game_id}"
        response = requests.get(api_url, timeout=5)

        if response.status_code == 404:
            raise RuntimeError("❌ La partie est déjà terminée — impossible de récupérer le PGN en direct.")

        response.raise_for_status()
        return response.text

    except Exception as e:
        raise RuntimeError(f"⚠️ Erreur récupération PGN : {e}")

def get_lichess_evaluation(fen: str):
    try:
        api_url = f"https://lichess.org/api/cloud-eval?fen={fen}"
        response = requests.get(api_url, timeout=5)
        response.raise_for_status()
        data = response.json()
        if 'pvs' in data and data['pvs']:
            if 'cp' in data['pvs'][0]:
                return data['pvs'][0]['cp']
            elif 'mate' in data['pvs'][0]:
                return 10000 * (1 if data['pvs'][0]['mate'] > 0 else -1)
        return None
    except:
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

async def get_streamer_id(streamer_name: str) -> str | None:
    if streamer_name in streamer_id_cache: return streamer_id_cache[streamer_name]
    headers = {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {TWITCH_TOKEN}"}
    params = {"login": streamer_name.lower()}
    try:
        r = requests.get("https://api.twitch.tv/helix/users", headers=headers, params=params, timeout=5)
        r.raise_for_status()
        data = r.json()
        if data.get("data"):
            user_id = data["data"][0]["id"]
            streamer_id_cache[streamer_name] = user_id
            return user_id
    except:
        return None

async def get_stream_status(streamer_id: str) -> dict | None:
    headers = {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {TWITCH_TOKEN}"}
    params = {"user_id": streamer_id}
    try:
        r = requests.get("https://api.twitch.tv/helix/streams", headers=headers, params=params, timeout=5)
        r.raise_for_status()
        data = r.json()
        if data.get("data"): return data["data"][0]
    except:
        return None

# --- SECTION 6 : BOTS TWITCH ---

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
                embed = discord.Embed(title="🚨 Mot-Clé Twitch détecté !", description=message.content, color=discord.Color.orange())
                embed.set_footer(text=f"Chaîne : {message.channel.name} | Auteur : {message.author.name}")
                await self.target_discord_channel.send(embed=embed)

        elif self.mode == WatcherMode.MIRROR:
            msg = f"**{message.author.name}**: {message.content}"
            await self.target_discord_channel.send(msg[:2000])

# --- SECTION 7 : COMMANDES DISCORD ---

@bot.command(name="chess")
async def start_chess_analysis(ctx, url: str):
    if "chess.com/game/live/" not in url:
        await ctx.send("❌ URL de partie en direct Chess.com invalide.")
        return

    if ctx.channel.id in tracked_games:
        await ctx.send("⏳ Analyse déjà en cours. Utilise `!stopchess` pour l'arrêter.")
        return

    try:
        _ = get_chess_com_game_pgn(url)  # Teste la validité du PGN au lancement
    except Exception as e:
        await ctx.send(str(e))
        return

    await ctx.send("🧠 Analyse de la partie en cours... (toutes les 15 secondes)")
    task = game_analysis_loop.start(ctx, url)
    tracked_games[ctx.channel.id] = {'url': url, 'last_ply': 0, 'task': task}

@bot.command(name="stopchess")
async def stop_chess_analysis(ctx):
    if ctx.channel.id in tracked_games:
        tracked_games[ctx.channel.id]['task'].cancel()
        del tracked_games[ctx.channel.id]
        await ctx.send("⏹️ Analyse arrêtée.")
    else:
        await ctx.send("Aucune analyse active ici.")

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

# --- SECTION 8 : TÂCHES FOND : ANALYSE ÉCHECS ---

@tasks.loop(seconds=15)
async def game_analysis_loop(ctx, game_url):
    cid = ctx.channel.id
    if cid not in tracked_games or tracked_games[cid]['url'] != game_url:
        game_analysis_loop.stop()
        return

    try:
        pgn_data = get_chess_com_game_pgn(game_url)
        pgn_stream = io.StringIO(pgn_data)
        game = chess.pgn.read_game(pgn_stream)
        if not game: return

        board = game.board()
        current_ply = 0
        last_ply = tracked_games[cid]['last_ply']

        for move in game.mainline_moves():
            current_ply += 1
            if current_ply <= last_ply:
                board.push(move)
                continue

            fen_before = board.fen()
            turn = board.turn
            eval_before = get_lichess_evaluation(fen_before)

            san_move = board.san(move)
            board.push(move)

            eval_after = get_lichess_evaluation(board.fen())
            tracked_games[cid]['last_ply'] = current_ply

            if eval_before is not None and eval_after is not None:
                quality = classify_move(eval_before, eval_after, turn)
                if quality:
                    player = game.headers["White"] if turn == chess.WHITE else game.headers["Black"]
                    await ctx.send(
                        f"**{int((current_ply+1)/2)}. {san_move}** par **{player}** – {quality} "
                        f"(Éval : {eval_before/100:.2f} ➜ {eval_after/100:.2f})"
                    )

        if game.headers.get("Result") != "*":
            await ctx.send(f"🎯 Partie terminée : {game.headers['Result']}")
            tracked_games[cid]['task'].cancel()
            del tracked_games[cid]

    except Exception as e:
        await ctx.send(f"⚠️ Erreur analyse : {e}")
        if cid in tracked_games:
            tracked_games[cid]['task'].cancel()
            del tracked_games[cid]

# --- SECTION 9 : LANCEMENT ---

@bot.event
async def on_ready():
    print(f"Bot Discord connecté en tant que {bot.user.name}")

async def main():
    twitch_bot_instance = WatcherBot(bot)
    bot.twitch_bot = twitch_bot_instance
    await asyncio.gather(
        bot.start(DISCORD_TOKEN),
        twitch_bot_instance.start()
    )

if __name__ == "__main__":
    asyncio.run(main())