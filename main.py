 import os
import discord
import asyncio
from discord.ext import commands
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
INSTA_USERNAME = os.getenv("INSTA_USERNAME")
INSTA_PASSWORD = os.getenv("INSTA_PASSWORD")
ACCOUNT_TO_WATCH = os.getenv("ACCOUNT_TO_WATCH")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command()
async def insta(ctx):
    await ctx.send("📸 Connexion à Instagram en cours...")

    try:
        output_path = "/tmp/insta_record.webm"
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--use-gl=egl"])
            context = await browser.new_context(record_video_dir="/tmp", viewport={"width": 1280, "height": 720})
            page = await context.new_page()

            await page.goto("https://www.instagram.com/accounts/login/")
            await page.fill('input[name="Username, email or mobile number"]', INSTA_USERNAME)
            await page.fill('input[name="Password"]', INSTA_PASSWORD)
            await page.click('button[type="submit"]')
            await page.wait_for_timeout(5000)

            await page.goto(f"https://www.instagram.com/{ACCOUNT_TO_WATCH}/")
            await page.wait_for_timeout(25000)

            await browser.close()

            # Chercher la vidéo générée
            video_path = None
            for file in os.listdir("/tmp"):
                if file.endswith(".webm"):
                    video_path = os.path.join("/tmp", file)
                    break

            if video_path and os.path.exists(video_path):
                await ctx.send("🎥 Enregistrement terminé !", file=discord.File(video_path))
            else:
                await ctx.send("❌ Aucune vidéo trouvée.")

    except Exception as e:
        msg = str(e)
        if len(msg) > 1900:
            msg = msg[:1900]
        await ctx.send(f"❌ Erreur : {msg}")

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)