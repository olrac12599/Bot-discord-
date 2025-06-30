# --- IMPORTS ---
import discord
from discord.ext import commands
from twitchio.ext import commands as twitch_commands
import os
import asyncio
from enum import Enum, auto
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth
import io
from pathlib import Path
from stockfish import Stockfish
import chess.pgn

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TTV_BOT_TOKEN = os.getenv("TTV_BOT_TOKEN")
TTV_BOT_NICKNAME = os.getenv("TTV_BOT_NICKNAME")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")
DISCORD_FILE_LIMIT_BYTES = 8 * 1024 * 1024
STOCKFISH_PATH = "/usr/games/stockfish"  # À adapter si besoin (ex: "stockfish" si dans le PATH)

if not all([DISCORD_TOKEN, TTV_BOT_NICKNAME, TTV_BOT_TOKEN]):
    raise ValueError("Variables d'environnement Discord/Twitch manquantes. Vérifiez DISCORD_TOKEN, TTV_BOT_NICKNAME, TTV_BOT_TOKEN.")
if not all([CHESS_USERNAME, CHESS_PASSWORD]):
    raise ValueError("CHESS_USERNAME et CHESS_PASSWORD requis. Vérifiez CHESS_USERNAME, CHESS_PASSWORD.")

# --- INITIALISATION DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
last_video_paths = {}

# --- ERREUR CUSTOM ---
class ScrapingError(Exception):
    """Exception personnalisée pour les erreurs de scraping avec capture d'écran et vidéo."""
    def __init__(self, message, screenshot_bytes=None, video_path=None):
        super().__init__(message)
        self.screenshot_bytes = screenshot_bytes
        self.video_path = video_path

# --- SIMULACRE D'IA : OBSERVATEUR ET RÉSOLVEUR DE BLOCAGES ---
async def handle_potential_blockers(page, context_description=""):
    """
    Tente de détecter et de gérer les pop-ups ou éléments bloquants courants.
    Ceci simule une "intelligence" qui essaie de comprendre la page.
    """
    print(f"[{context_description}] AI-like blocker handler: Checking for common pop-ups...")

    # Tenter de gérer les pop-ups de consentement aux cookies
    try:
        accept_cookies_button = page.locator('button:has-text("I Accept"), button:has-text("J\'accepte"), button[aria-label="Accept cookies"], a[href*="cookie-policy"] >> xpath=.. >> button:has-text("Accept")')
        if await accept_cookies_button.is_visible(timeout=3000): # Timeout plus court pour ne pas bloquer
            print(f"[{context_description}] Found cookie consent pop-up. Clicking 'Accept'.")
            await accept_cookies_button.click()
            await asyncio.sleep(1) # Petit délai pour que le pop-up disparaisse
            return True # Blocage géré
    except PlaywrightTimeoutError:
        pass # Pas de pop-up de cookies trouvé dans ce délai
    except Exception as e:
        print(f"[{context_description}] Error handling cookie pop-up: {e}")

    # Tenter de gérer les pop-ups de newsletter ou autres modales génériques
    try:
        # Cherche un bouton de fermeture (X) ou un bouton "No Thanks", "Later"
        close_button = page.locator('button[aria-label="close"], button:has-text("No Thanks"), button:has-text("Not now"), .modal-close-button, .close-button')
        if await close_button.is_visible(timeout=2000):
            print(f"[{context_description}] Found generic pop-up. Clicking close/dismiss button.")
            await close_button.click()
            await asyncio.sleep(1)
            return True # Blocage géré
    except PlaywrightTimeoutError:
        pass
    except Exception as e:
        print(f"[{context_description}] Error handling generic pop-up: {e}")

    # Autres vérifications spécifiques à Chess.com ou autres sites
    # Exemple: Si Chess.com affiche un pop-up "Bienvenue", "Nouvelle fonctionnalité", etc.
    try:
        welcome_modal_close = page.locator('.modal-dialog:has-text("Welcome to Chess.com") button[aria-label="close"], .modal-dialog:has-text("New Feature") button[aria-label="close"]')
        if await welcome_modal_close.is_visible(timeout=1000):
            print(f"[{context_description}] Found Chess.com specific welcome/feature pop-up. Closing it.")
            await welcome_modal_close.click()
            await asyncio.sleep(1)
            return True
    except PlaywrightTimeoutError:
        pass
    except Exception as e:
        print(f"[{context_description}] Error handling Chess.com specific pop-up: {e}")

    print(f"[{context_description}] No known blockers detected.")
    return False # Aucun blocage connu n'a été géré

