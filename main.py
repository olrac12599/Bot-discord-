# main.py
import os
import asyncio
import io # Important: pour manipuler les images en mémoire
import discord
from discord.ext import commands
from playwright.async_api import async_playwright

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")

# Plus besoin de VNC_PUBLIC_URL

active_sessions = {}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

async def start_video_feed(ctx, url: str):
    """Lance le navigateur et envoie un flux de captures d'écran sur Discord."""
    page = None
    browser = None
    context = None
    last_message = None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False, # Doit rester False pour pouvoir faire des captures
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--window-size=1280,720",
                    "--display=:0"
                ]
            )
            context = await browser.new_context(viewport={"width": 1280, "height": 720})
            page = await context.new_page()

            # --- Processus de connexion ---
            await page.goto("https://www.chess.com/login_and_go", timeout=60000)
            await page.wait_for_timeout(2000)
            await page.get_by_placeholder("Username, Phone, or Email").fill(CHESS_USERNAME)
            await page.get_by_placeholder("Password").fill(CHESS_PASSWORD)
            await page.get_by_role("button", name="Log In").click()
            await page.wait_for_url("**/home", timeout=15000)
            
            # --- Aller à la page du jeu ---
            await page.goto(url, timeout=60000)
            await ctx.send(f"✅ Page du jeu chargée. Début du feed dans le salon...")
            await page.wait_for_timeout(5000) # Laisse le temps à la page de se stabiliser

            # --- Boucle de capture d'écran ---
            end_time = asyncio.get_event_loop().time() + 300  # Durée du feed (ici 5 minutes)
            while asyncio.get_event_loop().time() < end_time:
                screenshot_bytes = await page.screenshot()
                
                # Envoyer l'image en mémoire sans la sauvegarder sur le disque
                screenshot_file = discord.File(io.BytesIO(screenshot_bytes), filename="live.png")
                
                # Supprimer l'ancien message pour ne pas surcharger le salon
                if last_message:
                    try:
                        await last_message.delete()
                    except discord.errors.NotFound:
                        pass # Le message a déjà été supprimé

                last_message = await ctx.send(file=screenshot_file)
                await asyncio.sleep(5) # Intervalle entre chaque capture

    except Exception as e:
        print(f"[Erreur Playwright] : {e}")
        await ctx.send(f"❌ Une erreur est survenue pendant le feed : {e}")

    finally:
        if last_message:
            try:
                await last_message.delete()
            except discord.errors.NotFound:
                pass
        await ctx.send("⚫️ Feed terminé.")
        if browser:
            await browser.close()


@bot.command(name="chess")
async def cmd_chess(ctx, url: str):
    await ctx.send("🟢 Lancement du navigateur et préparation du feed...")
    # Lance la fonction de feed en tâche de fond
    asyncio.create_task(start_video_feed(ctx, url))


@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(f"Pong! Latence : {round(bot.latency * 1000)} ms")


@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")


async def main():
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
