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
# import shutil # <<< Nous n'aurons plus besoin de shutil pour cette approche

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
    driver = None # Initialiser driver à None pour le bloc finally
    try:
        print("[DEBUG] Début de record_game")
        chromedriver_autoinstaller.install()

        chrome_options = Options()
        # chrome_options.add_argument("--headless") # Décommenter si tu ne veux pas voir le navigateur
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1280,720")
        
        # <<< SUPPRIMER CETTE LIGNE : chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
        # En ne spécifiant pas --user-data-dir, Selenium utilisera un profil temporaire par défaut.
        
        driver = webdriver.Chrome(options=chrome_options)
        print("[DEBUG] Navigateur lancé")
        driver.get(url)
        time.sleep(3) # Laisse le temps à la page de charger

        with mss.mss() as sct:
            # S'assurer que le moniteur est valide. sct.monitors[0] est l'écran principal.
            # Si tu as plusieurs moniteurs et que tu veux cibler un spécifique, il faudra ajuster.
            monitor = sct.monitors[0] 
            print(f"[DEBUG] Capture depuis moniteur : {monitor}")
            
            # Utilise 'avc1' pour H.264 si 'mp4v' pose problème sur certains systèmes
            fourcc = cv2.VideoWriter_fourcc(*"mp4v") 
            # Assure-toi que les dimensions sont correctes.
            out = cv2.VideoWriter(VIDEO_PATH, fourcc, 10.0, (monitor["width"], monitor["height"]))

            start_time = time.time()
            frame_count = 0

            while time.time() - start_time < duration:
                img = np.array(sct.grab(monitor))
                frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                out.write(frame)
                frame_count += 1
                # Ajout d'un petit délai pour ne pas surcharger le CPU
                # et pour s'assurer que la capture est régulière.
                time.sleep(0.01) 

            out.release()
            print(f"[DEBUG] Enregistrement terminé. Frames capturées: {frame_count}")
        
        return True
    except Exception as e:
        last_error = f"[Erreur record_game] {e}"
        print(last_error)
        return False
    finally: # Ce bloc s'exécute toujours
        if driver: # S'assurer que le driver a bien été initialisé
            driver.quit() # Ferme le navigateur et nettoie les profils temporaires
            print("[DEBUG] Navigateur fermé et profil temporaire nettoyé.")
        # <<< SUPPRIMER CETTE PARTIE : Le bloc de suppression de shutil.rmtree n'est plus nécessaire ici.
        # if user_data_dir and os.path.exists(user_data_dir):
        #     try:
        #         shutil.rmtree(user_data_dir)
        #         print(f"[DEBUG] Répertoire de données utilisateur supprimé : {user_data_dir}")
        #     except OSError as e:
        #         print(f"[ERREUR] Impossible de supprimer le répertoire {user_data_dir}: {e}")

def compress_video():
    global last_error
    try:
        print("[DEBUG] Début compression")
        clip = VideoFileClip(VIDEO_PATH)
        # Pour une meilleure compatibilité et pour éviter des problèmes de codecs,
        # je te recommande de spécifier le codec audio sur 'aac' même si audio=False
        # car moviepy peut parfois se plaindre si ce n'est pas explicite.
        # Ou simplement laisser audio=False si tu es sûr que ça marche sans.
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
    # Exécuter record_game dans un thread séparé pour ne pas bloquer le bot Discord
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
    # Exécuter compress_video dans un thread séparé
    compressed = await loop.run_in_executor(None, compress_video)

    if compressed and os.path.exists(compressed):
        size = os.path.getsize(compressed)
        if size < 8 * 1024 * 1024: # Limite de 8MB pour Discord
            await ctx.send("🎥 Voici la vidéo compressée :", file=discord.File(compressed))
        else:
            await ctx.send("🚫 La vidéo reste trop grosse même après compression.")
            # Optionnel : tu pourrais offrir d'envoyer un lien de téléchargement si tu as un service d'hébergement.
    else:
        await ctx.send("❌ Erreur lors de la compression.")
        if last_error:
            await ctx.send(f"🪵 Log : ```{last_error}```")

if __name__ == "__main__":
    print("[INFO] Bot en cours de démarrage...")
    bot.run(DISCORD_TOKEN)

