import discord
from discord.ext import commands
import os
import asyncio
import time
import subprocess
import traceback
import requests

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURATION DES VARIABLES D'ENVIRONNEMENT ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")

if not all([DISCORD_TOKEN, CHESS_USERNAME, CHESS_PASSWORD]):
    raise ValueError("ERREUR: Variables d'environnement manquantes.")

# --- INITIALISATION DU BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- CAPTURE D'ÉCRAN EN CAS D'ERREUR ---
def capture_on_error(driver, label="error"):
    timestamp = int(time.time())
    filename = f"screenshot_{label}_{timestamp}.png"
    try:
        driver.save_screenshot(filename)
        return filename
    except Exception as e:
        print(f"[❌] Échec capture écran : {e}")
        return None

# --- ANALYSE EN DIRECT AVEC LICHESS ---
async def analyze_game_live(ctx, driver, game_id):
    await ctx.send(f"🔍 Analyse en direct lancée pour la partie `{game_id}`. J'arrêterai à la fin de la partie.")
    try:
        while True:
            await asyncio.sleep(10)

            status = driver.execute_script("return window.liveGame?.status || null;")
            if status and status.lower() != "playing":
                await ctx.send(f"🏁 Partie terminée (statut : `{status}`). Fin de l’analyse.")
                break

            fen = driver.execute_script("return window.liveGame?.fen || null;")
            if not fen:
                await ctx.send("⚠️ FEN non disponible, je réessaie dans 10 secondes...")
                continue

            response = requests.get("https://lichess.org/api/cloud-eval", params={"fen": fen, "multiPv": 1})
            if response.status_code != 200:
                await ctx.send("❌ Lichess ne répond pas pour l’analyse.")
                continue

            data = response.json()
            best_move = data["pvs"][0]["moves"]
            eval_info = data["pvs"][0].get("eval", {})
            cp = eval_info.get("cp")
            mate = eval_info.get("mate")

            evaluation = f"Mat en {mate}" if mate else f"{cp / 100:.2f}" if cp is not None else "Inconnue"
            await ctx.send(f"♟️ Coup suggéré : `{best_move}` | Évaluation : `{evaluation}`")
    except Exception as e:
        await ctx.send(f"🚨 Erreur analyse : {e}")

# --- ENREGISTREMENT VIDÉO ET RETOUR DRIVER ---
def record_chess_video(game_id):
    os.environ["DISPLAY"] = ":99"
    timestamp = int(time.time())
    video_filename = f"chess_{game_id}_{timestamp}.webm"
    screenshot_file = None

    xvfb = subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1920x1080x24"])
    time.sleep(1)

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--metrics-recording-only")
    chrome_options.add_argument("--mute-audio")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--disable-background-timer-throttling")
    chrome_options.add_argument("--disable-backgrounding-occluded-windows")
    chrome_options.add_argument("--disable-breakpad")
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--lang=en-US")
    chrome_options.add_experimental_option("prefs", {"intl.accept_languages": "en,en_US"})

    driver = None
    ffmpeg = None

    try:
        driver = webdriver.Chrome(ChromeDriverManager().install(), options=chrome_options)
        wait = WebDriverWait(driver, 20)

        ffmpeg = subprocess.Popen([
            "ffmpeg", "-y", "-video_size", "1920x1080", "-framerate", "25",
            "-f", "x11grab", "-i", ":99.0", "-c:v", "libvpx-vp9",
            "-b:v", "1M", "-pix_fmt", "yuv420p", video_filename
        ])

        # Connexion Chess.com
        driver.get("https://www.chess.com/login_and_go")

        try:
            accept_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'I Accept')] | //button[contains(., 'Reject All')]"))
            )
            accept_button.click()
            time.sleep(1)
        except:
            pass

        username_input = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='Username, Phone, or Email']"))
        )
        username_input.clear()
        username_input.send_keys(CHESS_USERNAME)

        password_input = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='Password']"))
        )
        password_input.clear()
        password_input.send_keys(CHESS_PASSWORD)

        login_button = wait.until(EC.element_to_be_clickable((By.ID, "login")))
        login_button.click()
        wait.until(EC.url_contains("chess.com/home"))
        time.sleep(2)

        try:
            dismiss_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Non, merci')] | //a[contains(@class, 'modal-trial-close-icon')]"))
            )
            dismiss_button.click()
            time.sleep(1)
        except:
            pass

        driver.get(f"https://www.chess.com/game/live/{game_id}")
        wait.until(EC.presence_of_element_located((By.ID, "game-board")))
        time.sleep(5)

        return video_filename, screenshot_file, driver

    except Exception as e:
        print(f"[🚨] Erreur Selenium : {e}")
        traceback.print_exc()
        if driver:
            screenshot_file = capture_on_error(driver, "record_error")
        return None, screenshot_file, None

    finally:
        if ffmpeg and ffmpeg.poll() is None:
            ffmpeg.terminate()
            try:
                ffmpeg.wait(timeout=5)
            except subprocess.TimeoutExpired:
                ffmpeg.kill()
        if xvfb:
            xvfb.terminate()

# --- COMMANDE DISCORD ---
@bot.command(name="videochess")
async def videochess(ctx, game_id: str):
    if not game_id.isdigit():
        await ctx.send("❌ L'ID de la partie doit être un numéro. Exemple: `!videochess 987654321`")
        return

    await ctx.send(f"🎥 Lancement de l'enregistrement pour la partie `{game_id}`...")
    try:
        video_file, screenshot, driver = await asyncio.to_thread(record_chess_video, game_id)

        if driver:
            await analyze_game_live(ctx, driver, game_id)
            driver.quit()

        if video_file and os.path.exists(video_file):
            if os.path.getsize(video_file) < 8 * 1024 * 1024:
                await ctx.send("✅ Enregistrement terminé !", file=discord.File(video_file))
            else:
                await ctx.send("⚠️ Vidéo trop lourde pour Discord (> 8MB).")
            os.remove(video_file)
        else:
            await ctx.send("❌ La vidéo n'a pas pu être générée.")

        if screenshot and os.path.exists(screenshot):
            await ctx.send("🖼️ Screenshot capturé :", file=discord.File(screenshot))
            os.remove(screenshot)

    except Exception as e:
        await ctx.send(f"🚨 Erreur critique : {e}")
        traceback.print_exc()

# --- COMMANDE PING ---
@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(f"Pong! Latence : {round(bot.latency * 1000)}ms")

# --- BOT PRÊT ---
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")
    print("🤖 Le bot est prêt à recevoir des commandes.")

# --- DÉMARRAGE ---
async def main():
    await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())