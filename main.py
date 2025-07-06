import os
import asyncio
import discord
from discord.ext import commands
from playwright.async_api import async_playwright
from pathlib import Path

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
INSTA_USERNAME = os.getenv("INSTA_USERNAME")
INSTA_PASSWORD = os.getenv("INSTA_PASSWORD")
ACCOUNT_TO_WATCH = os.getenv("ACCOUNT_TO_WATCH")

video_path = "/tmp/record.webm"
recording = None

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.command()
async def insta(ctx):
    global recording

    await ctx.send("🚀 Connexion à Instagram en cours...")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(record_video_dir="/tmp", record_video_size={"width": 1280, "height": 720})
            page = await context.new_page()

            await page.goto("https://www.instagram.com/accounts/login/")
            await page.wait_for_selector('input[name="username"]')

            await page.fill('input[name="username"]', INSTA_USERNAME)
            await page.fill('input[name="password"]', INSTA_PASSWORD)
            await page.click('button[type="submit"]')
            await page.wait_for_timeout(5000)

            await page.goto(f"https://www.instagram.com/{ACCOUNT_TO_WATCH}/")
            await page.wait_for_timeout(15000)

            await page.screenshot(path="/tmp/success.png")

            recording = context.pages[0].video
            await ctx.send("✅ Enregistrement en cours... Vous pouvez taper `!stop` pour l'arrêter.")

    except Exception as e:
        try:
            await page.screenshot(path="/tmp/error.png")
            await ctx.send("❌ Erreur détectée :", file=discord.File("/tmp/error.png"))
        except:
            pass
        await ctx.send(f"❌ Erreur : {str(e)[:1900]}")


@bot.command()
async def stop(ctx):
    global recording

    if recording:
        await ctx.send("🛑 Arrêt de l'enregistrement...")
        video_file = recording.path()
        recording = None

        await asyncio.sleep(2)  # Laisser le temps à Playwright de finaliser la vidéo
        if Path(video_file).exists():
            await ctx.send("🎥 Voici la vidéo :", file=discord.File(video_file))
        else:
            await ctx.send("⚠️ Aucun fichier vidéo trouvé.")
    else:
        await ctx.send("⚠️ Aucun enregistrement en cours.")


@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")


if __name__ == "__main__":
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        print("❌ Le token Discord est manquant.")