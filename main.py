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
import chess.svg #+ Ajout pour la génération d'images
from io import StringIO
import aiohttp
import cairosvg #+ Ajout pour la conversion d'images

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
live_chess_sessions = {} #+ Dictionnaire pour stocker les parties suivies par salon

# --- SECTION 5 : FONCTIONS UTILITAIRES (API & LOGIQUE) ---

# Fonctions pour l'API Twitch (inchangées)
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

#+ --- NOUVELLES FONCTIONS POUR LE SUIVI LIVE DE CHESS.COM ---

async def find_live_game(session: aiohttp.ClientSession, username: str) -> dict | None:
    """Trouve la partie en direct d'un joueur sur Chess.com."""
    api_url = f"https://api.chess.com/pub/player/{username}/games/archives"
    headers = {"User-Agent": f"MonSuperBotDiscord/1.0 ({bot.user.name})"}
    try:
        async with session.get(api_url, headers=headers, timeout=10) as archives_response:
            archives_response.raise_for_status()
            archives_data = await archives_response.json()
            archives_list = archives_data.get("archives")
            if not archives_list: return None

        # On vérifie l'archive du mois en cours
        last_month_url = archives_list[-1]
        async with session.get(last_month_url, headers=headers, timeout=10) as games_response:
            games_response.raise_for_status()
            games_data = await games_response.json()
            all_games = games_data.get("games", [])
            
            # On cherche une partie non terminée en partant de la plus récente
            for game_data in reversed(all_games):
                if game_data.get("in_progress", False) or (game_data.get("pgn") and 'Result "*"' in game_data["pgn"]):
                    game_data["source_archive_url"] = last_month_url # On sauvegarde l'URL pour les mises à jour
                    return game_data
    except aiohttp.ClientError as e:
        print(f"Erreur API Chess.com / aiohttp (find_live_game) : {e}")
    return None

def generate_board_image(board: chess.Board, last_move: chess.Move = None, player_pov: str = 'white') -> str:
    """Génère une image PNG de l'échiquier et retourne le nom du fichier."""
    # Détermine l'orientation de l'échiquier
    orientation = chess.WHITE if player_pov.lower() == 'white' else chess.BLACK
    
    # Génère le SVG
    boardsvg = chess.svg.board(board=board, lastmove=last_move, orientation=orientation, size=400)
    
    # Nom du fichier unique pour éviter les conflits
    filename = f"board_{board.fen().replace('/', '')[:15]}.png"
    filepath = os.path.join(os.getcwd(), filename) # Sauvegarde dans le répertoire courant

    # Convertit et sauvegarde
    cairosvg.svg2png(bytestring=boardsvg.encode('utf-8'), write_to=filepath)
    return filepath

# --- SECTION 6 : CLASSES DES BOTS EXTERNES (inchangée) ---

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

#+ --- NOUVELLES COMMANDES POUR LE SUIVI DE PARTIE ---

@bot.command(name='suivrechess')
@commands.cooldown(1, 30, commands.BucketType.channel)
async def suivre_chess(ctx, username: str = None):
    """Lance le suivi en direct d'une partie Chess.com."""
    if not username:
        await ctx.send("Veuillez fournir un nom d'utilisateur Chess.com. Syntaxe : `!suivrechess <pseudo>`")
        ctx.command.reset_cooldown(ctx)
        return
        
    if ctx.channel.id in live_chess_sessions:
        await ctx.send("Un suivi de partie est déjà en cours dans ce salon. Utilisez `!stopchess` pour l'arrêter.")
        ctx.command.reset_cooldown(ctx)
        return

    msg = await ctx.send(f"🔍 Recherche d'une partie en direct pour **{username}**...")

    try:
        async with aiohttp.ClientSession() as session:
            game_data = await find_live_game(session, username.lower())

        if not game_data or not game_data.get('pgn'):
            await msg.edit(content=f"Aucune partie en direct trouvée pour **{username}**.")
            return
        
        pgn = StringIO(game_data['pgn'])
        game = chess.pgn.read_game(pgn)
        board = game.board()
        
        # Détermine le point de vue
        player_pov = 'white'
        if game.headers.get('White', '').lower() != username.lower():
            player_pov = 'black'

        # Génère l'image et l'embed
        last_move = game.mainline().moves[-1] if list(game.mainline().moves) else None
        image_path = generate_board_image(board, last_move, player_pov)
        file = discord.File(image_path, filename=os.path.basename(image_path))

        embed = discord.Embed(
            title=f"🔴 Suivi en direct : {game.headers.get('White')} vs {game.headers.get('Black')}",
            description=f"Partie de **{username}** en cours. Les mises à jour apparaîtront ici.",
            color=discord.Color.green(),
            url=game.headers.get('Link')
        )
        embed.set_image(url=f"attachment://{os.path.basename(image_path)}")
        embed.set_footer(text=f"Partie suivie pour {username} | Joueur au trait : {'Blancs' if board.turn == chess.WHITE else 'Noirs'}")
        
        await msg.delete() # Supprime "Recherche en cours..."
        new_msg = await ctx.send(file=file, embed=embed)
        os.remove(image_path)

        # Sauvegarde de la session
        live_chess_sessions[ctx.channel.id] = {
            "message": new_msg,
            "username": username.lower(),
            "game_url": game.headers.get('Link'),
            "last_pgn": game_data['pgn'],
            "source_archive_url": game_data['source_archive_url'],
            "player_pov": player_pov
        }
        
    except Exception as e:
        await msg.edit(content=f"Une erreur est survenue : {e}")
        print(f"Erreur dans !suivrechess : {e}")


