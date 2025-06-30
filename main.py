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

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_TOKEN = os.getenv("TWITCH_TOKEN")
TTV_BOT_NICKNAME = os.getenv("TTV_BOT_NICKNAME")
TTV_BOT_TOKEN = os.getenv("TTV_BOT_TOKEN")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")
DISCORD_FILE_LIMIT_BYTES = 8 * 1024 * 1024

if not all([DISCORD_TOKEN, TWITCH_CLIENT_ID, TWITCH_TOKEN, TTV_BOT_NICKNAME, TTV_BOT_TOKEN]):
    raise ValueError("ERREUR CRITIQUE: Variables d'environnement Twitch/Discord manquantes.")
if not all([CHESS_USERNAME, CHESS_PASSWORD]):
    raise ValueError("ERREUR CRITIQUE: CHESS_USERNAME et CHESS_PASSWORD doivent être définis.")

# --- INIT BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# --- EXCEPTION PERSONNALISÉE ---
class ScrapingError(Exception):
    def __init__(self, message, screenshot_bytes=None):
        super().__init__(message)
        self.screenshot_bytes = screenshot_bytes


# --- FONCTION DE SCRAPING ENCORE AMÉLIORÉE ---
async def get_pgn_from_chess_com(url: str, username: str, password: str) -> str:
    """
    Utilise une méthode de sélection robuste ("get_by_label") pour la connexion.
    """
    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=True)
        page = await browser.new_page()
        try:
            print("Navigation vers la page de connexion...")
            await page.goto("https://www.chess.com/login_and_go", timeout=90000)
            
            try:
                print("Vérification de la présence de la bannière de cookies...")
                accept_button = page.get_by_role("button", name="I Accept")
                await accept_button.wait_for(state="visible", timeout=10000)
                print("Bannière trouvée. Clic sur 'I Accept'...")
                await accept_button.click()
                print("Cookies acceptés.")
                await page.wait_for_timeout(1000) 
            except PlaywrightTimeoutError:
                print("Aucune bannière de cookies détectée, on continue.")
            
            # --- MODIFICATION CLÉ : ON UTILISE get_by_label ---
            # Cette méthode est beaucoup plus fiable car elle imite un utilisateur
            # qui cherche un champ à côté d'un texte spécifique.
            # Elle attend automatiquement que l'élément soit visible et cliquable.
            
            print("Remplissage du champ 'username' via son label...")
            await page.get_by_label("Username, Phone, or Email").fill(username)
            
            print("Remplissage du champ 'password' via son label...")
            await page.get_by_label("Password").fill(password)
            
            print("Clic sur le bouton de connexion...")
            # On cible le bouton par son rôle et son nom visible pour plus de fiabilité
            await page.get_by_role("button", name="Log In").click()
            
            print("Attente de la redirection après connexion...")
            await page.wait_for_url("https://www.chess.com/home", timeout=60000)
            print("Connexion réussie !")

            print(f"Navigation vers l'URL de la partie : {url}")
            await page.goto(url, timeout=90000)

            share_button_selector = ".icon-font-chess.share"
            await page.wait_for_selector(share_button_selector, state="visible", timeout=30000)
            await page.click(share_button_selector)

            pgn_tab_selector = 'div.share-menu-tab-component-header:has-text("PGN")'
            await page.wait_for_selector(pgn_tab_selector, state="visible", timeout=20000)
            await page.click(pgn_tab_selector)
            
            pgn_content_selector = 'textarea.share-menu-tab-pgn-textarea'
            await page.wait_for_selector(pgn_content_selector, state="visible", timeout=20000)
            pgn_text = await page.input_value(pgn_content_selector)
            
            await browser.close()
            return pgn_text

        except Exception as e:
            print(f"ERREUR: Une erreur de scraping est survenue. Prise de la capture d'écran...")
            screenshot_bytes = await page.screenshot(full_page=True)
            await browser.close()
            raise ScrapingError(f"Détails: {e}", screenshot_bytes=screenshot_bytes)


