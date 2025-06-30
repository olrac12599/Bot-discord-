import os
import asyncio
import subprocess
import threading
import time
import sys
import io
import logging
from pathlib import Path
from enum import Enum, auto

import numpy as np
import cv2
import discord
from discord.ext import commands
import twitchio
from twitchio.ext import commands as twitch_commands
from playwright.async_api import async_playwright, Page, TimeoutError # CORRECTED: PlaywrightTimeoutError -> TimeoutError
from playwright_stealth import Stealth # CORRECTED: stealth_async -> Stealth
import chess.pgn
from stockfish import Stockfish
from flask import Flask, Response

# --- CONFIGURATION DES LOGS ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TTV_BOT_TOKEN = os.getenv("TTV_BOT_TOKEN")
TTV_BOT_NICKNAME = os.getenv("TTV_BOT_NICKNAME")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")
DISCORD_FILE_LIMIT_BYTES = 8 * 1024 * 1024

STOCKFISH_PATH = "/usr/games/stockfish" # Assurez-vous que Stockfish est bien installé ici sur le système

VIDEO_STREAM_PORT = int(os.getenv("PORT", 5000))

# Résolution standard 16:9 pour éviter la déformation
VIDEO_WIDTH, VIDEO_HEIGHT = 1280, 720
FPS = 10
DISPLAY_NUM = ":99"

if not all([DISCORD_TOKEN, TTV_BOT_NICKNAME, TTV_BOT_TOKEN, CHESS_USERNAME, CHESS_PASSWORD]):
    logger.critical("ERREUR: Variables d'environnement DISCORD_TOKEN, TTV_BOT_NICKNAME, TTV_BOT_TOKEN, CHESS_USERNAME ou CHESS_PASSWORD manquantes.")
    logger.critical("Veuillez les définir avant de lancer le bot sur Railway.")
    sys.exit(1)

# --- FLASK APP POUR LE STREAM ---
app = Flask(__name__)
video_frame = None
video_lock = threading.Lock()

@app.route('/video_feed')
def video_feed():
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
    try:
        app.run(host='0.0.0.0', port=VIDEO_STREAM_PORT, debug=False)
    except Exception as e:
        logger.critical(f"Flask application failed to start: {e}")

# --- INITIALISATION DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
last_video_paths = {}

# --- ERREUR CUSTOM ---
class ScrapingError(Exception):
    def __init__(self, message, screenshot_bytes=None, video_path=None):
        super().__init__(message)
        self.screenshot_bytes = screenshot_bytes
        self.video_path = video_path

