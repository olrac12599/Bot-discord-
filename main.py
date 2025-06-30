# --- IMPORTS ---
import discord
from discord.ext import commands
from twitchio.ext import commands as twitch_commands
import os
import asyncio
from enum import Enum, auto
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth
import io
from pathlib import Path
from stockfish import Stockfish
import chess.pgn

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TTV_BOT_TOKEN = os.getenv("TTV_BOT_TOKEN")
TTV_BOT_NICKNAME = os.getenv("TTV_BOT_NICKNAME")
CHESS_USERNAME = os.getenv("CHESS_USERNAME")
CHESS_PASSWORD = os.getenv("CHESS_PASSWORD")
DISCORD_FILE_LIMIT_BYTES = 8 * 1024 * 1024
STOCKFISH_PATH = "/usr/games/stockfish"  # À adapter si besoin

if not all([DISCORD_TOKEN, TTV_BOT_NICKNAME, TTV_BOT_TOKEN]):
    raise ValueError("Variables d'environnement Discord/Twitch manquantes.")
if not all([CHESS_USERNAME, CHESS_PASSWORD]):
    raise ValueError("CHESS_USERNAME et CHESS_PASSWORD requis.")

# --- INITIALISATION DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
last_video_paths = {}

# --- ERREUR CUSTOM ---
class ScrapingError(Exception):
    def __init__(self, message, screenshot_bytes=None, video_path=None):
        super().__init__(message)
        self.screenshot_bytes = screenshot_bytes
        self.video_path = video_path

# --- PGN SCRAPER ---
async def get_pgn_from_chess_com(url: str, username: str, password: str):
    videos_dir = Path("debug_videos")
    videos_dir.mkdir(exist_ok=True)
    stealth = Stealth()
    browser_args = ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']

    async with stealth.use_async(async_playwright()) as p:
        browser = await p.chromium.launch(headless=True, args=browser_args)
        context = await browser.new_context(
            record_video_dir=str(videos_dir),
            record_video_size={"width": 1280, "height": 720},
            base_url="https://www.chess.com"
        )
        page = await context.new_page()

        try:
            await page.goto("/login_and_go", timeout=90000)
            await page.get_by_placeholder("Username, Phone, or Email").type(username)
            await page.get_by_placeholder("Password").type(password)
            await page.get_by_role("button", name="Log In").click()
            await page.wait_for_url("**/home", timeout=15000)

            await page.goto(url, timeout=90000)
            await page.locator("button.share-button-component").click()
            await page.locator('div.share-menu-tab-component-header:has-text("PGN")').click()
            pgn_text = await page.input_value('textarea.share-menu-tab-pgn-textarea')

            video_path = await page.video.path()
            await context.close()
            await browser.close()
            return pgn_text, video_path

        except Exception as e:
            screenshot_bytes, video_path = None, None
            try: video_path = await page.video.path()
            except: pass
            if not page.is_closed():
                screenshot_bytes = await page.screenshot(full_page=True)
            await context.close()
            await browser.close()
            raise ScrapingError(str(e), screenshot_bytes, video_path)

# --- STOCKFISH ANALYSE ---
def analyse_pgn_with_stockfish(pgn_text):
    stockfish = Stockfish(path=STOCKFISH_PATH)
    stockfish.set_skill_level(20)
    stockfish.set_depth(15)

    game = chess.pgn.read_game(io.StringIO(pgn_text))
    board, annotations = game.board(), []

    for move in game.mainline_moves():
        stockfish.set_fen_position(board.fen())
        best = stockfish.get_best_move()
        stockfish.make_moves_from_current_position([best])
        best_eval = stockfish.get_evaluation()
        stockfish.set_fen_position(board.fen())
        stockfish.make_moves_from_current_position([move.uci()])
        played_eval = stockfish.get_evaluation()

        delta = 0
        if best_eval['type'] == 'cp' and played_eval['type'] == 'cp':
            delta = played_eval['value'] - best_eval['value']
        elif best_eval['type'] == 'mate' or played_eval['type'] == 'mate':
            delta = 1000

        if best == move.uci():
            verdict = "théorique"
        elif abs(delta) < 50:
            verdict = "acceptable"
        elif abs(delta) < 150:
            verdict = "imprécision"
        elif abs(delta) < 300:
            verdict = "erreur"
        else:
            verdict = "blunder"

        color = "Blanc" if board.turn == chess.BLACK else "Noir"
        annotations.append(f"{color} joue {board.san(move)} : {verdict}")
        board.push(move)

    return annotations

