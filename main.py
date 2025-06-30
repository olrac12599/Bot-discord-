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
import chess.com  # Bibliothèque pour l'API Chess.com

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
# NOUVEAU : Dictionnaire pour stocker les parties suivies par salon
tracked_games = {}

# --- SECTION 5 : FONCTIONS UTILITAIRES (API & LOGIQUE) ---

# Fonctions pour l'API Twitch (inchangées)
async def get_streamer_id(streamer_name: str) -> str | None:
    # ... (code inchangé)
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
    except requests.exceptions.RequestException as e:
        print(f"Erreur API (get_streamer_id): {e}")
    return None

async def get_stream_status(streamer_id: str) -> dict | None:
    # ... (code inchangé)
    headers = {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {TWITCH_TOKEN}"}
    params = {"user_id": streamer_id}
    try:
        r = requests.get("https://api.twitch.tv/helix/streams", headers=headers, params=params, timeout=5)
        r.raise_for_status()
        data = r.json()
        if data.get("data"): return data["data"][0]
    except requests.exceptions.RequestException as e:
        print(f"Erreur API (get_stream_status): {e}")
    return None

# NOUVEAU : Fonctions d'analyse d'échecs
def get_lichess_evaluation(fen: str):
    """Interroge Lichess pour obtenir l'évaluation d'une position FEN."""
    try:
        api_url = f"https://lichess.org/api/cloud-eval?fen={fen}"
        response = requests.get(api_url, timeout=5)
        response.raise_for_status()
        data = response.json()
        if 'pvs' in data and len(data['pvs']) > 0:
            if 'cp' in data['pvs'][0]:
                return data['pvs'][0]['cp']
            elif 'mate' in data['pvs'][0]:
                return 10000 * (1 if data['pvs'][0]['mate'] > 0 else -1)
        return None
    except Exception:
        return None

def classify_move(eval_before, eval_after, turn):
    """Détermine si un coup est une gaffe, une erreur, etc."""
    if turn == chess.BLACK:
        eval_before = -eval_before
        eval_after = -eval_after
    
    loss = eval_before - eval_after
    
    if loss >= 300: return "🤯 Gaffe monumentale"
    if loss >= 150: return "⁉️ Gaffe"
    if loss >= 70: return "❓ Erreur"
    if loss >= 30: return "🤔 Imprécision"
    return None

# --- SECTION 6 : CLASSES DES BOTS EXTERNES (inchangée) ---
class WatcherMode(Enum):
    IDLE = auto(); KEYWORD = auto(); MIRROR = auto()

class WatcherBot(twitch_commands.Bot):
    # ... (code inchangé, aucune modification ici)
    def __init__(self, discord_bot_instance):
        super().__init__(token=TTV_BOT_TOKEN, prefix='!', initial_channels=[])
        self.discord_bot = discord_bot_instance
        self.mode = WatcherMode.IDLE
        self.current_channel_name = None
        self.target_discord_channel = None
        self.keyword_to_watch = None

    async def event_ready(self):
        print("-------------------------------------------------")
        print(f"Bot Twitch '{TTV_BOT_NICKNAME}' connecté et prêt.")
        print("-------------------------------------------------")

    async def stop_task(self):
        if self.current_channel_name:
            await self.part_channels([self.current_channel_name])
        self.mode = WatcherMode.IDLE
        self.current_channel_name = None
        self.target_discord_channel = None
        self.keyword_to_watch = None
        print("[TWITCH] Tâche arrêtée. En attente de nouvelles instructions.")

    async def start_keyword_watch(self, twitch_channel: str, keyword: str, discord_channel: discord.TextChannel):
        await self.stop_task()
        self.mode = WatcherMode.KEYWORD
        self.keyword_to_watch = keyword
        self.target_discord_channel = discord_channel
        self.current_channel_name = twitch_channel.lower()
        await self.join_channels([self.current_channel_name])
        print(f"[TWITCH] Mode MOT-CLÉ activé pour #{self.current_channel_name}, mot='{keyword}'.")

    async def start_mirror(self, twitch_channel: str, discord_channel: discord.TextChannel):
        await self.stop_task()
        self.mode = WatcherMode.MIRROR
        self.target_discord_channel = discord_channel
        self.current_channel_name = twitch_channel.lower()
        await self.join_channels([self.current_channel_name])
        print(f"[TWITCH] Mode MIROIR activé pour #{self.current_channel_name}.")

    async def event_message(self, message):
        if message.echo or self.mode == WatcherMode.IDLE: return

        if self.mode == WatcherMode.KEYWORD:
            if self.keyword_to_watch.lower() in message.content.lower():
                embed = discord.Embed(title="🚨 Mot-Clé Détecté sur Twitch !", color=discord.Color.orange())
                embed.add_field(name="Chaîne", value=f"#{message.channel.name}", inline=True)
                embed.add_field(name="Auteur", value=message.author.name, inline=True)
                embed.add_field(name="Message", value=f"`{message.content}`", inline=False)
                try:
                    await self.target_discord_channel.send(embed=embed)
                except Exception as e:
                    print(f"Erreur envoi notif mot-clé: {e}")
        elif self.mode == WatcherMode.MIRROR:
            formatted_message = f"**{message.author.name}**: {message.content}"
            await self.target_discord_channel.send(formatted_message[:2000])


# --- SECTION 7 : COMMANDES DISCORD ---

# --- SECTION 7A : NOUVELLES COMMANDES D'ANALYSE D'ÉCHECS ---

@bot.command(name="chess")
async def start_chess_analysis(ctx, url: str):
    """Démarre l'analyse en direct d'une partie de Chess.com."""
    if "chess.com/game/live/" not in url:
        await ctx.send("Veuillez fournir une URL de partie **en direct** de Chess.com.")
        return

    if ctx.channel.id in tracked_games:
        await ctx.send("Une analyse est déjà en cours dans ce salon. Utilisez `!stopchess` pour l'arrêter.")
        return

    await ctx.send(f"✅ D'accord, je commence à analyser la partie. Je vérifierai les nouveaux coups toutes les 15 secondes.")
    
    task = game_analysis_loop.start(ctx, url)
    tracked_games[ctx.channel.id] = {'url': url, 'last_ply': 0, 'task': task}

@bot.command(name="stopchess")
async def stop_chess_analysis(ctx):
    """Arrête l'analyse de la partie en cours dans ce salon."""
    if ctx.channel.id in tracked_games:
        tracked_games[ctx.channel.id]['task'].cancel()
        del tracked_games[ctx.channel.id]
        await ctx.send("⏹️ J'ai arrêté de suivre la partie dans ce salon.")
    else:
        await ctx.send("Aucune partie n'est actuellement suivie dans ce salon.")

# --- SECTION 7B : AUTRES COMMANDES (Blazx, Twitch) ---

# Commandes pour les notifications Blazx (inchangées)
@bot.command(name='blazx')
async def subscribe_blazx(ctx):
    # ... (code inchangé)
    subscription = {"user_id": ctx.author.id, "channel_id": ctx.channel.id, "streamer_login": "blazx", "last_status_online": False, "last_known_category": None}
    for sub in blazx_subscriptions:
        if sub['user_id'] == ctx.author.id and sub['channel_id'] == ctx.channel.id:
            await ctx.send(f"Hey {ctx.author.mention}, vous êtes déjà abonné aux notifications pour Blazx dans ce salon !")
            return
    blazx_subscriptions.append(subscription)
    await ctx.send(f"✅ Parfait, {ctx.author.mention} ! Vous serez notifié ici dès que Blazx lance un stream ou change de catégorie.")

@bot.command(name='stopblazx')
async def unsubscribe_blazx(ctx):
    # ... (code inchangé)
    subs_to_remove = [sub for sub in blazx_subscriptions if sub['user_id'] == ctx.author.id and sub['channel_id'] == ctx.channel.id]
    if not subs_to_remove:
        await ctx.send(f"{ctx.author.mention}, vous n'étiez pas abonné aux notifications pour Blazx dans ce salon.")
        return
    for sub in subs_to_remove: blazx_subscriptions.remove(sub)
    await ctx.send(f"☑️ C'est noté, {ctx.author.mention}. Vous ne recevrez plus de notifications pour Blazx ici.")

# Commandes pour le contrôle du chat Twitch (inchangées)
@bot.command(name='motcle')
@commands.has_permissions(administrator=True)
async def watch_keyword(ctx, streamer: str = None, *, keyword: str = None):
    if not streamer or not keyword: await ctx.send("Syntaxe : `!motcle <streamer> <mot-clé>`"); return
    if hasattr(bot, 'twitch_bot'): await bot.twitch_bot.start_keyword_watch(streamer, keyword, ctx.channel); await ctx.send(f"✅ Surveillance du mot-clé **'{keyword}'** dans le chat de **{streamer}** activée.")

@bot.command(name='tchat')
@commands.has_permissions(administrator=True)
async def mirror_chat(ctx, streamer: str = None):
    if not streamer: await ctx.send("Syntaxe : `!tchat <streamer>`"); return
    if hasattr(bot, 'twitch_bot'): await ctx.send("⚠️ Lancement du miroir..."); await bot.twitch_bot.start_mirror(streamer, ctx.channel); await ctx.send(f"✅ Miroir du chat de **{streamer}** activé.")

@bot.command(name='stop')
@commands.has_permissions(administrator=True)
async def stop_watcher(ctx):
    if hasattr(bot, 'twitch_bot'): await bot.twitch_bot.stop_task(); await ctx.send("✅ Surveillance Twitch arrêtée.")

# --- SECTION 8 : TÂCHES DE FOND ---

# NOUVEAU : Tâche de fond pour l'analyse des parties
@tasks.loop(seconds=15)
async def game_analysis_loop(ctx, game_url):
    channel_id = ctx.channel.id
    if channel_id not in tracked_games or tracked_games[channel_id]['url'] != game_url:
        game_analysis_loop.stop()
        return

    try:
        pgn_data = chess.com.get_game_pgn(game_url)
        pgn_stream = io.StringIO(pgn_data)
        game = chess.pgn.read_game(pgn_stream)

        if not game: return
            
        board = game.board()
        current_ply = 0
        last_analyzed_ply = tracked_games[channel_id]['last_ply']
        
        for move in game.mainline_moves():
            current_ply += 1
            if current_ply <= last_analyzed_ply:
                board.push(move)
                continue

            fen_before = board.fen()
            turn = board.turn
            eval_before = get_lichess_evaluation(fen_before)
            
            san_move = board.san(move)
            board.push(move)
            
            eval_after = get_lichess_evaluation(board.fen())
            
            tracked_games[channel_id]['last_ply'] = current_ply
            
            if eval_before is not None and eval_after is not None:
                move_quality = classify_move(eval_before, eval_after, turn)
                if move_quality:
                    player_name = game.headers["White" if turn == chess.WHITE else "Black"]
                    message = (
                        f"**{int((current_ply + 1) / 2)}. {san_move}** par **{player_name}**"
                        f" - {move_quality} ! (Éval: {eval_before/100:.2f} ➔ {eval_after/100:.2f})"
                    )
                    await ctx.send(message)

        if game.headers.get("Result") != "*":
            await ctx.send(f"Partie terminée. Résultat : {game.headers['Result']}. Arrêt de l'analyse.")
            tracked_games[channel_id]['task'].cancel()
            del tracked_games[channel_id]

    except Exception as e:
        await ctx.send(f"Une erreur est survenue pendant le suivi de la partie : {e}")
        tracked_games[channel_id]['task'].cancel()
        del tracked_games[channel_id]

# Tâche de fond pour Blazx (inchangée)
@tasks.loop(minutes=1)
async def check_blazx_status():
    # ... (code inchangé)
    if not blazx_subscriptions: return
    blazx_id = await get_streamer_id("blazx")
    if not blazx_id: return
    stream_info = await get_stream_status(blazx_id)

    if stream_info:
        current_category = stream_info.get("game_name", "N/A")
        for sub in blazx_subscriptions:
            channel = bot.get_channel(sub['channel_id'])
            if not channel: continue
            if not sub['last_status_online']:
                embed = discord.Embed(title=f"🔴 Blazx est en LIVE !", description=f"**{stream_info.get('title')}**", url="https://www.twitch.tv/blazx", color=discord.Color.red())
                embed.add_field(name="Jeu", value=current_category)
                embed.set_thumbnail(url=stream_info.get("thumbnail_url", "").replace("{width}", "1920").replace("{height}", "1080"))
                await channel.send(embed=embed)
            elif sub['last_known_category'] != current_category:
                embed = discord.Embed(title=f"🔄 Blazx a changé de catégorie !", url="https://www.twitch.tv/blazx", color=discord.Color.blue())
                embed.add_field(name="Ancienne catégorie", value=sub['last_known_category'], inline=True)
                embed.add_field(name="Nouvelle catégorie", value=current_category, inline=True)
                await channel.send(embed=embed)
            sub['last_status_online'] = True
            sub['last_known_category'] = current_category
    else:
        for sub in blazx_subscriptions:
            if sub['last_status_online']:
                sub['last_status_online'] = False
                sub['last_known_category'] = None


# --- SECTION 9 : ÉVÉNEMENTS ET DÉMARRAGE ---
@bot.event
async def on_ready():
    print("-------------------------------------------------")
    print(f"Bot Discord '{bot.user.name}' connecté.")
    check_blazx_status.start()
    print("[API] Tâche de surveillance pour Blazx activée.")
    print("[API] L'analyse de parties d'échecs est prête à être lancée via commande.")
    print("-------------------------------------------------")

async def main():
    discord_bot_instance = bot
    twitch_bot_instance = WatcherBot(discord_bot_instance)
    discord_bot_instance.twitch_bot = twitch_bot_instance
    
    await asyncio.gather(
        discord_bot_instance.start(DISCORD_TOKEN),
        twitch_bot_instance.start()
    )

if __name__ == "__main__":
    asyncio.run(main())
