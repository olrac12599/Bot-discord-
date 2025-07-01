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

# --- CONFIGURATION DES VARIABLES D'ENVIRONNEMENT ---
# Assure-toi que tes variables d'environnement sont bien chargées
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")

if not all([DISCORD_TOKEN, CHESS_USERNAME, CHESS_PASSWORD]):
    raise ValueError("ERREUR: Des variables d'environnement (DISCORD_TOKEN, CHESS_USERNAME, CHESS_PASSWORD) sont manquantes.")

# --- INITIALISATION DU BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- FONCTION DE CAPTURE D'ÉCRAN EN CAS D'ERREUR ---
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

# --- FONCTION D'ENREGISTREMENT VIDÉO (VERSION FINALE CORRIGÉE) ---
def record_chess_video(game_id):
    os.environ["DISPLAY"] = ":99"
    timestamp = int(time.time())
    video_filename = f"chess_{game_id}_{timestamp}.webm"
    screenshot_file = None

    # Configuration pour le navigateur headless (sans interface graphique)
    xvfb = subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1920x1080x24"])
    time.sleep(1)

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    # Forcer la langue en anglais aide à avoir des sélecteurs de boutons prévisibles ("I Accept", etc.)
    chrome_options.add_argument("--lang=en-US") 
    chrome_options.add_experimental_option('prefs', {'intl.accept_languages': 'en,en_US'})


    driver = None
    ffmpeg = None

    try:
        driver = webdriver.Chrome(options=chrome_options)
        wait = WebDriverWait(driver, 20)

        # Démarrage de l'enregistrement vidéo avec FFmpeg
        ffmpeg = subprocess.Popen([
            "ffmpeg", "-y", "-video_size", "1920x1080", "-framerate", "25",
            "-f", "x11grab", "-i", ":99.0", "-c:v", "libvpx-vp9",
            "-b:v", "1M", "-pix_fmt", "yuv420p", video_filename
        ])

        # 1. Aller sur la page de connexion
        driver.get("https://www.chess.com/login_and_go")

        # 2. Gérer le pop-up de confidentialité (étape cruciale)
        try:
            print("[⏳] Recherche du pop-up de confidentialité...")
            # On cherche un bouton contenant "I Accept" OU "Reject All" pour plus de robustesse
            accept_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'I Accept')] | //button[contains(., 'Reject All')]"))
            )
            accept_button.click()
            print("[✅] Pop-up de confidentialité fermé.")
            time.sleep(1) # Attendre que le pop-up disparaisse
        except Exception:
            print("[ℹ️] Aucun pop-up de confidentialité n'a été détecté.")

        # 3. Se connecter
        print("[⏳] Tentative de connexion...")
        username_input = wait.until(EC.element_to_be_clickable((By.ID, "username")))
        username_input.send_keys(CHESS_USERNAME)
        
        password_input = driver.find_element(By.ID, "password")
        password_input.send_keys(CHESS_PASSWORD)
        
        login_button = driver.find_element(By.ID, "login")
        login_button.click()

        wait.until(EC.url_contains("chess.com/home"))
        print("[✅] Connexion réussie.")

        # 4. Fermer le pop-up "Leçon rapide" ou autre pop-up post-connexion
        try:
            print("[⏳] Recherche de pop-ups post-connexion...")
            # Cherche le bouton "Non, merci" ou une icône de fermeture de modal
            dismiss_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Non, merci')] | //a[contains(@class, 'modal-trial-close-icon')]"))
            )
            dismiss_button.click()
            print("[✅] Pop-up post-connexion fermé.")
            time.sleep(1)
        except Exception:
            print("[ℹ️] Aucun pop-up post-connexion n'a été détecté.")

        # 5. Naviguer vers la partie en direct
        print(f"[➡️] Navigation vers la partie : {game_id}")
        driver.get(f"https://www.chess.com/game/live/{game_id}")
        
        wait.until(EC.presence_of_element_located((By.ID, "game-board")))
        print("[✅] La partie est chargée.")
        time.sleep(10) # Laisse le temps d'enregistrer quelques secondes de la partie

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
    if not game_id.isdigit():
        await ctx.send("❌ L'ID de la partie doit être un numéro. Exemple: `!videochess 987654321`")
        return
        
    await ctx.send(f"🎥 Lancement de l'enregistrement pour la partie `{game_id}`...")
    try:
        video_file, screenshot = await asyncio.to_thread(record_chess_video, game_id)

        if video_file and os.path.exists(video_file):
            if os.path.getsize(video_file) < 8 * 1024 * 1024:
                await ctx.send("✅ Enregistrement terminé !", file=discord.File(video_file))
            else:
                await ctx.send("⚠️ La vidéo a été enregistrée mais est trop lourde pour Discord (> 8MB).")
            os.remove(video_file)
        else:
            await ctx.send("❌ La génération de la vidéo a échoué.")

        if screenshot and os.path.exists(screenshot):
            await ctx.send("🖼️ Voici un screenshot capturé au moment de l'erreur :", file=discord.File(screenshot))
            os.remove(screenshot)

    except Exception as e:
        await ctx.send(f"🚨 Une erreur critique est survenue : {e}")
        traceback.print_exc()

# --- COMMANDE PING POUR TESTER LE BOT ---
@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(f"Pong! Latence : {round(bot.latency * 1000)}ms")

# --- ÉVÉNEMENT QUAND LE BOT EST PRÊT ---
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")
    print("🤖 Le bot est prêt à recevoir des commandes.")

# --- DÉMARRAGE DU BOT ---
async def main():
    await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())

