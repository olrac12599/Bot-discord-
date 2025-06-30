# --- IMPORTS ---
import discord
from discord.ext import commands
from twitchio.ext import commands as twitch_commands
import os
import asyncio
from enum import Enum, auto
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_TOKEN = os.getenv("TWITCH_TOKEN")
TTV_BOT_NICKNAME = os.getenv("TTV_BOT_NICKNAME")
TTV_BOT_TOKEN = os.getenv("TTV_BOT_TOKEN")
# NOUVELLES VARIABLES POUR LA CONNEXION À CHESS.COM
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")

if not all([DISCORD_TOKEN, TWITCH_CLIENT_ID, TWITCH_TOKEN, TTV_BOT_NICKNAME, TTV_BOT_TOKEN]):
    raise ValueError("ERREUR CRITIQUE: Variables d'environnement Twitch/Discord manquantes.")
if not all([CHESS_USERNAME, CHESS_PASSWORD]):
    raise ValueError("ERREUR CRITIQUE: CHESS_USERNAME et CHESS_PASSWORD doivent être définis dans les variables d'environnement.")

# --- INIT BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# --- FONCTION DE SCRAPING AVEC CONNEXION ---
async def get_pgn_from_chess_com(url: str, username: str, password: str) -> str:
    """
    Se connecte à Chess.com PUIS navigue vers la partie pour extraire le PGN.
    """
    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=True)
        page = await browser.new_page()
        try:
            # ETAPE 1 : CONNEXION
            print("Tentative de connexion à Chess.com...")
            await page.goto("https://www.chess.com/login_and_go", timeout=90000)
            
            # Remplir les champs de connexion
            # Ces sélecteurs sont standards mais peuvent changer
            await page.fill("#username", username)
            await page.fill("#password", password)
            
            # Cliquer sur le bouton de connexion
            await page.click("button#login")
            
            # Attendre que la connexion soit effective (attendre la navigation vers la page d'accueil)
            await page.wait_for_url("https://www.chess.com/home", timeout=60000)
            print("Connexion réussie !")

            # ETAPE 2 : ALLER À LA PARTIE
            print(f"Navigation vers l'URL de la partie : {url}")
            await page.goto(url, timeout=90000)

            # ETAPE 3 : EXTRAIRE LE PGN (logique précédente)
            share_button_selector = ".icon-font-chess.share"
            await page.wait_for_selector(share_button_selector, timeout=30000)
            await page.click(share_button_selector)

            pgn_tab_selector = 'div.share-menu-tab-component-header:has-text("PGN")'
            await page.wait_for_selector(pgn_tab_selector, timeout=20000)
            await page.click(pgn_tab_selector)
            
            pgn_content_selector = 'textarea.share-menu-tab-pgn-textarea'
            await page.wait_for_selector(pgn_content_selector, timeout=20000)
            pgn_text = await page.input_value(pgn_content_selector)
            
            await browser.close()
            return pgn_text

        except Exception as e:
            screenshot_path = "debug_screenshot.png"
            await page.screenshot(path=screenshot_path)
            print(f"ERREUR: Capture d'écran de débogage sauvegardée dans '{screenshot_path}'")
            await browser.close()
            raise RuntimeError(f"Une erreur est survenue pendant la connexion ou la récupération. Vérifiez les identifiants ou le site. Détails : {e}")


# --- CLASSE BOT TWITCH (INCHANGÉE) ---
class WatcherMode(Enum):
    # ... (code identique)
    IDLE = auto()
    KEYWORD = auto()
    MIRROR = auto()
class WatcherBot(twitch_commands.Bot):
    # ... (code identique)
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
async def get_chess_pgn(ctx, url: str):
    if not ("chess.com/game/live/" in url or "chess.com/play/game/" in url):
        await ctx.send("❌ URL invalide. Veuillez fournir une URL de partie live de Chess.com.")
        return
    
    msg = await ctx.send("🌐 Connexion à Chess.com et récupération du PGN en cours... (peut prendre jusqu'à 2 minutes)")
    try:
        # On passe maintenant les identifiants à la fonction
        pgn = await get_pgn_from_chess_com(url, CHESS_USERNAME, CHESS_PASSWORD)
        
        if len(pgn) > 1900:
            pgn_short = pgn[:1900] + "..."
        else:
            pgn_short = pgn
            
        await msg.edit(content=f"✅ PGN récupéré avec succès !\n```\n{pgn_short}\n```")
    except Exception as e:
        await msg.edit(content=f"❌ Erreur lors de la récupération du PGN : {e}")

# ... (Les autres commandes Discord restent identiques)
@bot.command(name="motcle")
@commands.has_permissions(administrator=True)
async def watch_keyword(ctx, streamer: str, *, keyword: str):
    if hasattr(bot, 'twitch_bot'):
        await bot.twitch_bot.start_keyword_watch(streamer, keyword, ctx.channel)
        await ctx.send(f"🔍 Mot-clé **{keyword}** sur la chaîne de **{streamer}** surveillé.")
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

