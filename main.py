import os
import discord
from discord.ext import commands
import asyncio
import subprocess
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- CHARGEMENT DES VARIABLES D'ENVIRONNEMENT ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
INSTA_USERNAME = os.getenv("INSTA_USERNAME")
INSTA_PASSWORD = os.getenv("INSTA_PASSWORD")
ACCOUNT_TO_WATCH = os.getenv("ACCOUNT_TO_WATCH")

# --- VARIABLES GLOBALES POUR L'ENREGISTREMENT ---
recording_process = None
recording_path = "/tmp/insta_session.webm"

# --- CONFIGURATION DU BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- FONCTIONS D'ENREGISTREMENT ---
def start_recording():
    """Lance l'enregistrement de l'écran avec ffmpeg."""
    global recording_process
    # Commande pour enregistrer l'affichage virtuel :99
    cmd = [
        "ffmpeg", "-y",
        "-video_size", "1280x720",
        "-f", "x11grab",
        "-i", ":99.0",
        "-r", "25",
        recording_path
    ]
    recording_process = subprocess.Popen(cmd)

def stop_recording():
    """Arrête le processus ffmpeg et retourne le chemin de la vidéo."""
    global recording_process
    if recording_process:
        recording_process.terminate()
        recording_process.wait()
        recording_process = None
        return recording_path
    return None

# --- COMMANDE PRINCIPALE DU BOT ---
@bot.command()
async def insta(ctx):
    """Lance une session Instagram, l'enregistre et envoie la vidéo."""
    await ctx.send("🎬 Lancement de l'enregistrement et de la session Instagram...")
    start_recording()

    driver = None  # Initialise le driver à None pour le bloc finally
    try:
        # Configuration des options pour Chrome
        options = uc.ChromeOptions()
        options.add_argument("--headless=new") # Mode headless moderne
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1280,720")

        # Initialisation du driver
        driver = uc.Chrome(options=options, display_visible=True)
        wait = WebDriverWait(driver, 20) # Temps d'attente max pour les éléments

        # Processus de connexion
        await ctx.send("🌐 Navigation vers Instagram...")
        driver.get("https://www.instagram.com/accounts/login/")

        wait.until(EC.visibility_of_element_located((By.NAME, "username"))).send_keys(INSTA_USERNAME)
        wait.until(EC.visibility_of_element_located((By.NAME, "password"))).send_keys(INSTA_PASSWORD)
        wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@type='submit']"))).click()
        
        await ctx.send("🔒 Connexion en cours...")
        # Attendre un élément de la page d'accueil pour confirmer la connexion
        wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(@href, '/direct/inbox/')]")))
        
        # Navigation vers le profil cible
        await ctx.send(f"👀 Visite du profil de {ACCOUNT_TO_WATCH}...")
        driver.get(f"https://www.instagram.com/{ACCOUNT_TO_WATCH}/")
        
        # Attendre que le nom du profil soit visible
        wait.until(EC.visibility_of_element_located((By.XPATH, "//h2")))
        await asyncio.sleep(5) # Pause pour s'assurer que tout est bien chargé

        await ctx.send("✅ Visite du compte terminée avec succès.")

    except Exception as e:
        # En cas d'erreur, envoyer un message et un screenshot
        await ctx.send(f"❌ Une erreur est survenue : {str(e)[:1900]}")
        if driver:
            try:
                driver.save_screenshot("/tmp/error.png")
                await ctx.send("📸 Voici ce que le bot voyait :", file=discord.File("/tmp/error.png"))
            except Exception as screenshot_error:
                await ctx.send(f"⚠️ Impossible de prendre un screenshot : {screenshot_error}")

    finally:
        # Ce bloc s'exécute toujours, que le try ait réussi ou non
        await ctx.send("🛑 Arrêt de la session...")
        if driver:
            driver.quit()
        
        path = stop_recording()
        if path and os.path.exists(path):
            await ctx.send("🎥 Voici la vidéo de la session :", file=discord.File(path))
        else:
            await ctx.send("⚠️ La vidéo n'a pas pu être récupérée.")

# --- ÉVÉNEMENT 'on_ready' ---
@bot.event
async def on_ready():
    """S'affiche dans la console quand le bot est connecté."""
    print(f"✅ Connecté en tant que {bot.user}")

# --- DÉMARRAGE DU BOT ---
if __name__ == "__main__":
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        print("❌ Erreur critique : Le DISCORD_TOKEN n'est pas défini.")
