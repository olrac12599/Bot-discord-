import os
import asyncio
import discord
from discord.ext import commands
from playwright.async_api import async_playwright
from datetime import datetime

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
INSTA_USERNAME = os.getenv("INSTA_USERNAME")
INSTA_PASSWORD = os.getenv("INSTA_PASSWORD")
ACCOUNT_TO_WATCH = os.getenv("ACCOUNT_TO_WATCH")

# Vérification des variables d'environnement
if not DISCORD_TOKEN or not INSTA_USERNAME or not INSTA_PASSWORD or not ACCOUNT_TO_WATCH:
    raise ValueError("❌ .env incomplet : vérifie les variables INSTA_USERNAME, INSTA_PASSWORD, ACCOUNT_TO_WATCH et DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

async def take_screenshot(page, name="error"):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"/tmp/screenshot_{name}_{timestamp}.png"
    await page.screenshot(path=path)
    return path

@bot.command()
async def insta(ctx):
    await ctx.send("📸 Lancement du bot Instagram...")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1280, "height": 720})
            page = await context.new_page()

            await page.goto("https://www.instagram.com/accounts/login/", timeout=60000)
            await page.fill('input[name="username"]', INSTA_USERNAME)
            await page.fill('input[name="password"]', INSTA_PASSWORD)
            await page.click('button[type="submit"]')
            await page.wait_for_timeout(5000)

            await page.goto(f"https://www.instagram.com/{ACCOUNT_TO_WATCH}/", timeout=60000)
            await page.wait_for_timeout(10000)

            await page.screenshot(path="/tmp/insta_done.png")
            await ctx.send("✅ Instagram visité avec succès.", file=discord.File("/tmp/insta_done.png"))

            await browser.close()

    except Exception as e:
        error_message = f"{type(e).__name__}: {e}"
        screenshot_path = "/tmp/insta_error.png"
        try:
            await page.screenshot(path=screenshot_path)
            await ctx.send("❌ Erreur détectée. Voici le screenshot :", file=discord.File(screenshot_path))
        except Exception as screenshot_err:
            await ctx.send(f"⚠️ Impossible de prendre une capture : {screenshot_err}")
        if len(error_message) > 1900:
            error_message = error_message[:1900]
        await ctx.send(f"❌ Erreur : {error_message}")

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)