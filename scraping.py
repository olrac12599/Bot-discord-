import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth
from pathlib import Path

videos_dir = Path("videos")
videos_dir.mkdir(exist_ok=True)

class ScrapingError(Exception):
    def __init__(self, message, screenshot_bytes=None, video_path=None):
        super().__init__(message)
        self.screenshot_bytes = screenshot_bytes
        self.video_path = video_path

async def get_pgn_from_chess_com(url: str, username: str, password: str) -> (str, str):
    max_retries = 3
    browser_args = ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']

    stealth = Stealth()
    async with stealth.use_async(async_playwright()) as p:
        browser = await p.chromium.launch(headless=True, args=browser_args)
        context = await browser.new_context(record_video_dir=str(videos_dir))
        page = await context.new_page()

        try:
            for attempt in range(max_retries):
                await page.goto("https://www.chess.com/login_and_go", timeout=90000)
                await page.wait_for_load_state('domcontentloaded')

                if await page.is_visible("text=Verify you are human"):
                    raise ScrapingError("Bloqué par CAPTCHA Cloudflare")

                try:
                    await page.get_by_role("button", name="I Accept").click(timeout=5000)
                except PlaywrightTimeoutError:
                    pass

                await page.get_by_placeholder("Username, Phone, or Email").type(username, delay=50)
                await page.get_by_placeholder("Password").type(password, delay=50)
                await page.get_by_role("button", name="Log In").click()

                try:
                    await page.wait_for_url("**/home", timeout=15000)
                    break
                except PlaywrightTimeoutError:
                    if await page.is_visible("text=This password is incorrect"):
                        continue
                    raise ScrapingError("Erreur de connexion")

            await page.goto(url, timeout=90000)
            await page.locator("button.share-button-component").click(timeout=30000)
            await page.locator('div.share-menu-tab-component-header:has-text("PGN")').click(timeout=20000)
            pgn_text = await page.input_value('textarea.share-menu-tab-pgn-textarea', timeout=20000)

            video_path = await page.video.path()
            await context.close()
            await browser.close()
            return pgn_text, video_path

        except Exception as e:
            screenshot_bytes = None
            video_path = None
            try:
                video_path = await page.video.path()
            except:
                pass
            if not page.is_closed():
                screenshot_bytes = await page.screenshot(full_page=True)
            await context.close()
            await browser.close()

            raise ScrapingError(str(e), screenshot_bytes=screenshot_bytes, video_path=video_path)