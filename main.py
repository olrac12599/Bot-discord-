import os
import asyncio
from pathlib import Path

import discord
from discord.ext import commands

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")
DISCORD_FILE_LIMIT_BYTES = 8 * 1024 * 1024  # 8 Mo

videos_dir = Path("videos")
videos_dir.mkdir(exist_ok=True)

last_video_paths = {}  # channel_id -> str
active_sessions = {}   # channel_id -> {"page": ..., "context": ..., "browser": ...}

# --- EXCEPTION PERSONNALISÉE ---
class ScrapingError(Exception):
    def __init__(self, message, video_path=None):
        super().__init__(message)
        self.video_path = video_path

# --- SCRAPING AVEC ENREGISTREMENT VIDÉO ---
async def get_pgn_from_chess_com(url: str, username: str, password: str, channel_id: int) -> (str, str):
    stealth = Stealth()
    async with stealth.use_async(async_playwright()) as p:
        browser = await p.chromium.launch(
            headless=False,  # True en prod
            args=[
                "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-dev-shm-usage", "--disable-gpu"
            ]
        )
        context = await browser.new_context(record_video_dir=str(videos_dir))
        page = await context.new_page()

        # Enregistrement de la session
        active_sessions[channel_id] = {
            "page": page,
            "context": context,
            "browser": browser
        }

        video_path = None
        pgn_text = None
        error = None

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
            await page.wait_for_timeout(2000)

            # Clic sur Share
            try:
                await page.get_by_role("button", name="Share").click(timeout=15000)
                await page.wait_for_timeout(1000)
            except Exception as e:
                raise ScrapingError(f"Erreur en cliquant sur 'Share': {e}")

            # Onglet PGN
            try:
                await page.get_by_role("tab", name="PGN").click(timeout=5000)
                await page.wait_for_timeout(1000)
                pgn_text = await page.locator("textarea.share-menu-tab-pgn-textarea").input_value(timeout=10000)
            except Exception as e:
                raise ScrapingError(f"Erreur en récupérant le PGN: {e}")

        except Exception as e:
            error = str(e)

        if pgn_text:
            return pgn_text, None  # La vidéo sera récupérée plus tard par !vidéo
        else:
            raise ScrapingError(error or "Erreur inconnue", video_path=None)

# --- DISCORD BOT ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- !chess ---
@bot.command(name="chess")
async def get_chess_pgn(ctx, url: str):
    msg = await ctx.send("🕵️ Connexion à Chess.com et enregistrement vidéo en cours...")
    try:
        pgn, _ = await get_pgn_from_chess_com(url, CHESS_USERNAME, CHESS_PASSWORD, ctx.channel.id)
        pgn_short = (pgn[:1900] + "...") if len(pgn) > 1900 else pgn
        await msg.edit(content=f"✅ **PGN récupéré :**\n```\n{pgn_short}\n```\n*Utilisez `!vidéo` pour récupérer la vidéo.*")
    except ScrapingError as e:
        await msg.edit(content="❌ Erreur lors du scraping.")
        if e.video_path:
            last_video_paths[ctx.channel.id] = e.video_path
            await ctx.send("🎥 Voici la vidéo de la session échouée :", file=discord.File(e.video_path, "debug_video.webm"))
        else:
            await ctx.send("❌ Aucun enregistrement vidéo disponible.")

# --- !vidéo ---
@bot.command(name="vidéo")
async def force_send_video(ctx):
    session = active_sessions.get(ctx.channel.id)
    if not session:
        return await ctx.send("❌ Aucune session d'enregistrement active pour ce salon.")

    page = session["page"]
    context = session["context"]
    browser = session["browser"]

    try:
        await page.wait_for_timeout(1000)
        video_path = await page.video.path()

        await context.close()
        await browser.close()

        del active_sessions[ctx.channel.id]
        last_video_paths[ctx.channel.id] = video_path

        video_file = Path(video_path)
        if not video_file.exists():
            return await ctx.send("❌ Vidéo introuvable.")
        
        if video_file.stat().st_size < DISCORD_FILE_LIMIT_BYTES:
            await ctx.send("📽️ Vidéo enregistrée :", file=discord.File(str(video_file), "debug_video.webm"))
        else:
            await ctx.send(f"📦 Vidéo trop lourde ({video_file.stat().st_size / 1_000_000:.2f} Mo).")
    except Exception as e:
        await ctx.send(f"❌ Erreur lors de la récupération de la vidéo : {e}")

# --- !cam (ancienne méthode de lecture vidéo) ---
@bot.command(name="cam")
async def send_last_video(ctx):
    video_path_str = last_video_paths.get(ctx.channel.id)
    if not video_path_str:
        return await ctx.send("❌ Aucune vidéo récente trouvée.")

    video_file = Path(video_path_str)
    if not video_file.exists():
        return await ctx.send("❌ Fichier vidéo introuvable.")

    if video_file.stat().st_size < DISCORD_FILE_LIMIT_BYTES:
        await ctx.send("📹 Voici la vidéo de la dernière opération :", file=discord.File(str(video_file), "debug_video.webm"))
    else:
        await ctx.send(f"📦 Vidéo trop lourde ({video_file.stat().st_size / 1_000_000:.2f} Mo).")

# --- !ping ---
@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(f"Pong! Latence : {round(bot.latency * 1000)}ms")

# --- on_ready ---
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}.")

# --- LANCEMENT ---
async def main():
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot arrêté.")