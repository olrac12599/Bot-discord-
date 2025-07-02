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

if not all([DISCORD_TOKEN, CHESS_USERNAME, CHESS_PASSWORD]):
    raise ValueError("❌ Variables d'environnement manquantes.")

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
        print(f"❌ Screenshot failed: {e}")
        return None

# --- ANALYSE LICHESS LIVE ---
async def analyze_game_live(ctx, driver, game_id):
    await ctx.send(f"🔍 Analyse en direct lancée pour `{game_id}`.")
    try:
        while True:
            await asyncio.sleep(10)
            status = driver.execute_script("return window.liveGame?.status || null;")
            if status and status.lower() != "playing":
                await ctx.send(f"🏁 Partie terminée (statut : `{status}`)")
                break

            fen = driver.execute_script("return window.liveGame?.fen || null;")
            if not fen:
                await ctx.send("⚠️ FEN non dispo. Nouvelle tentative dans 10s...")
                continue

            res = requests.get("https://lichess.org/api/cloud-eval", params={"fen": fen, "multiPv": 1})
            if res.status_code != 200:
                await ctx.send("❌ Lichess ne répond pas.")
                continue

            data = res.json()
            move = data["pvs"][0]["moves"]
            eval_info = data["pvs"][0].get("eval", {})
            cp = eval_info.get("cp")
            mate = eval_info.get("mate")
            eval_str = f"Mat en {mate}" if mate else f"{cp / 100:.2f}" if cp else "Inconnue"
            await ctx.send(f"♟️ Coup suggéré : `{move}` | Éval : `{eval_str}`")
    except Exception as e:
        await ctx.send(f"🚨 Erreur analyse : {e}")

# --- VIDÉO & DRIVER SETUP ---
def record_chess_video(game_id):
    os.environ["DISPLAY"] = ":99"
    filename = f"chess_{game_id}_{int(time.time())}.webm"
    screenshot_file = None

    xvfb = subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1920x1080x24"])
    time.sleep(1)

    options = uc.ChromeOptions()
    options.binary_location = "/usr/bin/chromium"
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=en-US")
    options.add_argument("--mute-audio")
    options.add_argument("--disable-blink-features=AutomationControlled")

    ffmpeg = None
    driver = None

    try:
        driver = uc.Chrome(
            headless=True,
            options=options,
            use_subprocess=True,
            driver_executable_path="/usr/local/bin/chromedriver"
        )

        # Masquer webdriver JS fingerprint
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })

        wait = WebDriverWait(driver, 20)

        ffmpeg = subprocess.Popen([
            "ffmpeg", "-y", "-video_size", "1920x1080", "-framerate", "25",
            "-f", "x11grab", "-i", ":99.0", "-c:v", "libvpx-vp9",
            "-b:v", "1M", "-pix_fmt", "yuv420p", filename
        ])

        driver.get("https://www.chess.com/login_and_go")

        # Cookies / Pop-up
        try:
            accept = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Accept')]"))
            )
            accept.click()
            time.sleep(1)
        except:
            pass

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
        await ctx.send("❌ L'ID doit être un numéro.")
        return

    await ctx.send(f"🎥 Enregistrement pour `{game_id}`...")
    try:
        video_file, screenshot, driver = await asyncio.to_thread(record_chess_video, game_id)

        if driver:
            await analyze_game_live(ctx, driver, game_id)
            driver.quit()

        if video_file and os.path.exists(video_file):
            if os.path.getsize(video_file) < 8 * 1024 * 1024:
                await ctx.send("✅ Enregistrement terminé :", file=discord.File(video_file))
            else:
                await ctx.send("⚠️ Vidéo trop lourde (>8MB).")
            os.remove(video_file)
        else:
            await ctx.send("❌ La vidéo n’a pas pu être générée.")

        if screenshot and os.path.exists(screenshot):
            await ctx.send("🖼️ Screenshot capturé :", file=discord.File(screenshot))
            os.remove(screenshot)

    except Exception as e:
        await ctx.send(f"🚨 Erreur : {e}")
        traceback.print_exc()

# --- PING ---
@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(f"Pong! Latence : {round(bot.latency * 1000)}ms")

# --- READY ---
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")
    print("🤖 Prêt à recevoir des commandes.")

# --- MAIN ---
async def main():
    await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())