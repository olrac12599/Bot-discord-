import os
import discord
from discord.ext import commands
from playwright.async_api import async_playwright

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
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context()
            page = await context.new_page()

            await page.goto("https://www.instagram.com/accounts/login/")
            await page.wait_for_selector('input[name="username"]', timeout=15000)

            await page.fill('input[name="username"]', INSTA_USERNAME)
            await page.fill('input[name="password"]', INSTA_PASSWORD)
            await page.click('button[type="submit"]')
            await page.wait_for_timeout(7000)

            # Aller sur le compte à surveiller
            await page.goto(f"https://www.instagram.com/{ACCOUNT_TO_WATCH}/")
            await page.wait_for_load_state("networkidle")
            await page.screenshot(path="/tmp/insta.png")

            await browser.close()

            await ctx.send("✅ Profil visité !", file=discord.File("/tmp/insta.png"))

    except Exception as e:
        error = str(e)
        if len(error) > 1900:
            error = error[:1900]
        await ctx.send(f"❌ Erreur : {error}")

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

if __name__ == "__main__":
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        print("❌ Le token DISCORD est manquant.")