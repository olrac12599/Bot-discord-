import os
import discord
import asyncio
from discord.ext import commands
from playwright.async_api import async_playwright, Error as PlaywrightError

# Variables Railway
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
INSTA_USERNAME = os.getenv("INSTA_USERNAME")
INSTA_PASSWORD = os.getenv("INSTA_PASSWORD")
ACCOUNT_TO_WATCH = os.getenv("ACCOUNT_TO_WATCH")

# Vérification des variables
for var, name in [(DISCORD_TOKEN, "DISCORD_TOKEN"),
                  (INSTA_USERNAME, "INSTA_USERNAME"),
                  (INSTA_PASSWORD, "INSTA_PASSWORD"),
                  (ACCOUNT_TO_WATCH, "ACCOUNT_TO_WATCH")]:
    if not var:
        print(f"❌ Erreur : {name} non défini.")
        exit(1)

# Setup bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command()
async def insta(ctx):
    await ctx.send("🔍 Lancement de l'automatisation Instagram...")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=["--no-sandbox"]
            )
            context = await browser.new_context(viewport={"width": 1280, "height": 720})
            page = await context.new_page()

            # Page login
            await page.goto("https://www.instagram.com/accounts/login/", timeout=60000)
            await page.wait_for_selector('input[name="username"]')
            await page.screenshot(path="/tmp/step1_login.png")

            # Login
            await page.fill('input[name="username"]', INSTA_USERNAME)
            await page.fill('input[name="password"]', INSTA_PASSWORD)
            await page.screenshot(path="/tmp/step2_credentials.png")
            await page.click('button[type="submit"]')
            await page.wait_for_timeout(7000)
            await page.screenshot(path="/tmp/step3_loggedin.png")

            # Bypass popups
            try:
                await page.locator("text=Not Now, Plus tard").click(timeout=5000)
            except:
                pass

            # Profile page
            await page.goto(f"https://www.instagram.com/{ACCOUNT_TO_WATCH}/", timeout=60000)
            await page.wait_for_load_state("networkidle")
            await page.screenshot(path="/tmp/step4_account.png")

            await browser.close()

            # Send images
            files = [
                discord.File("/tmp/step1_login.png"),
                discord.File("/tmp/step2_credentials.png"),
                discord.File("/tmp/step3_loggedin.png"),
                discord.File("/tmp/step4_account.png"),
            ]
            await ctx.send("✅ Instagram visité. Captures d'écran :", files=files)

    except Exception as e:
        trg = f"❌ Erreur : {type(e).__name__} — {str(e)[:1900]}"
        await ctx.send(trg)
        try:
            await page.screenshot(path="/tmp/error.png")
            await ctx.send("📸 Aperçu de l'erreur :", file=discord.File("/tmp/error.png"))
        except:
            pass
        if browser:
            await browser.close()

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)