import discord
from discord.ext import commands
import os
import asyncio
import time
import subprocess
import traceback
import random
import undetected_chromedriver as uc  # ✅ Import sans .v2
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException

# --- CONFIGURATION DES VARIABLES D'ENVIRONNEMENT ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
INSTA_USERNAME = os.getenv("INSTA_USERNAME")
INSTA_PASSWORD = os.getenv("INSTA_PASSWORD")
DEFAULT_ACCOUNT = os.getenv("ACCOUNT_TO_WATCH", "instagram")

if not all([DISCORD_TOKEN, INSTA_USERNAME, INSTA_PASSWORD]):
    raise ValueError("ERREUR: Variables d'environnement manquantes.")

# --- INITIALISATION DU BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- FONCTION DE CAPTURE D'ÉCRAN ---
def capture_on_error(driver, label="error"):
    timestamp = int(time.time())
    filename = f"/tmp/screenshot_{label}_{timestamp}.png"
    try:
        driver.save_screenshot(filename)
        print(f"[📸] Screenshot : {filename}")
        return filename
    except Exception as e:
        print(f"[❌] Échec screenshot : {e}")
    return None

# --- FONCTION D'ENREGISTREMENT INSTAGRAM ---
def record_insta_session(account_to_watch):
    os.environ["DISPLAY"] = ":99"
    timestamp = int(time.time())
    video_filename = f"/tmp/insta_{account_to_watch}_{timestamp}.webm"
    screenshot_file = None

    xvfb = subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1280x720x24"])
    time.sleep(1)

    chrome_options = uc.ChromeOptions()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1280,720")
    chrome_options.add_argument("--lang=en-US")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    driver = None
    ffmpeg = None

    try:
        driver = uc.Chrome(options=chrome_options, headless=False)  # ✅ headless désactivé
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        wait = WebDriverWait(driver, 20)

        ffmpeg = subprocess.Popen([
            "ffmpeg", "-y", "-video_size", "1280x720", "-framerate", "25",
            "-f", "x11grab", "-i", ":99.0", "-c:v", "libvpx-vp9",
            "-b:v", "1M", "-pix_fmt", "yuv420p", video_filename
        ])

        # Tentative de connexion avec retry en cas de 429
        MAX_RETRIES = 3
        RETRY_DELAY = 5
        for attempt in range(MAX_RETRIES):
            driver.get("https://www.instagram.com/accounts/login/")
            time.sleep(random.uniform(3, 6))
            if "Too Many Requests" in driver.page_source:
                print(f"[🚫] Tentative {attempt+1}/{MAX_RETRIES} : 429 détecté.")
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                break
        else:
            raise Exception("Erreur 429 répétée")

        # Cookies
        try:
            cookie_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Allow all cookies')]"))
            )
            cookie_btn.click()
            time.sleep(random.uniform(1, 2))
        except:
            print("[ℹ️] Pas de pop-up cookies.")

        # Login
        print("[🔐] Connexion...")
        wait.until(EC.visibility_of_element_located((By.NAME, "username"))).send_keys(INSTA_USERNAME)
        time.sleep(random.uniform(1, 2))
        driver.find_element(By.NAME, "password").send_keys(INSTA_PASSWORD)
        time.sleep(random.uniform(1, 2.5))
        driver.find_element(By.XPATH, "//button[@type='submit']").click()

        wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(@href, '/direct/inbox/')]")))
        print("[✅] Connecté à Instagram.")
        time.sleep(random.uniform(2, 4))

        # Pop-up "Enregistrer infos"
        try:
            btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Not Now')]"))
            )
            btn.click()
            time.sleep(random.uniform(1, 2))
        except:
            print("[ℹ️] Pas de pop-up 'infos'.")

        # Pop-up notifications
        try:
            notif = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Not Now')]"))
            )
            notif.click()
            time.sleep(random.uniform(1, 2))
        except:
            print("[ℹ️] Pas de pop-up notif.")

        # Aller au profil
        driver.get(f"https://www.instagram.com/{account_to_watch}/")
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "h2")))
        print("[✅] Profil chargé.")
        time.sleep(10)

    except Exception as e:
        print(f"[❌] Erreur principale : {e}")
        traceback.print_exc()
        if driver:
            screenshot_file = capture_on_error(driver, "insta_error")

    finally:
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

    return video_filename if os.path.exists(video_filename) else None, \
           screenshot_file if screenshot_file and os.path.exists(screenshot_file) else None

# --- COMMANDE DISCORD ---
@bot.command(name="videoinsta")
async def videoinsta(ctx, account_name: str = None):
    target_account = account_name or DEFAULT_ACCOUNT
    await ctx.send(f"🎥 Enregistrement du profil `{target_account}`...")
    try:
        video_file, screenshot = await asyncio.to_thread(record_insta_session, target_account)

        if video_file:
            if os.path.getsize(video_file) < 25 * 1024 * 1024:
                await ctx.send("✅ Enregistrement terminé !", file=discord.File(video_file))
            else:
                await ctx.send("⚠️ Vidéo trop lourde pour Discord (> 25MB).")
            os.remove(video_file)
        else:
            await ctx.send("❌ Erreur pendant l'enregistrement.")

        if screenshot:
            await ctx.send("🖼️ Screenshot lors de l'erreur :", file=discord.File(screenshot))
            os.remove(screenshot)

    except Exception as e:
        await ctx.send(f"🚨 Erreur critique : {e}")
        traceback.print_exc()

@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(f"Pong! Latence : {round(bot.latency * 1000)}ms")

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")
    print("🤖 Prêt à recevoir des commandes.")

async def main():
    await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())