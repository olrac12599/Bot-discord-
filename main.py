import os
import asyncio
import discord
from discord.ext import commands
from playwright.async_api import async_playwright, Error as PlaywrightError

# --- CHARGEMENT DES VARIABLES D'ENVIRONNEMENT ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
INSTA_USERNAME = os.getenv("INSTA_USERNAME")
INSTA_PASSWORD = os.getenv("INSTA_PASSWORD")
ACCOUNT_TO_WATCH = os.getenv("ACCOUNT_TO_WATCH")

# --- CONFIGURATION DU BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# --- COMMANDE !insta ---
@bot.command()
async def insta(ctx):
    if not all([DISCORD_TOKEN, INSTA_USERNAME, INSTA_PASSWORD, ACCOUNT_TO_WATCH]):
        await ctx.send("❌ Erreur : Une ou plusieurs variables d'environnement sont manquantes.")
        return

    await ctx.send("📸 Lancement de l'automatisation Instagram...")

    async with async_playwright() as p:
        browser = None # Initialiser à None en dehors du try
        # 💡 LE CHANGEMENT EST ICI : Le 'try...except' est maintenant À L'INTÉRIEUR
        # de 'async with'. Cela garantit que le navigateur reste ouvert en cas d'erreur.
        try:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            # Navigation
            await page.goto("https://www.instagram.com/accounts/login/", timeout=60000)
            await page.wait_for_timeout(3000)

            # Gestion des cookies (si présent)
            cookie_button_selector = "button:has-text('Allow all cookies'), button:has-text('Tout autoriser')"
            try:
                await page.locator(cookie_button_selector).click(timeout=5000)
                await ctx.send("🍪 Bannière de cookies gérée.")
                await page.wait_for_timeout(1000)
            except PlaywrightError:
                await ctx.send("🍪 Pas de bannière de cookies détectée.")

            # Remplissage des identifiants
            # C'est ici que le TimeoutError se produit probablement
            await page.locator('input[name="username"]').fill(INSTA_USERNAME)
            await page.locator('input[name="password"]').fill(INSTA_PASSWORD)
            
            # Connexion
            await page.locator('button[type="submit"]').click()
            await page.wait_for_timeout(7000)

            # Gestion du popup "Enregistrer les informations"
            not_now_button = "div[role='dialog'] button:has-text('Not Now'), div[role='dialog'] button:has-text('Plus tard')"
            try:
                await page.locator(not_now_button).click(timeout=5000)
                await ctx.send("팝업 'Enregistrer les infos' géré.")
            except PlaywrightError:
                 await ctx.send("ポップアップ 'Enregistrer les infos' non détecté.")

            # Visite du profil cible
            await page.goto(f"https://www.instagram.com/{ACCOUNT_TO_WATCH}/", timeout=60000)
            await page.wait_for_load_state("networkidle", timeout=15000)
            await page.screenshot(path="/tmp/final_account_view.png")
            
            await browser.close()
            browser = None # Marquer comme fermé

            # Envoi du résultat final
            await ctx.send("✅ Visite terminée avec succès !", file=discord.File("/tmp/final_account_view.png"))

        except Exception as e:
            error_message = f"❌ Une erreur est survenue : {type(e).__name__}"
            await ctx.send(error_message)
            print(f"Erreur détaillée : {e}")

            # Maintenant, la capture d'écran devrait fonctionner car le navigateur est encore ouvert.
            if 'page' in locals():
                try:
                    await page.screenshot(path="/tmp/error_screenshot.png")
                    await ctx.send("📸 Voici ce que le bot voyait au moment de l'erreur :", file=discord.File("/tmp/error_screenshot.png"))
                except Exception as screenshot_error:
                    await ctx.send(f"⚠️ Impossible de prendre une capture d'écran : {screenshot_error}")
            else:
                 await ctx.send("⚠️ Impossible de prendre une capture d'écran car la page n'a pas pu être initialisée.")
        
        finally:
            # S'assurer que le navigateur est bien fermé à la fin, même en cas d'erreur
            if browser:
                await browser.close()


@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")


if __name__ == "__main__":
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        print("❌ Erreur critique : Le DISCORD_TOKEN n'est pas défini. Le bot ne peut pas démarrer.")
