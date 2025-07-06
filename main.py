import os
import asyncio
from discord.ext import commands
import discord
from dotenv import load_dotenv
from playwright.async_api import async_playwright
import datetime

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
INSTAGRAM_USERNAME = os.getenv("name")
INSTAGRAM_PASSWORD = os.getenv("mdp")
ACCOUNT_TO_WATCH = os.getenv("name2")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


async def record_screen(duration: int = 30, output_file="screen.mp4"):
    """Lance ffmpeg pour enregistrer l'écran."""
    filename = f"/tmp/{output_file}"
    cmd = [
        "ffmpeg",
        "-y",
        "-video_size", "1280x720",
        "-f", "x11grab",
        "-i", ":99.0",
        "-t", str(duration),
        "-r", "30",
        "-codec:v", "libx264",
        "-preset", "ultrafast",
        filename
    ]
    proc = await asyncio.create_subprocess_exec(*cmd)
    await proc.communicate()
    return filename


async def run_playwright():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--no-sandbox"])
        context = await browser.new_context(viewport={"width": 1280, "height": 720})
        page = await context.new_page()

        await page.goto("https://www.instagram.com/accounts/login/")
        await page.wait_for_timeout(5000)

        await page.fill("input[name='username']", INSTAGRAM_USERNAME)
        await page.fill("input[name='password']", INSTAGRAM_PASSWORD)
        await page.click("button[type='submit']")

        await page.wait_for_timeout(7000)  # Attente après login

        if ACCOUNT_TO_WATCH:
            await page.goto(f"https://www.instagram.com/{ACCOUNT_TO_WATCH}/")
            await page.wait_for_timeout(15000)  # Laisse le temps à l'utilisateur de voir

        await browser.close()


@bot.command()
async def insta(ctx):
    await ctx.send("⏳ Lancement de l'enregistrement et de la session Instagram...")

    try:
        screen_task = asyncio.create_task(record_screen(duration=30))
        await run_playwright()
        video_path = await screen_task

        await ctx.send("📹 Voici la vidéo enregistrée :", file=discord.File(video_path))

    except Exception as e:
        await ctx.send(f"❌ Erreur : {e}")


@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)