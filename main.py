# --- IMPORTS ---
import discord
from discord.ext import commands
from twitchio.ext import commands as twitch_commands
import os
import asyncio
from enum import Enum, auto
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, Page, BrowserContext
from playwright_stealth import Stealth
import io
from pathlib import Path
from stockfish import Stockfish
import chess.pgn
import logging # Pour une meilleure gestion des logs

# Pour le streaming vidéo
from flask import Flask, Response
import cv2
import subprocess
import numpy as np
import threading
import time
import sys # Pour sys.exit()

# --- CONFIGURATION DES LOGS ---
# Configurez le logging au début du script pour avoir des informations détaillées
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
# Assurez-vous que ces variables d'environnement sont définies sur votre système
# ou sur la plateforme d'hébergement (ex: Railway.app).
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TTV_BOT_TOKEN = os.getenv("TTV_BOT_TOKEN")
TTV_BOT_NICKNAME = os.getenv("TTV_BOT_NICKNAME")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")
DISCORD_FILE_LIMIT_BYTES = 8 * 1024 * 1024 # Limite de taille de fichier Discord (8 Mo)

# Configuration pour Stockfish
# Sur Railway, si Stockfish est installé via le Dockerfile dans /usr/games/, ce chemin est correct.
STOCKFISH_PATH = "/usr/games/stockfish"

# Configuration pour le stream vidéo
# Railway fournira la variable PORT. Il est crucial que Flask écoute sur ce port.
VIDEO_STREAM_PORT = int(os.getenv("PORT", 5000))

# OPTIMISATION MAJEURE: Réduction de la résolution et du FPS pour économiser les ressources.
# C'est la cause la plus fréquente des "Aw, Snap!" sur les hébergeurs partagés.
VIDEO_WIDTH, VIDEO_HEIGHT = 800, 600 # Résolution réduite pour économiser RAM/CPU
FPS = 10 # Images par seconde réduites pour économiser RAM/CPU
DISPLAY_NUM = ":99" # Numéro d'affichage virtuel pour Xvfb (nécessaire sur les serveurs headless)

# Vérification des variables d'environnement critiques au démarrage
if not all([DISCORD_TOKEN, TTV_BOT_NICKNAME, TTV_BOT_TOKEN, CHESS_USERNAME, CHESS_PASSWORD]):
    logger.error("ERREUR: Variables d'environnement DISCORD_TOKEN, TTV_BOT_NICKNAME, TTV_BOT_TOKEN, CHESS_USERNAME ou CHESS_PASSWORD manquantes.")
    logger.error("Veuillez les définir avant de lancer le bot sur Railway.")
    sys.exit(1) # Quitte le programme si les variables sont manquantes

# --- FLASK APP POUR LE STREAM ---
app = Flask(__name__)
video_frame = None # Variable globale pour stocker la frame vidéo la plus récente
video_lock = threading.Lock() # Verrou pour un accès thread-safe à video_frame

@app.route('/video_feed')
def video_feed():
    """
    Route Flask qui sert le flux vidéo MJPEG du navigateur Playwright.
    """
    def generate():
        while True:
            with video_lock:
                if video_frame is not None:
                    (flag, encodedImage) = cv2.imencode(".jpg", video_frame)
                    if not flag:
                        continue
                    yield(b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + bytearray(encodedImage) + b'\r\n')
            time.sleep(1/FPS)

    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

def run_flask_app():
    """
    Démarre l'application Flask sur l'hôte et le port spécifiés.
    Important pour Railway: '0.0.0.0' et le port fourni par l'environnement.
    """
    try:
        app.run(host='0.0.0.0', port=VIDEO_STREAM_PORT, debug=False)
    except Exception as e:
        logger.critical(f"Flask application failed to start: {e}")
        # En cas d'échec critique, on peut choisir de quitter ou de continuer sans le stream
        # Pour un bot, il est souvent préférable de continuer sans le stream si Discord fonctionne.

# --- INITIALISATION DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
last_video_paths = {}

# --- ERREUR CUSTOM ---
class ScrapingError(Exception):
    """
    Exception personnalisée pour les erreurs de scraping, incluant
    des données de débogage comme une capture d'écran et le chemin d'une vidéo.
    """
    def __init__(self, message, screenshot_bytes=None, video_path=None):
        super().__init__(message)
        self.screenshot_bytes = screenshot_bytes
        self.video_path = video_path

