import os
import asyncio
import discord
from discord.ext import commands
from playwright.async_api import async_playwright
from dotenv import load_dotenv
import subprocess

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
INSTA_USERNAME = os.getenv("INSTA_USERNAME")
INSTA_PASSWORD = os.getenv("INSTA_PASSWORD")
ACCOUNT_TO_WATCH = os.getenv("ACCOUNT_TO_WATCH")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

async def record_screen(duration=30):
    output_file = "/tmp/insta_record.mp4"
    cmd = [
        "ffmpeg",
        "-video_size", "1280x720",
        "-framerate", "25",
        "-f", "x11grab",
        "-i", ":99.0",
        "-t", str(duration),
        output_file
    ]
    return await asyncio.create_subprocess_exec(*cmd)

@bot.command()
async def insta(ctx):
    await ctx.send("📸 Lancement de l'enregistrement Instagram...")

    try:
        ffmpeg_proc = await record_screen(duration=30)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False, args=["--display=:99"])
            context = await browser.new_context(viewport={"width": 1280, "height": 720})
            page = await context.new_page()

            await page.goto("https://www.instagram.com/accounts/login/", timeout=60000)
            await page.fill('input[name="username"]', INSTA_USERNAME)
            await page.fill('input[name="password"]', INSTA_PASSWORD)
            await page.click('button[type="submit"]')
            await page.wait_for_timeout(5000)

            await page.goto(f"https://www.instagram.com/{ACCOUNT_TO_WATCH}/", timeout=60000)
            await page.wait_for_timeout(25000)

            await browser.close()

        await ffmpeg_proc.wait()
        await ctx.send("🎥 Enregistrement terminé.", file=discord.File("/tmp/insta_record.mp4"))

    except Exception as e:
        error_text = str(e)
        if len(error_text) > 1900:
            error_text = error_text[:1900]
        await ctx.send(f"❌ Erreur : {error_text}")

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)