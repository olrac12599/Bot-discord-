import discord
from discord.ext import commands, tasks
from discord import app_commands
import requests
import os
import asyncio
from enum import Enum, auto

# --- NOUVEAU : Import pour le bot Twitch et la gestion des états ---
from twitchio.ext import commands as twitch_commands

# --- 1. CONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
# Identifiants pour l'API Twitch (utilisés par les anciennes commandes /alerte_live, si vous les gardez)
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_TOKEN = os.getenv("TWITCH_TOKEN") 
# Identifiants pour la connexion au CHAT Twitch
TTV_BOT_NICKNAME = os.getenv("TTV_BOT_NICKNAME")
TTV_BOT_TOKEN = os.getenv("TTV_BOT_TOKEN") 

if not all([DISCORD_TOKEN, TTV_BOT_NICKNAME, TTV_BOT_TOKEN]):
    raise ValueError("ERREUR CRITIQUE: Variables d'environnement manquantes (DISCORD_TOKEN, TTV_BOT_NICKNAME, TTV_BOT_TOKEN).")

intents = discord.Intents.default()
intents.message_content = True
# On utilise un préfixe personnalisable
bot = commands.Bot(command_prefix="!", intents=intents)


# --- NOUVEAU : Gestion des états pour le bot Twitch ---
class WatcherMode(Enum):
    IDLE = auto()       # Ne fait rien
    KEYWORD = auto()    # Cherche un mot-clé
    MIRROR = auto()     # Copie tout le chat

# --- MODIFIÉ : BOT DE SURVEILLANCE TWITCH POLYVALENT ---
class WatcherBot(twitch_commands.Bot):
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
        """Arrête toute tâche en cours et quitte le salon Twitch."""
        if self.current_channel_name:
            await self.part_channels([self.current_channel_name])
        self.mode = WatcherMode.IDLE
        self.current_channel_name = None
        self.target_discord_channel = None
        self.keyword_to_watch = None
        print("[TWITCH] Tâche arrêtée. En attente de nouvelles instructions.")

    async def start_keyword_watch(self, twitch_channel: str, keyword: str, discord_channel: discord.TextChannel):
        """Démarre la surveillance d'un mot-clé."""
        await self.stop_task() # On s'assure d'arrêter la tâche précédente
        self.mode = WatcherMode.KEYWORD
        self.keyword_to_watch = keyword
        self.target_discord_channel = discord_channel
        self.current_channel_name = twitch_channel.lower()
        await self.join_channels([self.current_channel_name])
        print(f"[TWITCH] Mode MOT-CLÉ activé pour le salon #{self.current_channel_name}, mot='{keyword}'.")

    async def start_mirror(self, twitch_channel: str, discord_channel: discord.TextChannel):
        """Démarre le miroir de chat."""
        await self.stop_task()
        self.mode = WatcherMode.MIRROR
        self.target_discord_channel = discord_channel
        self.current_channel_name = twitch_channel.lower()
        await self.join_channels([self.current_channel_name])
        print(f"[TWITCH] Mode MIROIR activé pour le salon #{self.current_channel_name}.")

    async def event_message(self, message):
        if message.echo or self.mode == WatcherMode.IDLE:
            return

        # --- Logique pour le mode MOT-CLÉ ---
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
        
        # --- Logique pour le mode MIROIR ---
        elif self.mode == WatcherMode.MIRROR:
            formatted_message = f"**{message.author.name}**: {message.content}"
            if len(formatted_message) > 2000:
                formatted_message = formatted_message[:1997] + "..."
            try:
                await self.target_discord_channel.send(formatted_message)
            except Exception as e:
                print(f"Erreur envoi message miroir: {e}")


# --- NOUVEAU : COMMANDES DE CONTRÔLE TWITCH ---
@bot.command(name='motcle')
@commands.has_permissions(administrator=True)
async def watch_keyword(ctx, streamer: str = None, *, keyword: str = None):
    """Surveille un mot-clé dans un chat Twitch. Usage: !motcle <streamer> <mot-clé>"""
    if not streamer or not keyword:
        await ctx.send("❌ Usage incorrect. Syntaxe : `!motcle <nom_du_streamer> <mot_clé>`")
        return
    if hasattr(bot, 'twitch_bot'):
        await bot.twitch_bot.start_keyword_watch(streamer, keyword, ctx.channel)
        await ctx.send(f"✅ D'accord, je surveille le mot-clé **'{keyword}'** dans le chat de **{streamer}**.")
    else:
        await ctx.send("Le module Twitch n'est pas encore prêt.")

@bot.command(name='tchat')
@commands.has_permissions(administrator=True)
async def mirror_chat(ctx, streamer: str = None):
    """Fait un miroir complet d'un chat Twitch. Usage: !tchat <streamer>"""
    if not streamer:
        await ctx.send("❌ Usage incorrect. Syntaxe : `!tchat <nom_du_streamer>`")
        return
    await ctx.send("⚠️ **Avertissement :** Le miroir de chat peut rapidement atteindre les limites de Discord et devenir instable. Lancement...")
    if hasattr(bot, 'twitch_bot'):
        await bot.twitch_bot.start_mirror(streamer, ctx.channel)
        await ctx.send(f"✅ D'accord, je commence le miroir du chat de **{streamer}** dans ce salon.")
    else:
        await ctx.send("Le module Twitch n'est pas encore prêt.")

@bot.command(name='stop')
@commands.has_permissions(administrator=True)
async def stop_watcher(ctx):
    """Arrête toute surveillance Twitch en cours."""
    if hasattr(bot, 'twitch_bot'):
        await bot.twitch_bot.stop_task()
        await ctx.send("✅ D'accord, j'ai arrêté toute surveillance Twitch.")
    else:
        await ctx.send("Le module Twitch n'est pas encore prêt.")


# --- DÉMARRAGE ET GESTIONNAIRE D'ERREURS ---
@bot.event
async def on_ready():
    print(f"-------------------------------------------------")
    print(f"Bot Discord '{bot.user.name}' connecté.")
    print(f"-------------------------------------------------")
    # Si vous voulez garder vos commandes slash, décommentez la ligne suivante
    # await bot.tree.sync()

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