# --- SIMULACRE D'IA : OBSERVATEUR ET RÉSOLVEUR DE BLOCAGES ---
async def handle_potential_blockers(page: Page, context_description: str = "") -> bool:
    """
    Tente de détecter et de gérer les pop-ups ou éléments bloquants courants sur une page web.
    Cette fonction est le "cerveau" de l'auto-correction du bot pour les scénarios connus.
    """
    logger.info(f"[{context_description}] AI-like blocker handler: Checking for common pop-ups...")
    handled_any = False

    # --- Stratégie 1 : Tenter de gérer les boutons d'acceptation de cookies ---
    accept_locators = [
        page.get_by_text("I Accept", exact=True),
        page.get_by_role("button", name="I Accept"),
        page.locator('button:has-text("I Accept")'),
        page.get_by_text("J'accepte", exact=True),
        page.get_by_role("button", name="J'accepte"),
        page.locator('button:has-text("J\'accepte")')
    ]

    for i, locator in enumerate(accept_locators):
        try:
            if await locator.is_visible(timeout=2000): # Check if visible quickly
                logger.info(f"[{context_description}] 'I Accept' button found visible with strategy {i+1}. Clicking.")
                await locator.click(force=True, timeout=3000) 
                await asyncio.sleep(2) # Give time for popup to disappear
                handled_any = True
                break # Break after first successful click
        except PlaywrightTimeoutError:
            pass
        except Exception as e_click:
            logger.warning(f"[{context_description}] Error clicking 'I Accept' button with strategy {i+1}: {e_click}")
    if handled_any: return True

    # --- Stratégie 2 : Tenter de gérer les pop-ups de cookies dans des IFRAMES ---
    iframe_selectors = [
        'iframe[title*="Privacy"], iframe[name*="privacy"]',
        'iframe[src*="privacy-policy"], iframe[src*="cookie-consent"]',
        'iframe'
    ]

    for iframe_selector in iframe_selectors:
        try:
            iframe_element = await page.wait_for_selector(iframe_selector, state='attached', timeout=2000)
            if iframe_element:
                iframe = await iframe_element.content_frame()
                if iframe:
                    logger.info(f"[{context_description}] Found potential iframe: {iframe_selector}. Checking for cookie button inside.")
                    try:
                        accept_cookies_button_in_iframe = iframe.locator('button:has-text("I Accept"), button:has-text("J\'accepte"), button[aria-label="Accept cookies"]')
                        if await accept_cookies_button_in_iframe.is_visible(timeout=2000):
                            logger.info(f"[{context_description}] Found 'I Accept' button inside iframe. Clicking.")
                            await accept_cookies_button_in_iframe.click(force=True)
                            await asyncio.sleep(2)
                            handled_any = True
                            break
                    except PlaywrightTimeoutError:
                        pass
                    except Exception as e_iframe_btn:
                        logger.warning(f"[{context_description}] Error clicking button in iframe: {e_iframe_btn}")
        except PlaywrightTimeoutError:
            pass
        except Exception as e_iframe:
            logger.warning(f"[{context_description}] Error locating/accessing iframe {iframe_selector}: {e_iframe}")
    if handled_any: return True


    # --- Stratégie 3 : Gérer les pop-ups génériques de fermeture (ex: newsletters) ---
    try:
        close_button = page.locator('button[aria-label="close"], button:has-text("No Thanks"), button:has-text("Not now"), .modal-close-button, .close-button, div[role="dialog"] >> button:has-text("No Thanks"), .x-button-icon')
        if await close_button.is_visible(timeout=2000):
            logger.info(f"[{context_description}] Found generic pop-up. Clicking close/dismiss button.")
            await close_button.click(force=True)
            await asyncio.sleep(1)
            handled_any = True
    except PlaywrightTimeoutError:
        pass
    except Exception as e:
        logger.warning(f"[{context_description}] Error handling generic pop-up: {e}")
    if handled_any: return True


    # --- Stratégie 4 : Vérifications spécifiques à Chess.com ---
    try:
        welcome_modal_close = page.locator('.modal-dialog:has-text("Welcome to Chess.com") button[aria-label="close"], .modal-dialog:has-text("New Feature") button[aria-label="close"], button.btn-close-x')
        if await welcome_modal_close.is_visible(timeout=1000):
            logger.info(f"[{context_description}] Found Chess.com specific welcome/feature pop-up. Closing it.")
            await welcome_modal_close.click(force=True)
            await asyncio.sleep(1)
            handled_any = True
    except PlaywrightTimeoutError:
        pass
    except Exception as e:
        logger.warning(f"[{context_description}] Error handling Chess.com specific pop-up: {e}")
    if handled_any: return True

    # --- Stratégie 5 : Gérer le message "Aw, Snap!" (priorité: Reload puis Learn more) ---
    # Cette logique est tentée EN DERNIER car un "Aw, Snap!" indique un crash potentiel
    # et une récupération est moins probable que de simples popups.
    try:
        reload_button = page.get_by_role("button", name="Reload", exact=True)
        learn_more_link = page.get_by_text("Learn more", exact=True)

        if await reload_button.is_visible(timeout=1500): # Timeout légèrement réduit
            logger.warning(f"[{context_description}] Detected 'Aw, Snap!' with 'Reload' button. Attempting to click Reload.")
            try:
                await reload_button.click(timeout=1000)
                await asyncio.sleep(5) # Laisser le temps à la page de recharger
                # Après un rechargement, il est ESSENTIEL de retenter de gérer d'autres blockers
                # ou de vérifier l'état de la page. Ici, on appelle à nouveau la fonction.
                await handle_potential_blockers(page, f"{context_description} after 'Reload' attempt")
                return True
            except Exception as reload_e:
                logger.error(f"[{context_description}] Failed to click 'Reload' or subsequent handling failed: {reload_e}")
                # Si le reload échoue, on pourrait alors essayer learn more
                if await learn_more_link.is_visible(timeout=1000):
                    logger.warning(f"[{context_description}] 'Reload' failed, trying 'Learn more' link.")
                    await learn_more_link.click(timeout=1000)
                    await asyncio.sleep(3)
                    return True
        elif await learn_more_link.is_visible(timeout=1000):
            logger.warning(f"[{context_description}] Detected 'Aw, Snap!' with 'Learn more' link. Attempting to click Learn more.")
            await learn_more_link.click(timeout=1000)
            await asyncio.sleep(3)
            return True
    except PlaywrightTimeoutError:
        pass
    except Exception as e:
        logger.error(f"[{context_description}] Error handling 'Aw, Snap!' elements: {e}")

    logger.info(f"[{context_description}] No known blockers or 'Aw, Snap!' elements detected.")
    return False

