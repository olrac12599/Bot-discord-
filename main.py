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

# --- INIT DISCORD BOT ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- CAPTURE EN CAS D'ERREUR ---
def capture_on_error(driver, label="error"):
    timestamp = int(time.time())
    filename = f"screenshot_{label}_{timestamp}.png"
    try:
        driver.save_screenshot(filename)
        print(f"[📸] Screenshot pris : {filename}")
        return filename
    except Exception as e:
        print(f"[❌] Capture échouée : {e}")
    return None

# --- ENREGISTREMENT VIDÉO ---
def record_chess_video(game_id):
    os.environ["DISPLAY"] = ":99"
    timestamp = int(time.time())
    video_filename = f"chess_{game_id}_{timestamp}.mp4"
    screenshot_file = None

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

        driver.get("https://www.chess.com/login_and_go")

        # Accepter les cookies si présent
        try:
            accept_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'I Accept')]"))
            )
            accept_button.click()
            print("[✅] 'I Accept' cliqué.")
            time.sleep(1)
        except Exception:
            print("[⚠️] Bouton 'I Accept' non affiché.")

        # Connexion par placeholder
        try:
            username_input = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='Username, Phone, or Email']"))
            )
            username_input.clear()
            username_input.send_keys(CHESS_USERNAME)

            password_input = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='Password']"))
            )
            password_input.clear()
            password_input.send_keys(CHESS_PASSWORD)

            login_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "login"))
            )
            login_button.click()

            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".home-user-info, .nav-menu-area"))
            )
            print("[✅] Connexion réussie")

        except Exception as e:
            print("[🚨] Échec de la connexion :", e)
            raise e

        # Accéder à la partie
        driver.get(f"https://www.chess.com/game/live/{game_id}")
        time.sleep(6)

    except Exception as e:
        print(f"[🚨] Erreur Selenium : {e}")
        traceback.print_exc()
        if driver:
            screenshot_file = capture_on_error(driver, "record_error")

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

    return video_filename if os.path.exists(video_filename) else None, screenshot_file

# --- COMMANDE DISCORD ---
@bot.command(name="videochess")
async def videochess(ctx, game_id: str):
    await ctx.send("🎥 Enregistrement du navigateur en cours...")
    try:
        video_file, screenshot = await asyncio.to_thread(record_chess_video, game_id)

        if video_file and os.path.exists(video_file):
            if os.path.getsize(video_file) < 8 * 1024 * 1024:
                await ctx.send(file=discord.File(video_file))
            else:
                await ctx.send("⚠️ Vidéo trop lourde pour Discord.")
            os.remove(video_file)
        else:
            await ctx.send("❌ Vidéo non générée.")

        if screenshot and os.path.exists(screenshot):
            await ctx.send("🖼️ Screenshot lors de l’erreur :")
            await ctx.send(file=discord.File(screenshot))
            os.remove(screenshot)

    except Exception as e:
        await ctx.send(f"🚨 Erreur pendant la commande : {e}")
        traceback.print_exc()

# --- COMMANDE PING ---
@bot.command(name="ping")
async def ping(ctx):
    await ctx.send("Pong!")

# --- READY EVENT ---
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

# --- MAIN ---
async def main():
    await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())