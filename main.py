import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from playwright.async_api import async_playwright
import subprocess
import uuid
from pathlib import Path

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
INSTA_USERNAME = os.getenv("INSTA_USERNAME")
INSTA_PASSWORD = os.getenv("INSTA_PASSWORD")

bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

@bot.command()
async def insta(ctx):
    await ctx.send("📲 Connexion à Instagram...")

    video_path = f"/tmp/insta_{uuid.uuid4().hex}.webm"
    screen_size = "1280x720"

    # Lance l'enregistrement écran avec ffmpeg
    ffmpeg_process = subprocess.Popen([
        "ffmpeg", "-y",
        "-video_size", screen_size,
        "-f", "x11grab",
        "-i", os.environ.get("DISPLAY", ":0"),
        "-r", "25",
        "-codec:v", "libvpx",
        video_path
    ])

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(viewport={"width": 1280, "height": 720})
            page = await context.new_page()

            await page.goto("https://www.instagram.com/accounts/login/")
            await page.wait_for_selector("input[name='username']")

            await page.fill("input[name='username']", INSTA_USERNAME)
            await page.fill("input[name='password']", INSTA_PASSWORD)
            await page.click("button[type='submit']")

            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(5000)  # Attendre que l'accueil charge

            # Va sur ton profil par exemple
            await page.goto(f"https://www.instagram.com/{INSTA_USERNAME}/")
            await page.wait_for_timeout(5000)

            await browser.close()

    finally:
        ffmpeg_process.terminate()
        await ctx.send("🎥 Traitement terminé, envoi de la vidéo...")
        await asyncio.sleep(2)

        if Path(video_path).exists():
            await ctx.send(file=discord.File(video_path))
        else:
            await ctx.send("❌ Échec de l'enregistrement vidéo.")

bot.run(DISCORD_TOKEN)