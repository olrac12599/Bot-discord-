
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
from io import StringIO
import aiohttp

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

# --- SECTION 5 : FONCTIONS UTILITAIRES (API & LOGIQUE) ---

# Fonctions pour l'API Twitch
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
    except requests.exceptions.RequestException as e:
        print(f"Erreur API (get_streamer_id): {e}")
    return None

async def get_stream_status(streamer_id: str) -> dict | None:
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

# Fonctions pour l'analyse d'échecs
async def get_last_game_pgn(username: str) -> str | None:
    # CORRIGÉ : Utilise la variable `username` au lieu d'un nom en dur
    api_url = f"https://api.chess.com/pub/player/{username}/games/archives"
    headers = {"User-Agent": "MonSuperBotDiscord/1.0 (contact@example.com)"}
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(api_url, timeout=10) as archives_response:
                archives_response.raise_for_status()
                archives_data = await archives_response.json()
                archives_list = archives_data.get("archives")
                if not archives_list: return None

            last_month_url = archives_list[-1]
            async with session.get(last_month_url, timeout=10) as games_response:
                games_response.raise_for_status()
                games_data = await games_response.json()
                all_games = games_data.get("games")
                if not all_games: return None
                
                return all_games[-1].get('pgn')
    except aiohttp.ClientError as e:
        print(f"Erreur API Chess.com / aiohttp : {e}")
        return None

async def get_lichess_evaluation(session: aiohttp.ClientSession, board: chess.Board) -> dict | None:
    fen = board.fen()
    url = f"https://lichess.org/api/cloud-eval?fen={fen}"
    try:
        async with session.get(url, timeout=10) as response:
            if response.status == 200: return await response.json()
            else: return None
    except aiohttp.ClientError:
        return None

def classify_lichess_move(eval_before: dict, eval_after: dict, player_pov: bool) -> str:
    if not eval_before or not eval_after or eval_after.get("knodes", 0) == 0:
        return "⚪ Coup Théorique"

    if "mate" in eval_after and eval_after["mate"] is not None:
        if (player_pov and eval_after["mate"] > 0) or (not player_pov and eval_after["mate"] < 0):
             return "🏆 Mat !"
    
    cp_before = eval_before.get("pvs", [{}])[0].get("cp", 0) if eval_before.get("pvs") else 0
    cp_after = eval_after.get("pvs", [{}])[0].get("cp", 0) if eval_after.get("pvs") else 0
    
    eval_pov_before = cp_before if player_pov else -cp_before
    eval_pov_after = cp_after if player_pov else -cp_after

    centipawn_loss = eval_pov_before - eval_pov_after

    if centipawn_loss <= 5: return "🚀 Coup Brillant"
    if centipawn_loss <= 20: return "✅ Meilleur Coup"
    if centipawn_loss <= 50: return "👍 Excellent Coup"
    if centipawn_loss <= 100: return "👌 Bon Coup"
    if centipawn_loss <= 200: return "❓ Imprécision"
    if centipawn_loss <= 350: return "❌ Erreur"
    return "🔥🔥 GAFEEEEE"

# --- SECTION 6 : CLASSES DES BOTS EXTERNES ---

class WatcherMode(Enum):
    IDLE = auto(); KEYWORD = auto(); MIRROR = auto()

class WatcherBot(twitch_commands.Bot):
    # CORRIGÉ : Les méthodes sont maintenant correctement indentées dans la classe
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

