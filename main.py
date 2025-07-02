# --- IMPORTS ---
import discord
from discord.ext import commands
import os
import asyncio
from enum import Enum, auto
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth
import io
from pathlib import Path

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")
DISCORD_FILE_LIMIT_BYTES = 8 * 1024 * 1024  # 8 Mo
videos_dir = Path("videos")
videos_dir.mkdir(exist_ok=True)

bot = commands.Bot(command_prefix="!")
last_video_paths = {}

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
        context = await browser.new_context(
            record_video_dir=str(videos_dir),
        )
        page = await context.new_page()

        try:
            login_successful = False
            for attempt in range(max_retries):
                print(f"Tentative de connexion n°{attempt + 1}/{max_retries}...")
                await page.goto("/login_and_go", timeout=90000)
                await page.wait_for_load_state('domcontentloaded')

                if await page.is_visible("text=Verify you are human"):
                    raise ScrapingError("Bloqué par le CAPTCHA de Cloudflare avant la connexion.")

                try:
                    await page.get_by_role("button", name="I Accept").click(timeout=5000)
                except PlaywrightTimeoutError:
                    pass

                await page.get_by_placeholder("Username, Phone, or Email").type(username, delay=50)
                await page.get_by_placeholder("Password").type(password, delay=50)
                await page.get_by_role("button", name="Log In").click()

                try:
                    await page.wait_for_url("**/home", timeout=15000)
                    login_successful = True
                    break
                except PlaywrightTimeoutError:
                    if await page.is_visible("text=This password is incorrect"):
                        continue
                    else:
                        raise ScrapingError("Erreur inattendue après la tentative de connexion.")

            if not login_successful:
                raise ScrapingError(f"Échec de la connexion après {max_retries} tentatives.")

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

            if isinstance(e, ScrapingError):
                raise ScrapingError(e, screenshot_bytes=screenshot_bytes, video_path=video_path)
            else:
                raise ScrapingError(f"Détails: {e}", screenshot_bytes=screenshot_bytes, video_path=video_path)

# --- COMMANDES DISCORD ---
@bot.command(name="chess")
async def get_chess_pgn(ctx, url: str):
    msg = await ctx.send("🕵️ **Lancement du scraping en mode furtif...** Connexion à Chess.com.")
    try:
        pgn, video_path = await get_pgn_from_chess_com(url, CHESS_USERNAME, CHESS_PASSWORD)
        if video_path:
            last_video_paths[ctx.channel.id] = video_path
        pgn_short = (pgn[:1900] + "...") if len(pgn) > 1900 else pgn
        await msg.edit(content=f"✅ **PGN récupéré !**\n```\n{pgn_short}\n```\n*Utilisez `!cam` pour voir la vidéo de l'opération.*")
    except ScrapingError as e:
        await msg.edit(content=f"❌ **Erreur de scraping.**")
        if e.video_path:
            last_video_paths[ctx.channel.id] = e.video_path
        files = [discord.File(io.BytesIO(e.screenshot_bytes), "debug.png")] if e.screenshot_bytes else []
        await ctx.send(f"**Erreur :** {e}", files=files)
        if e.video_path:
            await ctx.send(f"Utilisez `!cam` pour voir la vidéo de la session qui a échoué.")
    except Exception as e:
        await msg.edit(content=f"❌ Erreur système: {e}")

@bot.command(name="cam")
async def send_last_video(ctx):
    video_path_str = last_video_paths.get(ctx.channel.id)
    if not video_path_str:
        return await ctx.send("❌ Aucune vidéo récente trouvée.")
    video_file = Path(video_path_str)
    if not video_file.exists():
        return await ctx.send("❌ Fichier vidéo introuvable.")
    if video_file.stat().st_size < DISCORD_FILE_LIMIT_BYTES:
        await ctx.send("📹 Voici la vidéo de la dernière opération `!chess` :", file=discord.File(str(video_file), "debug_video.webm"))
    else:
        await ctx.send(f"📹 Vidéo trop lourde ({video_file.stat().st_size / 1_000_000:.2f} Mo).")

@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(f"Pong! Latence : {round(bot.latency * 1000)}ms")

# --- DÉMARRAGE ---
@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user}.")

async def main():
    await bot.start(DISCORD_TOKEN)

try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("\nArrêt du bot.")