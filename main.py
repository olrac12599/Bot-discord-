import os
import time
import discord
import asyncio
import mss
import cv2
import numpy as np
import chromedriver_autoinstaller
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from discord.ext import commands
from moviepy.editor import VideoFileClip
from dotenv import load_dotenv
import shutil # <<< Importer le module shutil

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
VIDEO_PATH = "recording.mp4"
COMPRESSED_PATH = "compressed.mp4"

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Global pour stocker le dernier message d'erreur
last_error = ""

def record_game(url, duration=10):
    global last_error
    user_data_dir = None # Initialiser à None
    try:
        print("[DEBUG] Début de record_game")
        chromedriver_autoinstaller.install()

        chrome_options = Options()
        # chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1280,720")
        
        # Générer un chemin unique et le stocker pour une suppression ultérieure
        user_data_dir = f"/tmp/selenium_profile_{int(time.time())}" # Utiliser int() pour un nom plus propre
        chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
        
        driver = webdriver.Chrome(options=chrome_options)
        print("[DEBUG] Navigateur lancé")
        driver.get(url)
        time.sleep(3)

        with mss.mss() as sct:
            monitor = sct.monitors[0]
            print(f"[DEBUG] Capture depuis moniteur : {monitor}")
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            out = cv2.VideoWriter(VIDEO_PATH, fourcc, 10.0, (monitor["width"], monitor["height"]))

            start_time = time.time()
            frame_count = 0

            while time.time() - start_time < duration:
                img = np.array(sct.grab(monitor))
                frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                out.write(frame)
                frame_count += 1

            out.release()
            print(f"[DEBUG] Enregistrement terminé. Frames capturées: {frame_count}")
        
        driver.quit()
        return True
    except Exception as e:
        last_error = f"[Erreur record_game] {e}"
        print(last_error)
        return False
    finally: # <<< Le bloc finally s'exécute toujours, que l'erreur se produise ou non
        if user_data_dir and os.path.exists(user_data_dir):
            try:
                shutil.rmtree(user_data_dir) # <<< Supprime récursivement le répertoire
                print(f"[DEBUG] Répertoire de données utilisateur supprimé : {user_data_dir}")
            except OSError as e:
                print(f"[ERREUR] Impossible de supprimer le répertoire {user_data_dir}: {e}")

def compress_video():
    global last_error
    try:
        print("[DEBUG] Début compression")
        clip = VideoFileClip(VIDEO_PATH)
        clip_resized = clip.resize(height=360)
        clip_resized.write_videofile(COMPRESSED_PATH, bitrate="500k", codec="libx264", audio=False)
        print("[DEBUG] Compression terminée")
        return COMPRESSED_PATH
    except Exception as e:
        last_error = f"[Erreur compress_video] {e}"
        print(last_error)
        return None

@bot.command()
async def chess(ctx, game_id: str):
    global last_error
    url = f"https://www.chess.com/game/live/{game_id}"
    await ctx.send(f"Connexion à la partie : {url}")
    await ctx.send("Enregistrement de 10 secondes en cours...")

    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(None, record_game, url)

    if success:
        await ctx.send("✅ Partie enregistrée ! Utilise `!cam` pour récupérer la vidéo.")
    else:
        await ctx.send("❌ Erreur lors de l'enregistrement.")
        if last_error:
            await ctx.send(f"🪵 Log : ```{last_error}```")

@bot.command()
async def cam(ctx):
    global last_error
    if not os.path.exists(VIDEO_PATH):
        await ctx.send("⚠️ Aucune vidéo enregistrée.")
        return

    await ctx.send("Compression de la vidéo...")

    loop = asyncio.get_event_loop()
    compressed = await loop.run_in_executor(None, compress_video)

    if compressed and os.path.exists(compressed):
        size = os.path.getsize(compressed)
        if size < 8 * 1024 * 1024:
            await ctx.send("🎥 Voici la vidéo compressée :", file=discord.File(compressed))
        else:
            await ctx.send("🚫 La vidéo reste trop grosse même après compression.")
    else:
        await ctx.send("❌ Erreur lors de la compression.")
        if last_error:
            await ctx.send(f"🪵 Log : ```{last_error}```")

if __name__ == "__main__":
    print("[INFO] Bot en cours de démarrage...")
    bot.run(DISCORD_TOKEN)
