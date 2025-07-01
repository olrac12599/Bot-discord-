import discord
from discord.ext import commands
import requests
import os
import asyncio
import time
import subprocess
import traceback
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- CONFIG ENV ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")

if not all([DISCORD_TOKEN, CHESS_USERNAME, CHESS_PASSWORD]):
    raise ValueError("ERREUR: variables d'environnement manquantes.")

# --- DISCORD BOT ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- CAPTURE D'ÉCRAN SI ERREUR ---
def capture_on_error(driver, label="error"):
    timestamp = int(time.time())
    filename = f"screenshot_{label}_{timestamp}.png"
    try:
        driver.save_screenshot(filename)
        print(f"[📸] Capture d’écran prise : {filename}")
    except Exception as e:
        print(f"[❌] Capture échouée : {e}")
    return filename

# --- UPLOAD SUR TRANSFER.SH ---
def upload_file_transfer_sh(filename):
    try:
        with open(filename, 'rb') as f:
            r = requests.put(f"https://transfer.sh/{os.path.basename(filename)}", data=f)
        if r.ok:
            return r.text.strip()
    except Exception as e:
        print(f"[❌] Upload échoué : {e}")
    return None

# --- ENREGISTRE TOUT LE BROWSER (vidéo complète) ---
def record_chess_video(game_id):
    os.environ["DISPLAY"] = ":99"
    timestamp = int(time.time())
    video_filename = f"chess_{game_id}_{timestamp}.mp4"

    # Lancer l'écran virtuel
    xvfb = subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1920x1080x24"])
    time.sleep(1)

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    driver = None
    ffmpeg = None

    try:
        driver = webdriver.Chrome(options=chrome_options)
        wait = WebDriverWait(driver, 20)

        # 🎥 Démarrer l'enregistrement
        ffmpeg = subprocess.Popen([
            "ffmpeg", "-y",
            "-video_size", "1920x1080",
            "-framerate", "25",
            "-f", "x11grab",
            "-i", ":99.0",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            video_filename
        ])

        # 🌐 Navigation complète
        driver.get("https://www.chess.com/login_and_go")
        wait.until(EC.visibility_of_element_located((By.ID, "username"))).send_keys(CHESS_USERNAME)
        wait.until(EC.visibility_of_element_located((By.ID, "password"))).send_keys(CHESS_PASSWORD)
        wait.until(EC.element_to_be_clickable((By.ID, "login"))).click()
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".home-user-info, .nav-menu-area")))

        driver.get(f"https://www.chess.com/game/live/{game_id}")
        time.sleep(6)

    except Exception as e:
        print(f"[🚨] Erreur Selenium : {e}")
        traceback.print_exc()
        if driver:
            capture_on_error(driver, "record_error")
        return None

    finally:
        if driver:
            driver.quit()
        if ffmpeg and ffmpeg.poll() is None:
            ffmpeg.terminate()
            try:
                ffmpeg.wait(timeout=5)
            except subprocess.TimeoutExpired:
                ffmpeg.kill()
        xvfb.terminate()

    if os.path.exists(video_filename):
        print(f"[✅] Vidéo créée : {video_filename}")
        return video_filename
    else:
        print(f"[❌] Fichier vidéo manquant.")
        return None

# --- COMMANDE DISCORD ---
@bot.command(name="videochess")
async def videochess(ctx, game_id: str):
    await ctx.send("🎥 Enregistrement du navigateur en cours...")
    try:
        video_file = await asyncio.to_thread(record_chess_video, game_id)
        if not video_file or not os.path.exists(video_file):
            return await ctx.send("❌ Vidéo non générée.")

        link = upload_file_transfer_sh(video_file)
        if link:
            await ctx.send(f"📽️ Vidéo disponible : {link}")
        else:
            await ctx.send("⚠️ Upload échoué.")

        os.remove(video_file)

    except Exception as e:
        await ctx.send(f"🚨 Erreur : {e}")
        traceback.print_exc()

# --- COMMANDE PING ---
@bot.command(name="ping")
async def ping(ctx):
    await ctx.send("Pong!")

# --- READY EVENT ---
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

# --- LANCEMENT ---
async def main():
    await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())