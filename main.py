import discord
from discord.ext import commands
import os
import asyncio
import time
import subprocess
import traceback
import requests
import undetected_chromedriver as uc

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- CONFIGURATION ENV ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")
PROXY_SERVER = os.getenv("PROXY_SERVER") # Récupère le proxy depuis les variables d'env

if not all([DISCORD_TOKEN, CHESS_USERNAME, CHESS_PASSWORD]):
    raise ValueError("❌ Des variables d'environnement (DISCORD_TOKEN, CHESS_USERNAME, CHESS_PASSWORD) sont manquantes.")

# --- DISCORD BOT ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- CAPTURE D'ÉCRAN ---
def capture_on_error(driver, label="error"):
    filename = f"screenshot_{label}_{int(time.time())}.png"
    try:
        driver.save_screenshot(filename)
        return filename
    except Exception as e:
        print(f"❌ La capture du screenshot a échoué : {e}")
        return None

# --- ANALYSE LICHESS LIVE (Fonction non utilisée pour Chess.com, conservée de ton code) ---
async def analyze_game_live(ctx, driver, game_id):
    await ctx.send(f"🔍 Analyse en direct lancée pour `{game_id}`.")
    try:
        while True:
            await asyncio.sleep(10)
            # Cette partie est spécifique à une certaine structure de page et peut nécessiter une adaptation
            status_script = "return window.liveGame?.status || null;"
            status = driver.execute_script(status_script)
            if status and status.lower() != "playing":
                await ctx.send(f"🏁 Partie terminée (statut : `{status}`)")
                break

            fen_script = "return window.liveGame?.fen || null;"
            fen = driver.execute_script(fen_script)
            if not fen:
                await ctx.send("⚠️ FEN non disponible. Nouvelle tentative dans 10s...")
                continue

            res = requests.get("https://lichess.org/api/cloud-eval", params={"fen": fen, "multiPv": 1})
            if res.status_code != 200:
                await ctx.send("❌ L'API de Lichess ne répond pas.")
                continue

            data = res.json()
            move = data["pvs"][0]["moves"]
            eval_info = data["pvs"][0].get("eval", {})
            cp = eval_info.get("cp")
            mate = eval_info.get("mate")
            eval_str = f"Mat en {mate}" if mate else f"{cp / 100:.2f}" if cp else "Inconnue"
            await ctx.send(f"♟️ Coup suggéré : `{move}` | Éval : `{eval_str}`")

    except Exception as e:
        await ctx.send(f"🚨 Erreur durant l'analyse : {e}")

# --- VIDÉO & DRIVER SETUP ---
def record_chess_video(game_id):
    os.environ["DISPLAY"] = ":99"
    filename = f"chess_{game_id}_{int(time.time())}.webm"
    screenshot_file = None

    xvfb = subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1920x1080x24"])
    time.sleep(1)

    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=en-US")
    options.add_argument("--mute-audio")
    
    # --- AJOUT DU PROXY (RECOMMANDÉ) ---
    # Assure-toi d'avoir défini la variable d'environnement PROXY_SERVER
    # Format : "http://user:password@host:port"
    if PROXY_SERVER:
        print("[ℹ️] Utilisation du serveur proxy configuré.")
        options.add_argument(f'--proxy-server={PROXY_SERVER}')
    else:
        print("[⚠️] Aucun serveur proxy configuré.")

    ffmpeg = None
    driver = None

    try:
        driver = uc.Chrome(options=options)
        wait = WebDriverWait(driver, 20)

        ffmpeg = subprocess.Popen([
            "ffmpeg", "-y", "-video_size", "1920x1080", "-framerate", "25",
            "-f", "x11grab", "-i", ":99.0", "-c:v", "libvpx-vp9",
            "-b:v", "1M", "-pix_fmt", "yuv420p", filename
        ])

        driver.get("https://www.chess.com/login_and_go")

        # --- TENTATIVE DE GESTION DU CHALLENGE CLOUDFLARE ---
        try:
            print("[⏳] Recherche d'un challenge Cloudflare...")
            iframe = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "iframe[title='Widget containing a Cloudflare security challenge']"))
            )
            driver.switch_to.frame(iframe)
            checkbox = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "cf-stage-human-check"))
            )
            checkbox.click()
            print("[✅] Clic sur la case de vérification Cloudflare.")
            driver.switch_to.default_content()
            time.sleep(5)
        except Exception:
            print("[ℹ️] Pas de challenge Cloudflare détecté ou impossible à cliquer.")

        # Connexion
        username_input = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='Username, Phone, or Email']"))
        )
        username_input.send_keys(CHESS_USERNAME)
        password_input = driver.find_element(By.XPATH, "//input[@placeholder='Password']")
        password_input.send_keys(CHESS_PASSWORD)
        login_button = driver.find_element(By.ID, "login")
        login_button.click()

        wait.until(EC.url_contains("chess.com/home"))
        time.sleep(2)

        # Partie
        driver.get(f"https://www.chess.com/game/live/{game_id}")
        wait.until(EC.presence_of_element_located((By.ID, "game-board")))
        time.sleep(5)

        return filename, screenshot_file, driver

    except Exception as e:
        print(f"🚨 Erreur Selenium : {e}")
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
        await ctx.send("❌ L'ID de la partie doit être un numéro.")
        return

    await ctx.send(f"🎥 Lancement de l'enregistrement pour la partie `{game_id}`...")
    try:
        # On ne garde pas le driver actif pour l'analyse, car la fonction d'analyse est pour Lichess
        video_file, screenshot, driver = await asyncio.to_thread(record_chess_video, game_id)

        if driver:
            # Si tu veux utiliser la fonction `analyze_game_live` plus tard, le driver est ici.
            # Pour l'instant, on le ferme simplement.
            driver.quit()

        if video_file and os.path.exists(video_file):
            if os.path.getsize(video_file) < 8 * 1024 * 1024:
                await ctx.send("✅ Enregistrement terminé :", file=discord.File(video_file))
            else:
                await ctx.send("⚠️ La vidéo est trop lourde pour Discord (>8MB).")
            os.remove(video_file)
        else:
            await ctx.send("❌ La vidéo n’a pas pu être générée.")

        if screenshot and os.path.exists(screenshot):
            await ctx.send("🖼️ Un screenshot a été capturé durant l'erreur :", file=discord.File(screenshot))
            os.remove(screenshot)

    except Exception as e:
        await ctx.send(f"🚨 Erreur critique lors de l'exécution de la commande : {e}")
        traceback.print_exc()

# --- PING ---
@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(f"Pong! Latence : {round(bot.latency * 1000)}ms")

# --- READY ---
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")
    print("🤖 Le bot est prêt à recevoir des commandes.")

# --- MAIN ---
async def main():
    await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
