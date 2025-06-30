import os
import time
import discord
import asyncio
import mss
import cv2
import numpy as np
import chromedriver_autoinstaller
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from discord.ext import commands
from moviepy.editor import VideoFileClip
from playwright.async_api import async_playwright
from playwright_stealth.async_api import stealth_async
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")

VIDEO_PATH = "recording.mp4"
COMPRESSED_PATH = "compressed.mp4"

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)
last_error = ""
last_video_path = None

# --- Fonction Playwright furtive pour récupérer PGN ---
class ScrapingError(Exception):
    pass

async def get_pgn_from_chess_com(url: str, username: str, password: str):
    videos_dir = Path("debug_videos")
    videos_dir.mkdir(exist_ok=True)
    browser_args = ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=browser_args)
        context = await browser.new_context(
            record_video_dir=str(videos_dir),
            record_video_size={"width": 1280, "height": 720},
            base_url="https://www.chess.com"
        )
        page = await context.new_page()
        await stealth_async(page)
        try:
            await page.goto("/login_and_go", timeout=90000)
            await page.wait_for_load_state('domcontentloaded')

            await page.get_by_placeholder("Username, Phone, or Email").type(username, delay=50)
            await page.get_by_placeholder("Password").type(password, delay=50)
            await page.get_by_role("button", name="Log In").click()
            await page.wait_for_url("**/home", timeout=15000)

            await page.goto(url, timeout=90000)
            await page.locator("button.share-button-component").click(timeout=30000)
            await page.locator('div.share-menu-tab-component-header:has-text("PGN")').click(timeout=20000)
            pgn_text = await page.input_value('textarea.share-menu-tab-pgn-textarea', timeout=20000)

            video_path = await page.video.path()
            await context.close()
            await browser.close()
            return pgn_text, video_path
        except Exception as e:
            await context.close()
            await browser.close()
            raise ScrapingError(str(e))

# --- Fonctions du second script (enregistrement vidéo + compression) ---

def record_game(url, duration=10):
    global last_error
    driver = None
    try:
        chromedriver_autoinstaller.install()
        chrome_options = Options()
        # chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1280,720")

        driver = webdriver.Chrome(options=chrome_options)
        driver.get(url)
        time.sleep(3)

        with mss.mss() as sct:
            monitor = sct.monitors[0]
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            out = cv2.VideoWriter(VIDEO_PATH, fourcc, 10.0, (monitor["width"], monitor["height"]))
            start_time = time.time()
            while time.time() - start_time < duration:
                img = np.array(sct.grab(monitor))
                frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                out.write(frame)
                time.sleep(0.01)
            out.release()
        return True
    except Exception as e:
        last_error = f"[Erreur record_game] {e}"
        return False
    finally:
        if driver:
            driver.quit()

def compress_video():
    global last_error
    try:
        clip = VideoFileClip(VIDEO_PATH)
        clip_resized = clip.resize(height=360)
        clip_resized.write_videofile(COMPRESSED_PATH, bitrate="500k", codec="libx264", audio=False)
        return COMPRESSED_PATH
    except Exception as e:
        last_error = f"[Erreur compress_video] {e}"
        return None

# --- Commandes Discord ---

@bot.command()
async def chess(ctx, url: str):
    if "chess.com/game/live/" not in url and "chess.com/play/game/" not in url:
        await ctx.send("❌ URL invalide. L'URL doit provenir d'une partie sur Chess.com.")
        return

    msg = await ctx.send("🕵️ **Lancement du scraping furtif...** Connexion à Chess.com.")
    try:
        pgn, video_path = await get_pgn_from_chess_com(url, CHESS_USERNAME, CHESS_PASSWORD)
        pgn_short = (pgn[:1900] + "...") if len(pgn) > 1900 else pgn
        await msg.edit(content=f"✅ **PGN récupéré !**\n```\n{pgn_short}\n```\n*Vidéo enregistrée en debug.*")
        # Optionnel: gérer video_path, sauvegarde, etc.
    except ScrapingError as e:
        await msg.edit(content=f"❌ Erreur lors du scraping: {e}")

@bot.command()
async def record(ctx, url: str):
    await ctx.send(f"Enregistrement vidéo de la partie : {url}")
    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(None, record_game, url)
    if success:
        await ctx.send("✅ Partie enregistrée ! Utilise `!cam` pour récupérer la vidéo.")
    else:
        await ctx.send("❌ Erreur lors de l'enregistrement vidéo.")
        if last_error:
            await ctx.send(f"🪵 Log : ```{last_error}```")

@bot.command()
async def cam(ctx):
    if not os.path.exists(VIDEO_PATH):
        await ctx.send("⚠️ Aucune vidéo enregistrée.")
        return

    await ctx.send("Compression de la vidéo...")
    loop = asyncio.get_event_loop()
    compressed = await loop.run_in_executor(None, compress_video)
    if compressed and os.path.exists(compressed):
        size = os.path.getsize(compressed)
        if size < 8 * 1024 * 1024:
            await ctx.send("🎥 Voici la vidéo compressée :", file=discord.File(compressed))
        else:
            await ctx.send("🚫 La vidéo reste trop grosse même après compression.")
    else:
        await ctx.send("❌ Erreur lors de la compression.")
        if last_error:
            await ctx.send(f"🪵 Log : ```{last_error}```")

if __name__ == "__main__":
    print("[INFO] Bot en cours de démarrage...")
    bot.run(DISCORD_TOKEN)