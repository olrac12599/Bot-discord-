import logging
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth
from analyzer import analyze_fen_sequence
import discord

# --- LOGGER ---
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
)
logger = logging.getLogger("scraping")

# --- FICHIERS VIDÉO ---
videos_dir = Path("videos")
videos_dir.mkdir(exist_ok=True)

class ScrapingError(Exception):
    def __init__(self, message, video_path=None):
        super().__init__(message)
        self.video_path = video_path

async def get_fen_from_page(page):
    try:
        element = await page.query_selector("cg-container")
        return await element.get_attribute("data-fen")
    except:
        return None

async def get_pgn_from_chess_com(url, username, password, discord_channel):
    logger.info("🚀 Démarrage du scraping...")
    stealth = Stealth()

    async with stealth.use_async(async_playwright()) as p:
        browser = await p.chromium.launch(headless=True, args=[
            '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu'
        ])
        context = await browser.new_context(record_video_dir=str(videos_dir))
        page = await context.new_page()

        video_path = None
        last_fen = None
        color = "white"

        try:
            logger.info("🌐 Connexion à Chess.com...")
            await page.goto("https://www.chess.com/login_and_go", timeout=90000)
            await page.wait_for_load_state('domcontentloaded')

            try:
                await page.get_by_role("button", name="I Accept").click(timeout=3000)
                logger.info("✅ 'I Accept' cliqué")
            except PlaywrightTimeoutError:
                logger.warning("🔎 'I Accept' non trouvé")

            await page.get_by_placeholder("Username, Phone, or Email").type(username)
            await page.get_by_placeholder("Password").type(password)
            await page.get_by_role("button", name="Log In").click()
            logger.info("🔐 Connexion envoyée...")

            await page.wait_for_url("**/home", timeout=15000)
            logger.info("✅ Connexion réussie.")

            await page.goto(url, timeout=90000)
            logger.info(f"📥 Partie ouverte : {url}")

            # Suivre et analyser les coups pendant 30 secondes (3 * 10s)
            for i in range(3):
                await asyncio.sleep(10)

                current_fen = await get_fen_from_page(page)
                logger.info(f"[FEN] ({i+1}/3) {current_fen}")

                if not current_fen:
                    continue

                if current_fen != last_fen and last_fen:
                    logger.info("🔄 Nouveau coup détecté. Analyse...")
                    result = await analyze_fen_sequence(last_fen, current_fen, color)
                    if result:
                        annotation, diff = result
                        piece = "♙ Blanc" if color == "white" else "♟️ Noir"
                        logger.info(f"{piece} joue : {annotation} ({diff})")
                        await discord_channel.send(f"{piece} joue : **{annotation}** ({diff})")
                    color = "black" if color == "white" else "white"

                last_fen = current_fen

            logger.info("🕒 30 secondes écoulées. Fin de session.")

            # Enregistrer la vidéo
            video_path = await page.video.path()
            if Path(video_path).exists():
                await discord_channel.send("📹 Vidéo enregistrée automatiquement :", file=discord.File(video_path, "debug_video.webm"))
                logger.info(f"🎥 Vidéo envoyée : {video_path}")
            else:
                await discord_channel.send("❌ Impossible de trouver la vidéo enregistrée.")
                logger.error("❌ Vidéo non trouvée.")

            await context.close()
            await browser.close()

            return "", video_path  # on ne retourne pas le PGN ici car il n’est pas prioritaire

        except Exception as e:
            try:
                video_path = await page.video.path()
                logger.warning(f"⚠️ Vidéo récupérée malgré erreur : {video_path}")
            except:
                logger.error("❌ Impossible de récupérer la vidéo.")
                video_path = None
            await context.close()
            await browser.close()
            raise ScrapingError(str(e), video_path=video_path)