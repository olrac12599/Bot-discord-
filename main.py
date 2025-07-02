import os
import io
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
last_video_paths = {}
active_sessions = {}

class ScrapingError(Exception):
    def __init__(self, message, video_path=None):
        super().__init__(message)
        self.video_path = video_path

# --- SCRAPING ---
async def get_pgn_from_chess_com(url: str, username: str, password: str, channel_id: int):
    stealth = Stealth()
    async with stealth.use_async(async_playwright()) as p:
        browser = await p.chromium.launch(headless=True, args=[
            '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu'
        ])
        context = await browser.new_context(record_video_dir=str(videos_dir))
        page = await context.new_page()

        # ⚠️ Enregistre la session dès maintenant
        active_sessions[channel_id] = {
            "page": page,
            "context": context,
            "browser": browser
        }

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

            await page.locator("button.share-button-component").click(timeout=30000)
            await page.locator('div.share-menu-tab-component-header:has-text("PGN")').click(timeout=20000)
            pgn_text = await page.input_value('textarea.share-menu-tab-pgn-textarea', timeout=20000)

            video_path = await page.video.path()
            last_video_paths[channel_id] = video_path

            await context.close()
            await browser.close()
            active_sessions.pop(channel_id, None)

            return pgn_text, video_path

        except Exception as e:
            try:
                video_path = await page.video.path()
                last_video_paths[channel_id] = video_path
            except Exception:
                video_path = None
            await context.close()
            await browser.close()
            active_sessions.pop(channel_id, None)
            raise ScrapingError(str(e), video_path=video_path)

# --- BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command(name="chess")
async def get_chess_pgn(ctx, url: str):
    msg = await ctx.send("🕵️ Connexion à Chess.com et enregistrement vidéo en cours...")
    try:
        pgn, video_path = await get_pgn_from_chess_com(url, CHESS_USERNAME, CHESS_PASSWORD, ctx.channel.id)
        pgn_short = (pgn[:1900] + "...") if len(pgn) > 1900 else pgn
        await msg.edit(content=f"✅ **PGN récupéré :**\n```\n{pgn_short}\n```\n*Utilisez `!cam` ou `!vidéo` pour voir l'enregistrement.*")
    except ScrapingError as e:
        await msg.edit(content="❌ Erreur lors du scraping.")
        if e.video_path:
            await ctx.send("🎥 Voici la vidéo de la session échouée :", file=discord.File(e.video_path, "debug_video.webm"))
        else:
            await ctx.send("❌ Aucun enregistrement vidéo disponible.")

@bot.command(name="cam")
async def send_last_video(ctx):
    video_path = last_video_paths.get(ctx.channel.id)
    if not video_path or not Path(video_path).exists():
        return await ctx.send("❌ Aucune vidéo récente trouvée.")
    if Path(video_path).stat().st_size < DISCORD_FILE_LIMIT_BYTES:
        await ctx.send("📹 Voici la vidéo de la dernière opération :", file=discord.File(video_path, "debug_video.webm"))
    else:
        await ctx.send(f"📦 Vidéo trop lourde ({Path(video_path).stat().st_size / 1_000_000:.2f} Mo).")

@bot.command(name="vidéo")
async def force_stop_recording(ctx):
    session = active_sessions.get(ctx.channel.id)
    if not session:
        return await ctx.send("❌ Aucune session d'enregistrement active pour ce salon.")

    page = session["page"]
    context = session["context"]
    browser = session["browser"]

    try:
        video_path = await page.video.path()
        last_video_paths[ctx.channel.id] = video_path
        await context.close()
        await browser.close()
        active_sessions.pop(ctx.channel.id, None)
        if Path(video_path).stat().st_size < DISCORD_FILE_LIMIT_BYTES:
            await ctx.send("📥 Enregistrement vidéo terminé :", file=discord.File(video_path, "debug_video.webm"))
        else:
            await ctx.send(f"📦 Vidéo trop lourde ({Path(video_path).stat().st_size / 1_000_000:.2f} Mo).")
    except Exception as e:
        await ctx.send(f"❌ Erreur lors de l'arrêt de l'enregistrement : {e}")

@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(f"Pong! Latence : {round(bot.latency * 1000)}ms")

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}.")

async def main():
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot arrêté.")