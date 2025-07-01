import discord
from discord.ext import commands, tasks
import requests
import os
import asyncio
import chess
import re
import time
import subprocess
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import traceback

def capture_on_error(driver, label="error"):
    timestamp = int(time.time())
    filename = f"screenshot_{label}_{timestamp}.png"
    try:
        driver.save_screenshot(filename)
        print(f"[📸] Capture d’écran prise : {filename}")
    except Exception as e:
        print(f"[❌] Erreur lors de la capture : {e}")
    return filename
# --- CONFIG ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")

if not all([DISCORD_TOKEN, CHESS_USERNAME, CHESS_PASSWORD]):
    raise ValueError("ERREUR: DISCORD_TOKEN, CHESS_USERNAME, ou CHESS_PASSWORD manquant.")

# --- DISCORD BOT ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
tracked_games = {}

# --- UPLOAD FUNCTION ---
def upload_file_transfer_sh(filename):
    try:
        with open(filename, 'rb') as f:
            r = requests.put(f"https://transfer.sh/{os.path.basename(filename)}", data=f)
        if r.ok:
            return r.text.strip()
    except Exception as e:
        print("Upload error:", e)
    return None

# --- RECORD VIDEO ---
def record_chess_video(game_id):
    os.environ["DISPLAY"] = ":99"
    xvfb = subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1920x1080x24"])
    time.sleep(1)

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 20)

    timestamp = int(time.time())
    video_filename = f"chess_{game_id}_{timestamp}.mp4"

    ffmpeg = subprocess.Popen([
        "ffmpeg", "-y",
        "-video_size", "1920x1080",
        "-framerate", "25",
        "-f", "x11grab",
        "-i", ":99.0",
        "-t", "10",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        video_filename
    ])

    try:
        driver.get("https://www.chess.com/login_and_go")
        wait.until(EC.visibility_of_element_located((By.ID, "username"))).send_keys(CHESS_USERNAME)
        wait.until(EC.visibility_of_element_located((By.ID, "password"))).send_keys(CHESS_PASSWORD)
        wait.until(EC.element_to_be_clickable((By.ID, "login"))).click()
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".home-user-info, .nav-menu-area")))

        driver.get(f"https://www.chess.com/game/live/{game_id}")
        time.sleep(8)

        ffmpeg.wait()
        return video_filename

    finally:
        driver.quit()
        xvfb.terminate()

# --- DISCORD COMMAND ---
@bot.command(name="videochess")
async def videochess(ctx, game_id: str):
    await ctx.send("🎥 Enregistrement vidéo en cours…")
    try:
        video = await asyncio.to_thread(record_chess_video, game_id)
        if not video or not os.path.exists(video):
            return await ctx.send("❌ Problème: vidéo non générée.")
        link = upload_file_transfer_sh(video)
        if link:
            await ctx.send(f"📽️ Vidéo prête : {link}")
        else:
            await ctx.send("⚠️ Échec de l'upload.")
        os.remove(video)
    except Exception as e:
        await ctx.send(f"🚨 Erreur : {e}")

# --- PING COMMAND ---
@bot.command(name="ping")
async def ping(ctx):
    await ctx.send("Pong!")

# --- RUN ---
@bot.event
async def on_ready():
    print(f"Connecté comme {bot.user}")

async def main():
    await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())