# --- DISCORD COMMANDES ---
@bot.command(name="chess")
async def get_chess_pgn(ctx, url: str):
    if "chess.com/game/live/" not in url and "chess.com/play/game/" not in url:
        return await ctx.send("❌ URL invalide.")
    msg = await ctx.send("🕵️ Connexion Chess.com en cours...")
    try:
        pgn, video_path = await get_pgn_from_chess_com(url, CHESS_USERNAME, CHESS_PASSWORD)
        if video_path:
            last_video_paths[ctx.channel.id] = video_path
        await msg.edit(content="✅ PGN récupéré. Analyse en cours...")
        annotations = analyse_pgn_with_stockfish(pgn)
        for ligne in annotations:
            await ctx.send(ligne)
    except ScrapingError as e:
        await msg.edit(content="❌ Échec lors du scraping.")
        if e.video_path:
            last_video_paths[ctx.channel.id] = e.video_path
        if e.screenshot_bytes:
            await ctx.send("📸 Capture d'écran :", file=discord.File(io.BytesIO(e.screenshot_bytes), "debug.png"))
        if e.video_path:
            await ctx.send("📹 Vidéo dispo via `!cam`")

@bot.command(name="cam")
async def send_last_video(ctx):
    video_path = last_video_paths.get(ctx.channel.id)
    if not video_path:
        return await ctx.send("❌ Aucune vidéo trouvée.")
    video_file = Path(video_path)
    if not video_file.exists():
        return await ctx.send("❌ Fichier manquant.")
    if video_file.stat().st_size < DISCORD_FILE_LIMIT_BYTES:
        await ctx.send("📹 Vidéo :", file=discord.File(str(video_file), "debug_video.webm"))
    else:
        await ctx.send(f"📹 Vidéo trop lourde ({video_file.stat().st_size / 1_000_000:.2f} Mo).")

# --- TWITCH MIRROR OPTIONNEL ---
class WatcherMode(Enum): IDLE, KEYWORD, MIRROR = auto(), auto(), auto()

class WatcherBot(twitch_commands.Bot):
    def __init__(self, discord_bot):
        super().__init__(token=TTV_BOT_TOKEN, prefix="!", initial_channels=[])
        self.discord_bot = discord_bot
        self.mode = WatcherMode.IDLE
        self.current_channel_name = self.target_discord_channel = self.keyword_to_watch = None

    async def event_ready(self):
        print(f"Twitch bot '{TTV_BOT_NICKNAME}' connecté.")

    async def event_message(self, message):
        if message.echo or self.mode == WatcherMode.IDLE:
            return
        author = message.author.name if message.author else "Inconnu"
        if self.mode == WatcherMode.KEYWORD and self.keyword_to_watch.lower() in message.content.lower():
            embed = discord.Embed(title="Mot-Clé détecté", description=message.content, color=discord.Color.orange())
            embed.set_footer(text=f"{message.channel.name} - {author}")
            await self.target_discord_channel.send(embed=embed)
        elif self.mode == WatcherMode.MIRROR:
            await self.target_discord_channel.send(f"**{author}**: {message.content}"[:2000])

    async def stop_task(self):
        if self.current_channel_name:
            await self.part_channels([self.current_channel_name])
        self.mode = WatcherMode.IDLE
        self.current_channel_name = self.target_discord_channel = self.keyword_to_watch = None

    async def start_keyword_watch(self, channel, keyword, discord_channel):
        await self.stop_task()
        self.mode = WatcherMode.KEYWORD
        self.keyword_to_watch = keyword
        self.target_discord_channel = discord_channel
        self.current_channel_name = channel.lower()
        await self.join_channels([self.current_channel_name])

    async def start_mirror(self, channel, discord_channel):
        await self.stop_task()
        self.mode = WatcherMode.MIRROR
        self.target_discord_channel = discord_channel
        self.current_channel_name = channel.lower()
        await self.join_channels([self.current_channel_name])

@bot.command(name="motcle")
@commands.has_permissions(administrator=True)
async def watch_keyword(ctx, streamer: str, *, keyword: str):
    await bot.twitch_bot.start_keyword_watch(streamer, keyword, ctx.channel)
    await ctx.send(f"🔍 Mot-clé `{keyword}` surveillé sur `{streamer}`.")

@bot.command(name="tchat")
@commands.has_permissions(administrator=True)
async def mirror_chat(ctx, streamer: str):
    await bot.twitch_bot.start_mirror(streamer, ctx.channel)
    await ctx.send(f"💬 Miroir activé sur le tchat de `{streamer}`.")

@bot.command(name="stop")
@commands.has_permissions(administrator=True)
async def stop_watch(ctx):
    await bot.twitch_bot.stop_task()
    await ctx.send("🛑 Surveillance Twitch stoppée.")

@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(f"Pong! Latence : {round(bot.latency * 1000)}ms")

@bot.event
async def on_ready():
    print(f"Bot Discord connecté en tant que {bot.user}")

async def main():
    twitch_bot = WatcherBot(bot)
    bot.twitch_bot = twitch_bot
    await asyncio.gather(bot.start(DISCORD_TOKEN), twitch_bot.start())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stoppé.")