import os
import discord
from discord.ext import commands
import asyncio
import subprocess
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
INSTA_USERNAME = os.getenv("INSTA_USERNAME")
INSTA_PASSWORD = os.getenv("INSTA_PASSWORD")
ACCOUNT_TO_WATCH = os.getenv("ACCOUNT_TO_WATCH")

recording_process = None
recording_path = "/tmp/insta_record.webm"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def start_recording():
    global recording_process
    cmd = [
        "ffmpeg", "-y",
        "-video_size", "1280x720",
        "-f", "x11grab",
        "-i", ":99.0",
        "-r", "25",
        recording_path
    ]
    recording_process = subprocess.Popen(cmd)

def stop_recording():
    global recording_process
    if recording_process:
        recording_process.terminate()
        recording_process.wait()
        recording_process = None
        return recording_path
    return None

@bot.command()
async def insta(ctx):
    await ctx.send("📸 Lancement de l'enregistrement et de la session Instagram...")
    start_recording()

    try:
        options = uc.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1280,720")

        driver = uc.Chrome(options=options)
        driver.get("https://www.instagram.com/accounts/login/")

        wait = WebDriverWait(driver, 20)
        username_input = wait.until(EC.presence_of_element_located((By.NAME, "username")))
        password_input = wait.until(EC.presence_of_element_located((By.NAME, "password")))

        username_input.send_keys(INSTA_USERNAME)
        password_input.send_keys(INSTA_PASSWORD)

        login_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@type='submit']")))
        login_button.click()

        await asyncio.sleep(5)

        driver.get(f"https://www.instagram.com/{ACCOUNT_TO_WATCH}/")
        await asyncio.sleep(10)

        await ctx.send("✅ Visite du compte terminée.")

        driver.quit()

    except Exception as e:
        try:
            driver.save_screenshot("/tmp/error.png")
            await ctx.send("❌ Erreur détectée. Voici ce que le bot voyait :", file=discord.File("/tmp/error.png"))
        except:
            pass

        await ctx.send(f"❌ Erreur : {str(e)[:1900]}")

@bot.command()
async def stop(ctx):
    path = stop_recording()
    if path and os.path.exists(path):
        await ctx.send("🎬 Voici la vidéo enregistrée :", file=discord.File(path))
    else:
        await ctx.send("⚠️ Aucun enregistrement n'était en cours.")

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)