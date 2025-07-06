import os
import asyncio
import discord
from discord.ext import commands
from playwright.async_api import async_playwright, Error as PlaywrightError
from playwright_stealth import stealth  # ✅ Import corrigé

# --- VARIABLES D'ENV ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
INSTA_USERNAME = os.getenv("INSTA_USERNAME")
INSTA_PASSWORD = os.getenv("INSTA_PASSWORD")
ACCOUNT_TO_WATCH = os.getenv("ACCOUNT_TO_WATCH")

# --- DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.command()
async def insta(ctx):
    if not all([DISCORD_TOKEN, INSTA_USERNAME, INSTA_PASSWORD, ACCOUNT_TO_WATCH]):
        await ctx.send("❌ Erreur : Une ou plusieurs variables d'environnement sont manquantes.")
        return

    await ctx.send("🕵️ Lancement de l'automatisation Instagram...")

    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu"
                ]
            )
            context = await browser.new_context()
            page = await context.new_page()

            # ✅ Appliquer le mode furtif
            await stealth(page)

            await page.goto("https://www.instagram.com/accounts/login/", timeout=60000)

            # Gérer les cookies si présents
            try:
                await page.locator("text=Allow all cookies, Tout autoriser").click(timeout=5000)
                await ctx.send("🍪 Cookies acceptés.")
            except:
                pass

            await page.wait_for_timeout(1000)
            await page.locator('input[name="username"]').fill(INSTA_USERNAME)
            await page.locator('input[name="password"]').fill(INSTA_PASSWORD)
            await page.locator('button[type="submit"]').click()
            await page.wait_for_timeout(7000)

            # Fermer les popups
            try:
                await page.locator("text=Not Now, Plus tard").click(timeout=5000)
            except:
                pass

            await page.goto(f"https://www.instagram.com/{ACCOUNT_TO_WATCH}/", timeout=60000)
            await page.wait_for_load_state("networkidle")
            await page.screenshot(path="/tmp/final_account_view.png")

            await ctx.send("✅ Visite terminée avec succès !", file=discord.File("/tmp/final_account_view.png"))

        except Exception as e:
            await ctx.send(f"❌ Une erreur est survenue : {type(e).__name__}")
            print("Erreur détaillée :", e)
            if 'page' in locals() and not page.is_closed():
                await page.screenshot(path="/tmp/error_screenshot.png")
                await ctx.send("📸 Voici ce que le bot voyait :", file=discord.File("/tmp/error_screenshot.png"))

        finally:
            if browser:
                await browser.close()

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

if __name__ == "__main__":
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        print("❌ DISCORD_TOKEN manquant.")