# --- AI-LIKE BLOCKER HANDLER (CORRIGÉ ET AMÉLIORÉ) ---
async def handle_potential_blockers(page: Page, context_description: str = "") -> bool:
    logger.info(f"[{context_description}] AI-like blocker handler: Checking for common pop-ups...")
    
    # Stratégie 1: Accepter les cookies ou fermer les bannières d'information
    accept_selectors = [
        'button:has-text("I Accept")', 'button:has-text("J\'accepte")',
        '[aria-label="Accept"]', '[aria-label="J\'accepte"]',
        '[data-testid="accept-button"]',
        'button[class*="accept"], .accept-button',
        'div[role="button"]:has-text("I Accept")', 'div[role="button"]:has-text("J\'accepte")',
        '#onetrust-accept-btn-handler',
        'button.qc-cmp2-summary-tapbtn'
    ]

    for selector in accept_selectors:
        locator = page.locator(selector)
        try:
            # Attendre que l'élément soit visible et enabled
            await locator.wait_for(state='visible', timeout=3000)
            await locator.wait_for(state='enabled', timeout=3000) # Assurer qu'il est cliquable
            
            logger.info(f"[{context_description}] Found potential cookie/accept button with selector '{selector}'. Attempting to scroll into view and click.")
            await locator.scroll_into_view_if_needed(timeout=3000) # Added timeout here
            await locator.click(force=True, timeout=5000)
            await asyncio.sleep(2)
            logger.info(f"[{context_description}] Successfully clicked cookie/accept button using selector '{selector}'.")
            return True # Bloqueur géré, sortir
        except TimeoutError: # Correction : capturer TimeoutError
            logger.debug(f"[{context_description}] Cookie/accept button with selector '{selector}' not visible/enabled within timeout on page.")
        except Exception as e:
            logger.warning(f"[{context_description}] Error clicking cookie/accept button with selector '{selector}': {e}")

    # Stratégie 2: Gérer les pop-ups de cookies dans des IFRAMES
    iframe_selectors = [
        'iframe[title*="Privacy"]', 'iframe[name*="privacy"]',
        'iframe[src*="privacy-policy"]', 'iframe[src*="cookie-consent"]',
        'iframe[id*="sp_message_container"]',
        'iframe[title*="cookie"]',
        'iframe' # Last resort, try generic iframes
    ]

    for iframe_selector in iframe_selectors:
        try:
            iframe_element = await page.wait_for_selector(iframe_selector, state='attached', timeout=3000)
            if iframe_element:
                iframe = await iframe_element.content_frame()
                if iframe:
                    logger.info(f"[{context_description}] Found potential iframe with selector '{iframe_selector}'. Checking for cookie button inside.")
                    for selector in accept_selectors:
                        iframe_locator = iframe.locator(selector)
                        try:
                            await iframe_locator.wait_for(state='visible', timeout=3000) # Attendre visibilité
                            await iframe_locator.wait_for(state='enabled', timeout=3000) # Assurer cliquable
                            
                            logger.info(f"[{context_description}] Found 'I Accept' button inside iframe with selector '{selector}'. Attempting to scroll into view and click.")
                            await iframe_locator.scroll_into_view_if_needed(timeout=3000) # Added timeout here
                            await iframe_locator.click(force=True, timeout=5000)
                            await asyncio.sleep(2)
                            logger.info(f"[{context_description}] Successfully clicked button in iframe using selector '{selector}'.")
                            return True # Bloqueur géré, sortir
                        except TimeoutError: # Correction : capturer TimeoutError
                            logger.debug(f"[{context_description}] Cookie/accept button with selector '{selector}' not visible/enabled within timeout in iframe.")
                        except Exception as e:
                            logger.warning(f"[{context_description}] Error clicking button in iframe with selector '{selector}': {e}")
        except TimeoutError: # Correction : capturer TimeoutError for the iframe itself
            logger.debug(f"[{context_description}] Iframe with selector '{iframe_selector}' not found within timeout.")
        except Exception as e_iframe:
            logger.warning(f"[{context_description}] Error locating/accessing iframe {iframe_selector}: {e_iframe}")

    # Stratégie 3: Gérer les pop-ups génériques de fermeture
    try:
        close_button = page.locator(
            'button[aria-label="close"], button:has-text("No Thanks"), button:has-text("Not now"), '
            '.modal-close-button, .close-button, div[role="dialog"] >> button:has-text("No Thanks"), .x-button-icon, '
            'a.close-button, [data-qa="close-button"], ._modal_x_button'
        )
        if await close_button.is_visible(timeout=2000): # The timeout is correct here for Locator.is_visible()
            logger.info(f"[{context_description}] Found generic pop-up. Attempting to click close/dismiss button.")
            await close_button.scroll_into_view_if_needed(timeout=2000) # Added timeout here
            await close_button.click(force=True, timeout=3000)
            await asyncio.sleep(1)
            # Re-vérifier la visibilité après le clic
            if not await close_button.is_visible(timeout=1000): # Timeout is correct here too
                logger.info(f"[{context_description}] Successfully closed generic pop-up.")
                return True
            else:
                logger.warning(f"[{context_description}] Generic pop-up still visible after click, trying ESC key.")
                await page.keyboard.press("Escape")
                await asyncio.sleep(1)
                if not await close_button.is_visible(timeout=1000): # Timeout is correct here
                    logger.info(f"[{context_description}] Successfully closed generic pop-up with ESC key.")
                    return True
    except TimeoutError: # Correction : capturer TimeoutError
        logger.debug(f"[{context_description}] No generic close pop-up found (likely not visible within timeout).")
    except Exception as e:
        logger.warning(f"[{context_description}] Error handling generic pop-up: {e}")

    # Stratégie 4: Vérifications spécifiques à Chess.com
    try:
        chess_com_specific_close_selectors = [
            '.modal-dialog:has-text("Welcome to Chess.com") button[aria-label="close"]',
            '.modal-dialog:has-text("New Feature") button[aria-label="close"]',
            'button.btn-close-x',
            'div.modal-title-text:has-text("Welcome to Chess.com") + button.modal-close-button',
            'div.modal-title-text:has-text("Important Update") + button.modal-close-button',
            'button[data-qa="modal-close"]'
        ]
        
        for selector in chess_com_specific_close_selectors:
            specific_close_button = page.locator(selector)
            if await specific_close_button.is_visible(timeout=1000): # Timeout is correct here for Locator.is_visible()
                logger.info(f"[{context_description}] Found Chess.com specific pop-up with selector '{selector}'. Closing it.")
                await specific_close_button.scroll_into_view_if_needed(timeout=1000) # Added timeout here
                await specific_close_button.click(force=True, timeout=3000)
                await asyncio.sleep(1)
                if not await specific_close_button.is_visible(timeout=500): # Timeout is correct here
                    logger.info(f"[{context_description}] Successfully closed Chess.com specific pop-up.")
                    return True
    except TimeoutError: # Correction : capturer TimeoutError
        logger.debug(f"[{context_description}] No Chess.com specific pop-up found (likely not visible within timeout).")
    except Exception as e:
        logger.warning(f"[{context_description}] Error handling Chess.com specific pop-up: {e}")

    # Stratégie 5: Gérer le message "Aw, Snap!"
    try:
        reload_button = page.get_by_role("button", name="Reload", exact=True)
        learn_more_link = page.get_by_text("Learn more", exact=True)

        if await reload_button.is_visible(timeout=1500):
            logger.warning(f"[{context_description}] Detected 'Aw, Snap!' with 'Reload' button. Attempting to click Reload.")
            try:
                await reload_button.click(timeout=1000)
                await asyncio.sleep(5)
                await handle_potential_blockers(page, f"{context_description} after 'Reload' attempt")
                return True
            except Exception as reload_e:
                logger.error(f"[{context_description}] Failed to click 'Reload' or subsequent handling failed: {reload_e}")
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
    except TimeoutError: # Correction : capturer TimeoutError
        logger.debug(f"[{context_description}] No 'Aw, Snap!' elements detected.")
    except Exception as e:
        logger.error(f"[{context_description}] Error handling 'Aw, Snap!' elements: {e}")

    logger.info(f"[{context_description}] No known blockers handled after all strategies.")
    return False

