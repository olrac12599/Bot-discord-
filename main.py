import discord
from discord.ext import commands, tasks
import requests
import os
import asyncio
from enum import Enum, auto

# --- NOUVEAU : Import pour le bot Twitch et la gestion des états ---
from twitchio.ext import commands as twitch_commands

# --- 1. CONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
# Identifiants pour l'API Twitch (utilisés pour les alertes Blazx)
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_TOKEN = os.getenv("TWITCH_TOKEN") 
# Identifiants pour la connexion au CHAT Twitch
TTV_BOT_NICKNAME = os.getenv("TTV_BOT_NICKNAME")
TTV_BOT_TOKEN = os.getenv("TTV_BOT_TOKEN") 

if not all([DISCORD_TOKEN, TWITCH_CLIENT_ID, TWITCH_TOKEN, TTV_BOT_NICKNAME, TTV_BOT_TOKEN]):
    raise ValueError("ERREUR CRITIQUE: Variables d'environnement manquantes.")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- NOUVEAU : STOCKAGE POUR LES ABONNEMENTS BLAZX ---
blazx_subscriptions = []
streamer_id_cache = {} # On réutilise ce cache pour l'ID de Blazx

# --- NOUVEAU : FONCTIONS UTILITAIRES API TWITCH ---
# Nécessaires pour vérifier le statut du stream de Blazx
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
    except requests.exceptions.RequestException as e: print(f"Erreur API (get_streamer_id): {e}")
    return None

