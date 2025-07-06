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
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
INSTA_USERNAME = os.getenv("INSTA_USERNAME") # <-- CHANGÉ
INSTA_PASSWORD = os.getenv("INSTA_PASSWORD") # <-- CHANGÉ
# Compte par défaut à visiter si aucun n'est spécifié dans la commande
DEFAULT_ACCOUNT = os.getenv("ACCOUNT_TO_WATCH", "instagram") 

if not all([DISCORD_TOKEN, INSTA_USERNAME, INSTA_PASSWORD]):
    raise ValueError("ERREUR: Des variables d'environnement (DISCORD_TOKEN, INSTA_USERNAME, INSTA_PASSWORD) sont manquantes.")

# --- INITIALISATION DU BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- FONCTION DE CAPTURE D'ÉCRAN EN CAS D'ERREUR (INCHANGÉE) ---
def capture_on_error(driver, label="error"):
    timestamp = int(time.time())
    filename = f"/tmp/screenshot_{label}_{timestamp}.png"
    try:
        driver.save_screenshot(filename)
        print(f"[📸] Screenshot d'erreur capturé : {filename}")
        return filename
    except Exception as e:
        print(f"[❌] La capture du screenshot a échoué : {e}")
    return None

# --- FONCTION D'ENREGISTREMENT VIDÉO (MODIFIÉE POUR INSTAGRAM) ---
def record_insta_session(account_to_watch):
    os.environ["DISPLAY"] = ":99"
    timestamp = int(time.time())
    video_filename = f"/tmp/insta_{account_to_watch}_{timestamp}.webm"
    screenshot_file = None

    # Configuration pour le navigateur headless (sans interface graphique)
    xvfb = subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1280x720x24"])
    time.sleep(1)

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1280,720")
    chrome_options.add_argument("--lang=en-US") 
    chrome_options.add_experimental_option('prefs', {'intl.accept_languages': 'en,en_US'})

    driver = None
    ffmpeg = None

    try:
        driver = webdriver.Chrome(options=chrome_options)
        wait = WebDriverWait(driver, 20)

        # Démarrage de l'enregistrement vidéo
        ffmpeg = subprocess.Popen([
            "ffmpeg", "-y", "-video_size", "1280x720", "-framerate", "25",
            "-f", "x11grab", "-i", ":99.0", "-c:v", "libvpx-vp9",
            "-b:v", "1M", "-pix_fmt", "yuv420p", video_filename
        ])

        # 1. Aller sur la page de connexion Instagram
        driver.get("https://www.instagram.com/accounts/login/")

        # 2. Gérer le pop-up de cookies
        try:
            print("[⏳] Recherche du pop-up de cookies...")
            cookie_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Allow all cookies')]"))
            )
            cookie_button.click()
            print("[✅] Pop-up de cookies fermé.")
            time.sleep(1)
        except Exception:
            print("[ℹ️] Aucun pop-up de cookies n'a été détecté.")

        # 3. Se connecter
        print("[⏳] Tentative de connexion...")
        wait.until(EC.visibility_of_element_located((By.NAME, "username"))).send_keys(INSTA_USERNAME)
        driver.find_element(By.NAME, "password").send_keys(INSTA_PASSWORD)
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        
        # Attendre la fin du chargement en cherchant un élément de la page d'accueil
        wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(@href, '/direct/inbox/')]")))
        print("[✅] Connexion réussie.")

        # 4. Gérer le pop-up "Enregistrer les informations de connexion"
        try:
            print("[⏳] Recherche du pop-up 'Enregistrer les infos'...")
            not_now_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//div[text()='Not Now']"))
            )
            not_now_button.click()
            print("[✅] Pop-up 'Enregistrer les infos' fermé.")
            time.sleep(1)
        except Exception:
            print("[ℹ️] Aucun pop-up 'Enregistrer les infos' n'a été détecté.")

        # 5. Gérer le pop-up "Activer les notifications"
        try:
            print("[⏳] Recherche du pop-up 'Notifications'...")
            notif_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Not Now')]"))
            )
            notif_button.click()
            print("[✅] Pop-up 'Notifications' fermé.")
        except Exception:
            print("[ℹ️] Aucun pop-up de notifications n'a été détecté.")

        # 6. Naviguer vers le profil cible
        print(f"[➡️] Navigation vers le profil : {account_to_watch}")
        driver.get(f"https://www.instagram.com/{account_to_watch}/")
        
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "h2"))) # Attendre que le nom du profil apparaisse
        print("[✅] Le profil est chargé.")
        time.sleep(10) # Laisse le temps d'enregistrer quelques secondes du profil

    except Exception as e:
        print(f"[🚨] Une erreur majeure est survenue dans Selenium : {e}")
        traceback.print_exc()
        if driver:
            screenshot_file = capture_on_error(driver, "insta_error")

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

    # Retourner les fichiers générés (s'ils existent)
    video_result = video_filename if os.path.exists(video_filename) else None
    screenshot_result = screenshot_file if screenshot_file and os.path.exists(screenshot_file) else None
    return video_result, screenshot_result

# --- COMMANDE DISCORD (MODIFIÉE POUR INSTAGRAM) ---
@bot.command(name="videoinsta")
async def videoinsta(ctx, account_name: str = None):
    # Utilise le compte spécifié, ou le compte par défaut si aucun n'est donné
    target_account = account_name if account_name else DEFAULT_ACCOUNT
        
    await ctx.send(f"🎥 Lancement de l'enregistrement pour le profil `{target_account}`...")
    try:
        # Exécute la fonction de blocage dans un thread séparé pour ne pas bloquer le bot
        video_file, screenshot = await asyncio.to_thread(record_insta_session, target_account)

        if video_file:
            # Discord a une limite de taille de fichier
            if os.path.getsize(video_file) < 25 * 1024 * 1024: # Limite augmentée à 25MB pour Nitro Basic
                await ctx.send("✅ Enregistrement terminé !", file=discord.File(video_file))
            else:
                await ctx.send(f"⚠️ La vidéo a été enregistrée mais est trop lourde pour Discord (> 25MB). Chemin: `{video_file}`")
            os.remove(video_file)
        else:
            await ctx.send("❌ La génération de la vidéo a échoué. Une erreur s'est produite.")

        # Envoyer le screenshot si un a été pris lors d'une erreur
        if screenshot:
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

