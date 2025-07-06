import os
import asyncio
import discord
from discord.ext import commands
from playwright.async_api import async_playwright
from dotenv import load_dotenv
import subprocess

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
IG_USERNAME = os.getenv("name")
IG_PASSWORD = os.getenv("mdp")
ACCOUNT_TO_WATCH = os.getenv("name2")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

VIDEO_PATH = "/tmp/insta_record.mp4"

async def record_screen(duration=30):
    cmd = [
        "ffmpeg", "-y",
        "-video_size", "1280x720",
        "-f", "x11grab", "-i", ":99.0",
        "-t", str(duration),
        "-pix_fmt", "yuv420p",
        VIDEO_PATH
    ]
    return await asyncio.create_subprocess_exec(*cmd)

async def visit_instagram():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--window-size=1280,720"])
        context = await browser.new_context(viewport={"width": 1280, "height": 720})
        page = await context.new_page()

        await page.goto("https://www.instagram.com/accounts/login/")
        await page.wait_for_selector("input[name='username']")

        await page.fill("input[name='username']", IG_USERNAME)
        await page.fill("input[name='password']", IG_PASSWORD)
        await page.click("button[type='submit']")

        await page.wait_for_timeout(5000)
        await page.goto(f"https://www.instagram.com/{ACCOUNT_TO_WATCH}/")
        await page.wait_for_timeout(10000)

        await browser.close()

@bot.command()
async def insta(ctx):
    await ctx.send("📸 Lancement de l'enregistrement et connexion à Instagram...")

    ffmpeg_proc = await record_screen(duration=30)
    await asyncio.sleep(3)  # Petit délai avant d’ouvrir le navigateur

    await visit_instagram()
    await ffmpeg_proc.wait()

    if os.path.exists(VIDEO_PATH):
        await ctx.send("🎥 Voici l'enregistrement :", file=discord.File(VIDEO_PATH))
    else:
        await ctx.send("❌ Aucune vidéo trouvée.")

@bot.event
async def on_ready():
    print(f"✅ Bot connecté en tant que {bot.user}")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)