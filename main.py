# --- IMPORTS ---
import discord
from discord.ext import commands
from twitchio.ext import commands as twitch_commands
import os
import asyncio
from enum import Enum, auto
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import io
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

# --- INITIALISATION ET STOCKAGE ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Dictionnaire pour stocker le chemin de la dernière vidéo par salon Discord
last_video_paths = {}

# --- EXCEPTION PERSONNALISÉE ---
class ScrapingError(Exception):
    def __init__(self, message, screenshot_bytes=None, video_path=None):
        super().__init__(message)
        self.screenshot_bytes = screenshot_bytes
        self.video_path = video_path


# --- FONCTION DE SCRAPING CHESS.COM (AVEC CHROMIUM) ---
async def get_pgn_from_chess_com(url: str, username: str, password: str) -> (str, str):
    """
    Se connecte à Chess.com avec Chromium et retourne le PGN et le chemin de la vidéo.
    """
    videos_dir = Path("debug_videos")
    videos_dir.mkdir(exist_ok=True)
    max_retries = 3

    # Arguments pour rendre Chromium plus stable dans les conteneurs
    browser_args = [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-accelerated-2d-canvas',
        '--no-first-run',
        '--no-zygote',
        '--disable-gpu'
    ]

    async with async_playwright() as p:
        # On utilise Chromium
        browser = await p.chromium.launch(headless=True, args=browser_args)
        context = await browser.new_context(
            record_video_dir=str(videos_dir),
            record_video_size={"width": 1280, "height": 720},
            base_url="https://www.chess.com"
        )
        page = await context.new_page()

        try:
            # (La logique de connexion reste la même, elle fonctionnait bien)
            login_successful = False
            for attempt in range(max_retries):
                # ... (code de la boucle de connexion inchangé)
                print(f"Tentative de connexion n°{attempt + 1}/{max_retries}...")
                await page.goto("/login_and_go", timeout=90000)
                await page.wait_for_load_state('domcontentloaded')

                try:
                    await page.get_by_role("button", name="I Accept").click(timeout=5000)
                    print("Cookies acceptés.")
                except PlaywrightTimeoutError:
                    print("Aucune bannière de cookies détectée ou déjà acceptée.")

                await page.get_by_placeholder("Username, Phone, or Email").type(username, delay=50)
                await page.get_by_placeholder("Password").type(password, delay=50)
                await page.get_by_role("button", name="Log In").click()
                
                try:
                    await page.wait_for_url("**/home", timeout=15000)
                    print("Connexion réussie !")
                    login_successful = True
                    break

                except PlaywrightTimeoutError:
                    error_message_visible = await page.is_visible("text=This password is incorrect")
                    if error_message_visible:
                        print(f"Erreur de mot de passe détectée. Nouvelle tentative ({attempt + 1}/{max_retries})...")
                        continue
                    else:
                        raise ScrapingError("Une erreur inattendue est survenue après la tentative de connexion.")

            if not login_successful:
                raise ScrapingError(f"Échec de la connexion après {max_retries} tentatives.")

            print(f"Navigation vers l'URL de la partie : {url}")
            await page.goto(url, timeout=90000)
            
            print("Clic sur le bouton de partage...")
            await page.locator("button.share-button-component").click(timeout=30000)
            
            print("Clic sur l'onglet PGN...")
            await page.locator('div.share-menu-tab-component-header:has-text("PGN")').click(timeout=20000)
            
            print("Récupération du texte PGN...")
            pgn_text = await page.input_value('textarea.share-menu-tab-pgn-textarea', timeout=20000)
            
            # On récupère le chemin de la vidéo même en cas de succès
            video_path = await page.video.path()
            await context.close()
            await browser.close()
            return pgn_text, video_path

        except Exception as e:
            # (Gestion d'erreur inchangée)
            print(f"ERREUR: Une erreur de scraping est survenue. Détails: {e}")
            video_path = None
            screenshot_bytes = None
            try:
                video_path = await page.video.path()
            except Exception:
                print("Impossible de récupérer le chemin de la vidéo.")
            if not page.is_closed():
                screenshot_bytes = await page.screenshot(full_page=True)
            await context.close()
            await browser.close()
            
            if isinstance(e, ScrapingError):
                raise ScrapingError(e, screenshot_bytes=screenshot_bytes, video_path=video_path)
            else:
                raise ScrapingError(f"Détails: {e}", screenshot_bytes=screenshot_bytes, video_path=video_path)

# --- CLASSE DU BOT TWITCH (INCHANGÉE) ---
# ... (copiez ici toute la classe WatcherBot, elle est correcte)
class WatcherMode(Enum):
    IDLE, KEYWORD, MIRROR = auto(), auto(), auto()

