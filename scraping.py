from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth
from analyzer import analyze_fen_sequence
from pathlib import Path
import asyncio

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

async def get_pgn_from_chess_com(url: str, username: str, password: str, discord_channel) -> (str, str):
    stealth = Stealth()
    async with stealth.use_async(async_playwright()) as p:
        browser = await p.chromium.launch(headless=True, args=[
            '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu'
        ])
        context = await browser.new_context(record_video_dir=str(videos_dir))
        page = await context.new_page()

        video_path = None
        last_fen = None
        color_to_move = "white"

        try:
            await page.goto("https://www.chess.com/login_and_go", timeout=90000)
            await page.wait_for_load_state('domcontentloaded')

            try:
                await page.get_by_role("button", name="I Accept").click(timeout=3000)
            except PlaywrightTimeoutError:
                pass

            await page.get_by_placeholder("Username, Phone, or Email").type(username, delay=50)
            await page.get_by_placeholder("Password").type(password, delay=50)
            await page.get_by_role("button", name="Log In").click()
            await page.wait_for_url("**/home", timeout=15000)

            await page.goto(url, timeout=90000)

            # Analyse en direct pendant 60 secondes
            for _ in range(60):
                await asyncio.sleep(10)
                current_fen = await get_fen_from_page(page)

                if not current_fen:
                    continue

                if current_fen != last_fen and last_fen is not None:
                    result = await analyze_fen_sequence(last_fen, current_fen, color_to_move)
                    if result:
                        annotation, score_diff = result
                        piece = "♙ Blanc" if color_to_move == "white" else "♟️ Noir"
                        await discord_channel.send(f"{piece} joue : **{annotation}** ({score_diff})")
                    color_to_move = "black" if color_to_move == "white" else "white"

                last_fen = current_fen

            # Extraction du PGN
            await page.locator("button.share-button-component").click(timeout=30000)
            await page.locator('div.share-menu-tab-component-header:has-text("PGN")').click(timeout=20000)
            pgn_text = await page.input_value('textarea.share-menu-tab-pgn-textarea', timeout=20000)

            video_path = await page.video.path()
            await context.close()
            await browser.close()

            return pgn_text, video_path

        except Exception as e:
            try:
                video_path = await page.video.path()
            except:
                pass
            await context.close()
            await browser.close()
            raise ScrapingError(str(e), video_path=video_path)