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
# Assure-toi que tes variables d'environnement sont bien chargées
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")

if not all([DISCORD_TOKEN, CHESS_USERNAME, CHESS_PASSWORD]):
    raise ValueError("ERREUR: Des variables d'environnement (DISCORD_TOKEN, CHESS_USERNAME, CHESS_PASSWORD) sont manquantes.")

# --- INIT DISCORD BOT ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- CAPTURE ERREUR ---
def capture_on_error(driver, label="error"):
    timestamp = int(time.time())
    filename = f"screenshot_{label}_{timestamp}.png"
    try:
        driver.save_screenshot(filename)
        print(f"[📸] Screenshot d'erreur capturé : {filename}")
        return filename
    except Exception as e:
        print(f"[❌] La capture du screenshot a échoué : {e}")
    return None

# --- ENREGISTREMENT VIDÉO (FONCTION CORRIGÉE) ---
def record_chess_video(game_id):
    os.environ["DISPLAY"] = ":99"
    timestamp = int(time.time())
    video_filename = f"chess_{game_id}_{timestamp}.webm"
    screenshot_file = None

    xvfb = subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1920x1080x24"])
    time.sleep(1) # Laisser le temps à Xvfb de démarrer

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--lang=fr-FR") # Définir la langue pour des pop-ups prévisibles

    driver = None
    ffmpeg = None

    try:
        driver = webdriver.Chrome(options=chrome_options)
        wait = WebDriverWait(driver, 20)

        # Démarrage de l'enregistrement vidéo avec FFmpeg
        ffmpeg = subprocess.Popen([
            "ffmpeg", "-y",
            "-video_size", "1920x1080",
            "-framerate", "25",
            "-f", "x11grab",
            "-i", ":99.0",
            "-c:v", "libvpx-vp9",
            "-b:v", "1M",
            "-pix_fmt", "yuv420p",
            video_filename
        ])

        # 1. Aller sur la page de connexion
        driver.get("https://www.chess.com/login_and_go")

        # 2. Se connecter
        print("[⏳] Tentative de connexion...")
        username_input = wait.until(EC.element_to_be_clickable((By.ID, "username")))
        username_input.send_keys(CHESS_USERNAME)
        
        password_input = driver.find_element(By.ID, "password")
        password_input.send_keys(CHESS_PASSWORD)
        
        login_button = driver.find_element(By.ID, "login")
        login_button.click()

        # Attendre que la connexion soit effective en vérifiant l'URL
        wait.until(EC.url_contains("chess.com/home"))
        print("[✅] Connexion réussie, redirection vers /home.")

        # 3. Fermer le pop-up "Leçon rapide" (la correction clé est ici)
        try:
            # On attend jusqu'à 10 secondes car le pop-up peut être lent à apparaître
            dismiss_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Non, merci')]"))
            )
            dismiss_button.click()
            print("[✅] Pop-up 'Leçon rapide' fermé.")
            time.sleep(1) # Petite pause pour laisser le temps à l'interface de se stabiliser
        except Exception:
            # Si le pop-up n'apparaît pas, on continue simplement
            print("[ℹ️] Aucun pop-up 'Leçon rapide' n'a été détecté.")

        # 4. Naviguer vers la partie en direct
        print(f"[➡️] Navigation vers la partie : {game_id}")
        driver.get(f"https://www.chess.com/game/live/{game_id}")
        
        # Attendre que le plateau de jeu soit visible pour s'assurer que la page est chargée
        wait.until(EC.presence_of_element_located((By.ID, "game-board")))
        print("[✅] La partie est chargée et visible.")
        
        # Laisser le temps d'enregistrer un peu de la partie
        time.sleep(10)

    except Exception as e:
        print(f"[🚨] Une erreur majeure est survenue dans Selenium : {e}")
        traceback.print_exc()
        if driver:
            screenshot_file = capture_on_error(driver, "record_error")

    finally:
        # Arrêter proprement tous les processus
        if ffmpeg and ffmpeg.poll() is None:
            ffmpeg.terminate()
            try:
                ffmpeg.wait(timeout=5)
            except subprocess.TimeoutExpired:
                ffmpeg.kill()
        if driver:
            driver.quit()
        if xvfb:
            xvfb.terminate()

    return video_filename if os.path.exists(video_filename) else None, screenshot_file


# --- COMMANDE DISCORD ---
@bot.command(name="videochess")
async def videochess(ctx, game_id: str):
    # Vérifier que game_id est un nombre
    if not game_id.isdigit():
        await ctx.send("❌ L'ID de la partie doit être un numéro. Exemple: `!videochess 987654321`")
        return
        
    await ctx.send(f"🎥 Lancement de l'enregistrement pour la partie `{game_id}`...")
    try:
        # Lancer la fonction d'enregistrement dans un thread pour ne pas bloquer le bot
        video_file, screenshot = await asyncio.to_thread(record_chess_video, game_id)

        if video_file and os.path.exists(video_file):
            # Vérifier la taille du fichier avant de l'envoyer
            if os.path.getsize(video_file) < 8 * 1024 * 1024: # Limite de 8MB de Discord
                await ctx.send("✅ Enregistrement terminé !", file=discord.File(video_file))
            else:
                await ctx.send("⚠️ La vidéo a été enregistrée mais est trop lourde pour être envoyée sur Discord (> 8MB).")
            os.remove(video_file)
        else:
            await ctx.send("❌ La génération de la vidéo a échoué. Un screenshot a peut-être été pris.")

        if screenshot and os.path.exists(screenshot):
            await ctx.send("🖼️ Voici un screenshot capturé au moment de l'erreur :", file=discord.File(screenshot))
            os.remove(screenshot)

    except Exception as e:
        await ctx.send(f"🚨 Une erreur critique est survenue lors de l'exécution de la commande : {e}")
        traceback.print_exc()

# --- COMMANDE PING ---
@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(f"Pong! Latence : {round(bot.latency * 1000)}ms")

# --- READY EVENT ---
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

# --- MAIN ---
async def main():
    await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