class WatcherBot(twitch_commands.Bot):
    # ... (code complet de la classe ici)
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
        print("Surveillance Twitch arrêtée.")
    async def start_keyword_watch(self, twitch_channel, keyword, discord_channel):
        await self.stop_task()
        self.mode = WatcherMode.KEYWORD
        self.keyword_to_watch = keyword
        self.target_discord_channel = discord_channel
        self.current_channel_name = twitch_channel.lower()
        await self.join_channels([self.current_channel_name])
        print(f"Surveillance du mot-clé '{keyword}' activée sur la chaîne '{self.current_channel_name}'.")
    async def start_mirror(self, twitch_channel, discord_channel):
        await self.stop_task()
        self.mode = WatcherMode.MIRROR
        self.target_discord_channel = discord_channel
        self.current_channel_name = twitch_channel.lower()
        await self.join_channels([self.current_channel_name])
        print(f"Mode miroir activé pour la chaîne '{self.current_channel_name}'.")
    async def event_message(self, message):
        if message.echo or self.mode == WatcherMode.IDLE:
            return
        author_name = message.author.name if message.author else "Quelqu'un"
        if self.mode == WatcherMode.KEYWORD:
            if self.keyword_to_watch.lower() in message.content.lower():
                embed = discord.Embed(title="🚨 Mot-Clé Twitch détecté !", description=message.content, color=discord.Color.orange())
                embed.set_footer(text=f"Chaîne : {message.channel.name} | Auteur : {author_name}")
                await self.target_discord_channel.send(embed=embed)
        elif self.mode == WatcherMode.MIRROR:
            msg = f"**{author_name}**: {message.content}"
            await self.target_discord_channel.send(msg[:2000])


# --- COMMANDES DISCORD (AVEC !CAM) ---
@bot.command(name="chess")
async def get_chess_pgn(ctx, url: str):
    if not ("chess.com/game/live/" in url or "chess.com/play/game/" in url):
        await ctx.send("❌ URL invalide. L'URL doit provenir d'une partie sur Chess.com.")
        return
        
    msg = await ctx.send("🌐 **Lancement du scraping...** Connexion à Chess.com avec Chromium.")

    try:
        # La fonction retourne maintenant le PGN et le chemin de la vidéo
        pgn, video_path = await get_pgn_from_chess_com(url, CHESS_USERNAME, CHESS_PASSWORD)
        
        # On stocke le chemin de la vidéo pour la commande !cam
        if video_path:
            last_video_paths[ctx.channel.id] = video_path
        
        pgn_short = (pgn[:1900] + "...") if len(pgn) > 1900 else pgn
        await msg.edit(content=f"✅ **PGN récupéré avec succès !**\n```\n{pgn_short}\n```\n*Utilisez `!cam` pour voir la vidéo de l'opération.*")

    except ScrapingError as e:
        await msg.edit(content=f"❌ **Erreur lors de la récupération du PGN.**")
        
        # On stocke le chemin de la vidéo même en cas d'erreur
        if e.video_path:
            last_video_paths[ctx.channel.id] = e.video_path
        
        files_to_send = [discord.File(io.BytesIO(e.screenshot_bytes), filename="debug_screenshot.png")] if e.screenshot_bytes else []

        if files_to_send:
            await ctx.send(f"**Erreur de scraping :** {e}", files=files_to_send)
        else:
            await ctx.send(f"**Erreur de scraping :** {e}")

        if e.video_path:
            await ctx.send(f"Utilisez `!cam` pour voir la vidéo de la session qui a échoué.")
            
    except Exception as e:
        await msg.edit(content=f"❌ Une erreur système imprévue est survenue : {e}")

@bot.command(name="cam")
async def send_last_video(ctx):
    """Envoie la vidéo de la dernière opération de scraping."""
    video_path_str = last_video_paths.get(ctx.channel.id)
    
    if not video_path_str:
        await ctx.send("❌ Aucune vidéo récente n'a été trouvée pour ce salon.")
        return

    video_file = Path(video_path_str)
    if video_file.exists():
        file_size = video_file.stat().st_size
        if file_size < DISCORD_FILE_LIMIT_BYTES:
            await ctx.send(f"📹 Voici la vidéo de la dernière opération `!chess` :", file=discord.File(str(video_file), filename="debug_video.webm"))
        else:
            await ctx.send(f"📹 La dernière vidéo a été enregistrée mais est trop lourde ({file_size / 1_000_000:.2f} Mo) pour être envoyée sur Discord.")
    else:
        await ctx.send("❌ Le fichier de la dernière vidéo semble avoir été supprimé ou est introuvable.")


# ... (copiez ici les autres commandes : motcle, tchat, stop, ping)
@bot.command(name="motcle")
@commands.has_permissions(administrator=True)
async def watch_keyword(ctx, streamer: str, *, keyword: str):
    if hasattr(bot, 'twitch_bot'):
        await bot.twitch_bot.start_keyword_watch(streamer, keyword, ctx.channel)
        await ctx.send(f"✅ Surveillance activée pour le mot-clé **`{keyword}`** sur la chaîne Twitch de **`{streamer}`**.")
@bot.command(name="tchat")
@commands.has_permissions(administrator=True)
async def mirror_chat(ctx, streamer: str):
    if hasattr(bot, 'twitch_bot'):
        await bot.twitch_bot.start_mirror(streamer, ctx.channel)
        await ctx.send(f"✅ Mode miroir activé pour le tchat de **`{streamer}`**.")
@bot.command(name="stop")
@commands.has_permissions(administrator=True)
async def stop_twitch_watch(ctx):
    if hasattr(bot, 'twitch_bot'):
        await bot.twitch_bot.stop_task()
        await ctx.send("🛑 Surveillance Twitch arrêtée.")
@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(f"Pong! Latence : {round(bot.latency * 1000)}ms")


# --- ÉVÉNEMENTS DISCORD ---
@bot.event
async def on_ready():
    print(f"Bot Discord connecté en tant que {bot.user} !")

# --- LANCEMENT CONCURRENT DES BOTS ---
async def main():
    twitch_bot_instance = WatcherBot(bot)
    bot.twitch_bot = twitch_bot_instance
    await asyncio.gather(bot.start(DISCORD_TOKEN), twitch_bot_instance.start())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nArrêt du bot demandé.")
