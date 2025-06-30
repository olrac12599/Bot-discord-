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

if not all([DISCORD_TOKEN, TWITCH_CLIENT_ID, TWITCH_TOKEN, TTV_BOT_NICKNAME, TTV_BOT_TOKEN]):
    raise ValueError("ERREUR CRITIQUE: Variables d'environnement manquantes.")

# --- INIT BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# --- NOUVELLE FONCTION DE SCRAPING CHESS.COM ---
async def get_pgn_from_chess_com(url: str) -> str:
    """
    Utilise Playwright pour lancer un navigateur, aller sur une URL de partie Chess.com,
    et extraire le PGN via les boutons de la page.
    ATTENTION : Très fragile. Cassera si Chess.com change son site.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        try:
            # Naviguer vers l'URL de la partie
            await page.goto(url, timeout=60000)

            # Tenter de fermer la fenêtre de "consentement aux cookies" si elle existe
            try:
                # Ce sélecteur cible le bouton "Accepter" ou similaire. Il devra peut-être être ajusté.
                await page.click('button[aria-label="Consent"], button:has-text("Agree")', timeout=5000)
            except PlaywrightTimeoutError:
                # Le bouton n'était pas là, on continue
                print("Pas de bannière de cookies détectée ou déjà acceptée.")

            # Cliquer sur l'icône de partage
            # Le sélecteur cible le bouton avec une classe "share-menu-icon". C'est fragile.
            share_button_selector = ".icon-font-chess.share"
            await page.wait_for_selector(share_button_selector, timeout=15000)
            await page.click(share_button_selector)

            # Cliquer sur l'onglet PGN dans le menu qui vient de s'ouvrir
            # Le sélecteur cible un onglet qui contient le texte "PGN"
            pgn_tab_selector = 'div.share-menu-tab-component-header:has-text("PGN")'
            await page.wait_for_selector(pgn_tab_selector, timeout=10000)
            await page.click(pgn_tab_selector)
            
            # Récupérer le contenu du PGN
            # Le sélecteur cible la zone de texte contenant le PGN
            pgn_content_selector = 'textarea.share-menu-tab-pgn-textarea'
            await page.wait_for_selector(pgn_content_selector, timeout=10000)
            pgn_text = await page.input_value(pgn_content_selector)
            
            await browser.close()
            return pgn_text

        except PlaywrightTimeoutError as e:
            await browser.close()
            print(f"Erreur de timeout pendant le scraping : {e}")
            raise RuntimeError("Impossible de trouver un élément sur la page (le site a peut-être changé) ou la page est trop lente à charger.")
        except Exception as e:
            await browser.close()
            print(f"Erreur inattendue pendant le scraping : {e}")
            raise RuntimeError(f"Une erreur inattendue est survenue : {e}")

# --- CLASSE BOT TWITCH (INCHANGÉE) ---

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
    if not "chess.com/game/live/" in url:
        await ctx.send("❌ URL invalide. Veuillez fournir une URL de partie live de Chess.com.")
        return
    
    msg = await ctx.send("🌐 Lancement du navigateur et récupération du PGN en cours... (peut prendre jusqu'à 1 minute)")
    try:
        pgn = await get_pgn_from_chess_com(url)
        # Discord a une limite de 2000 caractères par message
        if len(pgn) > 1900:
            pgn_short = pgn[:1900] + "..."
        else:
            pgn_short = pgn
            
        await msg.edit(content=f"✅ PGN récupéré avec succès !\n```\n{pgn_short}\n```")
    except Exception as e:
        await msg.edit(content=f"❌ Erreur lors de la récupération du PGN : {e}")

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
    # Lancement du bot Twitch en arrière-plan
    twitch_bot_instance = WatcherBot(bot)
    bot.twitch_bot = twitch_bot_instance
    
    # Démarrage des deux bots
    await asyncio.gather(
        bot.start(DISCORD_TOKEN),
        twitch_bot_instance.start()
    )

if __name__ == "__main__":
    asyncio.run(main())
