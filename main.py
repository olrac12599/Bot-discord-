import discord
from discord.ext import commands
import os
import asyncio
import time
import subprocess
import traceback
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ENV
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
INSTA_USERNAME = os.getenv("INSTA_USERNAME")
INSTA_PASSWORD = os.getenv("INSTA_PASSWORD")
ACCOUNT_TO_WATCH = os.getenv("ACCOUNT_TO_WATCH")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

recording_process = None
video_path = None

def start_instagram_recording():
    global recording_process, video_path
    os.environ["DISPLAY"] = ":99"
    timestamp = int(time.time())
    video_path = f"insta_record_{timestamp}.webm"

    xvfb = subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1280x720x24"])
    time.sleep(1)

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1280,720")

    driver = None
    ffmpeg = None

    try:
        driver = webdriver.Chrome(options=chrome_options)
        wait = WebDriverWait(driver, 20)

        ffmpeg = subprocess.Popen([
            "ffmpeg", "-y",
            "-video_size", "1280x720",
            "-framerate", "25",
            "-f", "x11grab",
            "-i", ":99.0",
            "-c:v", "libvpx-vp9",
            "-b:v", "1M",
            video_path
        ])

        recording_process = (xvfb, ffmpeg, driver)

        driver.get("https://www.instagram.com/accounts/login/")
        wait.until(EC.presence_of_element_located((By.NAME, "username"))).send_keys(INSTA_USERNAME)
        wait.until(EC.presence_of_element_located((By.NAME, "password"))).send_keys(INSTA_PASSWORD)
        wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@type='submit']"))).click()

        time.sleep(5)
        driver.get(f"https://www.instagram.com/{ACCOUNT_TO_WATCH}/")
        time.sleep(10)

    except Exception as e:
        print("Erreur : ", e)
        traceback.print_exc()
    return

@bot.command()
async def insta(ctx):
    global recording_process
    if recording_process:
        await ctx.send("⚠️ Enregistrement déjà en cours.")
        return

    await ctx.send("📸 Lancement de l’enregistrement Instagram...")
    await asyncio.to_thread(start_instagram_recording)
    await ctx.send("🎥 Enregistrement en cours... Tape `!stop` pour terminer.")

@bot.command()
async def stop(ctx):
    global recording_process, video_path
    if not recording_process:
        await ctx.send("⚠️ Aucun enregistrement en cours.")
        return

    xvfb, ffmpeg, driver = recording_process
    try:
        if driver:
            driver.quit()
        if ffmpeg and ffmpeg.poll() is None:
            ffmpeg.terminate()
            ffmpeg.wait(timeout=5)
        if xvfb:
            xvfb.terminate()

        recording_process = None

        if os.path.exists(video_path):
            await ctx.send("🎬 Vidéo terminée :", file=discord.File(video_path))
            os.remove(video_path)
        else:
            await ctx.send("❌ Vidéo non trouvée.")
    except Exception as e:
        await ctx.send(f"❌ Erreur lors de l'arrêt : {e}")

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

if __name__ == "__main__":
    asyncio.run(bot.start(DISCORD_TOKEN))