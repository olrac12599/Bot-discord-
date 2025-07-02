import logging
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth
from analyzer import analyze_fen_sequence

# --- LOGGER ---
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
)
logger = logging.getLogger("scraping")

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

            for i in range(60):
                await asyncio.sleep(10)
                if asyncio.current_task().cancelled():
                    logger.warning("🛑 Scraping annulé par !stop")
                    try:
                        video_path = await page.video.path()
                        logger.info(f"🎥 Vidéo récupérée : {video_path}")
                    except:
                        logger.error("❌ Échec récupération vidéo")
                    break

                current_fen = await get_fen_from_page(page)
                if not current_fen:
                    continue

                if current_fen != last_fen and last_fen:
                    logger.info("🔄 Nouveau coup détecté. Analyse en cours...")
                    result = await analyze_fen_sequence(last_fen, current_fen, color)
                    if result:
                        annotation, diff = result
                        piece = "♙ Blanc" if color == "white" else "♟️ Noir"
                        logger.info(f"{piece} joue : {annotation} ({diff})")
                        await discord_channel.send(f"{piece} joue : **{annotation}** ({diff})")
                    color = "black" if color == "white" else "white"

                last_fen = current_fen

            await page.locator("button.share-button-component").click(timeout=30000)
            await page.locator('div.share-menu-tab-component-header:has-text("PGN")').click(timeout=20000)
            pgn = await page.input_value('textarea.share-menu-tab-pgn-textarea')
            logger.info("✅ PGN récupéré.")

            video_path = await page.video.path()
            logger.info(f"🎥 Vidéo enregistrée à : {video_path}")

            await context.close()
            await browser.close()
            return pgn, video_path

        except Exception as e:
            logger.error(f"❌ Erreur scraping : {e}")
            try:
                video_path = await page.video.path()
                logger.info(f"🎥 Vidéo récupérée malgré l'erreur : {video_path}")
            except:
                logger.error("❌ Impossible de récupérer la vidéo")
            await context.close()
            await browser.close()
            raise ScrapingError(str(e), video_path=video_path)