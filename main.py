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

# Charger les variables d'environnement
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
VIDEO_PATH = "recording.mp4"
COMPRESSED_PATH = "compressed.mp4"

# Configurer les intents Discord
intents = discord.Intents.default()
intents.message_content = True

# Initialiser le bot
bot = commands.Bot(command_prefix='!', intents=intents)

# 📹 Fonction d'enregistrement
def record_game(url, duration=10):
    try:
        print("[DEBUG] Début de record_game")
        chromedriver_autoinstaller.install()

        chrome_options = Options()
        # chrome_options.add_argument("--headless")  # Désactive pour tester
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1280,720")

        driver = webdriver.Chrome(options=chrome_options)
        print("[DEBUG] Navigateur lancé")
        driver.get(url)
        time.sleep(3)  # attendre que la page charge

        with mss.mss() as sct:
            monitor = sct.monitors[0]  # capture tout l'écran
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
        print(f"[Erreur record_game] {e}")
        return False

# 🗜️ Compression vidéo
def compress_video():
    try:
        print("[DEBUG] Début compression")
        clip = VideoFileClip(VIDEO_PATH)
        clip_resized = clip.resize(height=360)
        clip_resized.write_videofile(COMPRESSED_PATH, bitrate="500k", codec="libx264", audio=False)
        print("[DEBUG] Compression terminée")
        return COMPRESSED_PATH
    except Exception as e:
        print(f"[Erreur compress_video] {e}")
        return None

# 📥 Commande !chess
@bot.command()
async def chess(ctx, game_id: str):
    url = f"https://www.chess.com/game/live/{game_id}"
    await ctx.send(f"Connexion à la partie : {url}")
    await ctx.send("Enregistrement de 10 secondes en cours...")

    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(None, record_game, url)

    if success:
        await ctx.send("✅ Partie enregistrée ! Utilise `!cam` pour récupérer la vidéo.")
    else:
        await ctx.send("❌ Erreur lors de l'enregistrement. Regarde la console pour plus de détails.")

# 🎬 Commande !cam
@bot.command()
async def cam(ctx):
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

# 🚀 Lancer le bot
if __name__ == "__main__":
    print("[INFO] Bot en cours de démarrage...")
    bot.run(DISCORD_TOKEN)