async def get_stream_status(streamer_id: str) -> dict | None:
    headers = {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {TWITCH_TOKEN}"}
    params = {"user_id": streamer_id}
    try:
        r = requests.get("https://api.twitch.tv/helix/streams", headers=headers, params=params, timeout=5)
        r.raise_for_status()
        data = r.json()
        if data.get("data"): return data["data"][0]
    except requests.exceptions.RequestException as e: print(f"Erreur API (get_stream_status): {e}")
    return None

# --- Gestion des états pour le bot de chat Twitch ---
class WatcherMode(Enum):
    IDLE = auto(); KEYWORD = auto(); MIRROR = auto()

# --- BOT DE SURVEILLANCE TWITCH POLYVALENT (INCHANGÉ) ---
class WatcherBot(twitch_commands.Bot):
    # ... (le code de cette classe reste exactement le même que dans la version précédente)
    def __init__(self, discord_bot_instance):
        super().__init__(token=TTV_BOT_TOKEN, prefix='!')
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
        if self.current_channel_name: await self.part_channels([self.current_channel_name])
        self.mode = WatcherMode.IDLE; self.current_channel_name = None; self.target_discord_channel = None; self.keyword_to_watch = None
        print("[TWITCH] Tâche arrêtée. En attente de nouvelles instructions.")
    async def start_keyword_watch(self, twitch_channel: str, keyword: str, discord_channel: discord.TextChannel):
        await self.stop_task(); self.mode = WatcherMode.KEYWORD; self.keyword_to_watch = keyword; self.target_discord_channel = discord_channel
        self.current_channel_name = twitch_channel.lower(); await self.join_channels([self.current_channel_name])
        print(f"[TWITCH] Mode MOT-CLÉ activé pour #{self.current_channel_name}, mot='{keyword}'.")
    async def start_mirror(self, twitch_channel: str, discord_channel: discord.TextChannel):
        await self.stop_task(); self.mode = WatcherMode.MIRROR; self.target_discord_channel = discord_channel
        self.current_channel_name = twitch_channel.lower(); await self.join_channels([self.current_channel_name])
        print(f"[TWITCH] Mode MIROIR activé pour #{self.current_channel_name}.")
    async def event_message(self, message):
        if message.echo or self.mode == WatcherMode.IDLE: return
        if self.mode == WatcherMode.KEYWORD:
            if self.keyword_to_watch.lower() in message.content.lower():
                embed = discord.Embed(title="🚨 Mot-Clé Détecté sur Twitch !", color=discord.Color.orange())
                embed.add_field(name="Chaîne", value=f"#{message.channel.name}", inline=True); embed.add_field(name="Auteur", value=message.author.name, inline=True)
                embed.add_field(name="Message", value=f"`{message.content}`", inline=False)
                try: await self.target_discord_channel.send(embed=embed)
                except Exception as e: print(f"Erreur envoi notif mot-clé: {e}")
        elif self.mode == WatcherMode.MIRROR:
            formatted_message = f"**{message.author.name}**: {message.content}"; await self.target_discord_channel.send(formatted_message[:2000])


# --- NOUVEAU : COMMANDES SPÉCIFIQUES POUR BLAZX ---
@bot.command(name='blazx')
async def subscribe_blazx(ctx):
    """S'abonne aux notifications de live et de changement de jeu pour Blazx."""
    subscription = {
        "user_id": ctx.author.id,
        "channel_id": ctx.channel.id,
        "streamer_login": "blazx",
        "last_status_online": False,
        "last_known_category": None
    }
    # Vérifier si l'utilisateur n'est pas déjà abonné dans ce salon
    for sub in blazx_subscriptions:
        if sub['user_id'] == ctx.author.id and sub['channel_id'] == ctx.channel.id:
            await ctx.send(f"Hey {ctx.author.mention}, vous êtes déjà abonné aux notifications pour Blazx dans ce salon !")
            return

    blazx_subscriptions.append(subscription)
    await ctx.send(f"✅ Parfait, {ctx.author.mention} ! Vous serez notifié ici dès que Blazx lance un stream ou change de catégorie.")

@bot.command(name='stopblazx')
async def unsubscribe_blazx(ctx):
    """Se désabonne des notifications pour Blazx."""
    subs_to_remove = [sub for sub in blazx_subscriptions if sub['user_id'] == ctx.author.id and sub['channel_id'] == ctx.channel.id]
    if not subs_to_remove:
        await ctx.send(f"{ctx.author.mention}, vous n'étiez pas abonné aux notifications pour Blazx dans ce salon.")
        return
    
    for sub in subs_to_remove:
        blazx_subscriptions.remove(sub)
        
    await ctx.send(f"☑️ C'est noté, {ctx.author.mention}. Vous ne recevrez plus de notifications pour Blazx ici.")


# --- COMMANDES DE CONTRÔLE DU CHAT (INCHANGÉES) ---
@bot.command(name='motcle')
@commands.has_permissions(administrator=True)
async def watch_keyword(ctx, streamer: str = None, *, keyword: str = None):
    if not streamer or not keyword: await ctx.send("Syntaxe : `!motcle <streamer> <mot-clé>`"); return
    if hasattr(bot, 'twitch_bot'): await bot.twitch_bot.start_keyword_watch(streamer, keyword, ctx.channel); await ctx.send(f"✅ Surveillance du mot-clé **'{keyword}'** dans le chat de **{streamer}** activée.")
@bot.command(name='tchat')
@commands.has_permissions(administrator=True)
async def mirror_chat(ctx, streamer: str = None):
    if not streamer: await ctx.send("Syntaxe : `!tchat <streamer>`"); return
    if hasattr(bot, 'twitch_bot'): await ctx.send("⚠️ Lancement du miroir... (Attention aux limites de Discord)"); await bot.twitch_bot.start_mirror(streamer, ctx.channel); await ctx.send(f"✅ Miroir du chat de **{streamer}** activé.")
@bot.command(name='stop')
@commands.has_permissions(administrator=True)
async def stop_watcher(ctx):
    if hasattr(bot, 'twitch_bot'): await bot.twitch_bot.stop_task(); await ctx.send("✅ Surveillance Twitch arrêtée.")

# --- NOUVEAU : TÂCHE DE FOND POUR BLAZX ---
@tasks.loop(minutes=1)
async def check_blazx_status():
    if not blazx_subscriptions: return # Ne rien faire s'il n'y a pas d'abonnés

    blazx_id = await get_streamer_id("blazx")
    if not blazx_id: return
    
    stream_info = await get_stream_status(blazx_id)

    # Scénario 1: Blazx est en live
    if stream_info:
        current_category = stream_info.get("game_name")
        for sub in blazx_subscriptions:
            channel = bot.get_channel(sub['channel_id'])
            if not channel: continue # Si le salon n'est plus accessible

            # Notification de MISE EN LIVE
            if not sub['last_status_online']:
                embed = discord.Embed(title=f"🔴 Blazx est en LIVE !", description=f"**{stream_info.get('title')}**", url="https://www.twitch.tv/blazx", color=discord.Color.red())
                embed.add_field(name="Jeu", value=current_category)
                embed.set_thumbnail(url="https://static-cdn.jtvnw.net/previews-ttv/live_user_blazx-1920x1080.jpg") # Image du live
                await channel.send(embed=embed)
            
            # Notification de CHANGEMENT DE CATÉGORIE
            elif sub['last_known_category'] and sub['last_known_category'] != current_category:
                embed = discord.Embed(title=f"🔄 Blazx a changé de catégorie !", url="https://www.twitch.tv/blazx", color=discord.Color.blue())
                embed.add_field(name="Ancienne catégorie", value=sub['last_known_category'], inline=True)
                embed.add_field(name="Nouvelle catégorie", value=current_category, inline=True)
                await channel.send(embed=embed)

            # Mise à jour de l'état
            sub['last_status_online'] = True
            sub['last_known_category'] = current_category

    # Scénario 2: Blazx n'est pas en live
    else:
        for sub in blazx_subscriptions:
            if sub['last_status_online']:
                # Optionnel : notifier que le stream est terminé
                # channel = bot.get_channel(sub['channel_id'])
                # if channel: await channel.send("Le stream de Blazx est terminé.")
                sub['last_status_online'] = False
                sub['last_known_category'] = None

# --- DÉMARRAGE ET GESTIONNAIRES D'ERREURS ---
@bot.event
async def on_ready():
    print(f"-------------------------------------------------")
    print(f"Bot Discord '{bot.user.name}' connecté.")
    check_blazx_status.start() # Démarrage de la tâche de fond pour Blazx
    print("[API] Tâche de surveillance pour Blazx activée.")
    print(f"-------------------------------------------------")

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