# --- PGN SCRAPER ---
async def get_pgn_from_chess_com(url: str, username: str, password: str):
    videos_dir = Path("debug_videos")
    videos_dir.mkdir(exist_ok=True)
    stealth = Stealth()
    browser_args = ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']

    async with stealth.use_async(async_playwright()) as p:
        browser = await p.chromium.launch(headless=True, args=browser_args)
        context = await browser.new_context(
            record_video_dir=str(videos_dir),
            record_video_size={"width": 1280, "height": 720},
            base_url="https://www.chess.com"
        )
        page = await context.new_page()

        try:
            # Naviguer à la page de connexion
            print("Navigating to login page...")
            await page.goto("/login_and_go", timeout=90000)

            # --- DÉBUT DE L'INTERVENTION DE L'IA ---
            # Attendre un court instant après le chargement initial au cas où un pop-up apparaît immédiatement
            await asyncio.sleep(2) # Attente initiale pour les popups immédiats

            # Tenter de gérer les bloqueurs avant la connexion
            await handle_potential_blockers(page, "Before Login Attempt")

            # Attendre les 5 secondes demandées avant la connexion
            print("Waiting 5 seconds before login action...")
            await asyncio.sleep(5)

            login_successful = False
            for attempt in range(3): # Tenter la connexion plusieurs fois en cas de blocage
                print(f"Login attempt {attempt + 1}...")
                try:
                    # Tenter d'entrer les identifiants et de cliquer sur le bouton de connexion
                    # Utilisez force=True pour éviter les problèmes de "element not interactable" si un overlay temporaire est là
                    await page.get_by_placeholder("Username, Phone, or Email").fill(username)
                    await page.get_by_placeholder("Password").fill(password)
                    await page.get_by_role("button", name="Log In").click()
                    
                    # Attendre que l'URL de la page d'accueil soit chargée après la connexion
                    await page.wait_for_url("**/home", timeout=15000)
                    print("Login successful.")
                    login_successful = True
                    break # Sortir de la boucle si la connexion est réussie
                except PlaywrightTimeoutError as e:
                    print(f"Login attempt {attempt + 1} failed (timeout): {e}. Checking for blockers...")
                    # Si la connexion échoue, demander à l'IA de vérifier les bloqueurs
                    blocker_handled = await handle_potential_blockers(page, f"After Login Fail (Attempt {attempt + 1})")
                    if not blocker_handled:
                        print(f"No known blocker handled after failed login attempt {attempt + 1}. Retrying...")
                    # Attendre un peu avant de retenter
                    await asyncio.sleep(3)
                except Exception as e:
                    print(f"An unexpected error occurred during login attempt {attempt + 1}: {e}. Retrying...")
                    await asyncio.sleep(3) # Attendre avant de retenter

            if not login_successful:
                raise ScrapingError("Failed to log in to Chess.com after multiple attempts.")
            # --- FIN DE L'INTERVENTION DE L'IA ---

            # Naviguer vers l'URL du jeu spécifique
            print(f"Navigating to game URL: {url}")
            await page.goto(url, timeout=90000)

            # Gérer d'éventuels bloqueurs après la navigation vers le jeu (ex: pop-ups spécifiques au jeu)
            await handle_potential_blockers(page, "After Game Page Load")

            # Cliquer sur le bouton de partage et l'onglet PGN
            print("Clicking share button and PGN tab...")
            await page.locator("button.share-button-component").click()
            await page.locator('div.share-menu-tab-component-header:has-text("PGN")').click()

            # Récupérer le texte PGN de la zone de texte
            print("Extracting PGN text...")
            pgn_text = await page.input_value('textarea.share-menu-tab-pgn-textarea')
            print("PGN extracted.")

            video_path = await page.video.path()
            await context.close()
            await browser.close()
            return pgn_text, video_path

        except Exception as e:
            screenshot_bytes, video_path = None, None
            try:
                if not page.is_closed():
                    screenshot_bytes = await page.screenshot(full_page=True)
                video_path = await page.video.path()
            except Exception as debug_e:
                print(f"Error during debug data collection: {debug_e}")
            finally:
                await context.close()
                await browser.close()
            raise ScrapingError(f"Scraping failed: {e}", screenshot_bytes, video_path)