# Commande pour l'analyse d'échecs
@bot.command(name='analysechess')
@commands.cooldown(1, 120, commands.BucketType.channel)
async def analyse_chess_game_lichess(ctx, username: str = None):
    if not username:
        await ctx.send("Veuillez fournir un nom d'utilisateur Chess.com. Syntaxe : `!analysechess <username>`")
        return

    msg = await ctx.send(f"🔍 Recherche de la dernière partie de **{username}**...")
    pgn_data = await get_last_game_pgn(username.lower())
    if not pgn_data:
        await msg.edit(content=f"Impossible de trouver des parties pour le joueur **{username}**. Vérifiez le pseudo.")
        return

    await msg.edit(content=f"Partie trouvée ! ♟️ Envoi pour analyse aux serveurs Lichess... (cela peut prendre un instant)")
    game = chess.pgn.read_game(StringIO(pgn_data))
    board = game.board()
    analysis_results = []
    move_number = 1

    try:
        async with aiohttp.ClientSession() as session:
            for node in game.mainline():
                move = node.move
                eval_before = await get_lichess_evaluation(session, board)
                is_white_turn = board.turn == chess.WHITE
                player = "Blancs" if is_white_turn else "Noirs"
                move_san = board.san(move)
                board.push(move)
                eval_after = await get_lichess_evaluation(session, board)
                
                classification = classify_lichess_move(eval_before, eval_after, is_white_turn)
                analysis_results.append(f"**{move_number}. {player} ({move_san})** : {classification}")

                if not is_white_turn: move_number += 1
            
        white_player, black_player, game_result, game_url = game.headers.get('White'), game.headers.get('Black'), game.headers.get('Result'), game.headers.get('Link')
        embed = discord.Embed(title=f"Analyse Lichess : {white_player} vs {black_player}", description=f"**Résultat : {game_result}**\n[Voir la partie sur Chess.com]({game_url})", color=discord.Color.purple())
        output_text = "\n".join(analysis_results[-20:])
        if len(analysis_results) > 20: output_text = "(...) \n" + output_text
        embed.add_field(name="Analyse des derniers coups", value=output_text, inline=False)
        embed.set_footer(text=f"Analyse pour {username} demandée par {ctx.author.name}")
        await msg.edit(content="✅ Analyse Lichess terminée !", embed=embed)
    except Exception as e:
        await msg.edit(content=f"Une erreur est survenue durant l'analyse : {e}")
        print(f"Erreur d'analyse Lichess: {e}")

@analyse_chess_game_lichess.error
async def analyse_chess_game_lichess_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Respectons les serveurs de Lichess ! Veuillez patienter {error.retry_after:.1f} secondes.")

# Commandes pour les notifications Blazx
@bot.command(name='blazx')
async def subscribe_blazx(ctx):
    subscription = {"user_id": ctx.author.id, "channel_id": ctx.channel.id, "streamer_login": "blazx", "last_status_online": False, "last_known_category": None}
    for sub in blazx_subscriptions:
        if sub['user_id'] == ctx.author.id and sub['channel_id'] == ctx.channel.id:
            await ctx.send(f"Hey {ctx.author.mention}, vous êtes déjà abonné aux notifications pour Blazx dans ce salon !")
            return
    blazx_subscriptions.append(subscription)
    await ctx.send(f"✅ Parfait, {ctx.author.mention} ! Vous serez notifié ici dès que Blazx lance un stream ou change de catégorie.")

@bot.command(name='stopblazx')
async def unsubscribe_blazx(ctx):
    subs_to_remove = [sub for sub in blazx_subscriptions if sub['user_id'] == ctx.author.id and sub['channel_id'] == ctx.channel.id]
    if not subs_to_remove:
        await ctx.send(f"{ctx.author.mention}, vous n'étiez pas abonné aux notifications pour Blazx dans ce salon.")
        return
    for sub in subs_to_remove: blazx_subscriptions.remove(sub)
    await ctx.send(f"☑️ C'est noté, {ctx.author.mention}. Vous ne recevrez plus de notifications pour Blazx ici.")

# Commandes pour le contrôle du chat Twitch
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
@tasks.loop(minutes=1)
async def check_blazx_status():
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
    print("-------------------------------------------------")

async def main():
    # On lie l'instance du bot Twitch au bot Discord pour pouvoir y accéder dans les commandes
    discord_bot_instance = bot
    twitch_bot_instance = WatcherBot(discord_bot_instance)
    discord_bot_instance.twitch_bot = twitch_bot_instance
    
    await asyncio.gather(
        discord_bot_instance.start(DISCORD_TOKEN),
        twitch_bot_instance.start()
    )

if __name__ == "__main__":
    asyncio.run(main())