@bot.command(name='stopchess')
async def stop_chess(ctx):
    """Arrête le suivi de partie en cours dans le salon."""
    if ctx.channel.id in live_chess_sessions:
        session_data = live_chess_sessions.pop(ctx.channel.id)
        message_to_edit = session_data["message"]
        embed = message_to_edit.embeds[0]
        embed.title = f"⚫ Suivi terminé : {embed.title.split(': ')[1]}"
        embed.description = "Le suivi de cette partie a été arrêté manuellement."
        embed.color = discord.Color.dark_grey()
        await message_to_edit.edit(embed=embed)
        await ctx.send("Le suivi de la partie a été arrêté.")
    else:
        await ctx.send("Aucun suivi de partie n'est actif dans ce salon.")

@suivre_chess.error
async def suivre_chess_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Veuillez patienter {error.retry_after:.1f}s avant de lancer un autre suivi.")

# Commandes pour les notifications Blazx (inchangées)
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
@tasks.loop(seconds=15) #+ Tâche de mise à jour des parties d'échecs
async def update_live_games():
    if not live_chess_sessions:
        return

    # On utilise une copie des clés pour pouvoir modifier le dict pendant l'itération
    for channel_id in list(live_chess_sessions.keys()):
        session_data = live_chess_sessions[channel_id]
        
        try:
            headers = {"User-Agent": f"MonSuperBotDiscord/1.0 ({bot.user.name})"}
            async with aiohttp.ClientSession() as session:
                async with session.get(session_data["source_archive_url"], headers=headers, timeout=10) as response:
                    if response.status != 200: continue
                    games_data = await response.json()
                    
            # Retrouver la partie par son URL
            current_game_data = next((g for g in games_data.get('games', []) if g.get('url') == session_data['game_url']), None)
            
            if not current_game_data or not current_game_data.get('pgn'):
                continue
            
            new_pgn = current_game_data['pgn']
            
            # Si le PGN n'a pas changé, on ne fait rien
            if len(new_pgn) == len(session_data['last_pgn']):
                continue
            
            # --- Mise à jour de l'affichage ---
            game = chess.pgn.read_game(StringIO(new_pgn))
            board = game.board()
            
            is_finished = 'Result' in game.headers and game.headers['Result'] != '*'
            
            last_move = list(game.mainline().moves)[-1]
            image_path = generate_board_image(board, last_move, session_data["player_pov"])
            file = discord.File(image_path, filename=os.path.basename(image_path))
            
            embed = discord.Embed(
                title=f"🔴 Suivi en direct : {game.headers.get('White')} vs {game.headers.get('Black')}",
                url=game.headers.get('Link')
            )
            embed.set_image(url=f"attachment://{os.path.basename(image_path)}")
            
            if is_finished:
                embed.title = f"🏁 Partie terminée : {game.headers.get('White')} vs {game.headers.get('Black')}"
                embed.description = f"**Résultat : {game.headers.get('Result')}**"
                embed.color = discord.Color.dark_red()
            else:
                last_move_san = board.san(last_move)
                player_turn = "Blancs" if board.turn == chess.WHITE else "Noirs"
                embed.description = f"Dernier coup : **{last_move_san}**"
                embed.set_footer(text=f"Partie suivie pour {session_data['username']} | Au tour des {player_turn}")
                embed.color = discord.Color.green()

            await session_data['message'].edit(embed=embed, attachments=[file])
            os.remove(image_path)

            # Si la partie est terminée, on arrête le suivi
            if is_finished:
                del live_chess_sessions[channel_id]
            else:
                # Sinon, on met à jour le PGN
                live_chess_sessions[channel_id]['last_pgn'] = new_pgn

        except Exception as e:
            print(f"Erreur dans la boucle update_live_games pour le salon {channel_id}: {e}")


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
    update_live_games.start() #+ Démarrage de la nouvelle tâche
    print("[API] Tâche de surveillance pour Blazx activée.")
    print("[API] Tâche de surveillance pour Chess.com activée.") #+
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