# --- CLASSE BOT TWITCH (INCHANGÉE) ---
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
        if message.echo or self.mode == WatcherMode.IDLE: return
        if self.mode == WatcherMode.KEYWORD:
            if self.keyword_to_watch.lower() in message.content.lower():
                embed = discord.Embed(title="🚨 Mot-Clé Twitch détecté !", description=message.content, color=discord.Color.orange())
                embed.set_footer(text=f"Chaîne : {message.channel.name} | Auteur : {message.author.name}")
                await self.target_discord_channel.send(embed=embed)
        elif self.mode == WatcherMode.MIRROR:
            msg = f"**{message.author.name}**: {message.content}"
            await self.target_discord_channel.send(msg[:2000])


# --- COMMANDES DISCORD (INCHANGÉES) ---
@bot.command(name="chess")
async def get_chess_pgn(ctx, url: str):
    if not ("chess.com/game/live/" in url or "chess.com/play/game/" in url):
        await ctx.send("❌ URL invalide. L'URL doit pointer vers une partie live ou archivée sur chess.com.")
        return
        
    msg = await ctx.send("🌐 Lancement du scraping... Connexion à Chess.com en cours...")
    
    try:
        pgn = await get_pgn_from_chess_com(url, CHESS_USERNAME, CHESS_PASSWORD)
        
        if len(pgn) > 1900:
            pgn_short = pgn[:1900] + "..."
        else:
            pgn_short = pgn
            
        await msg.edit(content=f"✅ PGN récupéré !\n```\n{pgn_short}\n```")

    except ScrapingError as e:
        await msg.edit(content=f"❌ Erreur lors de la récupération du PGN. Une capture d'écran de l'erreur est en cours de traitement...")
        
        if e.screenshot_bytes:
            image_bytes = e.screenshot_bytes
            filename = "debug_screenshot.png"
            
            if len(image_bytes) > DISCORD_FILE_LIMIT_BYTES:
                await ctx.send(f"⚠️ La capture d'écran est trop lourde ({len(image_bytes) / 1_000_000:.2f} Mo). Compression en cours...")
                
                img = Image.open(io.BytesIO(image_bytes))
                output_buffer = io.BytesIO()
                img.convert("RGB").save(output_buffer, format="JPEG", quality=85, optimize=True)
                image_bytes = output_buffer.getvalue()
                filename = "debug_screenshot_compressed.jpg"

            await ctx.send(
                content=f"❌ **Erreur de scraping :** {e}",
                file=discord.File(io.BytesIO(image_bytes), filename=filename)
            )
        else:
            await ctx.send(f"❌ **Erreur de scraping :** {e} (aucune capture d'écran disponible).")
            
    except Exception as e:
        await msg.edit(content=f"❌ Une erreur imprévue est survenue : {e}")


@bot.command(name="motcle")
@commands.has_permissions(administrator=True)
async def watch_keyword(ctx, streamer: str, *, keyword: str):
    if hasattr(bot, 'twitch_bot'): await bot.twitch_bot.start_keyword_watch(streamer, keyword, ctx.channel); await ctx.send(f"🔍 Mot-clé **{keyword}** sur **{streamer}** surveillé.")
@bot.command(name="tchat")
@commands.has_permissions(administrator=True)
async def mirror_chat(ctx, streamer: str):
    if hasattr(bot, 'twitch_bot'): await bot.twitch_bot.start_mirror(streamer, ctx.channel); await ctx.send(f"🪞 Miroir du tchat de **{streamer}** activé.")
@bot.command(name="stop")
@commands.has_permissions(administrator=True)
async def stop_twitch_watch(ctx):
    if hasattr(bot, 'twitch_bot'): await bot.twitch_bot.stop_task(); await ctx.send("🛑 Surveillance Twitch arrêtée.")
@bot.command(name="ping")
async def ping(ctx): await ctx.send("Pong!")


# --- ÉVÉNEMENTS ---
@bot.event
async def on_ready(): print(f"Bot Discord connecté en tant que {bot.user} !")

# --- LANCEMENT ---
async def main():
    twitch_bot_instance = WatcherBot(bot)
    bot.twitch_bot = twitch_bot_instance
    await asyncio.gather(bot.start(DISCORD_TOKEN), twitch_bot_instance.start())

if __name__ == "__main__":
    asyncio.run(main())

