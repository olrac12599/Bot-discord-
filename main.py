import os
import asyncio
import discord
from discord.ext import commands
from playwright.async_api import async_playwright, Error as PlaywrightError
from playwright_stealth import stealth_async

# --- VARIABLES ENV ---
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
        await ctx.send("❌ Variables d'environnement manquantes.")
        return

    await ctx.send("🕵️ Lancement de la navigation furtive sur Instagram...")

    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115 Safari/537.36"
            )
            page = await context.new_page()
            await stealth_async(page)

            await page.goto("https://www.instagram.com/accounts/login/", timeout=60000)

            # Optional : accepter les cookies
            try:
                await page.locator("button:has-text('Accept'), button:has-text('Accepter')").click(timeout=5000)
            except:
                pass

            await page.wait_for_selector('input[name="username"]', timeout=15000)
            await page.fill('input[name="username"]', INSTA_USERNAME)
            await page.fill('input[name="password"]', INSTA_PASSWORD)

            await page.click('button[type="submit"]')
            await page.wait_for_timeout(7000)

            # Fermer popups
            try:
                await page.locator("text=Not Now").click(timeout=5000)
            except:
                pass

            await page.goto(f"https://www.instagram.com/{ACCOUNT_TO_WATCH}/", timeout=60000)
            await page.wait_for_load_state("networkidle")
            screenshot_path = "/tmp/account_view.png"
            await page.screenshot(path=screenshot_path)

            await browser.close()
            await ctx.send("✅ Visite terminée avec succès !", file=discord.File(screenshot_path))

        except Exception as e:
            if 'page' in locals() and not page.is_closed():
                try:
                    error_path = "/tmp/error.png"
                    await page.screenshot(path=error_path)
                    await ctx.send("⚠️ Une erreur est survenue. Voici le screenshot :", file=discord.File(error_path))
                except:
                    await ctx.send("⚠️ Une erreur est survenue mais aucune capture disponible.")
            await ctx.send(f"❌ Erreur : {type(e).__name__}: {str(e)[:1500]}")

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
        print("❌ DISCORD_TOKEN manquant")