# --- PGN SCRAPER AVEC STREAMING ---
async def get_pgn_from_chess_com(url: str, username: str, password: str):
    """
    Se connecte à Chess.com, gère les cookies/pop-ups, navigue vers l'URL du jeu,
    extrait le PGN et diffuse l'activité du navigateur en temps réel.
    """
    videos_dir = Path("debug_videos")
    videos_dir.mkdir(exist_ok=True)
    
    xvfb_process = None
    ffmpeg_process = None
    try:
        logger.info(f"Starting Xvfb on display {DISPLAY_NUM}...")
        xvfb_command = ['Xvfb', DISPLAY_NUM, '-screen', '0', f'{VIDEO_WIDTH}x{VIDEO_HEIGHT}x24', '+extension', 'GLX', '+render', '-noreset']
        xvfb_process = subprocess.Popen(xvfb_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await asyncio.sleep(2) # Give Xvfb time to start
        logger.info("Xvfb started successfully.")

        logger.info("Starting FFmpeg to capture Xvfb display...")
        ffmpeg_command = [
            'ffmpeg',
            '-f', 'x11grab',                 # Input format: X11 capture
            '-video_size', f'{VIDEO_WIDTH}x{VIDEO_HEIGHT}', # Capture resolution
            '-i', f'{DISPLAY_NUM}.0',        # Input: Xvfb virtual display
            '-c:v', 'rawvideo',              # Raw video output
            '-pix_fmt', 'bgr24',             # BGR pixel format (OpenCV compatible)
            '-f', 'image2pipe',              # Output to pipe
            '-vsync', '2',                   # Video sync control
            '-r', str(FPS),                  # Capture frame rate
            'pipe:1'                         # Output to stdout
        ]
        ffmpeg_process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        logger.info("FFmpeg capture process started.")

        def read_ffmpeg_output():
            global video_frame 
            bytes_per_frame = VIDEO_WIDTH * VIDEO_HEIGHT * 3
            while True:
                in_bytes = ffmpeg_process.stdout.read(bytes_per_frame)
                if not in_bytes:
                    logger.warning("FFmpeg output stream ended or encountered an error.")
                    break
                
                frame = np.frombuffer(in_bytes, np.uint8).reshape((VIDEO_HEIGHT, VIDEO_WIDTH, 3))
                with video_lock:
                    video_frame = frame
        
        ffmpeg_thread = threading.Thread(target=read_ffmpeg_output)
        ffmpeg_thread.daemon = True
        ffmpeg_thread.start()
        logger.info("FFmpeg frame reader thread started.")

    except Exception as e:
        logger.critical(f"ERREUR: Échec du démarrage de Xvfb/FFmpeg: {e}. Assurez-vous qu'ils sont installés sur votre serveur.")
        if xvfb_process and xvfb_process.poll() is None: xvfb_process.terminate()
        if ffmpeg_process and ffmpeg_process.poll() is None: ffmpeg_process.terminate()
        raise ScrapingError(f"Failed to start Xvfb/FFmpeg: {e}")

    stealth = Stealth()
    browser = None
    context = None
    page = None
    try:
        # 3. Lancer Playwright en mode non-headless, en utilisant l'affichage virtuel de Xvfb
        browser_args = ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu', f'--display={DISPLAY_NUM}']

        async with stealth.use_async(async_playwright()) as p:
            logger.info("Launching Chromium with Playwright...")
            browser = await p.chromium.launch(headless=False, args=browser_args)
            context = await browser.new_context(
                record_video_dir=str(videos_dir),
                record_video_size={"width": VIDEO_WIDTH, "height": VIDEO_HEIGHT},
                base_url="https://www.chess.com"
            )
            page = await context.new_page()

            logger.info("Navigating to login page...")
            await page.goto("/login_and_go", timeout=60000) # Reduced timeout for goto
            await asyncio.sleep(2)
            await handle_potential_blockers(page, "Before Login Attempt")
            await asyncio.sleep(2)

            logger.info("Waiting 5 seconds before login action...")
            await asyncio.sleep(5)

            login_successful = False
            for attempt in range(3): # Attempt login multiple times
                logger.info(f"Login attempt {attempt + 1}...")
                try:
                    await page.get_by_placeholder("Username, Phone, or Email").fill(username)
                    await page.get_by_placeholder("Password").fill(password)
                    await page.get_by_role("button", name="Log In").click()
                    
                    await page.wait_for_url("**/home", timeout=15000) # Wait for redirect
                    logger.info("Login successful.")
                    login_successful = True
                    break
                except PlaywrightTimeoutError as e:
                    logger.warning(f"Login attempt {attempt + 1} failed (timeout): {e}. Checking for blockers...")
                    blocker_handled = await handle_potential_blockers(page, f"After Login Fail (Attempt {attempt + 1})")
                    if not blocker_handled:
                        logger.info(f"No known blocker handled after failed login attempt {attempt + 1}. Retrying...")
                    await asyncio.sleep(3)
                except Exception as e:
                    logger.error(f"An unexpected error occurred during login attempt {attempt + 1}: {e}. Retrying...")
                    await asyncio.sleep(3)

            if not login_successful:
                raise ScrapingError("Failed to log in to Chess.com after multiple attempts.")

            logger.info(f"Navigating to game URL: {url}")
            await page.goto(url, timeout=60000) # Reduced timeout for goto
            await handle_potential_blockers(page, "After Game Page Load")

            logger.info("Clicking share button and PGN tab...")
            await page.locator("button.share-button-component").click(timeout=10000)
            await page.locator('div.share-menu-tab-component-header:has-text("PGN")').click(timeout=10000)

            logger.info("Extracting PGN text...")
            pgn_text = await page.input_value('textarea.share-menu-tab-pgn-textarea', timeout=10000)
            logger.info("PGN extracted.")

            video_path = await page.video.path() # Retrieve locally recorded video path
            return pgn_text, video_path

    except Exception as e:
        screenshot_bytes, video_path = None, None
        try:
            if page and not page.is_closed(): # Check if page object exists and is not closed
                logger.error(f"Scraping error: {e}. Attempting to capture debug info.")
                screenshot_bytes = await page.screenshot(full_page=True)
            if context: # Check if context object exists
                video_path = await context.video.path() # Get video path from context
        except Exception as debug_e:
            logger.error(f"Error during debug data collection: {debug_e}")
        finally:
            # Enhanced cleanup: Ensure all browser-related processes are closed
            if browser:
                try:
                    await browser.close()
                    logger.info("Playwright browser closed.")
                except Exception as close_e:
                    logger.error(f"Error closing Playwright browser: {close_e}")
            
            # Ensure FFmpeg and Xvfb processes are terminated
            if ffmpeg_process and ffmpeg_process.poll() is None:
                logger.info("Terminating FFmpeg process...")
                ffmpeg_process.terminate()
                ffmpeg_process.wait(timeout=5)
            if xvfb_process and xvfb_process.poll() is None:
                logger.info("Terminating Xvfb process...")
                xvfb_process.terminate()
                xvfb_process.wait(timeout=5)
            logger.info("Browser, FFmpeg, and Xvfb processes cleaned up.")
            
        raise ScrapingError(f"Scraping failed: {e}", screenshot_bytes, video_path)

    finally:
        # Final cleanup for FFmpeg and Xvfb even if no Playwright error
        if ffmpeg_process and ffmpeg_process.poll() is None:
            logger.info("Final cleanup: Terminating FFmpeg process...")
            ffmpeg_process.terminate()
            ffmpeg_process.wait(timeout=5)
        if xvfb_process and xvfb_process.poll() is None:
            logger.info("Final cleanup: Terminating Xvfb process...")
            xvfb_process.terminate()
            xvfb_process.wait(timeout=5)


# --- STOCKFISH ANALYSE (INCHANGÉ) ---
def analyse_pgn_with_stockfish(pgn_text):
    """
    Analyse un PGN de partie d'échecs en utilisant Stockfish
    et retourne des annotations sur les coups.
    """
    try:
        stockfish = Stockfish(path=STOCKFISH_PATH)
    except FileNotFoundError:
        logger.error(f"ERREUR: Stockfish non trouvé à l'emplacement '{STOCKFISH_PATH}'.")
        logger.error("Assurez-vous que Stockfish est installé et que le chemin est correct.")
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
    """
    Commande Discord pour récupérer le PGN d'une partie Chess.com,
    l'analyser, et activer un live stream du processus du bot.
    """
    if "chess.com/game/live/" not in url and "chess.com/play/game/" not in url:
        return await ctx.send("❌ URL invalide. Veuillez fournir une URL de partie Chess.com valide.")
    
    railway_public_url = os.getenv('RAILWAY_PUBLIC_URL') 
    
    if railway_public_url:
        stream_url = f"{railway_public_url}/video_feed"
    else:
        stream_url = f"http://localhost:{VIDEO_STREAM_PORT}/video_feed"
        await ctx.send("⚠️ La variable d'environnement `RAILWAY_PUBLIC_URL` n'est pas définie. "
                       "Assurez-vous de la définir sur votre tableau de bord Railway pour que le lien du stream fonctionne correctement en production.")


    await ctx.send(f"🕵️ Connexion Chess.com et récupération du PGN en cours... Cela peut prendre un moment.\n"
                   f"**💡 Vous pouvez suivre l'activité du bot en direct ici :** <{stream_url}>\n"
                   f"(Actualisez la page si le stream ne démarre pas immédiatement ou se fige. Le stream s'arrêtera à la fin de la tâche.)")
    
    msg = await ctx.send("Démarrage du processus de scraping et de streaming...")

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
        
        await ctx.send(f"✅ Analyse terminée pour la partie. Le stream s'est arrêté.\n"
                       f"Utilisez `!cam` si le bot a rencontré un problème pour voir la vidéo de débogage finale.")

    except ScrapingError as e:
        await msg.edit(content=f"❌ Échec lors du scraping de la partie Chess.com: {e.args[0]}")
        if e.video_path:
            last_video_paths[ctx.channel.id] = e.video_path
            await ctx.send("📹 Une vidéo de débogage est disponible (si l'enregistrement a pu être finalisé). Utilisez `!cam` pour la voir.")
        if e.screenshot_bytes:
            await ctx.send("📸 Capture d'écran de l'erreur :", file=discord.File(io.BytesIO(e.screenshot_bytes), "debug_screenshot.png"))
        logger.error(f"Scraping Error: {e.args[0]}")
    except Exception as e:
        await msg.edit(content=f"❌ Une erreur inattendue est survenue: {e}")
        logger.error(f"Unexpected Error in get_chess_pgn: {e}", exc_info=True)

@bot.command(name="cam")
async def send_last_video(ctx):
    """
    Commande Discord pour envoyer la dernière vidéo de débogage enregistrée.
    Utile si le stream en direct a échoué ou pour revoir une session.
    """
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
            logger.error(f"Discord HTTPException while sending video: {http_exc}")
    else:
        await ctx.send(f"📹 La vidéo de débogage est trop lourde pour être envoyée sur Discord "
                       f"({video_file.stat().st_size / (1024 * 1024):.2f} Mo). "
                       "La limite est de 8 Mo.")

# --- TWITCH MIRROR OPTIONNEL (INCHANGÉ) ---
class WatcherMode(Enum):
    IDLE = auto()
    KEYWORD = auto()
    MIRROR = auto()

class WatcherBot(twitch_commands.Bot):
    """
    Bot Twitch pour surveiller ou mirroirer un chat.
    """
    def __init__(self, discord_bot):
        super().__init__(token=TTV_BOT_TOKEN, prefix="!", initial_channels=[])
        self.discord_bot = discord_bot
        self.mode = WatcherMode.IDLE
        self.current_channel_name = None
        self.target_discord_channel = None
        self.keyword_to_watch = None

    async def event_ready(self):
        logger.info(f"Twitch bot '{TTV_BOT_NICKNAME}' connecté et prêt.")

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
            logger.info(f"Leaving Twitch channel: {self.current_channel_name}")
            await self.part_channels([self.current_channel_name])
        self.mode = WatcherMode.IDLE
        self.current_channel_name = None
        self.target_discord_channel = None
        self.keyword_to_watch = None
        logger.info("Twitch watch/mirror task stopped.")

    async def start_keyword_watch(self, channel: str, keyword: str, discord_channel: discord.TextChannel):
        await self.stop_task()
        self.mode = WatcherMode.KEYWORD
        self.keyword_to_watch = keyword
        self.target_discord_channel = discord_channel
        self.current_channel_name = channel.lower()
        await self.join_channels([self.current_channel_name])
        logger.info(f"Started watching keyword '{keyword}' on Twitch channel '{channel}'.")

    async def start_mirror(self, channel: str, discord_channel: discord.TextChannel):
        await self.stop_task()
        self.mode = WatcherMode.MIRROR
        self.target_discord_channel = discord_channel
        self.current_channel_name = channel.lower()
        await self.join_channels([self.current_channel_name])
        logger.info(f"Started mirroring Twitch chat for '{channel}'.")

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

# --- ÉVÉNEMENTS DU BOT DISCORD ---
@bot.event
async def on_ready():
    logger.info(f"Bot Discord connecté en tant que {bot.user} (ID: {bot.user.id})")
    logger.info(f"Version de Discord.py : {discord.__version__}")
    logger.info("Prêt à recevoir des commandes !")

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
        logger.error(f"Erreur inattendue dans la commande {ctx.command}: {error}", exc_info=True)
        await ctx.send(f"❌ Une erreur inattendue est survenue lors de l'exécution de la commande.")

# --- EXÉCUTION PRINCIPALE ---
async def main():
    logger.info("Starting main application sequence...")
    # 1. Démarrer l'application Flask dans un thread séparé
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.daemon = True
    flask_thread.start()
    logger.info(f"Flask app for video streaming started on port {VIDEO_STREAM_PORT}")

    # 2. Initialiser le bot Twitch et l'attacher au bot Discord
    twitch_bot = WatcherBot(bot)
    bot.twitch_bot = twitch_bot 
    
    # 3. Lancer les bots Discord et Twitch de manière asynchrone
    try:
        await asyncio.gather(
            bot.start(DISCORD_TOKEN),
            twitch_bot.start()
        )
    except Exception as e:
        logger.critical(f"One or more bots failed to start: {e}", exc_info=True)
        sys.exit(1) # Quitte le programme si les bots ne peuvent pas démarrer

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot(s) stopped by user (Ctrl+C).")
    except Exception as e:
        logger.critical(f"A fatal error occurred during main execution: {e}", exc_info=True)
        sys.exit(1) # Quitter avec un code d'erreur en cas d'erreur fatale

