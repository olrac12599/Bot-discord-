import os
import asyncio
from discord.ext import commands
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")
ACCOUNT_TO_WATCH = os.getenv("ACCOUNT_TO_WATCH")

intents = commands.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

async def record_screen(output="record.mp4", duration=30):
    cmd = [
        "ffmpeg", "-y",
        "-video_size", "1280x720",
        "-f", "x11grab",
        "-i", ":99.0",
        "-t", str(duration),
        output
    ]
    return await asyncio.create_subprocess_exec(*cmd)

@bot.command()
async def insta(ctx):
    await ctx.send("📸 Connexion à Instagram...")

    try:
        # Lancer l'enregistrement (async)
        ffmpeg_proc = await record_screen(duration=30)

        # Lancer Playwright en headless
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            await page.goto("https://www.instagram.com/accounts/login/")
            await page.wait_for_timeout(3000)

            await page.fill('input[name="username"]', INSTAGRAM_USERNAME)
            await page.fill('input[name="password"]', INSTAGRAM_PASSWORD)
            await page.click('button[type="submit"]')

            await page.wait_for_timeout(5000)
            await page.goto(f"https://www.instagram.com/{ACCOUNT_TO_WATCH}/")
            await page.wait_for_timeout(5000)

            await browser.close()

        await ffmpeg_proc.wait()

        if os.path.exists("record.mp4"):
            await ctx.send("🎥 Voici la vidéo : ", file=discord.File("record.mp4"))
        else:
            await ctx.send("❌ Échec de l'enregistrement vidéo.")

    except Exception as e:
        err_msg = f"❌ Erreur : {str(e)}"
        if len(err_msg) > 2000:
            err_msg = err_msg[:1990] + "..."
        await ctx.send(err_msg)

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)