# --- STOCKFISH ANALYSE ---
def analyse_pgn_with_stockfish(pgn_text):
    try:
        stockfish = Stockfish(path=STOCKFISH_PATH)
    except FileNotFoundError:
        print(f"ERREUR: Stockfish non trouvé à l'emplacement '{STOCKFISH_PATH}'.")
        print("Assurez-vous que Stockfish est installé et que le chemin est correct.")
        return ["Erreur: Stockfish introuvable pour l'analyse."]

    stockfish.set_skill_level(20)
    stockfish.set_depth(15)

    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        return ["Erreur: Impossible de lire le PGN. Le format est-il correct ?"]

    board = game.board()
    annotations = []

    for move in game.mainline_moves():
        stockfish.set_fen_position(board.fen())
        best_move_stockfish = stockfish.get_best_move()
        
        stockfish.set_fen_position(board.fen())
        stockfish.make_moves_from_current_position([best_move_stockfish])
        best_eval = stockfish.get_evaluation()

        stockfish.set_fen_position(board.fen())
        stockfish.make_moves_from_current_position([move.uci()])
        played_eval = stockfish.get_evaluation()

        delta = 0
        if best_eval['type'] == 'cp' and played_eval['type'] == 'cp':
            delta = played_eval['value'] - best_eval['value']
        elif best_eval['type'] == 'mate' or played_eval['type'] == 'mate':
            delta = 1000

        verdict = ""
        if best_move_stockfish == move.uci():
            verdict = "théorique (coup parfait!)"
        elif abs(delta) < 50:
            verdict = "acceptable"
        elif abs(delta) < 150:
            verdict = "imprécision"
        elif abs(delta) < 300:
            verdict = "erreur"
        else:
            verdict = "blunder (énorme gaffe!)"

        color = "Blanc" if board.turn == chess.BLACK else "Noir"
        annotations.append(f"{color} joue {board.san(move)} : {verdict}")
        board.push(move)

    return annotations

# --- DISCORD COMMANDES ---
@bot.command(name="chess")
async def get_chess_pgn(ctx, url: str):
    if "chess.com/game/live/" not in url and "chess.com/play/game/" not in url:
        return await ctx.send("❌ URL invalide. Veuillez fournir une URL de partie Chess.com valide (ex: `https://www.chess.com/game/live/...` ou `https://www.chess.com/play/game/...`).")
    
    msg = await ctx.send("🕵️ Connexion Chess.com et récupération du PGN en cours... Cela peut prendre un moment.")
    try:
        pgn, video_path = await get_pgn_from_chess_com(url, CHESS_USERNAME, CHESS_PASSWORD)
        if video_path:
            last_video_paths[ctx.channel.id] = video_path
        
        await msg.edit(content="✅ PGN récupéré. Analyse de la partie avec Stockfish en cours...")
        annotations = analyse_pgn_with_stockfish(pgn)
        
        response = "\n".join(annotations)
        if len(response) > 2000:
            chunks = [response[i:i + 2000] for i in range(0, len(response), 2000)]
            for chunk in chunks:
                await ctx.send(chunk)
        else:
            await ctx.send(response)
        
        await msg.edit(content=f"✅ Analyse terminée pour la partie. Utilisez `!cam` si le bot a rencontré un problème pour voir la vidéo de débogage.")

    except ScrapingError as e:
        await msg.edit(content=f"❌ Échec lors du scraping de la partie Chess.com: {e.args[0]}")
        if e.video_path:
            last_video_paths[ctx.channel.id] = e.video_path
            await ctx.send("📹 Une vidéo de débogage est disponible. Utilisez `!cam` pour la voir.")
        if e.screenshot_bytes:
            await ctx.send("📸 Capture d'écran de l'erreur :", file=discord.File(io.BytesIO(e.screenshot_bytes), "debug_screenshot.png"))
        print(f"Scraping Error: {e.args[0]}")
    except Exception as e:
        await msg.edit(content=f"❌ Une erreur inattendue est survenue: {e}")
        print(f"Unexpected Error: {e}")

@bot.command(name="cam")
async def send_last_video(ctx):
    video_path = last_video_paths.get(ctx.channel.id)
    if not video_path:
        return await ctx.send("❌ Aucune vidéo de débogage trouvée pour ce canal. Exécutez `!chess` d'abord.")
    
    video_file = Path(video_path)
    if not video_file.exists():
        return await ctx.send("❌ Le fichier vidéo n'existe plus ou a été déplacé.")
    
    if video_file.stat().st_size < DISCORD_FILE_LIMIT_BYTES:
        try:
            await ctx.send("📹 Voici la dernière vidéo de débogage :", file=discord.File(str(video_file), "debug_video.webm"))
        except discord.HTTPException as http_exc:
            await ctx.send(f"❌ Impossible d'envoyer la vidéo: {http_exc}. Elle est peut-être trop lourde ou corrompue.")
    else:
        await ctx.send(f"📹 La vidéo de débogage est trop lourde pour être envoyée sur Discord "
                       f"({video_file.stat().st_size / (1024 * 1024):.2f} Mo). "
                       "La limite est de 8 Mo.")

# --- TWITCH MIRROR OPTIONNEL ---
class WatcherMode(Enum):
    IDLE = auto()
    KEYWORD = auto()
    MIRROR = auto()

