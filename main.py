# --- IMPORTS ---
import discord
from discord.ext import commands
from twitchio.ext import commands as twitch_commands
import os
import asyncio
from enum import Enum, auto
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import io
from PIL import Image
from pathlib import Path

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_TOKEN = os.getenv("TWITCH_TOKEN")
TTV_BOT_NICKNAME = os.getenv("TTV_BOT_NICKNAME")
TTV_BOT_TOKEN = os.getenv("TTV_BOT_TOKEN")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")
DISCORD_FILE_LIMIT_BYTES = 8 * 1024 * 1024  # 8 Mo

if not all([DISCORD_TOKEN, TWITCH_CLIENT_ID, TWITCH_TOKEN, TTV_BOT_NICKNAME, TTV_BOT_TOKEN]):
    raise ValueError("ERREUR CRITIQUE: Variables d'environnement Twitch/Discord manquantes.")
if not all([CHESS_USERNAME, CHESS_PASSWORD]):
    raise ValueError("ERREUR CRITIQUE: CHESS_USERNAME et CHESS_PASSWORD doivent être définis.")

# --- INIT BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# --- EXCEPTION PERSONNALISÉE (avec support vidéo) ---
class ScrapingError(Exception):
    def __init__(self, message, screenshot_bytes=None, video_path=None):
        super().__init__(message)
        self.screenshot_bytes = screenshot_bytes
        self.video_path = video_path


# --- FONCTION DE SCRAPING AVEC ENREGISTREMENT VIDÉO ---
async def get_pgn_from_chess_com(url: str, username: str, password: str) -> str:
    """
    Enregistre une vidéo de la session de scraping pour le débogage.
    """
    videos_dir = Path("debug_videos")
    videos_dir.mkdir(exist_ok=True)

    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=True)
        context = await browser.new_context(
            record_video_dir=str(videos_dir),
            record_video_size={"width": 1280, "height": 720}
        )
        page = await context.new_page()
        try:
            print("Navigation vers la page de connexion...")
            await page.goto("https://www.chess.com/login_and_go", timeout=90000)

            try:
                await page.get_by_role("button", name="I Accept").click(timeout=10000)
                print("Cookies acceptés.")
            except PlaywrightTimeoutError:
                print("Aucune bannière de cookies détectée.")

            await page.get_by_placeholder("Username, Phone, or Email").fill(username)
            await page.get_by_placeholder("Password").fill(password)
            await page.get_by_role("button", name="Log In").click()
            await page.wait_for_url("https://www.chess.com/home", timeout=60000)
            print("Connexion réussie !")

            await page.goto(url, timeout=90000)
            await page.click(".icon-font-chess.share", timeout=30000)
            await page.click('div.share-menu-tab-component-header:has-text("PGN")', timeout=20000)
            pgn_text = await page.input_value('textarea.share-menu-tab-pgn-textarea', timeout=20000)

            await context.close()
            await browser.close()
            return pgn_text

        except Exception as e:
            print(f"ERREUR: Une erreur de scraping est survenue. Détails: {e}")
            screenshot_bytes = None
            video_path = None

            try:
                video_path = await page.video.path()
            except Exception:
                print("Impossible de récupérer le chemin de la vidéo.")

            if not page.is_closed():
                screenshot_bytes = await page.screenshot(full_page=True)

            await context.close()
            await browser.close()

            raise ScrapingError(f"Détails: {e}", screenshot_bytes=screenshot_bytes, video_path=video_path)


# --- CLASSE BOT TWITCH ---
class WatcherMode(Enum):
    IDLE, KEYWORD, MIRROR = auto(), auto(), auto()

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


# --- COMMANDES DISCORD ---
@bot.command(name="chess")
async def get_chess_pgn(ctx, url: str):
    if not ("chess.com/game/live/" in url or "chess.com/play/game/" in url):
        await ctx.send("❌ URL invalide.")
        return
        
    msg = await ctx.send("🌐 Lancement du scraping... Connexion à Chess.com en cours...")

    try:
        pgn = await get_pgn_from_chess_com(CHESS_USERNAME, CHESS_PASSWORD, url)
        if len(pgn) > 1900:
            pgn_short = pgn[:1900] + "..."
        else:
            pgn_short = pgn
        await msg.edit(content=f"✅ PGN récupéré !\n```\n{pgn_short}\n```")

    except ScrapingError as e:
        await msg.edit(content=f"❌ Erreur lors de la récupération du PGN. Analyse des fichiers de débogage...")
        
        files_to_send = []
        if e.screenshot_bytes:
            # La logique de compression pourrait être ajoutée ici si nécessaire
            files_to_send.append(discord.File(io.BytesIO(e.screenshot_bytes), filename="debug_screenshot.png"))

        if e.video_path:
            video_file = Path(e.video_path)
            if video_file.exists():
                file_size = video_file.stat().st_size
                if file_size < DISCORD_FILE_LIMIT_BYTES:
                    files_to_send.append(discord.File(str(video_file), filename="debug_video.webm"))
                    # On envoie un message séparé pour les fichiers pour éviter des erreurs
                    await ctx.send(f"❌ **Erreur de scraping :** {e}", files=files_to_send)
                else:
                    await ctx.send(f"❌ **Erreur de scraping :** {e}\n📹 La vidéo de débogage a été enregistrée mais est trop lourde ({file_size / 1_000_000:.2f} Mo) pour être envoyée.", files=files_to_send)
            else:
                await ctx.send(f"❌ **Erreur de scraping :** {e}", files=files_to_send)
        elif files_to_send:
            await ctx.send(f"❌ **Erreur de scraping :** {e}", files=files_to_send)
        else:
            await ctx.send(f"❌ **Erreur de scraping :** {e} (Aucun fichier de débogage généré)")

    except Exception as e:
        await msg.edit(content=f"❌ Une erreur imprévue est survenue : {e}")

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
        await ctx.send(f"🪞 Miroir du tchat de **{streamer}** activé.")

@bot.command(name="stop")
@commands.has_permissions(administrator=True)
async def stop_twitch_watch(ctx):
    if hasattr(bot, 'twitch_bot'):
        await bot.twitch_bot.stop_task()
        await ctx.send("🛑 Surveillance Twitch arrêtée.")

@bot.command(name="ping")
async def ping(ctx):
    await ctx.send("Pong!")


# --- ÉVÉNEMENTS DISCORD ---
@bot.event
async def on_ready():
    print(f"Bot Discord connecté en tant que {bot.user} !")


# --- LANCEMENT ---
async def main():
    twitch_bot_instance = WatcherBot(bot)
    bot.twitch_bot = twitch_bot_instance
    await asyncio.gather(bot.start(DISCORD_TOKEN), twitch_bot_instance.start())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Arrêt du bot demandé.")
