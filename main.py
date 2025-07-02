
import discord
from discord.ext import commands
import os
import asyncio
import aiohttp
import io
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth

# --- CONFIG ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")
DISCORD_FILE_LIMIT_BYTES = 8 * 1024 * 1024

videos_dir = Path("videos")
videos_dir.mkdir(exist_ok=True)
last_video_paths = {}
active_tasks = {}

# --- DISCORD BOT ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- UTILS ANALYSE ---
async def query_lichess_analysis(fen: str):
    url = f"https://lichess.org/api/cloud-eval?fen={fen}&multiPv=3"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            return None

def evaluate_move(score_before: float, score_after: float, color: str) -> str:
    delta = score_after - score_before if color == "white" else score_before - score_after
    if delta >= 150:
        return "Brillant"
    elif delta >= 80:
        return "Très bon coup"
    elif delta >= 20:
        return "Bon coup"
    elif -20 <= delta < 20:
        return "Coup neutre"
    elif -80 <= delta < -20:
        return "Inexact"
    elif -150 <= delta < -80:
        return "Erreur"
    else:
        return "Gaffe"

async def analyze_fen_sequence(fen_before, fen_after, color):
    eval_before = await query_lichess_analysis(fen_before)
    eval_after = await query_lichess_analysis(fen_after)
    if not eval_before or not eval_after:
        return None
    try:
        score_before = eval_before["pvs"][0]["cp"]
        score_after = eval_after["pvs"][0]["cp"]
    except (KeyError, IndexError):
        return None
    annotation = evaluate_move(score_before, score_after, color)
    return annotation, f"{score_before} → {score_after}"

# --- SCRAPING ---
class ScrapingError(Exception):
    def __init__(self, message, video_path=None):
        super().__init__(message)
        self.video_path = video_path

async def get_fen_from_page(page):
    try:
        element = await page.query_selector("cg-container")
        return await element.get_attribute("data-fen")
    except:
        return None

async def get_pgn_from_chess_com(url, username, password, discord_channel):
    stealth = Stealth()
    async with stealth.use_async(async_playwright()) as p:
        browser = await p.chromium.launch(headless=True, args=[
            '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu'
        ])
        context = await browser.new_context(record_video_dir=str(videos_dir))
        page = await context.new_page()

        video_path = None
        last_fen = None
        color_to_move = "white"

        try:
            await page.goto("https://www.chess.com/login_and_go", timeout=90000)
            await page.wait_for_load_state('domcontentloaded')
            try:
                await page.get_by_role("button", name="I Accept").click(timeout=3000)
            except PlaywrightTimeoutError:
                pass

            await page.get_by_placeholder("Username, Phone, or Email").type(username, delay=50)
            await page.get_by_placeholder("Password").type(password, delay=50)
            await page.get_by_role("button", name="Log In").click()
            await page.wait_for_url("**/home", timeout=15000)

            await page.goto(url, timeout=90000)

            for _ in range(60):
                await asyncio.sleep(10)
                if asyncio.current_task().cancelled():
                    break

                current_fen = await get_fen_from_page(page)
                if not current_fen:
                    continue

                if current_fen != last_fen and last_fen is not None:
                    result = await analyze_fen_sequence(last_fen, current_fen, color_to_move)
                    if result:
                        annotation, score_diff = result
                        piece = "♙ Blanc" if color_to_move == "white" else "♟️ Noir"
                        await discord_channel.send(f"{piece} joue : **{annotation}** ({score_diff})")
                    color_to_move = "black" if color_to_move == "white" else "white"

                last_fen = current_fen

            await page.locator("button.share-button-component").click(timeout=30000)
            await page.locator('div.share-menu-tab-component-header:has-text("PGN")').click(timeout=20000)
            pgn_text = await page.input_value('textarea.share-menu-tab-pgn-textarea', timeout=20000)

            video_path = await page.video.path()
            await context.close()
            await browser.close()
            return pgn_text, video_path

        except Exception as e:
            try:
                video_path = await page.video.path()
            except:
                pass
            await context.close()
            await browser.close()
            raise ScrapingError(str(e), video_path=video_path)

# --- COMMANDES DISCORD ---
@bot.command(name="chess")
async def chess(ctx, url: str):
    if ctx.channel.id in active_tasks:
        return await ctx.send("⚠️ Une analyse est déjà en cours ici. Tape `!stop` pour l'arrêter.")
    
    async def run():
        msg = await ctx.send("🕵️ Lancement de l'analyse et de l'enregistrement vidéo...")
        try:
            pgn, video_path = await get_pgn_from_chess_com(url, CHESS_USERNAME, CHESS_PASSWORD, ctx.channel)
            if video_path:
                last_video_paths[ctx.channel.id] = video_path
            pgn_short = (pgn[:1900] + "...") if len(pgn) > 1900 else pgn
            await msg.edit(content=f"✅ **PGN récupéré :**\n```\n{pgn_short}\n```\n*Utilisez `!cam` pour voir la vidéo.*")
        except ScrapingError as e:
            await msg.edit(content="❌ Erreur pendant l'analyse.")
            if e.video_path:
                last_video_paths[ctx.channel.id] = e.video_path
                await ctx.send("🎥 Vidéo disponible :", file=discord.File(e.video_path, "debug_video.webm"))
            else:
                await ctx.send("❌ Aucune vidéo disponible.")
        finally:
            active_tasks.pop(ctx.channel.id, None)

    task = asyncio.create_task(run())
    active_tasks[ctx.channel.id] = task

@bot.command(name="cam")
async def cam(ctx):
    video_path = last_video_paths.get(ctx.channel.id)
    if not video_path:
        return await ctx.send("❌ Aucune vidéo trouvée.")
    file = Path(video_path)
    if not file.exists():
        return await ctx.send("❌ Fichier vidéo introuvable.")
    if file.stat().st_size < DISCORD_FILE_LIMIT_BYTES:
        await ctx.send("📹 Voici la vidéo :", file=discord.File(str(file), "debug_video.webm"))
    else:
        await ctx.send(f"📦 Vidéo trop lourde ({file.stat().st_size / 1_000_000:.2f} Mo).")

@bot.command(name="stop")
async def stop(ctx):
    task = active_tasks.get(ctx.channel.id)
    if not task:
        return await ctx.send("❌ Aucun scraping en cours.")
    task.cancel()
    await ctx.send("🛑 Scraping interrompu. Envoi de la vidéo...")
    video_path = last_video_paths.get(ctx.channel.id)
    if video_path and Path(video_path).exists():
        await ctx.send("📹 Vidéo enregistrée :", file=discord.File(video_path, "debug_video.webm"))
    else:
        await ctx.send("❌ Vidéo indisponible.")
    active_tasks.pop(ctx.channel.id, None)

@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(f"Pong! {round(bot.latency * 1000)} ms")

@bot.command(name="aide")
async def aide(ctx):
    await ctx.send("""📖 **Commandes disponibles :**
`!chess <url>` – Lance l’analyse d’une partie Chess.com
`!cam` – Envoie la vidéo de la dernière session
`!stop` – Stoppe le scraping en cours et envoie la vidéo
`!ping` – Affiche la latence du bot
`!aide` – Affiche ce message
""")

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

# --- LANCEMENT ---
async def main():
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Bot arrêté.")