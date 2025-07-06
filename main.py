import os
import discord
from discord.ext import commands
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import asyncio
import subprocess

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
INSTA_USERNAME = os.getenv("INSTA_USERNAME")
INSTA_PASSWORD = os.getenv("INSTA_PASSWORD")
ACCOUNT_TO_WATCH = os.getenv("ACCOUNT_TO_WATCH")

recording_process = None

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def start_recording():
    global recording_process
    output = "/tmp/insta_record.webm"
    cmd = [
        "ffmpeg",
        "-y",
        "-video_size", "1280x720",
        "-f", "x11grab",
        "-i", ":99.0",
        "-r", "30",
        output
    ]
    recording_process = subprocess.Popen(cmd)
    return output

def stop_recording():
    global recording_process
    if recording_process:
        recording_process.terminate()
        recording_process.wait()
        recording_process = None
        return "/tmp/insta_record.webm"
    return None

@bot.command()
async def insta(ctx):
    await ctx.send("📸 Démarrage de l'automatisation et de l'enregistrement...")

    # Démarrer l'enregistrement
    start_recording()

    try:
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1280,720')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        driver = webdriver.Chrome(options=options)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            })
            """
        })

        driver.get("https://www.instagram.com/accounts/login/")
        await asyncio.sleep(5)

        username_field = driver.find_element(By.NAME, "username")
        password_field = driver.find_element(By.NAME, "password")
        username_field.send_keys(INSTA_USERNAME)
        password_field.send_keys(INSTA_PASSWORD)

        login_button = driver.find_element(By.XPATH, "//button[@type='submit']")
        login_button.click()

        await asyncio.sleep(7)

        driver.get(f"https://www.instagram.com/{ACCOUNT_TO_WATCH}/")
        await asyncio.sleep(15)

        driver.quit()
        await ctx.send("✅ Navigation Instagram terminée.")

    except Exception as e:
        await ctx.send(f"❌ Erreur : {e}")

@bot.command()
async def stop(ctx):
    path = stop_recording()
    if path and os.path.exists(path):
        await ctx.send("🎬 Vidéo terminée :", file=discord.File(path))
    else:
        await ctx.send("⚠️ Aucun enregistrement en cours.")

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)