# --- PGN SCRAPER AVEC STREAMING ---
async def get_pgn_from_chess_com(url: str, username: str, password: str):
    videos_dir = Path("debug_videos")
    videos_dir.mkdir(exist_ok=True)
    
    xvfb_process = None
    ffmpeg_process = None
    browser = None
    context = None
    page = None

    try:
        logger.info(f"Starting Xvfb on display {DISPLAY_NUM}...")
        xvfb_command = ['Xvfb', DISPLAY_NUM, '-screen', '0', f'{VIDEO_WIDTH}x{VIDEO_HEIGHT}x24', '+extension', 'GLX', '+render', '-noreset']
        xvfb_process = subprocess.Popen(xvfb_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await asyncio.sleep(2)
        logger.info("Xvfb started successfully.")

        logger.info("Starting FFmpeg to capture Xvfb display...")
        ffmpeg_command = [
            'ffmpeg', '-f', 'x11grab', '-video_size', f'{VIDEO_WIDTH}x{VIDEO_HEIGHT}',
            '-i', f'{DISPLAY_NUM}.0', '-c:v', 'rawvideo', '-pix_fmt', 'bgr24',
            '-f', 'image2pipe', '-vsync', '2', '-r', str(FPS), 'pipe:1'
        ]
        ffmpeg_process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        logger.info("FFmpeg capture process started.")

        def read_ffmpeg_output():
            global video_frame 
            bytes_per_frame = VIDEO_WIDTH * VIDEO_HEIGHT * 3 
            while True:
                in_bytes = ffmpeg_process.stdout.read(bytes_per_frame)
                if not in_bytes:
                    logger.warning("FFmpeg output stream ended or encountered an error. Stopping frame reader.")
                    break
                try:
                    frame = np.frombuffer(in_bytes, np.uint8).reshape((VIDEO_HEIGHT, VIDEO_WIDTH, 3))
                    with video_lock:
                        video_frame = frame
                except ValueError as ve:
                    logger.error(f"Error reshaping frame from FFmpeg: {ve}. Bytes read: {len(in_bytes)}")
                except Exception as e:
                    logger.error(f"Unexpected error in FFmpeg frame reader: {e}")
        
        ffmpeg_thread = threading.Thread(target=read_ffmpeg_output)
        ffmpeg_thread.daemon = True
        ffmpeg_thread.start()
        logger.info("FFmpeg frame reader thread started.")

        stealth = Stealth()
        async with stealth.use_async(async_playwright()) as p:
            logger.info("Launching Chromium with Playwright...")
            browser = await p.chromium.launch(
                headless=False,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu', f'--display={DISPLAY_NUM}', '--start-maximized'],
                timeout=60000
            )
            
            context = await browser.new_context(
                record_video_dir=str(videos_dir),
                record_video_size={"width": VIDEO_WIDTH, "height": VIDEO_HEIGHT},
                viewport={"width": VIDEO_WIDTH, "height": VIDEO_HEIGHT},
                base_url="https://www.chess.com"
            )
            page = await context.new_page()

            logger.info("Navigating to login page...")
            await page.goto("/login_and_go", timeout=90000)
            
            logger.info("Checking for initial blockers immediately after page load and before login attempts...")
            for i in range(5):
                if await handle_potential_blockers(page, f"Initial Load (Attempt {i+1})"):
                    logger.info("Initial blocker handled. Proceeding with login.")
                    break
                logger.info(f"Initial blocker still present after attempt {i+1}. Waiting 2 seconds and retrying...")
                await asyncio.sleep(2)
            
            logger.info("Attempting login...")
            login_successful = False
            for attempt in range(3):
                logger.info(f"Login attempt {attempt + 1}...")
                try:
                    username_field = page.get_by_placeholder("Username, Phone, or Email")
                    password_field = page.get_by_placeholder("Password")
                    login_button = page.get_by_role("button", name="Log In")

                    await username_field.wait_for(state='visible', timeout=10000)
                    await username_field.fill(username)
                    await password_field.fill(password)
                    
                    await login_button.wait_for(state='visible', timeout=10000)
                    await login_button.click()
                    
                    await page.wait_for_url("**/home", timeout=20000)
                    logger.info("Login successful.")
                    login_successful = True
                    break
                except TimeoutError as e: # Correction : capturer TimeoutError
                    logger.warning(f"Login attempt {attempt + 1} failed (timeout): {e}. Re-checking for blockers (may be new or persistent).")
                    await handle_potential_blockers(page, f"After Login Fail (Attempt {attempt + 1})")
                    await asyncio.sleep(3)
                except Exception as e:
                    logger.error(f"An unexpected error occurred during login attempt {attempt + 1}: {e}. Retrying...", exc_info=True)
                    await asyncio.sleep(3)

            if not login_successful:
                screenshot_bytes = None
                if page and not page.is_closed():
                    screenshot_bytes = await page.screenshot(full_page=True)
                raise ScrapingError("Failed to log in to Chess.com after multiple attempts.", screenshot_bytes=screenshot_bytes)

            logger.info(f"Navigating to game URL: {url}")
            await page.goto(url, timeout=60000)
            await asyncio.sleep(3)
            await handle_potential_blockers(page, "After Game Page Load")

            logger.info("Clicking share button and PGN tab...")
            share_button = page.locator("button.share-button-component")
            await share_button.wait_for(state='visible', timeout=15000)
            await share_button.click()
            await asyncio.sleep(1)

            pgn_tab = page.locator('div.share-menu-tab-component-header:has-text("PGN")')
            await pgn_tab.wait_for(state='visible', timeout=10000)
            await pgn_tab.click()
            await asyncio.sleep(1)

            logger.info("Extracting PGN text...")
            pgn_textarea = page.locator('textarea.share-menu-tab-pgn-textarea')
            await pgn_textarea.wait_for(state='visible', timeout=10000)
            pgn_text = await pgn_textarea.input_value()
            logger.info("PGN extracted.")

            video_path = await context.video.path()
            return pgn_text, video_path

    except Exception as e:
        screenshot_bytes, video_path = None, None
        try:
            if page and not page.is_closed():
                logger.error(f"Scraping error: {e}. Attempting to capture debug info.")
                screenshot_bytes = await page.screenshot(full_page=True)
            if context:
                try:
                    video_path = await context.video.path()
                except Exception as vp_e:
                    logger.warning(f"Could not get video path during error: {vp_e}")
        except Exception as debug_e:
            logger.error(f"Error during debug data collection: {debug_e}")
        finally:
            if browser:
                try:
                    await browser.close()
                    logger.info("Playwright browser closed.")
                except Exception as close_e:
                    logger.error(f"Error closing Playwright browser: {close_e}")
            
            if ffmpeg_process and ffmpeg_process.poll() is None:
                logger.info("Terminating FFmpeg process...")
                ffmpeg_process.terminate()
                ffmpeg_process.wait(timeout=5)
            if xvfb_process and xvfb_process.poll() is None:
                logger.info("Terminating Xvfb process...")
                xvfb_process.terminate()
                xvfb_process.wait(timeout=5)
            logger.info("Browser, FFmpeg, and Xvfb processes cleaned up.")
            
        # VERY IMPORTANT CHANGE HERE: How 'e' is passed to ScrapingError
        # Ensure 'e' is stringified cleanly to avoid issues with its internal representation.
        error_message_to_pass = str(e)
        # If 'e' is a TimeoutError, Playwright might put the old name in its string repr.
        # This explicitly replaces it just in case.
        error_message_to_pass = error_message_to_pass.replace("PlaywrightTimeoutError", "TimeoutError")
        
        raise ScrapingError(f"Scraping failed: {error_message_to_pass}", screenshot_bytes, video_path)

    finally:
        if ffmpeg_process and ffmpeg_process.poll() is None:
            logger.info("Final cleanup: Terminating FFmpeg process...")
            ffmpeg_process.terminate()
            ffmpeg_process.wait(timeout=5)
        if xvfb_process and xvfb_process.poll() is None:
            logger.info("Final cleanup: Terminating Xvfb process...")
            xvfb_process.terminate()
            xvfb_process.wait(timeout=5)
        logger.info("All processes cleaned up.")


# --- STOCKFISH ANALYSIS (UNCHANGED) ---
def analyse_pgn_with_stockfish(pgn_text):
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
        if best_eval and played_eval:
            if best_eval['type'] == 'cp' and played_eval['type'] == 'cp':
                delta = played_eval['value'] - best_eval['value']
            elif best_eval['type'] == 'mate' or played_eval['type'] == 'mate':
                delta = 1000
        else:
            logger.warning(f"Could not get evaluation for move {board.san(move)}. Skipping comparison.")


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
            screenshot_file = discord.File(io.BytesIO(e.screenshot_bytes), "debug_screenshot.png")
            await ctx.send("📸 Capture d'écran de l'erreur :", file=screenshot_file)
        logger.error(f"Scraping Error: {e.args[0]}", exc_info=True)
    except Exception as e:
        await msg.edit(content=f"❌ Une erreur inattendue est survenue: {e}")
        logger.error(f"Unexpected Error in get_chess_pgn: {e}", exc_info=True)

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
            with open(video_file, 'rb') as f:
                video_data = io.BytesIO(f.read())
            await ctx.send("📹 Voici la dernière vidéo de débogage :", file=discord.File(video_data, "debug_video.webm"))
        except discord.HTTPException as http_exc:
            await ctx.send(f"❌ Impossible d'envoyer la vidéo: {http_exc}. Elle est peut-être trop lourde ou corrompue.")
            logger.error(f"Discord HTTPException while sending video: {http_exc}")
        except Exception as exc:
            await ctx.send(f"❌ Une erreur est survenue lors de l'envoi de la vidéo : {exc}")
            logger.error(f"Error sending video: {exc}", exc_info=True)
    else:
        await ctx.send(f"📹 La vidéo de débogage est trop lourde pour être envoyée sur Discord "
                       f"({video_file.stat().st_size / (1024 * 1024):.2f} Mo). "
                       "La limite est de 8 Mo.")

# --- TWITCH MIRROR OPTIONAL ---
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
        logger.info(f"Twitch bot '{TTV_BOT_NICKNAME}' connected and ready.")

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

# --- DISCORD BOT EVENTS ---
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

# --- MAIN EXECUTION ---
async def main():
    logger.info("Starting main application sequence...")
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.daemon = True
    flask_thread.start()
    logger.info(f"Flask app for video streaming started on port {VIDEO_STREAM_PORT}")

    twitch_bot = WatcherBot(bot)
    bot.twitch_bot = twitch_bot 
    
    try:
        await asyncio.gather(
            bot.start(DISCORD_TOKEN),
            twitch_bot.start()
        )
    except Exception as e:
        logger.critical(f"One or more bots failed to start: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot(s) stopped by user (Ctrl+C).")
    except Exception as e:
        logger.critical(f"A fatal error occurred during main execution: {e}", exc_info=True)
        sys.exit(1)
