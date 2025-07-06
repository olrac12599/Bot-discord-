import os
import asyncio
import discord
from discord.ext import commands
from playwright.async_api import async_playwright, Error as PlaywrightError
from playwright_stealth import stealth_async # <-- 1. IMPORTER STEALTH

# --- CHARGEMENT DES VARIABLES D'ENVIRONNEMENT ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
INSTA_USERNAME = os.getenv("INSTA_USERNAME")
INSTA_PASSWORD = os.getenv("INSTA_PASSWORD")
ACCOUNT_TO_WATCH = os.getenv("ACCOUNT_TO_WATCH")

# --- CONFIGURATION DU BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.command()
async def insta(ctx):
    if not all([DISCORD_TOKEN, INSTA_USERNAME, INSTA_PASSWORD, ACCOUNT_TO_WATCH]):
        await ctx.send("❌ Erreur : Une ou plusieurs variables d'environnement sont manquantes.")
        return

    await ctx.send("🕵️ Lancement de l'automatisation en mode furtif...")

    async with async_playwright() as p:
        browser = None
        try:
            # 2. AJOUTER DES ARGUMENTS AU NAVIGATEUR POUR LA STABILITÉ
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

            # 3. APPLIQUER LE MODE FURTIF (STEALTH)
            # C'est l'étape la plus importante. Elle doit être faite avant la navigation.
            await stealth_async(page)

            await page.goto("https://www.instagram.com/accounts/login/", timeout=60000)
            
            # La suite du code reste identique...
            cookie_button_selector = "button:has-text('Allow all cookies'), button:has-text('Tout autoriser')"
            try:
                await page.locator(cookie_button_selector).click(timeout=5000)
                await ctx.send("🍪 Bannière de cookies gérée.")
            except PlaywrightError:
                await ctx.send("🍪 Pas de bannière de cookies détectée.")
            
            await page.wait_for_timeout(1000) # Petite pause

            await page.locator('input[name="username"]').fill(INSTA_USERNAME)
            await page.locator('input[name="password"]').fill(INSTA_PASSWORD)
            await page.locator('button[type="submit"]').click()
            await page.wait_for_timeout(7000)

            not_now_button = "div[role='dialog'] button:has-text('Not Now'), div[role='dialog'] button:has-text('Plus tard')"
            try:
                await page.locator(not_now_button).click(timeout=5000)
                await ctx.send("팝업 'Enregistrer les infos' géré.")
            except PlaywrightError:
                await ctx.send("ポップアップ 'Enregistrer les infos' non détecté.")

            await page.goto(f"https://www.instagram.com/{ACCOUNT_TO_WATCH}/", timeout=60000)
            await page.wait_for_load_state("networkidle")
            await page.screenshot(path="/tmp/final_account_view.png")
            
            await browser.close()
            browser = None
            
            await ctx.send("✅ Visite terminée avec succès !", file=discord.File("/tmp/final_account_view.png"))

        except Exception as e:
            error_message = f"❌ Une erreur est survenue : {type(e).__name__}"
            await ctx.send(error_message)
            print(f"Erreur détaillée : {e}")

            if 'page' in locals() and not page.is_closed():
                await page.screenshot(path="/tmp/error_screenshot.png")
                await ctx.send("📸 Voici ce que le bot voyait au moment de l'erreur :", file=discord.File("/tmp/error_screenshot.png"))
        
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
        print("❌ Erreur critique : Le DISCORD_TOKEN n'est pas défini.")

