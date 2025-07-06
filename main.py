import os
import asyncio
import discord
from discord.ext import commands
from playwright.async_api import async_playwright, Error as PlaywrightError

# --- VARIABLES ENV ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
INSTA_USERNAME = os.getenv("INSTA_USERNAME")
INSTA_PASSWORD = os.getenv("INSTA_PASSWORD")
ACCOUNT_TO_WATCH = os.getenv("ACCOUNT_TO_WATCH")

# --- DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- COMMANDE !insta ---
@bot.command()
async def insta(ctx):
    await ctx.send("📸 Lancement de l'automatisation Instagram...")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1280, "height": 720})
            page = await context.new_page()

            await page.goto("https://www.instagram.com/accounts/login/", timeout=60000)
            await page.screenshot(path="/tmp/step1_login.png")

            await page.fill('input[name="username"]', INSTA_USERNAME)
            await page.fill('input[name="password"]', INSTA_PASSWORD)
            await page.screenshot(path="/tmp/step2_credentials.png")

            await page.click('button[type="submit"]')
            await page.wait_for_timeout(5000)
            await page.screenshot(path="/tmp/step3_loggedin.png")

            await page.goto(f"https://www.instagram.com/{ACCOUNT_TO_WATCH}/", timeout=60000)
            await page.wait_for_timeout(15000)
            await page.screenshot(path="/tmp/step4_account.png")

            await browser.close()

            await ctx.send("✅ Visite terminée. Voici les captures :", files=[
                discord.File("/tmp/step1_login.png"),
                discord.File("/tmp/step2_credentials.png"),
                discord.File("/tmp/step3_loggedin.png"),
                discord.File("/tmp/step4_account.png"),
            ])

    except Exception as e:
        try:
            await page.screenshot(path="/tmp/error.png")
            await ctx.send("❌ Erreur détectée. Voici ce que le bot voyait :", file=discord.File("/tmp/error.png"))
        except:
            pass

        error_text = str(e)
        if len(error_text) > 1900:
            error_text = error_text[:1900]
        await ctx.send(f"❌ Erreur : {error_text}")

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)