class WatcherBot(twitch_commands.Bot):
    def __init__(self, discord_bot):
        super().__init__(token=TTV_BOT_TOKEN, prefix="!", initial_channels=[])
        self.discord_bot = discord_bot
        self.mode = WatcherMode.IDLE
        self.current_channel_name = None
        self.target_discord_channel = None
        self.keyword_to_watch = None

    async def event_ready(self):
        print(f"Twitch bot '{TTV_BOT_NICKNAME}' connecté et prêt.")

    async def event_message(self, message):
        if message.echo or self.mode == WatcherMode.IDLE:
            return

        author = message.author.name if message.author else "Inconnu"
        
        if self.mode == WatcherMode.KEYWORD:
            if self.keyword_to_watch and self.keyword_to_watch.lower() in message.content.lower():
                embed = discord.Embed(title="Mot-Clé détecté sur Twitch", description=message.content, color=discord.Color.orange())
                embed.set_footer(text=f"Chaîne: {message.channel.name} | Auteur: {author}")
                await self.target_discord_channel.send(embed=embed)
        elif self.mode == WatcherMode.MIRROR:
            await self.target_discord_channel.send(f"**{author}** ({message.channel.name}): {message.content}"[:2000])
        
        await self.handle_commands(message)

    async def stop_task(self):
        if self.current_channel_name:
            print(f"Leaving Twitch channel: {self.current_channel_name}")
            await self.part_channels([self.current_channel_name])
        self.mode = WatcherMode.IDLE
        self.current_channel_name = None
        self.target_discord_channel = None
        self.keyword_to_watch = None
        print("Twitch watch/mirror task stopped.")

    async def start_keyword_watch(self, channel: str, keyword: str, discord_channel: discord.TextChannel):
        await self.stop_task()
        self.mode = WatcherMode.KEYWORD
        self.keyword_to_watch = keyword
        self.target_discord_channel = discord_channel
        self.current_channel_name = channel.lower()
        print(f"Joining Twitch channel {self.current_channel_name} for keyword '{keyword}' watch.")
        await self.join_channels([self.current_channel_name])

    async def start_mirror(self, channel: str, discord_channel: discord.TextChannel):
        await self.stop_task()
        self.mode = WatcherMode.MIRROR
        self.target_discord_channel = discord_channel
        self.current_channel_name = channel.lower()
        print(f"Joining Twitch channel {self.current_channel_name} for chat mirror.")
        await self.join_channels([self.current_channel_name])

@bot.command(name="motcle")
@commands.has_permissions(administrator=True)
async def watch_keyword(ctx, streamer: str, *, keyword: str):
    if not streamer or not keyword:
        return await ctx.send("❌ Utilisation: `!motcle <nom_du_streamer> <mot_cle>`")
    await bot.twitch_bot.start_keyword_watch(streamer, keyword, ctx.channel)
    await ctx.send(f"🔍 Mot-clé `{keyword}` surveillé sur le chat de `{streamer}`. Les détections seront envoyées ici.")

@bot.command(name="tchat")
@commands.has_permissions(administrator=True)
async def mirror_chat(ctx, streamer: str):
    if not streamer:
        return await ctx.send("❌ Utilisation: `!tchat <nom_du_streamer>`")
    await bot.twitch_bot.start_mirror(streamer, ctx.channel)
    await ctx.send(f"💬 Miroir activé sur le tchat de `{streamer}`.")

@bot.command(name="stop")
@commands.has_permissions(administrator=True)
async def stop_watch(ctx):
    await bot.twitch_bot.stop_task()
    await ctx.send("🛑 Surveillance Twitch stoppée.")

@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(f"Pong! Latence : {round(bot.latency * 1000)}ms")

@bot.event
async def on_ready():
    print(f"Bot Discord connecté en tant que {bot.user} (ID: {bot.user.id})")
    print(f"Version de Discord.py : {discord.__version__}")
    print("Prêt à recevoir des commandes !")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Il manque un argument. Utilisation correcte : `{ctx.command.signature}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Mauvais argument fourni. Vérifiez votre saisie.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    elif isinstance(error, commands.CheckFailure):
        await ctx.send("🚫 Vous n'avez pas la permission d'utiliser cette commande.")
    else:
        print(f"Erreur inattendue dans la commande {ctx.command}: {error}")
        await ctx.send(f"❌ Une erreur inattendue est survenue lors de l'exécution de la commande.")

async def main():
    twitch_bot = WatcherBot(bot)
    bot.twitch_bot = twitch_bot
    
    await asyncio.gather(
        bot.start(DISCORD_TOKEN),
        twitch_bot.start()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bots stoppés par l'utilisateur (Ctrl+C).")
    except Exception as e:
        print(f"Une erreur fatale est survenue: {e}")
